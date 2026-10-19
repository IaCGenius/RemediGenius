import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('notes',Path(__file__).parents[1]/'profiles/ce/desk/plugins/ce-runtime/notes.py')
notes=importlib.util.module_from_spec(spec);spec.loader.exec_module(notes)

def test_exact_operator_confirmation_and_persistence(tmp_path):
    draft=notes.stage(tmp_path,{'action':'stage','title':'Test guidance','scope':'Unit-test fixture only','content':'This is synthetic unit-test context.'})
    params={'action':'publish','id':draft['id']}
    assert notes.publish(tmp_path,params,'Publish it please')['status']=='NEEDS_OPERATOR_CONFIRMATION'
    assert not notes.index(tmp_path)
    result=notes.publish(tmp_path,params,'publish knowledge '+draft['id'])
    assert result['status']=='PUBLISHED'
    assert result['path'] in notes.index(tmp_path)
    content=tmp_path/'ce-knowledge'/result['path']
    assert content.read_text()=='This is synthetic unit-test context.'
    assert notes.publish(tmp_path,params,'publish knowledge '+draft['id'])==result

def test_changed_draft_and_unsafe_collection_rejected(tmp_path):
    params={'action':'stage','title':'Test','scope':'Test','content':'Test','collection':'../escape'}
    with pytest.raises(ValueError):notes.stage(tmp_path,params)
    params['collection']='org/context'
    draft=notes.stage(tmp_path,params)
    (tmp_path/'ce-knowledge/drafts'/(draft['id']+'.json')).write_text('{}')
    with pytest.raises(ValueError):notes.publish(tmp_path,{'action':'publish','id':draft['id']},'publish knowledge '+draft['id'])
