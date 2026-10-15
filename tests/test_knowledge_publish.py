"""Local transport simulations test publication failure handling, not live AWS results."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from rgce.knowledge_library import add, view
from rgce.knowledge_publish import prepare, publish, main


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.writes = []
        self.fail_after = None

    def get_paginator(self, operation):
        assert operation == 'list_objects_v2'
        return self

    def paginate(self, Bucket, Prefix):
        yield {'Contents': [{'Key': k} for k in self.objects if k.startswith(Prefix)]}

    def get_object(self, Bucket, Key):
        return {'Body': io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, IfNoneMatch):
        assert IfNoneMatch == '*'
        assert Key not in self.objects
        if self.fail_after is not None and len(self.writes) >= self.fail_after:
            raise RuntimeError('Simulated transport interruption')
        self.objects[Key] = Body
        self.writes.append(Key)


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source = self.root/'note.md'
        source.write_text('Synthetic local test context', encoding='utf-8')
        add(self.root/'library', 'org/security', source, 'synthetic test only')
        self.directory = self.root/'view'
        view(self.root/'library', ['org/security'], self.directory)
        self.config = {'bucket': 'example-test-bucket', 'prefix': 'test-workspace', 'region': 'us-east-1'}

    def test_interrupted_upload_resumes_and_repeat_does_not_write(self):
        plan, files, token = prepare(self.directory, self.config)
        client = MemoryS3()
        client.fail_after = 1
        with self.assertRaises(RuntimeError):
            publish(plan, files, client)
        client.fail_after = None
        result = publish(plan, files, client)
        self.assertEqual(result['status'], 'PUBLISHED_VERIFIED_NOT_ACTIVATED')
        self.assertEqual(client.writes[-1], plan['prefix']+'index.md')
        writes = len(client.writes)
        publish(plan, files, client)
        self.assertEqual(len(client.writes), writes)
        changed = {**self.config, 'prefix': 'different-workspace'}
        self.assertNotEqual(token, prepare(self.directory, changed)[2])

    def test_remote_conflict_and_unlisted_objects_reject_before_writes(self):
        plan, files, _ = prepare(self.directory, self.config)
        for key, body in [(plan['prefix']+'index.md', b'changed'), (plan['prefix']+'private.txt', b'unlisted')]:
            client = MemoryS3(); client.objects[key] = body
            with self.assertRaises(ValueError):
                publish(plan, files, client)
            self.assertEqual(client.writes, [])

    def test_unlisted_source_is_not_accidentally_published(self):
        (self.directory/'source.txt').write_text('Must not be uploaded', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unlisted'):
            prepare(self.directory, self.config)

    def test_tampered_content_and_metadata_are_rejected(self):
        content = next(self.directory.rglob('content.md'))
        original = content.read_bytes()
        content.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Content changed'):
            prepare(self.directory, self.config)
        content.write_bytes(original)
        metadata = content.with_name('metadata.json')
        value = json.loads(metadata.read_text()); value['scope'] = 'different'
        metadata.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'metadata differ'):
            prepare(self.directory, self.config)

    def test_path_escape_rejected(self):
        path = self.directory/'manifest.json'
        value = json.loads(path.read_text()); value['documents'][0]['path'] = '../outside/content.md'
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            prepare(self.directory, self.config)

    def test_preview_and_wrong_token_never_load_aws_sdk(self):
        config = self.root/'config.json'; config.write_text(json.dumps(self.config))
        args = ['knowledge_publish', '--view', str(self.directory), '--config', str(config)]
        with patch.dict('sys.modules', {'boto3': None}), patch('sys.argv', args), redirect_stdout(io.StringIO()) as output:
            main()
        self.assertIn('No AWS calls', output.getvalue())
        with patch.dict('sys.modules', {'boto3': None}), patch('sys.argv', args+['--publish', 'wrong']):
            with self.assertRaisesRegex(ValueError, 'token'):
                main()

    def test_changed_prepared_bytes_never_write(self):
        plan, files, _ = prepare(self.directory, self.config)
        files['index.md'] = b'changed after preview'
        client = MemoryS3()
        with self.assertRaisesRegex(ValueError, 'Prepared content changed'):
            publish(plan, files, client)
        self.assertEqual(client.writes, [])


if __name__ == '__main__':
    unittest.main()
