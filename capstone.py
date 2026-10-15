"""Gold capstone: live checks, update the owned Lambda, and collect evidence."""
import argparse
import base64
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from prepare_capstone import ROOT, REPORT, BASE_SHA, sha

ACCOUNT = '593470989370'
REGION = 'us-east-1'
FUNCTION = 'multi-agent-orchestrator-nk'
BUCKET = 'bootcamp-day3-593470989370-us-east-1'
PUBLIC = Path.home() / 'bootcamp/day4-lambda-public'
STATE = ROOT / 'capstone-state.json'
_session = None
_local_ready = False


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str, allow_nan=False) + '\n')


def private_key():
    path = ROOT / '.private/confirmation-key'
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError('Signing key must be an owner-only regular file.')
    key = path.read_text().strip()
    if len(key) < 43:
        raise ValueError('Signing key is missing or too short.')
    return key


def session():
    global _session
    if _session is None:
        import boto3
        from botocore.config import Config
        candidate = boto3.Session(region_name=REGION)
        if candidate.client('sts', config=Config(retries={'total_max_attempts': 1})).get_caller_identity()['Account'] != ACCOUNT:
            raise ValueError('Use the existing default training AWS account, not bootcamp-sandbox.')
        _session = candidate
    return _session


def api(service):
    from botocore.config import Config
    return session().client(service, config=Config(retries={'total_max_attempts': 1}, read_timeout=360))


def owner():
    return json.loads((PUBLIC / 'public-deployment-state.json').read_text())['owner']


def live_config():
    config = api('lambda').get_function_configuration(FunctionName=FUNCTION)
    if (config.get('Description') != 'Bootcamp NK deployment owner=' + owner()
            or config.get('Runtime') != 'python3.12' or config.get('Architectures') != ['x86_64']
            or config.get('Handler') != 'lambda_handler.handler'
            or (config.get('VpcConfig') or {}).get('SubnetIds')):
        raise ValueError('The live Lambda ownership/runtime differs from the reviewed deployment.')
    return config  # Never print or save Environment.


def wait_active():
    for _ in range(120):
        config = live_config()
        if config.get('State') == 'Active' and config.get('LastUpdateStatus') == 'Successful':
            return config
        if config.get('State') == 'Failed' or config.get('LastUpdateStatus') == 'Failed':
            raise ValueError('Lambda update failed; inspect the safe AWS console status.')
        print('Waiting for Lambda update...', flush=True)
        time.sleep(5)
    raise ValueError('Lambda update did not complete. No invocation was attempted.')


def deploy():
    build = json.loads((ROOT / 'dist/gold-build-report.json').read_text())
    archive = Path(build['zip_path'])
    if not build.get('success') or sha(archive) != build['zip_sha256'] or build['base_sha256'] != BASE_SHA:
        raise ValueError('Gold build verification failed before AWS access.')
    if sha(ROOT / 'source-files.json') != build['source_manifest_sha256']:
        raise ValueError('The prepared source manifest changed after build.')
    config = live_config()
    state = json.loads(STATE.read_text()) if STATE.exists() else {'applied_shas': []}
    current_sha = base64.b64decode(config['CodeSha256']).hex()
    if current_sha not in {BASE_SHA, build['zip_sha256'], *state.get('applied_shas', [])}:
        raise ValueError('The function contains an unreviewed code version; preserved it.')
    environment = dict(config.get('Environment', {}).get('Variables', {}))
    if environment.get('RDS_USER') != 'agent_reader' or not all(environment.get(k) for k in ['RDS_HOST', 'RDS_DATABASE', 'RDS_PASSWORD']):
        raise ValueError('The verified SELECT-only database configuration must already be present.')
    environment['CONFIRMATION_SIGNING_KEY'] = private_key()
    lam = api('lambda')
    # Configuration and code updates are sequential; each waits before the next operation.
    lam.update_function_configuration(FunctionName=FUNCTION, RevisionId=config['RevisionId'],
                                      Environment={'Variables': environment})
    config = wait_active()
    key = 'unit3-capstone/' + owner() + '/' + build['zip_sha256'] + '/lambda-gold.zip'
    api('s3').upload_file(str(archive), BUCKET, key, ExtraArgs={
        'ServerSideEncryption': 'AES256', 'Metadata': {'sha256': build['zip_sha256'], 'owner': owner()}})
    head = api('s3').head_object(Bucket=BUCKET, Key=key)
    if head['ContentLength'] != archive.stat().st_size or head.get('Metadata', {}).get('sha256') != build['zip_sha256']:
        raise ValueError('S3 artifact verification failed.')
    lam.update_function_code(FunctionName=FUNCTION, RevisionId=config['RevisionId'], S3Bucket=BUCKET, S3Key=key)
    config = wait_active()
    if base64.b64decode(config['CodeSha256']).hex() != build['zip_sha256']:
        raise ValueError('The deployed code hash differs from the Gold ZIP.')
    state.update(function=FUNCTION, zip_sha256=build['zip_sha256'], s3_key=key,
                 applied_shas=list(dict.fromkeys(state.get('applied_shas', []) + [build['zip_sha256']])))
    save(STATE, state)
    report = {'success': True, 'function': FUNCTION, 'state': config['State'], 'last_update_status': config['LastUpdateStatus'],
              'runtime': config['Runtime'], 'architecture': config['Architectures'], 'zip_sha256': build['zip_sha256'],
              'confirmation_key_configured': True, 'database_user': 'agent_reader',
              'environment_values_disclosed': False, 'new_databases_or_domains_created': 0}
    save(ROOT / 'outputs/deployment.json', report)
    print('SUCCESS: owned Lambda updated to Gold. Existing RDS/OpenSearch, IAM policy, and reader settings preserved.')


