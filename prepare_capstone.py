"""Assemble complete portable source from the actual verified Day 4 ZIP."""
import hashlib
import json
import os
import secrets
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_SHA = '53a852652bdf8176598d7ace838ec25a412b520aec15f2a074c65df1c48f0b0c'
REPORT = Path.home() / 'bootcamp/day4-lambda-build/builds/20261015T171721073595Z/build-report.json'


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(part)
    return value.hexdigest()


def base_archive(report_path=REPORT):
    report = json.loads(Path(report_path).read_text())
    archive = Path(report['zip_path']).expanduser()
    if not report.get('success') or report.get('zip_sha256') != BASE_SHA or sha(archive) != BASE_SHA:
        raise ValueError('The original verified Day 4 archive must match its reviewed SHA256.')
    return archive


def prepare(report_path=REPORT):
    archive = base_archive(report_path)
    runtime = ROOT / 'runtime'
    manifest_path = ROOT / 'source-files.json'
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if any(not (runtime / name).is_file() or sha(runtime / name) != value for name, value in previous.items()):
            raise ValueError('Prepared source was edited. Preserve those edits before re-preparing.')
    runtime.mkdir(exist_ok=True)
    files = []
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        app_manifest = json.loads(z.read('SOURCE-MANIFEST.json'))
        application_names = {row['name'] for row in app_manifest['files']} | {'SOURCE-MANIFEST.json'}
        # Only application code, corpus descriptors, provenance and certificate. No native wheels or secrets.
        for name in names:
            p = Path(name)
            if '..' in p.parts or p.is_absolute():
                raise ValueError('Unsafe archive path.')
            eligible = name in application_names
            if eligible:
                target = runtime / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
                files.append(name)
    for source in sorted((ROOT / 'overrides').rglob('*')):
        if source.is_file() and '__pycache__' not in source.parts:
            name = str(source.relative_to(ROOT / 'overrides'))
            target = runtime / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            files.append(name)
    manifest = {name: sha(runtime / name) for name in sorted(set(files))}
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    private = ROOT / '.private'
    private.mkdir(mode=0o700, exist_ok=True)
    os.chmod(private, 0o700)
    key = private / 'confirmation-key'
    if not key.exists():
        fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(secrets.token_urlsafe(48))
    if key.is_symlink() or key.stat().st_mode & 0o077:
        raise ValueError('The signing-key file must be an owner-only regular file.')
    for source in runtime.rglob('*.py'):
        compile(source.read_text(), str(source), 'exec')
    print('Complete Gold source prepared in:', runtime)
    print('Original agents, AST validator, selected instructor corpus, model and native dependencies preserved.')
    print('No AWS calls or deployment performed. Private signing key was generated without displaying it.')
    return manifest


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--build-report', type=Path, default=REPORT)
    try:
        prepare(p.parse_args().build_report)
    except Exception as error:
        print('STOPPED:', str(error) if isinstance(error, ValueError) else type(error).__name__)
        raise SystemExit(1)
