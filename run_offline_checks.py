"""Gold regression and security tests. All database/model/cloud calls are mocked."""
import argparse
import base64
import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=ROOT / 'runtime')
args, remaining = parser.parse_known_args()
sys.path.insert(0, str(args.source.resolve()))
os.environ['CONFIRMATION_SIGNING_KEY'] = 'offline-test-key-' * 4
MODEL = 'arn:aws:bedrock:us-east-1:000000000000:inference-profile/us.anthropic.claude-sonnet-4-6'


def response(text, incoming=100, outgoing=10):
    return {'text': text, 'model': MODEL, 'input_tokens': incoming, 'output_tokens': outgoing,
            'stop_reason': 'end_turn', 'usage': {'input_tokens': incoming, 'output_tokens': outgoing}}


class GoldChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.env = patch.dict(os.environ, {'AGENT_LOG_PATH': str(Path(self.folder.name) / 'trace.jsonl')})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.console = contextlib.redirect_stdout(io.StringIO())
        self.console.__enter__()
        self.addCleanup(self.console.__exit__, None, None, None)
        import orchestrator
        import agents.sql_agent as sql
        import sql_validator
        self.app, self.sql, self.validator = orchestrator, sql, sql_validator
        self.backend = SimpleNamespace(SCHEMA_CONTEXT='clients(id,name,contract_value); projects(id,client_id,name,status)',
            validate_sql=sql_validator.validate_sql, execute_query_safely=Mock(return_value={
                'success': True, 'validation': 'PASSED', 'columns': ['count'], 'rows': [(1,)], 'execution_attempted': True}))

    def test_validator_required_cases_and_boundaries(self):
        cases = [('SELECT COUNT(*) FROM clients;', True), ('DROP TABLE clients', False),
                 ('SELECT deleted_at FROM projects', True), ('SELECT * FROM clients; DROP TABLE clients;', False),
                 ('SELECT * FROM clients; SELECT * FROM projects;', False),
                 ('dElEtE\n\tFROM projects', False), ("SELECT 'DROP;DELETE' AS note FROM clients", True),
                 ('SELECT * INTO x FROM clients', False), ('SELECT pg_sleep(30)', False),
                 ('SELECT * FROM projects FOR UPDATE', False), ('SELECT * FROM employee_records', False)]
        for sql, valid in cases:
            with self.subTest(sql=sql):
                self.assertEqual(self.validator.validate_sql(sql)['valid'], valid)

    def test_rejected_queries_never_connect_through_either_executor(self):
        import sql_runtime
        with patch.object(sql_runtime, 'connect', side_effect=AssertionError('Unexpected connection')) as connect:
            for sql in ['DROP TABLE clients', 'SELECT * FROM clients; SELECT * FROM projects;']:
                for execute in [sql_runtime.execute_query, sql_runtime.execute_query_safely, self.sql.execute_validated_sql]:
                    result = execute(sql)
                    self.assertEqual(result['validation'], 'BLOCKED')
                    self.assertFalse(result.get('execution_attempted'))
            connect.assert_not_called()

    def test_readonly_transaction_rolls_back_closes_and_bounds_rows(self):
        import sql_runtime
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.description = [('name',)]
        cursor.fetchmany.return_value = [(str(i),) for i in range(21)]
        with patch.object(sql_runtime, 'connect', return_value=connection):
            result = sql_runtime.execute_query_safely('SELECT name FROM clients LIMIT 30')
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['rows']), 20)
        connection.set_session.assert_called_once_with(readonly=True, autocommit=False)
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()

    def test_memory_caps_and_validates_structure(self):
        from memory import bounded_history
        history = [{'question': 'Q' * 1500, 'answer': 'A' * 3000}] * 8
        kept = bounded_history(history)
        self.assertEqual(len(kept), 3)
        self.assertEqual(len(kept[-1]['question']), 1000)
        self.assertEqual(len(kept[-1]['answer']), 2000)
        for invalid in [{}, ['bad'], [{'question': 'x', 'answer': 'y', 'sql': 'z'}]]:
            with self.assertRaises(ValueError):
                bounded_history(invalid)

    def test_classification_receives_history_and_resolves_entity(self):
        history = [{'question': 'How many active projects does Acme Corp have?', 'answer': 'One.'}]
        with patch.object(self.app, 'invoke_claude', return_value=response(json.dumps({
                'route': 'sql', 'resolved_question': "What is Acme Corp's total contract value?"}))) as invoke:
            state = self.app.route_question({'question': 'What about their total contract value?', 'history': history})
        self.assertEqual(state['route'], 'sql')
        self.assertIn('Acme Corp', state['resolved_question'])
        self.assertIn('Acme Corp', invoke.call_args.args[0])
        self.assertEqual(len(state['classification_usage']), 1)

    def test_no_stale_worker_results_are_replayed(self):
        with patch.object(self.app, 'invoke_claude', return_value=response('{"route":"retrieval","resolved_question":"Equipment policy?"}')):
            result = self.app.route_question({'question': 'Equipment policy?', 'sql_result': {'old': True}, 'executed_tools': ['sql_agent']})
        self.assertIsNone(result['sql_result'])
        self.assertEqual(result['executed_tools'], [])

    def test_review_criteria_allow_normal_counts_and_lookup(self):
        from confirmation import unusual_query
        for sql in ['SELECT COUNT(*) FROM projects', "SELECT contract_value FROM clients WHERE name='Acme Corp'", 'SELECT name FROM clients LIMIT 5']:
            self.assertFalse(unusual_query(sql)['unusual'], sql)
        for sql in ['SELECT * FROM clients', "SELECT p.* FROM projects p JOIN clients c ON c.id=p.client_id WHERE c.name='Acme Corp'", 'SELECT name FROM clients']:
            self.assertTrue(unusual_query(sql)['unusual'], sql)

    def test_unusual_generated_sql_pauses_without_execution(self):
        from memory import request_context
        token = request_context.set({'history': [], 'route': 'sql', 'original_question': 'Show all clients', 'resolved_question': 'Show all clients'})
        try:
            with patch.object(self.sql, 'sql_backend', return_value=self.backend), \
                 patch.object(self.sql, 'invoke_claude', return_value=response('SELECT * FROM clients;')):
                result = self.sql.run_sql_agent('Show all clients')
        finally:
            request_context.reset(token)
        self.assertEqual(result['metadata']['status'], 'NEEDS_CONFIRMATION')
        self.assertFalse(result['metadata']['execution_attempted'])
        self.assertEqual(result['metadata']['validation'], 'PASSED')
        self.backend.execute_query_safely.assert_not_called()

    def pending(self, sql='SELECT * FROM clients;', history=None):
        from confirmation import issue
        return {'sql': sql, 'token': issue(sql, 'Show all their clients', history or [], 'sql', 'Show Acme clients')}

    def test_exact_confirmation_survives_module_reload(self):
        import confirmation
        pending = self.pending()
        importlib.reload(confirmation)
        self.assertEqual(confirmation.verify(pending)['sql'], pending['sql'])

    def test_altered_sql_and_token_rejected(self):
        from confirmation import verify
        pending = self.pending()
        for changed in [{**pending, 'sql': pending['sql'] + ' '},
                        {**pending, 'sql': 'DROP TABLE clients;'},
                        {**pending, 'token': pending['token'][:-5] + 'abcde'}]:
            with self.assertRaises(ValueError):
                verify(changed)

    def test_expired_receipt_and_different_database_rejected(self):
        from confirmation import verify
        with patch('confirmation.time.time', return_value=100):
            pending = self.pending()
        with self.assertRaises(ValueError):
            verify(pending)
        pending = self.pending()
        with patch.dict(os.environ, {'RDS_HOST': 'different'}), self.assertRaises(ValueError):
            verify(pending)

    def test_history_cannot_be_swapped_during_confirmation(self):
        from confirmation import verify
        history = [{'question': 'Acme?', 'answer': 'Yes.'}]
        pending = self.pending(history=history)
        self.assertEqual(verify(pending, history)['history'], history)
        with self.assertRaises(ValueError):
            verify(pending, [])

    def test_signed_unsafe_sql_still_fails_validator_before_execution(self):
        from confirmation import verify
        from memory import request_context
        verified = verify(self.pending('DROP TABLE clients;'))
        token = request_context.set({'verified_confirmation': verified})
        try:
            with patch.object(self.sql, 'sql_backend', return_value=self.backend), \
                 patch.object(self.sql, 'invoke_claude') as invoke:
                result = self.sql.run_sql_agent('Confirmed')
            invoke.assert_not_called()
        finally:
            request_context.reset(token)
        self.assertEqual(result['metadata']['validation'], 'BLOCKED')
        self.backend.execute_query_safely.assert_not_called()

    def test_confirmation_executes_exact_query_without_regenerating(self):
        from confirmation import verify
        from memory import request_context
        pending = self.pending()
        token = request_context.set({'verified_confirmation': verify(pending)})
        try:
            with patch.object(self.sql, 'sql_backend', return_value=self.backend), \
                 patch.object(self.sql, 'invoke_claude', return_value=response('One client.')) as invoke:
                result = self.sql.run_sql_agent('Confirmed')
            self.assertEqual(invoke.call_count, 1)  # interpretation only
        finally:
            request_context.reset(token)
        self.assertTrue(result['success'])
        self.backend.execute_query_safely.assert_called_once_with(pending['sql'])

    def test_sql_generation_receives_bounded_history(self):
        from memory import request_context
        token = request_context.set({'history': [{'question': 'Acme Corp?', 'answer': 'One project.'}]})
        try:
            with patch.object(self.sql, 'sql_backend', return_value=self.backend), \
                 patch.object(self.sql, 'invoke_claude', side_effect=[response('SELECT COUNT(*) FROM projects'), response('One.')]) as invoke:
                result = self.sql.run_sql_agent('What about their project count?')
            self.assertIn('Acme Corp', invoke.call_args_list[0].args[0])
        finally:
            request_context.reset(token)
        self.assertTrue(result['success'])

    def test_incomplete_sql_never_executes_and_usage_is_retained(self):
        with patch.object(self.sql, 'sql_backend', return_value=self.backend), \
             patch.object(self.sql, 'invoke_claude', return_value={**response('SELECT'), 'stop_reason': 'max_tokens'}):
            result = self.sql.run_sql_agent('Count projects')
        self.assertEqual(result['metadata']['status'], 'INCOMPLETE_GENERATION')
        self.assertEqual(len(result['metadata']['token_usage']), 1)
        self.backend.execute_query_safely.assert_not_called()

    def test_unsafe_natural_language_is_blocked_in_full_graph(self):
        with patch.object(self.app, 'invoke_claude', side_effect=AssertionError('No classification needed')), \
             patch.object(self.sql, 'sql_backend', return_value=self.backend):
            state = self.app.orchestrator.invoke({'question': 'Delete all projects from the database.'})
        self.assertEqual(state['status'], 'BLOCKED')
        self.assertFalse(state['sql_result']['metadata']['execution_attempted'])
        self.backend.execute_query_safely.assert_not_called()

    def test_routing_failure_does_not_call_workers(self):
        with patch.object(self.app, 'invoke_claude', return_value=response('invalid JSON')), \
             patch.object(self.app, 'call_tool') as call:
            state = self.app.orchestrator.invoke({'question': 'How many projects?'})
        self.assertEqual(state['status'], 'ROUTING_ERROR')
        call.assert_not_called()

    def test_unanswerable_declines_without_calling_sources(self):
        with patch.object(self.app, 'invoke_claude', return_value=response('{"route":"neither","resolved_question":"Weather?"}')), \
             patch.object(self.app, 'call_tool') as call:
            state = self.app.orchestrator.invoke({'question': 'Weather?'})
        self.assertEqual(state['status'], 'UNANSWERABLE')
        self.assertEqual(state['token_usage']['reported_llm_calls'], 1)
        call.assert_not_called()

    def test_both_workers_reach_synthesis_and_each_model_call_is_priced(self):
        import orchestrator_base
        import tokenomics_logger
        from backends import usage_record
        def worker(tool, question):
            if tool == 'sql_agent':
                return {'success': True, 'answer': '4 projects.', 'sources': ['SQL: SELECT COUNT(*) FROM projects'],
                        'metadata': {'status': 'ANSWERED', 'answerable': True, 'validation': 'PASSED',
                            'token_usage': [usage_record('sql_generation', response('x')), usage_record('sql_interpretation', response('x'))]}}
            return {'success': True, 'answer': '$500 [Source 1].', 'sources': ['remote-work-policy.pdf'],
                    'metadata': {'status': 'ANSWERED', 'answerable': True, 'grounded': True,
                        'chunks': [{'content': '$500', 'document_name': 'remote-work-policy.pdf'}],
                        'token_usage': usage_record('retrieval_generation', response('x'))}}
        with patch.object(self.app, 'invoke_claude', return_value=response('{"route":"both","resolved_question":"How many projects and equipment policy?"}')), \
             patch.object(self.app, 'call_tool', side_effect=worker), \
             patch.object(orchestrator_base, 'invoke_claude', return_value=response('4 projects [SQL]. $500 [Retrieval: remote-work-policy.pdf, Source 1].')):
            state = tokenomics_logger.run_traced_query(tokenomics_logger.build_logged_orchestrator(), 'How many projects and equipment policy?')
        self.assertEqual(state['status'], 'ANSWERED')
        self.assertEqual(list(state['synthesis_input']), ['sql_agent', 'retrieval_agent'])
        self.assertEqual(state['token_usage']['reported_llm_calls'], 5)
        self.assertEqual(state['token_usage']['input'], 500)
        self.assertTrue(state['monitoring']['cost_breakdown']['complete'])
        rows = [json.loads(l) for l in Path(os.environ['AGENT_LOG_PATH']).read_text().splitlines()]
        calls = [r for r in rows if r['stage'] == 'llm_call']
        self.assertEqual(len(calls), 5)
        self.assertTrue(all(r['details']['calculated_cost_usd'] > 0 for r in calls))

    def test_memory_review_and_confirmation_coexist_through_handler(self):
        import lambda_handler
        lambda_handler._graph = None
        history = [{'question': 'How many projects does Acme Corp have?', 'answer': 'One active project.'}]
        resolved = 'Show all columns of projects for Acme Corp with no row limit.'
        sql = "SELECT p.* FROM projects p JOIN clients c ON c.id=p.client_id WHERE c.name='Acme Corp';"
        with patch.object(self.app, 'invoke_claude', return_value=response(json.dumps({'route': 'sql', 'resolved_question': resolved}))), \
             patch.object(self.sql, 'sql_backend', return_value=self.backend), \
             patch.object(self.sql, 'invoke_claude', return_value=response(sql)):
            first = json.loads(lambda_handler.handler({'question': 'Show all their projects with every column and no row limit.', 'history': history}, None)['body'])
        self.assertTrue(first['needs_confirmation'])
        self.assertIn('Acme Corp', first['sql'])
        self.assertEqual(first['history'], history)  # pending draft never becomes a completed turn
        self.backend.execute_query_safely.assert_not_called()
        with patch.object(self.sql, 'sql_backend', return_value=self.backend), \
             patch.object(self.sql, 'invoke_claude', return_value=response('One project.')), \
             patch('orchestrator_base.invoke_claude', return_value=response('One Acme Corp project [SQL].')):
            lambda_handler._graph = None  # simulate a fresh Lambda container
            second = json.loads(lambda_handler.handler({'confirmation': first['confirmation'], 'history': first['history']}, None)['body'])
        self.assertEqual(second['status'], 'ANSWERED')
        self.assertEqual(second['sql'], sql)
        self.assertEqual(len(second['history']), 2)
        self.assertEqual(second['token_usage']['reported_llm_calls'], 2)
        self.backend.execute_query_safely.assert_called_once_with(sql)

    def test_invalid_handler_requests_never_call_graph(self):
        import lambda_handler
        for event in [{}, {'question': ''}, {'question': 'x', 'history': 'bad'}, {'body': 'not json'}]:
            self.assertEqual(lambda_handler.handler(event, None)['statusCode'], 400)

    def test_unknown_registry_tool_has_exact_contract(self):
        from tool_registry import call_tool, valid_contract
        self.assertTrue(valid_contract(call_tool('missing', 'test')))

    def test_single_source_routes_do_not_call_the_other_worker(self):
        for route, tool in [('sql', 'sql_agent'), ('retrieval', 'retrieval_agent')]:
            record = {'component': 'sql_generation' if route == 'sql' else 'retrieval_generation', **response('usage')}
            metadata = {'status': 'ANSWERED', 'answerable': True, 'validation': 'PASSED',
                        'grounded': True, 'token_usage': [record], 'chunks': []}
            result = {'success': True, 'answer': 'A fact.', 'sources': [], 'metadata': metadata}
            label = '[SQL]' if route == 'sql' else '[Retrieval]'
            with patch.object(self.app, 'invoke_claude', return_value=response(json.dumps({'route': route, 'resolved_question': 'Test?'}))), \
                 patch.object(self.app, 'call_tool', return_value=result) as call, \
                 patch('orchestrator_base.invoke_claude', return_value=response('A fact ' + label)):
                state = self.app.orchestrator.invoke({'question': 'Test?'})
            self.assertEqual(state['status'], 'ANSWERED')
            self.assertEqual(state['executed_tools'], [tool])
            self.assertEqual(call.call_count, 1)

    def test_failed_worker_produces_partial_answer_from_other_source(self):
        def dispatch(tool, question):
            if tool == 'sql_agent':
                return {'success': False, 'answer': 'Unavailable', 'sources': [],
                        'metadata': {'status': 'EXECUTION_ERROR', 'validation': 'EXECUTION_ERROR'}}
            return {'success': True, 'answer': '$500 [Source 1].', 'sources': ['remote-work-policy.pdf'],
                    'metadata': {'status': 'ANSWERED', 'grounded': True, 'answerable': True,
                                 'chunks': [{'content': '$500', 'document_name': 'remote-work-policy.pdf'}]}}
        with patch.object(self.app, 'invoke_claude', return_value=response('{"route":"both","resolved_question":"Projects and policy?"}')), \
             patch.object(self.app, 'call_tool', side_effect=dispatch), \
             patch('orchestrator_base.invoke_claude', return_value=response('$500 [Retrieval: remote-work-policy.pdf, Source 1]. SQL is unavailable.')):
            state = self.app.orchestrator.invoke({'question': 'Projects and policy?'})
        self.assertEqual(state['status'], 'PARTIAL')
        self.assertIn('sql_agent', state['final_answer'])

    def test_pending_sql_defers_retrieval_in_both_source_request(self):
        pending = {'success': False, 'answer': 'Review required.', 'sources': [],
                   'metadata': {'status': 'NEEDS_CONFIRMATION', 'validation': 'PASSED', 'needs_confirmation': True}}
        with patch.object(self.app, 'invoke_claude', return_value=response('{"route":"both","resolved_question":"All clients and policy?"}')), \
             patch.object(self.app, 'call_tool', return_value=pending) as call:
            state = self.app.orchestrator.invoke({'question': 'All clients and policy?'})
        self.assertEqual(state['status'], 'NEEDS_CONFIRMATION')
        self.assertEqual(state['executed_tools'], ['sql_agent'])
        self.assertEqual(call.call_count, 1)

    def test_citation_membership_is_checked_without_claiming_entailment(self):
        from orchestrator_base import synthesis_check
        check = synthesis_check('Claim [SQL]. Fake [Retrieval: missing.pdf, Source 99].',
                                ['sql_agent', 'retrieval_agent'], {'retrieval_agent': {'sources': [], 'evidence': {'chunks': []}}})
        self.assertFalse(check['passed'])
        self.assertFalse(check['factual_support_verified'])

    def test_missing_usage_or_cache_pricing_does_not_fabricate_cost(self):
        from tokenomics_costs import price_records
        self.assertIsNone(price_records([{'component': 'classification', 'model': MODEL}])['total_cost'])
        record = {**response('x'), 'component': 'classification', 'usage': {'cache_read_input_tokens': 10}}
        self.assertIsNone(price_records([record])['total_cost'])


