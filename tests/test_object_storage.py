import io
import json
import sqlite3
from contextlib import contextmanager
import pytest
import boto3
from botocore.stub import Stubber, ANY
from rgce.object_storage import ObjectStorage
from rgce.store import Store, digest, canonical


def client():
    return boto3.client('s3', region_name='us-east-1', aws_access_key_id='test', aws_secret_access_key='test')


def test_write_failure_never_commits_local_success(tmp_path):
    c = client()
    with Stubber(c) as stub:
        stub.add_response('list_objects_v2', {'Contents': []}, {'Bucket': 'test-bucket', 'Prefix': 'ce/records/'})
        store = Store(tmp_path, ObjectStorage('test-bucket', 'ce', c))
        stub.add_client_error('put_object', 'AccessDenied')
        with pytest.raises(Exception):
            store.put('note', {'text': 'must not be saved'})
        assert store.list() == []
        with pytest.raises(ValueError, match='restart the workspace'):
            store.put('note', {'text': 'do not retry against an uncertain cache'})
        stub.assert_no_pending_responses()


def test_recovery_verifies_hash_before_replacing_index(tmp_path):
    c = client()
    with Stubber(c) as stub:
        stub.add_response('list_objects_v2', {'Contents': []})
        store = Store(tmp_path, ObjectStorage('test-bucket', 'ce', c))
        key = 'a' * 64
        stub.add_response('list_objects_v2', {'Contents': [{'Key': 'ce/records/' + key + '.json'}]})
        stub.add_response('get_object', {'Body': io.BytesIO(json.dumps({'id':key,'kind':'note','body':{},'stored_at':'2026-01-01T00:00:00Z'}).encode())})
        with pytest.raises(ValueError, match='integrity'):
            store.recover()


def test_conditional_record_retry_preserves_first_timestamp():
    c=client(); record={'id':digest({'kind':'note','body':{}}),'kind':'note','body':{},'stored_at':'2026-01-01T00:00:00Z'}
    with Stubber(c) as stub:
        stub.add_client_error('put_object', 'PreconditionFailed', http_status_code=412,
            expected_params={'Bucket':'test-bucket','Key':'ce/records/'+record['id']+'.json','Body':ANY,'IfNoneMatch':'*','ServerSideEncryption':'AES256'})
        stub.add_response('get_object', {'Body':io.BytesIO(json.dumps(record).encode())})
        actual=ObjectStorage('test-bucket','ce',c).put_record({**record,'stored_at':'2026-02-01T00:00:00Z'})
        assert actual==record


def test_cache_cannot_silently_switch_authority(tmp_path):
    record = Store(tmp_path).put('note', {})
    with pytest.raises(ValueError, match='fresh home'):
        Store(tmp_path, ObjectStorage('test-bucket','ce',client()))
    # A rejected transition must leave the original local workspace usable.
    assert Store(tmp_path).get(record['id']) == record


def test_remote_cache_rejects_missing_configuration(tmp_path):
    c=client()
    with Stubber(c) as stub:
        stub.add_response('list_objects_v2', {'Contents': []})
        Store(tmp_path, ObjectStorage('test-bucket','ce',c))
    with pytest.raises(ValueError, match='requires its S3'):
        Store(tmp_path)


def test_recovery_preserves_revision_chain_after_clock_moves_back(tmp_path, monkeypatch):
    from rgce import knowledge as k
    import rgce.store as storage
    local = Store(tmp_path/'local')
    monkeypatch.setattr(storage, 'now', lambda: '2030-01-02T00:00:00+00:00')
    monkeypatch.setattr(k, 'now', storage.now)
    draft = k.simple_draft(local, 'Original guidance')
    first = k.publish(local, draft['id'], draft['id'], 'Reviewer')
    monkeypatch.setattr(storage, 'now', lambda: '2030-01-01T00:00:00+00:00')
    monkeypatch.setattr(k, 'now', storage.now)
    draft = k.simple_draft(local, 'Updated guidance', revision_id=first['id'])
    second = k.publish(local, draft['id'], draft['id'], 'Reviewer')
    records = local.list(limit=500)
    c = client()
    with Stubber(c) as stub:
        stub.add_response('list_objects_v2', {'Contents': [{'Key':'ce/records/'+r['id']+'.json'} for r in records]})
        for record in records:
            stub.add_response('get_object', {'Body':io.BytesIO(canonical(record).encode())})
        recovered = Store(tmp_path/'recovered', ObjectStorage('test-bucket','ce',c))
    assert k.heads(recovered)[second['body']['concept_id']]['id'] == second['id']
    # The recovered head must also be used by publication's optimistic base check.
    with Stubber(c) as stub:
        stub.add_response('put_object', {})
        draft = k.simple_draft(recovered, 'Next revision', revision_id=second['id'])
        stub.add_response('put_object', {})
        third = k.publish(recovered, draft['id'], draft['id'], 'Reviewer')
    assert k.heads(recovered)[third['body']['concept_id']]['id'] == third['id']


def test_recovery_restores_document_receipt(tmp_path):
    from rgce import documents
    local=Store(tmp_path/'local')
    original=b'# Recover this document and its receipt'
    record=documents.intake(local,'policy.md',original)
    c=client()
    with Stubber(c) as stub:
        stub.add_response('list_objects_v2', {'Contents':[{'Key':'ce/records/'+record['id']+'.json'}]})
        stub.add_response('get_object', {'Body':io.BytesIO(canonical(record).encode())})
        stub.add_response('get_object', {'Body':io.BytesIO(original)})
        recovered=Store(tmp_path/'recovered',ObjectStorage('test-bucket','ce',c))
    relative='knowledge/documents/'+record['id']+'/receipt.json'
    assert (recovered.home/relative).read_bytes()==(local.home/relative).read_bytes()


def test_remote_success_local_commit_failure_requires_restart(tmp_path, monkeypatch):
    c=client()
    with Stubber(c) as stub:
        stub.add_response('list_objects_v2', {'Contents':[]})
        backend=ObjectStorage('test-bucket','ce',c)
        store=Store(tmp_path,backend)
        original_connect=store.connect
        @contextmanager
        def failing_commit():
            with original_connect() as db:
                yield db
                raise sqlite3.OperationalError('simulated local commit failure')
        monkeypatch.setattr(store,'connect',failing_commit)
        stub.add_response('put_object', {})
        with pytest.raises(sqlite3.OperationalError):
            store.put('note',{'text':'remote committed'})
        with pytest.raises(ValueError,match='restart the workspace'):
            store.put('note',{'text':'must not use the stale index'})
        stub.assert_no_pending_responses()
