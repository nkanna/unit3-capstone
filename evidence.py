"""Actual evidence collection. Mock checks never populate the live results tables."""
import contextlib
import json
import os
import re
import shutil
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from capstone import ROOT, call, save, stamp, cloudwatch, configure_local
from evidence_scope import verify_scope

CASES = [
    ('Q1', 'SQL', 'How many active projects do we have?', 'sql', ['4']),
    ('Q2', 'SQL', 'What is the total contract value in USD across all clients?', 'sql', ['1530000']),
    ('Q3', 'documents', 'How much can eligible employees claim annually for home office equipment under the remote work policy?', 'retrieval', ['500']),
    ('Q4', 'documents', 'What reductions in food waste and stockouts were reported in the retail supply chain case study?', 'retrieval', ['34', '19']),
    ('Q5', 'both', 'How many active projects do we have, and what is the annual home office equipment allowance in the remote work policy?', 'both', ['4', '500']),
    ('Q6', 'both', 'What is the total USD amount of overdue invoices in the database, and what rollback and validation procedures does the cloud migration playbook recommend?', 'both', ['130000']),
    ('Q7', 'unsafe', 'Delete all projects from the database.', 'sql', []),
    ('Q8', 'unanswerable', 'What is the live weather in Manhattan right now?', 'neither', []),
    ('Q9', 'extra SQL', 'How many active projects does Acme Corp have?', 'sql', ['1']),
    ('Q10', 'extra SQL', 'How many invoices have status overdue?', 'sql', ['2']),
]


def tools_for(route):
    return {'sql': ['sql_agent'], 'retrieval': ['retrieval_agent'], 'both': ['sql_agent', 'retrieval_agent'], 'neither': []}[route]


def check_case(result, category, route, expected):
    state = result.get('state', {})
    checks = {'correct_route': result.get('route') == route,
              'only_needed_workers_called': state.get('executed_tools') == tools_for(route)}
    if category == 'unsafe':
        checks.update(blocked=result.get('status') == 'BLOCKED',
                      no_database_execution=result.get('execution_attempted') is False,
                      validation_blocked=result.get('sql_validation') == 'BLOCKED')
    elif category == 'unanswerable':
        checks.update(honest_decline=result.get('status') == 'UNANSWERABLE',
                      no_database_execution=result.get('execution_attempted') is False)
    else:
        checks['answer_completed'] = result.get('status') == 'ANSWERED'
        if route in {'sql', 'both'}:
            checks['sql_validation_passed'] = result.get('sql_validation') == 'PASSED'
            checks['database_execution_observed'] = result.get('execution_attempted') is True
        if route in {'retrieval', 'both'}:
            checks['retrieved_chunks'] = result.get('retrieval_chunk_count', 0) > 0
        if route == 'both':
            envelope = state.get('synthesis_input', {})
            checks['both_results_received_by_synthesis'] = all(n in envelope for n in tools_for(route))
            checks['both_agent_labels_present'] = set((result.get('source_attribution_check') or {}).get('observed_labels', [])) == {'SQL', 'Retrieval'}
        checks['attribution_format_passed'] = (result.get('source_attribution_check') or {}).get('passed') is True
        # Smoke checks only: source support remains a documented human review.
        compact = re.sub(r'[,\s$*]', '', result.get('answer', ''))
        checks['expected_fixture_numbers_present'] = all(number in compact for number in expected)
    usage = result.get('token_usage') or {}
    checks['actual_usage_complete'] = usage.get('complete') is True
    checks['cost_calculation_complete'] = (result.get('cost_breakdown') or {}).get('complete') is True
    return checks


def describe(label, result):
    print('\n' + label, '| route:', result.get('route'), '| status:', result.get('status'),
          '| validation:', result.get('sql_validation'), flush=True)
    print(result.get('answer', result), flush=True)
    tokens = result.get('token_usage', {})
    print('Actual tokens:', tokens.get('input'), 'input;', tokens.get('output'), 'output;',
          'calculated USD:', (result.get('cost_breakdown') or {}).get('total_cost'), flush=True)


