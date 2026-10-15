"""Run only the cases affected by the source-review findings; retain baseline evidence."""
import json
import re
import zipfile
from pathlib import Path
import capstone
import evidence

ROOT = Path(__file__).resolve().parent


def main():
    root = ROOT / 'outputs' / ('source-review-' + capstone.stamp())
    root.mkdir()
    outcomes = []
    for mode in ['local', 'lambda']:
        old = Path(json.loads((ROOT / 'outputs' / ('latest-' + mode + '.json')).read_text())['directory'])
        dest = root / mode
        dest.mkdir()
        for label in ['Q3', 'Q4', 'Q5', 'Q6', 'memory-turn2']:
            request = json.loads((old / (label + '-request.json')).read_text())
            result = capstone.call(request, mode, dest, label)
            evidence.describe(mode + ' ' + label, result)
            if label == 'memory-turn2':
                category, route, expected = 'SQL', 'sql', ['250000']
            else:
                case = next(c for c in evidence.CASES if c[0] == label)
                category, route, expected = case[1], case[3], case[4]
            checks = evidence.check_case(result, category, route, expected)
            if label == 'memory-turn2':
                checks['no_contract_count_inferred_from_client_row'] = not bool(re.search(
                    r'\b(?:single|one|1)\s+contract\b', result['answer'], re.I))
            row = {'mode': mode, 'case': label, 'checks': checks, 'passed': all(checks.values())}
            outcomes.append(row)
            capstone.save(root / 'checks.json', {'actual_focused_rechecks': outcomes})
        if mode == 'lambda':
            capstone.cloudwatch(dest)
    success = all(row['passed'] for row in outcomes)
    capstone.save(root / 'review-summary.json', {
        'automated_checks_passed': success, 'actual_focused_queries': 10,
        'baseline_gold_evidence_preserved': True, 'human_citation_review_complete': False,
        'note': 'Baseline ten-query costs remain separately scoped; these focused rechecks have their own actual usage and costs.'})
    capstone.save(ROOT / 'outputs/latest-source-review.json', {'directory': str(root)})
    archive = ROOT / 'unit3-source-review-results.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(root.rglob('*')):
            if path.is_file():
                z.write(path, str(path.relative_to(root.parent)))
        z.write(ROOT / 'source-files.json', 'source-files.json')
        z.write(ROOT / 'outputs/deployment.json', 'deployment.json')
    print('Focused rechecks passed:', success)
    print('Review ZIP:', archive)
    print('Share this review ZIP for factual citation verification before final GitHub export.')
    if not success:
        raise ValueError('Inspect the saved focused results; a passing review was not invented.')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Stopped; no invocation was automatically retried.')
        raise SystemExit(130)
    except Exception as error:
        print('STOPPED:', str(error) if isinstance(error, ValueError) else type(error).__name__)
        raise SystemExit(1)
