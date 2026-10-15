"""Export a clean, evidence-bearing GitHub submission without private configuration."""
import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def redact(value):
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {k: ('[REDACTED confirmation receipt; SHA256 ' + sha(v.encode()) + ']'
                    if k == 'token' and isinstance(v, str) else redact(v)) for k,v in value.items()}
    if isinstance(value, str) and value.lstrip().startswith(('{', '[')):
        try:
            return json.dumps(redact(json.loads(value)), ensure_ascii=False)
        except ValueError:
            pass
    return value


def make_repo(destination):
    dest = Path(destination).expanduser().resolve()
    if dest.exists():
        raise ValueError('The destination already exists; preserved it. Use --output with a new folder.')
    pointer = json.loads((ROOT / 'outputs/latest-source-review.json').read_text())
    focused = Path(pointer['directory'])
    check = json.loads((focused / 'review-summary.json').read_text())
    if not check.get('automated_checks_passed'):
        raise ValueError('Focused local and deployed rechecks must pass before repository export.')
    observed = json.loads((focused / 'checks.json').read_text())['actual_focused_rechecks']
    expected = {(mode,case) for mode in ['local','lambda'] for case in ['Q3','Q4','Q5','Q6','memory-turn2']}
    if (len(observed) != 10 or {(r['mode'],r['case']) for r in observed} != expected
            or not all(r.get('passed') and r.get('checks') and all(r['checks'].values()) for r in observed)):
        raise ValueError('The focused evidence does not contain all ten passing local/deployed checks.')
    if not json.loads((focused / 'lambda/cloudwatch.json').read_text()).get('all_complete'):
        raise ValueError('Matching CloudWatch evidence for the focused Lambda calls is incomplete.')
    selections = {}
    for mode in ['local', 'lambda']:
        folder = Path(json.loads((ROOT / 'outputs' / ('latest-' + mode + '.json')).read_text())['directory'])
        if not json.loads((folder / 'run-summary.json').read_text()).get('success'):
            raise ValueError('The original local and deployed Gold checks must both pass.')
        selections[mode] = folder
    manifest = json.loads((ROOT / 'source-files.json').read_text())
    for name,digest in manifest.items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or sha((ROOT / 'runtime' / name).read_bytes()) != digest:
            raise ValueError('The reviewed source snapshot changed.')
    dest.mkdir(parents=True)
    for name in ['capstone.py', 'prepare_capstone.py', 'build_gold.py', 'evidence.py', 'evidence_scope.py',
                 'resume_local.py', 'recheck_review.py', 'prepare_repository.py',
                 'run_offline_checks.py', 'test_delivery_tools.py', 'source-files.json', 'CAPSTONE-REQUIREMENTS.txt']:
        shutil.copy2(ROOT / name, dest / name)
    for name in manifest:
        target = dest / 'runtime' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'runtime' / name, target)
    materials = ROOT / 'review-materials'
    for name in ['QUALITY-REVIEW.md', 'REFLECTION.md']:
        shutil.copy2(materials / name, dest / name)
    shutil.copy2(materials / 'GITHUB-README.md', dest / 'README.md')
    shutil.copy2(ROOT / 'DEMO.md', dest / 'DEMO.md')
    shutil.copy2(materials / 'requirements-linux.lock', dest / 'requirements-linux.lock')
    (dest / 'requirements-test.txt').write_text('boto3==1.43.112\nlanggraph==1.2.15\nsqlglot==30.22.0\n')
    (dest / '.gitignore').write_text('''# Local secrets and generated deployment assets
.private/
.env
.env.*
!.env.example
credentials
database-credentials.json
confirmation-key
.venv/
__pycache__/
*.pyc
dist/
backups/
outputs/
capstone-state.json
*.zip
model.onnx
tokenizer.json
.DS_Store
''')
    exported = []
    def copy_evidence(source, target):
        raw = source.read_bytes()
        if source.suffix == '.json':
            output = (json.dumps(redact(json.loads(raw)), indent=2, ensure_ascii=False) + '\n').encode()
        else:
            output = raw
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(output)
        exported.append({'source_file': str(source.relative_to(ROOT)), 'export_file': str(target.relative_to(dest)),
                         'original_sha256': sha(raw), 'export_sha256': sha(output),
                         'receipt_redaction_or_json_formatting_changed_bytes': raw != output})
    for mode,folder in selections.items():
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix in {'.json', '.jsonl', '.md', '.log'}:
                copy_evidence(path, dest / 'evidence' / mode / path.name)
    for path in sorted(focused.rglob('*')):
        if path.is_file() and path.suffix in {'.json', '.jsonl', '.md', '.log'}:
            copy_evidence(path, dest / 'evidence/recheck' / path.relative_to(focused))
    for source,target in [
        (ROOT / 'outputs/offline-checks.json', dest / 'evidence/offline/offline-checks.json'),
        (ROOT / 'offline-check-output.txt', dest / 'evidence/offline/offline-check-output.txt'),
        (ROOT / 'outputs/deployment.json', dest / 'evidence/deployment/deployment.json'),
        (ROOT / 'dist/gold-build-report.json', dest / 'evidence/deployment/gold-build-report.json')]:
        copy_evidence(source,target)
    (dest / 'evidence/EXPORT-PROVENANCE.json').write_text(json.dumps({
        'original_outputs_preserved_in_working_project': True,
        'note': 'Git export redacts executable confirmation receipt strings, including nested JSON response bodies. SQL, histories, answers, usage, check outcomes and logs are retained. Hashes identify the original and exported bytes.',
        'files': exported}, indent=2) + '\n')
    (dest / 'EVIDENCE-INDEX.md').write_text('''# Evidence index

| Requirement | Files |
|---|---|
| Four populated RDS tables and populated OpenSearch | evidence/lambda/foundation-result.json |
| Exact four-key tool interfaces | evidence/lambda/interfaces-result.json |
| Worker descriptions, LangGraph nodes and AST policy | runtime/tool_registry.py, runtime/orchestrator.py, runtime/sql_validator.py |
| Validator output including deleted_at and both stacking cases | evidence/offline/offline-check-output.txt |
| Required eight cases and ten-query cost table | evidence/lambda/TEST-RESULTS.md, evidence/lambda/TOKENOMICS.md |
| Both-source actual response and matching CloudWatch lines | evidence/lambda/Q5-response.json, evidence/lambda/cloudwatch.log |
| Local memory and confirmation, including corrected ID-based scope check | evidence/local/stretch-summary.json, evidence/local/acme-scope-evidence.json |
| Deployed memory and confirmation | evidence/lambda/stretch-summary.json; memory-turn1, memory-turn2, gold-flagged, gold-confirmed, confirmation-altered and confirmed-invalid-sql request/response pairs |
| Direct replay-cost measurement | evidence/local/memory-cost-impact.json, evidence/lambda/memory-cost-impact.json |
| Focused post-review local and Lambda results | evidence/recheck/ |
| Current deployed ZIP and runtime hash | evidence/deployment/ |
| Human source-review findings and reflection | QUALITY-REVIEW.md, REFLECTION.md |

The ten-query samples are the original measured runs. Their costs are not relabeled as post-review measurements. Focused rechecks have separate usage and costs. Receipt strings are redacted for Git; source and export file hashes are recorded in EXPORT-PROVENANCE.json. The working project's original files remain intact.

The instructor demo is a separate required activity. Machine tests and this export do not claim that the demo occurred.
''')
    # Guard against accidental secret material, not ordinary configuration names.
    patterns = [r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                r'(?i)(?:RDS_PASSWORD|CONFIRMATION_SIGNING_KEY)\s*[=:]\s*[\x22\x27][A-Za-z0-9_-]{20,}']
    for path in dest.rglob('*'):
        if path.is_file():
            text = path.read_text()
            if any(re.search(pattern,text) for pattern in patterns):
                raise ValueError('A possible secret was found in the export. Do not push it: ' + str(path.relative_to(dest)))
    output = dest.with_suffix('.zip')
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(dest.rglob('*')):
            if path.is_file():
                z.write(path, dest.name + '/' + str(path.relative_to(dest)))
    print('Clean repository folder:', dest)
    print('Repository ZIP:', output)
    print('Original live evidence was preserved. Review the focused answers before your final GitHub push.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path.home() / 'bootcamp/unit3-capstone')
    try:
        make_repo(parser.parse_args().output)
    except Exception as error:
        print('STOPPED:', str(error) if isinstance(error, ValueError) else type(error).__name__)
        raise SystemExit(1)