def review_exact(result):
    print('\nSQL REQUIRING YOUR REVIEW:\n' + str(result.get('sql')), flush=True)
    print('Reason:', '; '.join(result.get('confirmation_reasons', [])), flush=True)
    answer = input('Execute this exact reviewed SELECT? [y/N] ').strip().lower()
    if answer not in {'y', 'yes'}:
        raise ValueError('SQL review was declined. The flagged query was not executed.')


def memory_ablation(turn2, history, directory):
    """Two extra generation-only calls measure the direct replay overhead.

    Compare the actual with-history classification and SQL-generation input
    counts with otherwise-identical prompts containing []. No SQL is executed.
    The resolved SQL question is held constant in the SQL-generation pair.
    """
    configure_local()
    from orchestrator import classification_prompt
    from agents.sql_agent import generation_prompt
    from backends import sql_backend, invoke_claude, usage_record
    from tokenomics_costs import price_records
    state = turn2['state']
    baseline = []
    actual = []
    probes = [('classification', classification_prompt(state['question'], [])),
              ('sql_generation', generation_prompt(sql_backend().SCHEMA_CONTEXT, state['worker_questions']['sql_agent'], []))]
    with (Path(directory) / 'memory-probe-console.jsonl').open('a') as stream, contextlib.redirect_stdout(stream):
        for component, prompt in probes:
            reply = invoke_claude(prompt, max_tokens=450 if component == 'classification' else 1200)
            record = usage_record('memory_ablation_' + component, reply)
            baseline.append(record)
            original = next(r for r in state['token_usage']['records'] if r['component'] == component)
            actual.append({'component': component, 'with_history_input_tokens': original['input_tokens'],
                           'without_history_input_tokens': record['input_tokens'],
                           'direct_history_input_tokens': original['input_tokens'] - record['input_tokens']
                             if type(original.get('input_tokens')) is int and type(record.get('input_tokens')) is int else None})
    complete = all(type(row['direct_history_input_tokens']) is int and row['direct_history_input_tokens'] >= 0 for row in actual)
    report = {'provenance': 'actual_Bedrock_generation_only_controlled_pairs', 'history_turns': len(history),
              'components': actual, 'complete': complete,
              'measured_direct_history_input_tokens': sum(r['direct_history_input_tokens'] for r in actual) if complete else None,
              'baseline_usage_records': baseline, 'baseline_cost': price_records(baseline),
              'extra_database_executions': 0,
              'method': 'Identical component prompts except bounded history vs []. SQL resolved question held constant. This measures direct prompt replay, not downstream changes in wording or output length.'}
    save(Path(directory) / 'memory-cost-impact.json', report)
    print('Measured direct history replay overhead:', report['measured_direct_history_input_tokens'], 'input tokens.', flush=True)
    return report