if __name__ == '__main__':
    print('OFFLINE MOCK CHECKS: no AWS, model calls, database operations or model downloads.', flush=True)
    import boto3
    with patch.object(boto3, 'Session', side_effect=AssertionError('Live cloud call blocked')), \
         patch.object(boto3, 'client', side_effect=AssertionError('Live cloud call blocked')):
        from test_delivery_tools import DeliveryChecks
        suite = unittest.TestSuite([
            unittest.defaultTestLoader.loadTestsFromTestCase(GoldChecks),
            unittest.defaultTestLoader.loadTestsFromTestCase(DeliveryChecks)])
        class Tee:
            def __init__(self, *streams):
                self.streams = streams
            def write(self, value):
                for stream in self.streams:
                    stream.write(value)
            def flush(self):
                for stream in self.streams:
                    stream.flush()
        with (ROOT / 'offline-check-output.txt').open('w') as output:
            result = unittest.TextTestRunner(verbosity=2, stream=Tee(sys.stderr, output)).run(suite)
    from prepare_capstone import sha
    from sql_validator import validate_sql
    required = [('SELECT COUNT(*) FROM clients;', True), ('DROP TABLE clients;', False),
                ('SELECT deleted_at FROM projects;', True), ('SELECT * FROM clients; DROP TABLE clients;', False),
                ('SELECT * FROM clients; SELECT * FROM projects;', False), ('dElEtE\n\tFROM projects;', False)]
    validator_cases = []
    for query, expected in required:
        actual = validate_sql(query)
        row = {'sql': query, 'expected_valid': expected, 'actual': actual, 'passed': actual['valid'] == expected}
        validator_cases.append(row)
        print('PASS' if row['passed'] else 'FAIL', '|', repr(query), '|', actual['reason'])
        with (ROOT / 'offline-check-output.txt').open('a') as output:
            output.write(('PASS' if row['passed'] else 'FAIL') + ' | ' + repr(query) + ' | ' + actual['reason'] + '\n')
    report = {'success': result.wasSuccessful(), 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'provenance': 'offline_mock_checks',
              'live_aws_calls': 0, 'live_llm_calls': 0,
              'required_validator_cases': validator_cases,
              'source_manifest_sha256': sha(ROOT / 'source-files.json') if (ROOT / 'source-files.json').exists() else None}
    (ROOT / 'outputs').mkdir(exist_ok=True)
    (ROOT / 'outputs/offline-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
