"""Lambda JSON contract with caller-carried history and exact-query confirmation."""
import base64
import json
import os

os.environ.setdefault('AGENT_LOG_PATH', '/tmp/agent_decisions.jsonl')
os.environ.setdefault('LANGSMITH_TRACING', 'false')
os.environ.setdefault('LANGCHAIN_TRACING_V2', 'false')
_graph = None


def parse_request(event):
    if not isinstance(event, dict):
        raise ValueError('The event must be an object.')
    body = event.get('body', event)
    if event.get('isBase64Encoded'):
        if not isinstance(body, str):
            raise ValueError('Invalid encoded request.')
        body = base64.b64decode(body, validate=True).decode('utf-8')
    if isinstance(body, str):
        if len(body) > 90000:
            raise ValueError('Request is too large.')
        body = json.loads(body)
    if not isinstance(body, dict) or len(json.dumps(body)) > 90000:
        raise ValueError('Supply a bounded JSON object.')
    from memory import bounded_history
    if 'history' in body:
        bounded_history(body['history'])
    action = body.get('action', 'query')
    if action not in {'query', 'foundation', 'interfaces'}:
        raise ValueError('Unknown action.')
    if action == 'query':
        question = body.get('question', 'Confirm the previously reviewed SQL.' if 'confirmation' in body else None)
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
            raise ValueError('A question of 1-4000 characters is required.')
        body['question'] = question.strip()
    return body


def foundation():
    from agents.sql_agent import execute_validated_sql
    from retrieval_runtime import corpus_selection
    from runtime_cloud import get_opensearch_client, create_index_readonly
    import boto3
    tables = {}
    for name in ['clients', 'projects', 'consultants', 'invoices']:
        result = execute_validated_sql('SELECT COUNT(*) AS record_count FROM ' + name + ';')
        if not result.get('success'):
            raise ValueError('A training table could not be read.')
        tables[name] = result['rows'][0][0]
    selected, config = corpus_selection()
    client = get_opensearch_client(boto3.Session(region_name=config['region']), config)
    try:
        create_index_readonly(client, config['index'])
        total = client.count(index=config['index'])['count']
        count = client.count(index=config['index'], body={'query': {'terms': {'ingestion_id': selected['ingestion_ids']}}})['count']
    finally:
        client.close()
    return {'success': all(v > 0 for v in tables.values()) and count == selected['chunk_count'],
            'tables': tables, 'index': config['index'], 'total_index_count': total,
            'selected_document_count': selected['document_count'], 'selected_chunk_count': count}


def interfaces():
    from tool_registry import call_tool, valid_contract
    from tokenomics_costs import price_records
    results = {name: call_tool(name, question) for name, question in [
        ('sql_agent', 'How many active projects do we have?'),
        ('retrieval_agent', 'How much can eligible employees claim annually for home office equipment?')]}
    records = []
    for result in results.values():
        usage = result['metadata'].get('token_usage') or []
        records.extend(usage if isinstance(usage, list) else [usage])
    return {'success': all(valid_contract(r) and r['success'] for r in results.values()),
            'keys': {n: sorted(r) for n, r in results.items()}, 'results': results,
            'cost_breakdown': price_records(records)}


def handler(event, context):
    global _graph
    try:
        request = parse_request(event)
    except (ValueError, TypeError, UnicodeError):
        return {'statusCode': 400, 'body': json.dumps({'error': 'Supply a valid bounded JSON request.'})}
    try:
        if request.get('action') == 'foundation':
            payload = foundation()
        elif request.get('action') == 'interfaces':
            payload = interfaces()
        else:
            from tokenomics_logger import run_traced_query
            if _graph is None:
                from monitored_orchestrator import orchestrator
                _graph = orchestrator
            initial = {k: request[k] for k in ['history', 'confirmation'] if k in request}
            state = run_traced_query(_graph, request['question'], initial_state=initial)
            meta = (state.get('sql_result') or {}).get('metadata', {})
            docs = (state.get('retrieval_result') or {}).get('metadata', {})
            payload = {'answer': state['final_answer'], 'route': state['route'], 'status': state['status'],
                'sql_validation': meta.get('validation'), 'sql': meta.get('sql'),
                'execution_attempted': bool(meta.get('execution_attempted')),
                'needs_confirmation': bool(state.get('needs_confirmation')), 'confirmation': meta.get('confirmation'),
                'confirmation_reasons': meta.get('review_reasons', []), 'history': state['history'],
                'resolved_question': state['resolved_question'], 'memory': state['memory'],
                'retrieval_chunk_count': len(docs.get('chunks', [])),
                'sources': {'sql': (state.get('sql_result') or {}).get('sources', []),
                            'retrieval': (state.get('retrieval_result') or {}).get('sources', [])},
                'token_usage': state['token_usage'], 'trace_id': state['monitoring']['trace_id'],
                'cost_breakdown': state['monitoring']['cost_breakdown'],
                'source_attribution_check': state.get('synthesis_check'),
                'state': {k: v for k, v in state.items() if k not in {'confirmation', 'verified_confirmation'}},
                'request_id': getattr(context, 'aws_request_id', None)}
        ok = payload.get('status') not in {'ROUTING_ERROR', 'SYNTHESIS_ERROR', 'UNAVAILABLE',
                                           'SYNTHESIS_CHECK_FAILED', 'SYNTHESIS_INCOMPLETE'}
        return {'statusCode': 200 if ok else 502, 'body': json.dumps(payload, default=str, allow_nan=False)}
    except Exception as error:
        print(json.dumps({'stage': 'handler_error', 'error_type': type(error).__name__}))
        return {'statusCode': 500, 'body': json.dumps({'error': 'The request could not be completed. Check the trace logs.'})}
