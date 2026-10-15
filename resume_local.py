"""Resume only unfinished local Gold evidence; preserve the completed ten-query run."""
import contextlib
import json
import shutil
import sys
import time
from pathlib import Path
from unittest.mock import patch

import capstone
import evidence

ROOT = Path(__file__).resolve().parent


def main():
    source = Path(json.loads((ROOT / 'outputs/latest-local.json').read_text())['directory']).resolve()
    if not source.is_relative_to((ROOT / 'outputs').resolve()):
        raise ValueError('The local evidence directory is outside this project.')
    rows = json.loads((source / 'test-results.json').read_text())['cases']
    if len(rows) != 10:
        raise ValueError('The original ten-query evidence is incomplete.')
    checks = []
    for case, row in zip(evidence.CASES, rows):
        label, category, question, route, expected = case
        if row['id'] != label or row['question'] != question:
            raise ValueError('The saved cases do not match the capstone test set.')
        checks.append(all(evidence.check_case(row['result'], category, route, expected).values()))
    if not all(checks):
        raise ValueError('An original ten-query check actually failed; inspect it before resuming.')
    directory = ROOT / 'outputs' / ('local-resume-' + capstone.stamp())
    directory.mkdir()
    for path in source.iterdir():
        if path.is_file():
            shutil.copy2(path, directory / path.name)
    # Prior evidence is never overwritten. Only the pointer changes after success.
    capstone.save(directory / 'resume-provenance.json', {
        'original_directory': str(source), 'original_ten_queries_reexecuted': False,
        'original_outputs_preserved': True, 'cloud_deployment_changed': False})
    capstone.configure_local()
    actual_call = evidence.call
    reused = []
    def resumed_call(request, mode, target, label):
        if label in {'memory-turn1', 'memory-turn2', 'gold-flagged'}:
            prior_request = json.loads((source / (label + '-request.json')).read_text())
            prior_result = json.loads((source / (label + '-result.json')).read_text())
            if request != prior_request:
                raise ValueError('The resumed conversation differs from its saved request.')
            if label == 'gold-flagged':
                from confirmation import verify
                # First validate integrity and database binding without using an
                # expired receipt for execution. If expired, only regenerate the
                # paused follow-up; approval still happens afterwards.
                with patch('confirmation.time.time', return_value=0):
                    data = verify(prior_result['confirmation'], prior_result['history'])
                if data['expires'] <= int(time.time()):
                    print('The original receipt expired. Generating only a fresh paused follow-up; your review is still required.', flush=True)
                    return actual_call(request, mode, target, label)
            reused.append(label)
            print('Reusing saved actual result:', label, flush=True)
            return prior_result
        return actual_call(request, mode, target, label)
    with patch.object(evidence, 'call', side_effect=resumed_call):
        stretch = evidence.stretch_tests('local', directory)
    summary = json.loads((directory / 'tokenomics-summary.json').read_text())
    success = all(checks) and stretch['success'] and summary['cost']['complete']
    capstone.save(directory / 'run-summary.json', {
        'success': success, 'mode': 'local', 'actual_queries': 10,
        'eight_required_cases_passed': all(checks[:8]), 'ten_query_cost_summary_complete': summary['cost']['complete'],
        'gold_stretch_checks_passed': stretch['success'], 'cloudwatch_complete': None,
        'human_citation_review_complete': False, 'demo_complete': False,
        'original_ten_queries_reexecuted': False, 'reused_actual_stretch_results': reused,
        'resume_from': str(source)})
    if not success:
        raise ValueError('Resumed checks did not all pass; the previous evidence pointer was preserved.')
    capstone.save(ROOT / 'outputs/latest-local.json', {'directory': str(directory)})
    print('SUCCESS: local Gold evidence completed without repeating Q1-Q10.')
    print('Saved:', directory)
    print('Existing deployed Gold evidence remains unchanged. Next: review sources, demo, then capstone.py finalize.')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Stopped. The flagged query was not automatically approved or retried.')
        raise SystemExit(130)
    except Exception as error:
        print('STOPPED:', str(error) if isinstance(error, ValueError) else type(error).__name__)
        raise SystemExit(1)