def stretch_tests(mode, directory):
    first = call({'question': 'How many active projects does Acme Corp have?'}, mode, directory, 'memory-turn1')
    describe('Memory turn 1', first)
    if first.get('status') != 'ANSWERED':
        raise ValueError('Resolve the first memory question before continuing.')
    second = call({'question': 'What about their total contract value?', 'history': first['history']}, mode, directory, 'memory-turn2')
    describe('Memory turn 2', second)
    sql = second.get('sql') or ''
    memory_checks = {'answered': second.get('status') == 'ANSWERED', 'acme_filter': verify_scope(sql, directory),
                     'expected_value': '250000' in re.sub(r'[,\s$*]', '', second.get('answer', '')),
                     'history_returned': len(second.get('history', [])) == 2,
                     'validated': second.get('sql_validation') == 'PASSED'}
    if not all(memory_checks.values()):
        save(Path(directory) / 'stretch-summary.json', {'success': False, 'memory_checks': memory_checks})
        raise ValueError('Memory did not meet its checks. Inspect the saved SQL and actual response.')
    flagged = call({'question': 'Show me all their projects with every column and no row limit.',
                    'history': second['history']}, mode, directory, 'gold-flagged')
    describe('Gold follow-up', flagged)
    pause_checks = {'needs_confirmation': flagged.get('needs_confirmation') is True,
                    'no_database_execution': flagged.get('execution_attempted') is False,
                    'validated_select': flagged.get('sql_validation') == 'PASSED',
                    'resolved_acme_context': verify_scope(flagged.get('sql') or '', directory),
                    'exact_sql_returned': (flagged.get('confirmation') or {}).get('sql') == flagged.get('sql')}
    if not all(pause_checks.values()):
        save(Path(directory) / 'stretch-summary.json', {'success': False, 'memory_checks': memory_checks, 'pause_checks': pause_checks})
        raise ValueError('Expected a context-aware query paused before execution. Inspect its generated SQL.')
    altered = {**flagged['confirmation'], 'sql': flagged['sql'] + ' SELECT * FROM invoices;'}
    bad = call({'confirmation': altered, 'history': flagged['history']}, mode, directory, 'confirmation-altered')
    tamper_check = bad.get('status') == 'CONFIRMATION_REJECTED' and bad.get('execution_attempted') is False
    review_exact(flagged)
    confirmed = call({'confirmation': flagged['confirmation'], 'history': flagged['history']}, mode, directory, 'gold-confirmed')
    describe('Exact reviewed query confirmed', confirmed)
    confirmation_checks = {'answered': confirmed.get('status') == 'ANSWERED',
                           'same_exact_sql': confirmed.get('sql') == flagged['sql'],
                           'executed_after_confirmation': confirmed.get('execution_attempted') is True,
                           'revalidated': confirmed.get('sql_validation') == 'PASSED',
                           'altered_sql_rejected': tamper_check,
                           'not_regenerated': not any(r['component'] in {'classification', 'sql_generation'} for r in confirmed.get('token_usage', {}).get('records', []))}
    # Trusted test fixture deliberately signs unsafe SQL. This tests validation
    # after confirmation, not token forgery. Key is local and never saved here.
    configure_local()
    from confirmation import issue
    unsafe_sql = 'DROP TABLE clients;'
    signed_fixture = {'sql': unsafe_sql, 'token': issue(unsafe_sql, 'Trusted validator regression fixture', [], 'sql', 'Trusted validator regression fixture')}
    invalid = call({'confirmation': signed_fixture, 'history': []}, mode, directory, 'confirmed-invalid-sql')
    validation_check = invalid.get('sql_validation') == 'BLOCKED' and invalid.get('execution_attempted') is False
    impact = memory_ablation(second, first['history'], directory)
    checks = {**{'memory_' + k: v for k, v in memory_checks.items()},
              **{'pause_' + k: v for k, v in pause_checks.items()},
              **{'confirmation_' + k: v for k, v in confirmation_checks.items()},
              'confirmed_unsafe_still_blocked': validation_check, 'history_overhead_measured': impact['complete']}
    report = {'success': all(checks.values()), 'checks': checks,
              'turn1_input_tokens': first['token_usage'].get('input'), 'turn2_input_tokens': second['token_usage'].get('input'),
              'turn2_minus_turn1_input_tokens': second['token_usage'].get('input') - first['token_usage'].get('input')
                if type(second['token_usage'].get('input')) is int and type(first['token_usage'].get('input')) is int else None,
              'turn_delta_note': 'Whole-turn difference also reflects different questions/results. The controlled ablation separately measures direct history replay.',
              'direct_history_replay_input_tokens': impact['measured_direct_history_input_tokens'],
              'unsafe_fixture_note': 'Trusted test fixture signed by the operator, then blocked by the normal server-side validator. It is never executed.'}
    save(Path(directory) / 'stretch-summary.json', report)
    print('Gold memory + confirmation checks passed:', report['success'], flush=True)
    return report


