"""Structured local tracing around the existing nodes. Import makes no service calls."""
import contextvars
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tokenomics_costs import calculate_full_query_cost, calculate_state_cost

ROOT = Path(__file__).resolve().parent
_context = contextvars.ContextVar('agent_trace', default=None)
_write_lock = threading.Lock()


def default_log_path():
    return Path(os.environ.get('AGENT_LOG_PATH', ROOT / 'agent_decisions.jsonl')).expanduser().resolve()


def log_decision(stage: str, question: str, details: dict, *, trace_id=None, log_path=None):
    ctx = _context.get()
    with _write_lock:
        if ctx:
            ctx['sequence'] += 1
        entry = {'timestamp': datetime.now(timezone.utc).isoformat(),
            'trace_id': ctx['trace_id'] if ctx else trace_id or str(uuid.uuid4()),
            'sequence': ctx['sequence'] if ctx else 1, 'stage': stage,
            'question': question, 'details': details,
            'provenance': 'live_traced_execution' if ctx else 'standalone_log_event'}
        line = json.dumps(entry, allow_nan=False, default=str, ensure_ascii=False) + '\n'
        path = Path(log_path or (ctx['log_path'] if ctx else default_log_path()))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as stream:
            stream.write(line)
        print('[LOG] ' + line.rstrip(), flush=True)
    return entry


def _metadata(state, update, node):
    merged = {**state, **update}
    if node == 'router':
        return {'route': update.get('route'), 'method': (update.get('trace') or [{}])[0].get('method'), 'llm_calls': len(update.get('classification_usage', [])),
                'selected_tools': {'sql': ['sql_agent'], 'retrieval': ['retrieval_agent'],
                                   'both': ['sql_agent', 'retrieval_agent']}.get(update.get('route'), [])}
    if node in {'sql_agent', 'retrieval_agent'}:
        field = 'sql_result' if node == 'sql_agent' else 'retrieval_result'
        called = node in update.get('executed_tools', [])
        result = update.get(field) or {}
        meta = result.get('metadata') or {}
        return {'node': node, 'action': 'CALLED' if called else 'SKIPPED',
            'success': result.get('success') if called else None, 'status': meta.get('status'),
            'sql_validation': meta.get('validation') if node == 'sql_agent' else None,
            'row_count': meta.get('row_count') if node == 'sql_agent' else None,
            'retrieval_chunk_count': len(meta.get('chunks', [])) if node == 'retrieval_agent' and called else None,
            'distinct_document_count': len({c.get('source') for c in meta.get('chunks', [])}) if node == 'retrieval_agent' and called else None,
            'citation_check_passed': (meta.get('citation_check') or {}).get('passed'),
            'token_usage': meta.get('token_usage'),
            'source_document_names': result.get('sources') if node == 'retrieval_agent' else None}
    supplied = merged.get('synthesis_input') or {}
    return {'node': node, 'status': merged.get('status'), 'received_tools': list(supplied),
        'usable_tools': [name for name, value in supplied.items() if value.get('usable')],
        'unavailable_tools': [name for name, value in supplied.items() if not value.get('usable')],
        'observed_labels': (merged.get('synthesis_check') or {}).get('observed_labels', []),
        'source_attribution_passed': (merged.get('synthesis_check') or {}).get('passed'),
        'synthesis_usage': merged.get('synthesis_usage') or [],
        'query_usage': merged.get('token_usage')}


def _logged_node(function, node):
    def wrapped(state):
        question = state.get('question', '')
        log_decision('node_start', question, {'node': node})
        start = time.perf_counter()
        try:
            update = function(state)
        except Exception as error:
            log_decision('node_error', question, {'node': node, 'error_type': type(error).__name__,
                'elapsed_ms': round((time.perf_counter() - start) * 1000, 3), 'usage_complete': False})
            raise
        log_decision('routing' if node == 'router' else 'node_complete', question,
            {**_metadata(state, update, node), 'node': node,
             'elapsed_ms': round((time.perf_counter() - start) * 1000, 3)})
        return update
    return wrapped


def route_question_logged(state):
    from orchestrator import route_question
    return _logged_node(route_question, 'router')(state)


def build_logged_orchestrator(module=None):
    """Reuse existing node functions with the same four-node graph and no prompt changes."""
    if module is None:
        import orchestrator as module
    from langgraph.graph import END, StateGraph
    graph = StateGraph(module.OrchestratorState)
    nodes = [('router', module.route_question), ('sql_agent', module.call_sql_agent),
             ('retrieval_agent', module.call_retrieval_agent), ('synthesiser', module.synthesise)]
    for name, function in nodes:
        graph.add_node(name, _logged_node(function, name))
    graph.set_entry_point('router')
    for (left, _), (right, _) in zip(nodes, nodes[1:]):
        graph.add_edge(left, right)
    graph.add_edge('synthesiser', END)
    compiled = graph.compile()
    compiled.tokenomics_instrumented = True
    return compiled