def configure_local():
    global _local_ready
    if _local_ready:
        return
    if not (ROOT / 'runtime/orchestrator.py').is_file():
        raise ValueError('Run prepare_capstone.py first.')
    config = live_config()
    values = config.get('Environment', {}).get('Variables', {})
    if values.get('RDS_USER') != 'agent_reader':
        raise ValueError('Local live evidence requires the existing SELECT-only database user.')
    for key in ['RDS_HOST', 'RDS_PORT', 'RDS_DATABASE', 'RDS_USER', 'RDS_PASSWORD']:
        if key in values:
            os.environ[key] = values[key]
    os.environ['AWS_REGION'] = REGION
    os.environ['BEDROCK_MODEL_ID'] = values.get('BEDROCK_MODEL_ID',
        f'arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/us.anthropic.claude-sonnet-4-6')
    os.environ['CONFIRMATION_SIGNING_KEY'] = private_key()
    os.environ['AGENT_LOG_PATH'] = str(ROOT / 'outputs/local-agent-decisions.jsonl')
    sys.path.insert(0, str(ROOT / 'runtime'))
    # Local Mac continues using the exact cached Sentence Transformers model.
    # Deployed ZIP retains the verified equivalent Linux ONNX implementation.
    import onnx_embed
    from types import SimpleNamespace
    model = None
    def get_model():
        nonlocal model
        if model is None:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',
                                        revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41',
                                        local_files_only=True, device='cpu')
        return model
    def ids(text):
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Supply a nonempty embedding input.')
        tokens = get_model().tokenizer(text, add_special_tokens=True, truncation=False)['input_ids']
        if len(tokens) > 256:
            raise ValueError('The retrieval question exceeds the 256-token model limit.')
        return SimpleNamespace(ids=tokens)
    def embed(text):
        ids(text)
        return get_model().encode(text, normalize_embeddings=True).tolist()
    onnx_embed.encoded_ids = ids
    onnx_embed.get_embedding = embed
    _local_ready = True


def call(request, mode, directory, label):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    request_path = directory / (label + '-request.json')
    response_path = directory / (label + '-response.json')
    save(request_path, request)
    if mode == 'local':
        configure_local()
        from lambda_handler import handler
        from types import SimpleNamespace
        with (directory / 'local-console.jsonl').open('a') as stream, contextlib.redirect_stdout(stream):
            outer = handler(request, SimpleNamespace(aws_request_id='local-' + label + '-' + stamp()))
        save(response_path, outer)
    else:
        if not STATE.exists():
            raise ValueError('Deploy the Gold ZIP before collecting deployed evidence.')
        config = live_config()
        expected = json.loads(STATE.read_text())['zip_sha256']
        if base64.b64decode(config['CodeSha256']).hex() != expected or config.get('LastUpdateStatus') != 'Successful':
            raise ValueError('Wait for the intended Gold Lambda update before invoking.')
        if not shutil.which('aws'):
            raise ValueError('AWS CLI is required for the capstone invocation evidence.')
        env = {**os.environ, 'AWS_MAX_ATTEMPTS': '1', 'AWS_RETRY_MODE': 'standard'}
        command = ['aws', 'lambda', 'invoke', '--function-name', FUNCTION, '--region', REGION,
                   '--cli-binary-format', 'raw-in-base64-out', '--cli-read-timeout', '360',
                   '--payload', 'fileb://' + str(request_path.resolve()), str(response_path.resolve()), '--output', 'json']
        completed = subprocess.run(command, capture_output=True, text=True, env=env)
        if completed.returncode:
            # Do not echo SDK stderr, raw secrets, or automatically replay an uncertain invocation.
            save(directory / (label + '-transport-error.json'), {'return_code': completed.returncode, 'automatic_retry': False})
            raise ValueError('Lambda invocation transport failed. Inspect AWS locally; no automatic replay occurred.')
        metadata = json.loads(completed.stdout)
        save(directory / (label + '-invoke-metadata.json'), {k: metadata.get(k) for k in ['StatusCode', 'FunctionError', 'ExecutedVersion']})
        outer = json.loads(response_path.read_text())
        if metadata.get('FunctionError'):
            raise ValueError('Lambda reported a function error; inspect the saved response.')
    if outer.get('statusCode') not in {200, 400, 502}:
        raise ValueError('The handler returned an error. Inspect its saved safe response and logs.')
    payload = json.loads(outer['body'])
    save(directory / (label + '-result.json'), payload)
    return payload


