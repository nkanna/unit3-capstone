"""Mock tests for source preparation, immutable packaging, deployment and evidence."""
import base64
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import prepare_capstone as prepare
import build_gold
import capstone
import evidence


class DeliveryChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.console = contextlib.redirect_stdout(io.StringIO())
        self.console.__enter__()
        self.addCleanup(self.console.__exit__, None, None, None)

    def test_preparation_copies_only_application_files_and_generates_private_key(self):
        archive = self.root / 'base.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('SOURCE-MANIFEST.json', json.dumps({'files': [{'name': 'app.py'}, {'name': 'selected-corpus.json'}]}))
            z.writestr('app.py', 'VALUE = 1\n')
            z.writestr('selected-corpus.json', '{}')
            z.writestr('typing_extensions.py', '# dependency stays in Linux zip')
            z.writestr('model.onnx', b'model')
        (self.root / 'overrides').mkdir()
        (self.root / 'overrides/gold.py').write_text('GOLD = True\n')
        with patch.object(prepare, 'ROOT', self.root), patch.object(prepare, 'base_archive', return_value=archive):
            manifest = prepare.prepare()
        self.assertIn('gold.py', manifest)
        self.assertFalse((self.root / 'runtime/typing_extensions.py').exists())
        self.assertFalse((self.root / 'runtime/model.onnx').exists())
        self.assertEqual((self.root / '.private/confirmation-key').stat().st_mode & 0o777, 0o600)

    def test_preparation_preserves_user_modified_source(self):
        runtime = self.root / 'runtime'
        runtime.mkdir()
        (runtime / 'app.py').write_text('changed')
        (self.root / 'source-files.json').write_text(json.dumps({'app.py': 'old hash'}))
        with patch.object(prepare, 'ROOT', self.root), patch.object(prepare, 'base_archive', return_value=self.root / 'unused'), self.assertRaises(ValueError):
            prepare.prepare()
        self.assertEqual((runtime / 'app.py').read_text(), 'changed')

    def test_build_preserves_native_assets_removes_stale_bytecode_and_checks_size(self):
        archive = self.root / 'base.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('app.py', 'OLD = True')
            z.writestr('__pycache__/app.pyc', b'old cached code')
            z.writestr('model.onnx', b'unchanged model')
            z.writestr('lib/native.so', b'unchanged native')
        runtime = self.root / 'runtime'; runtime.mkdir()
        (runtime / 'app.py').write_text('NEW = True')
        manifest = {'app.py': prepare.sha(runtime / 'app.py')}
        capstone.save(self.root / 'source-files.json', manifest)
        capstone.save(self.root / 'outputs/offline-checks.json', {'success': True, 'tests_run': 25,
                      'source_manifest_sha256': prepare.sha(self.root / 'source-files.json')})
        with patch.object(build_gold, 'ROOT', self.root), patch.object(build_gold, 'base_archive', return_value=archive):
            report = build_gold.build()
        with zipfile.ZipFile(report['zip_path']) as z:
            self.assertEqual(z.read('app.py'), b'NEW = True')
            self.assertEqual(z.read('model.onnx'), b'unchanged model')
            self.assertEqual(z.read('lib/native.so'), b'unchanged native')
            self.assertNotIn('__pycache__/app.pyc', z.namelist())

    def test_bad_build_stops_before_any_aws_client(self):
        archive = self.root / 'bad.zip'; archive.write_bytes(b'bad')
        capstone.save(self.root / 'dist/gold-build-report.json', {'success': True, 'zip_path': str(archive),
                     'zip_sha256': 'wrong', 'base_sha256': prepare.BASE_SHA})
        with patch.object(capstone, 'ROOT', self.root), patch.object(capstone, 'api') as api, self.assertRaises(ValueError):
            capstone.deploy()
        api.assert_not_called()

    def test_unknown_owned_name_cannot_adopt_different_function(self):
        client = Mock()
        client.get_function_configuration.return_value = {'Description': 'somebody else'}
        with patch.object(capstone, 'api', return_value=client), patch.object(capstone, 'owner', return_value='mine'), self.assertRaises(ValueError):
            capstone.live_config()

    def test_cloud_updates_preserve_environment_and_wait_between_updates(self):
        archive = self.root / 'gold.zip'; archive.write_bytes(b'new zip')
        capstone.save(self.root / 'source-files.json', {})
        new_sha = prepare.sha(archive)
        capstone.save(self.root / 'dist/gold-build-report.json', {'success': True, 'zip_path': str(archive),
                      'zip_sha256': new_sha, 'base_sha256': prepare.BASE_SHA,
                      'source_manifest_sha256': prepare.sha(self.root / 'source-files.json')})
        environment = {'RDS_USER': 'agent_reader', 'RDS_HOST': 'db', 'RDS_DATABASE': 'bootcamp', 'RDS_PASSWORD': 'secret-reader-value', 'OTHER': 'preserved'}
        config = {'CodeSha256': base64.b64encode(bytes.fromhex(prepare.BASE_SHA)).decode(), 'RevisionId': 'before', 'Environment': {'Variables': environment}}
        ready1 = {**config, 'RevisionId': 'after-config'}
        ready2 = {**ready1, 'CodeSha256': base64.b64encode(bytes.fromhex(new_sha)).decode(),
                  'State': 'Active', 'LastUpdateStatus': 'Successful', 'Runtime': 'python3.12', 'Architectures': ['x86_64']}
        lam, s3 = Mock(), Mock()
        s3.head_object.return_value = {'ContentLength': archive.stat().st_size, 'Metadata': {'sha256': new_sha}}
        order = []
        lam.update_function_configuration.side_effect = lambda **kw: order.append('config')
        lam.update_function_code.side_effect = lambda **kw: order.append('code')
        def wait():
            order.append('wait')
            return ready1 if len(order) < 4 else ready2
        with patch.object(capstone, 'ROOT', self.root), patch.object(capstone, 'STATE', self.root / 'state.json'), \
             patch.object(capstone, 'live_config', return_value=config), patch.object(capstone, 'private_key', return_value='private-key'), \
             patch.object(capstone, 'owner', return_value='owner'), patch.object(capstone, 'wait_active', side_effect=wait), \
             patch.object(capstone, 'api', side_effect=lambda name: lam if name == 'lambda' else s3):
            capstone.deploy()
        self.assertEqual(order, ['config', 'wait', 'code', 'wait'])
        supplied = lam.update_function_configuration.call_args.kwargs
        self.assertEqual(supplied['Environment']['Variables']['OTHER'], 'preserved')
        self.assertNotIn('VpcConfig', supplied)
        self.assertNotIn('secret-reader-value', (self.root / 'outputs/deployment.json').read_text())

    def test_lambda_evidence_uses_cli_once_with_retries_disabled(self):
        directory = self.root / 'evidence'
        state = self.root / 'state.json'
        capstone.save(state, {'zip_sha256': prepare.BASE_SHA})
        config = {'CodeSha256': base64.b64encode(bytes.fromhex(prepare.BASE_SHA)).decode(), 'LastUpdateStatus': 'Successful'}
        commands = []
        def cli(command, **kwargs):
            commands.append((command, kwargs))
            output = Path(command[-3])
            capstone.save(output, {'statusCode': 200, 'body': json.dumps({'status': 'ANSWERED'})})
            return SimpleNamespace(returncode=0, stdout='{"StatusCode": 200}')
        with patch.object(capstone, 'STATE', state), patch.object(capstone, 'live_config', return_value=config), \
             patch.object(capstone.shutil, 'which', return_value='/usr/bin/aws'), patch.object(capstone.subprocess, 'run', side_effect=cli):
            result = capstone.call({'question': 'Test'}, 'lambda', directory, 'case')
        self.assertEqual(result['status'], 'ANSWERED')
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0][:3], ['aws', 'lambda', 'invoke'])
        self.assertEqual(commands[0][1]['env']['AWS_MAX_ATTEMPTS'], '1')

    def test_confirmation_requires_a_real_human_yes(self):
        result = {'sql': 'SELECT * FROM clients', 'confirmation_reasons': ['Unrestricted']}
        with patch('builtins.input', return_value='n'), self.assertRaises(ValueError):
            evidence.review_exact(result)
        with patch('builtins.input', return_value='y'):
            evidence.review_exact(result)

    def test_evidence_has_required_eight_plus_two_mix(self):
        cases = evidence.CASES
        self.assertEqual(len(cases), 10)
        self.assertEqual([c[1] for c in cases[:8]], ['SQL', 'SQL', 'documents', 'documents', 'both', 'both', 'unsafe', 'unanswerable'])

    def test_submission_excludes_private_key_and_native_package(self):
        (self.root / 'runtime').mkdir()
        (self.root / 'runtime/orchestrator.py').write_text('# source')
        (self.root / '.private').mkdir()
        (self.root / '.private/confirmation-key').write_text('private')
        (self.root / 'dist').mkdir()
        (self.root / 'dist/lambda.zip').write_bytes(b'large zip')
        with patch.object(evidence, 'ROOT', self.root):
            evidence.package()
        with zipfile.ZipFile(self.root / 'unit3-capstone-submission.zip') as z:
            self.assertEqual(z.namelist(), ['unit3-capstone/runtime/orchestrator.py'])


if __name__ == '__main__':
    print('DELIVERY MOCK CHECKS: no AWS requests or model calls.')
    unittest.main(verbosity=2)