def run_traced_query(orchestrator, question: str, *, log_path=None, initial_state=None) -> dict:
    """Pass build_logged_orchestrator() or monitored_orchestrator.orchestrator here."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError('Supply a nonempty question.')
    if not getattr(orchestrator, 'tokenomics_instrumented', False):
        raise ValueError('Use monitored_orchestrator.orchestrator so every actual node is logged.')
    if _context.get() is not None:
        raise ValueError('Nested traced queries require a separate trace context.')
    trace_id = str(uuid.uuid4())
    path = Path(log_path).expanduser().resolve() if log_path else default_log_path()
    token = _context.set({'trace_id': trace_id, 'log_path': path, 'sequence': 0})
    start = time.perf_counter()
    try:
        log_decision('query_start', question, {'status': 'STARTED'})
        state = orchestrator.invoke({**(initial_state or {}), 'question': question})
        cost = calculate_state_cost(state)
        sql = (state.get('sql_result') or {}).get('metadata') or {}
        retrieval = (state.get('retrieval_result') or {}).get('metadata') or {}
        supplied = state.get('synthesis_input') or {}
        log_decision('query_complete', question, {'status': state.get('status'), 'route': state.get('route'),
            'executed_tools': state.get('executed_tools', []), 'received_tools': list(supplied),
            'usable_tools': [n for n, v in supplied.items() if v.get('usable')],
            'observed_labels': (state.get('synthesis_check') or {}).get('observed_labels', []),
            'sql_validation': sql.get('validation'),
            'retrieval_chunk_count': len(retrieval.get('chunks', [])) if state.get('retrieval_result') else None,
            'token_usage': state.get('token_usage'), 'cost_breakdown': cost,
            'elapsed_ms': round((time.perf_counter() - start) * 1000, 3)})
        state['monitoring'] = {'trace_id': trace_id, 'log_path': str(path), 'cost_breakdown': cost}
        return state
    except Exception as error:
        log_decision('query_error', question, {'status': 'ERROR', 'error_type': type(error).__name__,
            'usage_complete': False, 'cost_complete': False})
        raise
    finally:
        _context.reset(token)


def read_trace(trace_id, log_path=None):
    path = Path(log_path) if log_path else default_log_path()
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [row for row in rows if row.get('trace_id') == trace_id]


def audit_recent_queries(limit=5, log_path=None):
    if type(limit) is not int or limit <= 0:
        raise ValueError('Supply a positive query count for the audit.')
    path = Path(log_path) if log_path else default_log_path()
    lines = path.read_text().splitlines() if path.is_file() else []
    malformed = []
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            malformed.append(number)
    latest = []
    seen = set()
    for row in reversed(rows):
        if row.get('stage') in {'query_complete', 'query_error'} and row.get('trace_id') not in seen:
            latest.append(row)
            seen.add(row['trace_id'])
            if len(latest) == limit:
                break
    results = []
    for last in reversed(latest):
        details = last['details']
        chain = [r for r in rows if r.get('trace_id') == last['trace_id']]
        route = next((r['details'].get('route') for r in chain if r['stage'] == 'routing'), None)
        called = [r['details']['node'] for r in chain if r['stage'] == 'node_complete'
                  and r['details'].get('action') == 'CALLED']
        selected = {'sql': ['sql_agent'], 'retrieval': ['retrieval_agent'],
                    'both': ['sql_agent', 'retrieval_agent']}.get(route)
        received = details.get('received_tools', [])
        usable = details.get('usable_tools', [])
        observed = details.get('observed_labels', [])
        omitted = [n for n in usable if ('SQL' if n == 'sql_agent' else 'Retrieval') not in observed]
        finished_nodes = [r['details'].get('node') for r in chain
                          if r['stage'] in {'routing', 'node_complete'}]
        sequence_intact = [r.get('sequence') for r in chain] == list(range(1, len(chain) + 1))
        results.append({'trace_id': last['trace_id'], 'question': last['question'], 'route': route,
            'status': details.get('status'), 'called_tools': called, 'received_by_synthesis': received,
            'called_but_not_received': [n for n in called if n not in received],
            'received_but_unavailable': [n for n in received if n not in usable],
            'usable_but_unattributed': omitted,
            'unnecessary_or_duplicate_calls_relative_to_route': called != selected,
            'trace_complete': last['stage'] == 'query_complete' and
                 [r['details'].get('node') for r in chain if r['stage'] == 'node_start'] ==
                 ['router', 'sql_agent', 'retrieval_agent', 'synthesiser'] and
                 finished_nodes == ['router', 'sql_agent', 'retrieval_agent', 'synthesiser'] and
                 chain[0]['stage'] == 'query_start' and sequence_intact,
            'sql_validation': details.get('sql_validation'),
            'retrieval_chunk_count': details.get('retrieval_chunk_count'),
            'calculated_token_cost_usd': (details.get('cost_breakdown') or {}).get('total_cost')})
    return {'requested_query_count': limit, 'reviewed_query_count': len(results),
        'five_query_activity_complete': len(results) >= limit and all(r['trace_complete'] for r in results),
        'malformed_log_line_numbers': malformed, 'queries': results,
        'limits': 'Compares actual calls with the chosen route and checks receipt/attribution. It does not prove semantic routing correctness or factual use of every passage.'}