def cloudwatch(directory):
    directory = Path(directory)
    traces = {r.get('trace_id') for path in directory.glob('*-result.json')
              for r in [json.loads(path.read_text())] if r.get('trace_id')}
    events = []
    logs = api('logs')
    for trace in sorted(traces):
        rows = []
        # Delivery polling reads logs only. It never replays a Lambda invocation.
        for attempt in range(6):
            token = None
            seen_tokens = set()
            collected = {}
            while True:
                kwargs = {'logGroupName': '/aws/lambda/' + FUNCTION, 'filterPattern': '"' + trace + '"'}
                if token:
                    kwargs['nextToken'] = token
                page = logs.filter_log_events(**kwargs)
                for row in page.get('events', []):
                    text = row['message']
                    if '[LOG] ' in text:
                        try:
                            parsed = json.loads(text.split('[LOG] ', 1)[1])
                            if parsed.get('trace_id') == trace:
                                collected[row['eventId']] = {'cloudwatch_timestamp': row['timestamp'], 'message': text, 'event': parsed}
                        except (ValueError, KeyError):
                            pass
                next_token = page.get('nextToken')
                if not next_token or next_token == token or next_token in seen_tokens:
                    break
                seen_tokens.add(next_token)
                token = next_token
            rows = sorted(collected.values(), key=lambda r: r['event'].get('sequence', 0))
            if rows and rows[-1]['event'].get('stage') in {'query_complete', 'query_error'}:
                break
            if attempt < 5:
                print('Waiting for CloudWatch trace delivery...', flush=True)
                time.sleep(5)
        events.extend(rows)
    summary = {trace: any(r['event'].get('trace_id') == trace and r['event'].get('stage') == 'query_complete' for r in events) for trace in traces}
    save(directory / 'cloudwatch.json', {'traces_complete': summary, 'events': events, 'all_complete': all(summary.values()) and bool(summary)})
    (directory / 'cloudwatch.log').write_text(''.join(r['message'].rstrip() + '\n' for r in events))
    print('CloudWatch traces complete:', all(summary.values()) and bool(summary), '| events:', len(events))
    return all(summary.values()) and bool(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['deploy', 'foundation', 'local', 'lambda', 'logs', 'finalize', 'package'])
    parser.add_argument('--directory', type=Path)
    args = parser.parse_args()
    if args.command == 'deploy':
        return deploy()
    if args.command == 'foundation':
        directory = ROOT / 'outputs/foundation'
        result = call({'action': 'foundation'}, 'local', directory, 'foundation')
        print(json.dumps(result, indent=2))
        if not result.get('success'):
            raise ValueError('Foundation checks failed.')
        return
    import evidence
    if args.command in {'local', 'lambda'}:
        return evidence.run(args.command)
    if args.command == 'logs':
        pointer = json.loads((ROOT / 'outputs/latest-lambda.json').read_text())
        return cloudwatch(args.directory or pointer['directory'])
    if args.command == 'finalize':
        return evidence.finalize()
    if args.command == 'package':
        return evidence.package()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nStopped. Existing outputs were preserved; no invocation was retried.')
        raise SystemExit(130)
    except Exception as error:
        print('STOPPED:', str(error) if isinstance(error, ValueError) else type(error).__name__)
        raise SystemExit(1)