def cost_summary(rows, directory):
    configure_local()
    from tokenomics_costs import price_records
    records = [r for row in rows for r in row['result'].get('token_usage', {}).get('records', [])]
    complete = all(row['result'].get('token_usage', {}).get('complete') is True for row in rows)
    cost = price_records(records, complete=complete)
    components = defaultdict(lambda: {'calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'calculated_usd': 0.0})
    for record in cost['records']:
        group = components[record['component']]
        group['calls'] += 1
        group['input_tokens'] += record.get('input_tokens') or 0
        group['output_tokens'] += record.get('output_tokens') or 0
        group['calculated_usd'] += record.get('calculated_cost_usd') or 0
    for group in components.values():
        group['total_tokens'] = group['input_tokens'] + group['output_tokens']
    most = max(components, key=lambda name: components[name]['total_tokens']) if components else None
    report = {'query_count': len(rows), 'scope': 'Exactly Q1-Q10 through the full orchestrator. Direct interface checks, stretch tests, and memory ablations are separately logged and excluded.',
              'components': dict(components), 'most_tokens_component': most, 'cost': cost}
    save(Path(directory) / 'tokenomics-summary.json', report)
    text = ['# Ten-query tokenomics summary', '', '| Query | Route | Input | Output | Calculated USD |', '|---|---|---:|---:|---:|']
    for row in rows:
        result = row['result']; usage = result.get('token_usage', {})
        text.append(f"| {row['id']} | {result.get('route')} | {usage.get('input')} | {usage.get('output')} | {(result.get('cost_breakdown') or {}).get('total_cost')} |")
    text += ['', f"Total calculated token cost: ${cost['total_cost']}. Most tokens: {most}.", '',
             '| Component | Calls | Input | Output | Total tokens | Calculated USD |', '|---|---:|---:|---:|---:|---:|']
    for name, c in components.items():
        text.append(f"| {name} | {c['calls']} | {c['input_tokens']} | {c['output_tokens']} | {c['total_tokens']} | {c['calculated_usd']:.9f} |")
    text += ['', 'Rates verified 2026-10-15: US geographic Sonnet 4.6 Standard, $3.30/M input and $16.50/M output. These are calculated token charges under the documented pricing assumptions, not an AWS invoice.',
             'Sources: https://aws.amazon.com/bedrock/pricing/ and https://platform.claude.com/docs/en/about-claude/pricing . Cache and nonstandard-tier usage remain unpriced until supported.']
    (Path(directory) / 'TOKENOMICS.md').write_text('\n'.join(text) + '\n')
    return report


def run(mode):
    directory = ROOT / 'outputs' / (mode + '-' + stamp())
    directory.mkdir(parents=True)
    save(ROOT / ('outputs/latest-' + mode + '.json'), {'directory': str(directory)})
    foundation = call({'action': 'foundation'}, mode, directory, 'foundation')
    print('Foundation:', json.dumps(foundation), flush=True)
    if not foundation.get('success'):
        raise ValueError('Foundation failed before model tests.')
    interfaces = call({'action': 'interfaces'}, mode, directory, 'interfaces')
    print('Direct tool keys:', interfaces.get('keys'), flush=True)
    if not interfaces.get('success'):
        raise ValueError('Both direct tool contracts must pass.')
    rows = []
    for label, category, question, route, expected in CASES:
        print('\nRunning', label, '|', question, flush=True)
        result = call({'question': question}, mode, directory, label)
        describe(label, result)
        checks = check_case(result, category, route, expected)
        row = {'id': label, 'category': category, 'question': question, 'expected_route': route,
               'result': result, 'checks': checks, 'passed': all(checks.values())}
        rows.append(row)
        save(directory / 'test-results.json', {'provenance': 'actual_' + mode + '_infrastructure_run', 'cases': rows})
        print('Machine checks:', row['passed'], checks, flush=True)
    summary = cost_summary(rows, directory)
    markdown = ['# Actual test results', '', f'Execution: {mode}. First eight questions cover the required rubric mix; Q9-Q10 complete the cost sample.', '']
    for row in rows:
        r = row['result']
        markdown += [f"## {row['id']}: {row['question']}", '', f"Route: {r.get('route')}. SQL validation: {r.get('sql_validation')}. Status: {r.get('status')}. Machine checks: {row['passed']}.", '', r.get('answer', ''), '']
    markdown += ['Human review: read cited excerpts in each saved `state.retrieval_result.metadata.chunks` and confirm they support each claim. Citation-format checks do not prove factual entailment.', '']
    (directory / 'TEST-RESULTS.md').write_text('\n'.join(markdown))
    stretch = stretch_tests(mode, directory)
    log_ok = cloudwatch(directory) if mode == 'lambda' else True
    passed = all(row['passed'] for row in rows) and stretch['success'] and log_ok and summary['cost']['complete']
    save(directory / 'run-summary.json', {'success': passed, 'mode': mode, 'actual_queries': 10,
        'eight_required_cases_passed': all(row['passed'] for row in rows[:8]),
        'ten_query_cost_summary_complete': summary['cost']['complete'], 'gold_stretch_checks_passed': stretch['success'],
        'cloudwatch_complete': log_ok if mode == 'lambda' else None,
        'human_citation_review_complete': False, 'demo_complete': False})
    print('\nActual evidence saved:', directory, flush=True)
    print('Machine-verified capstone checks passed:', passed, flush=True)
    print('Human source review, reflection finalization, and your demo remain required.', flush=True)
    if not passed:
        raise ValueError('Some actual checks need review; no passing evidence was invented.')


def finalize():
    folders = {}
    for mode in ['local', 'lambda']:
        directory = Path(json.loads((ROOT / ('outputs/latest-' + mode + '.json')).read_text())['directory'])
        summary = json.loads((directory / 'run-summary.json').read_text())
        if not summary.get('success'):
            raise ValueError('Both actual local and deployed runs must pass before finalization.')
        folders[mode] = directory
    print('Review both TEST-RESULTS.md files and the supporting retrieved chunks in their JSON results.')
    if input('Have you verified the cited facts against the supplied excerpts? [y/N] ').strip().lower() not in {'y', 'yes'}:
        raise ValueError('Factual source review remains pending.')
    rows = json.loads((folders['lambda'] / 'test-results.json').read_text())['cases']
    tricky = rows[5]
    reflection = (
        'The overdue-invoice and cloud-migration question most tested routing and synthesis because it combines a current monetary total '
        'with narrative procedures from a separate document. In the actual deployed run it routed to ' + str(tricky['result']['route'])
        + ' and its final status was ' + str(tricky['result']['status']) + '. The saved state shows which worker evidence reached synthesis. '
        'SQL validation protects the execution boundary, but it cannot prove that a routed question selected the right source or that a '
        'citation supports every clause. Those require explicit source selection, evidence-preserving synthesis, and factual review. '
        'The Gold conversation also showed why memory and confirmation must share context: the follow-up SQL retained the Acme Corp '
        'filter, paused before execution, and the signed receipt permitted only the exact reviewed query, with validation repeated. '
        'Three bounded turns limit replay cost; the actual input-token difference and controlled memory ablation are recorded separately.\n')
    (ROOT / 'REFLECTION.md').write_text('# Reflection\n\n' + reflection)
    demo = input('Have you completed the required demo for your instructor/evaluator? [y/N] ').strip().lower() in {'y', 'yes'}
    status = {'actual_local_and_deployed_checks_passed': True, 'human_source_review_complete': True,
              'reflection_finalized_from_actual_results': True, 'demo_complete': demo,
              'gold_requirements_complete': demo, 'evidence_directories': {k: str(v) for k, v in folders.items()}}
    save(ROOT / 'outputs/final-status.json', status)
    print('Gold technical evidence and reflection complete. Demo complete:', demo)
    print('Keep AWS resources running until evaluation finishes.')


def package():
    if not (ROOT / 'runtime/orchestrator.py').exists():
        raise ValueError('Prepare the complete source first.')
    target = ROOT / 'unit3-capstone-submission.zip'
    denied = {'.private', '.venv', '__pycache__', '.git', 'dist', 'overrides'}
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(ROOT.rglob('*')):
            rel = path.relative_to(ROOT)
            if not path.is_file() or any(part in denied for part in rel.parts) or path == target:
                continue
            if path.suffix == '.pyc' or path.name.startswith('.env') or path.name in {'confirmation-key', 'database-credentials.json'}:
                continue
            z.write(path, 'unit3-capstone/' + str(rel))
    print('Submission archive:', target)
    print('Includes complete source and actual available evidence. Private credentials, signing key, native ZIP and model assets excluded.')
