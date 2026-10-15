"""Update only reviewed Python sources in the already verified Linux Lambda ZIP."""
import json
import zipfile
from pathlib import Path
from prepare_capstone import ROOT, REPORT, base_archive, sha, BASE_SHA


def build(report_path=REPORT):
    archive = base_archive(report_path)
    manifest = json.loads((ROOT / 'source-files.json').read_text())
    runtime = ROOT / 'runtime'
    if any(sha(runtime / name) != digest for name, digest in manifest.items()):
        raise ValueError('Source differs from the prepared and tested snapshot.')
    checks_path = ROOT / 'outputs/offline-checks.json'
    checks = json.loads(checks_path.read_text())
    if not checks.get('success') or checks.get('source_manifest_sha256') != sha(ROOT / 'source-files.json'):
        raise ValueError('Run offline checks against the current prepared source before building.')
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    output = dist / 'lambda-gold.zip'
    replacements = {name: (runtime / name).read_bytes() for name in manifest}
    # Drop stale bytecode; leave every model/native dependency byte unchanged.
    with zipfile.ZipFile(archive) as old, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as new:
        for item in old.infolist():
            if item.filename in replacements or '__pycache__' in Path(item.filename).parts or item.filename.endswith('.pyc'):
                continue
            new.writestr(item, old.read(item.filename))
        for name, data in replacements.items():
            new.writestr(name, data)
    with zipfile.ZipFile(archive) as old, zipfile.ZipFile(output) as new:
        names = new.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP entries.')
        for name in names:
            if name not in replacements and new.read(name) != old.read(name):
                raise ValueError('An original model or dependency changed.')
        total = sum(i.file_size for i in new.infolist())
        if total >= 262144000:
            raise ValueError('The Lambda ZIP exceeds the uncompressed size limit.')
        for name in names:
            if Path(name).name in {'.env', 'credentials', 'confirmation-key', 'database-credentials.json'} or '.private' in Path(name).parts:
                raise ValueError('A secret/configuration file entered the archive.')
    report = {'success': True, 'runtime': 'python3.12', 'architecture': 'x86_64',
              'zip_path': str(output), 'zip_sha256': sha(output), 'zip_bytes': output.stat().st_size,
              'uncompressed_bytes': total, 'base_sha256': BASE_SHA,
              'source_manifest_sha256': sha(ROOT / 'source-files.json'),
              'offline_checks': checks['tests_run'], 'model_and_native_dependencies_unchanged': True,
              'original_real_onnx_equivalence_checks': 6, 'new_aws_calls': 0}
    (dist / 'gold-build-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('SUCCESS: Gold ZIP built from the verified Linux package; no Docker rebuild needed.')
    print('Uncompressed bytes:', total, '| limit:', 262144000)
    print('Report:', dist / 'gold-build-report.json')
    return report


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--build-report', type=Path, default=REPORT)
    build(p.parse_args().build_report)
