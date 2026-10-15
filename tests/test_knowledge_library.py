"""Real file/converter checks; synthetic documents, no AWS or model claims."""
import json
from pathlib import Path
import tempfile
import unittest
from rgce.knowledge_library import add, view, collection_path, inventory


class LibraryTests(unittest.TestCase):
    def test_slice_excludes_unselected_and_retains_scope(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            root = Path(d)
            source = root/'policy.md'
            source.write_text('# Synthetic policy\nDevelopment only.', encoding='utf-8')
            add(root/'library', 'org/policies', source, 'development accounts')
            source.write_text('# Unselected synthetic payroll', encoding='utf-8')
            add(root/'library', 'private/payroll', source, 'payroll')
            result = view(root/'library', ['org/policies'], root/'view')
            self.assertEqual(result['documents'], 1)
            files = list((root/'view').rglob('content.md'))
            self.assertEqual(len(files), 1)
            self.assertNotIn('payroll', files[0].read_text())
            m = json.loads((root/'view/manifest.json').read_text())
            self.assertEqual(m['documents'][0]['scope'], 'development accounts')

    def test_modified_document_is_not_silently_republished(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            root=Path(d); source=root/'note.txt'
            source.write_text('Original synthetic note', encoding='utf-8')
            record=add(root/'library','org',source,'all accounts')
            (Path(record['path'])/'content.md').write_text('Edited',encoding='utf-8')
            with self.assertRaises(ValueError):
                view(root/'library',['org'],root/'view')

    def test_collection_escape_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            for name in ('../private','org/../../other','/absolute','org\\private'):
                with self.assertRaises(ValueError): collection_path(d,name)

    def test_refresh_keeps_history_and_old_view_but_selects_explicit_replacement(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            root=Path(d); source=root/'note.md'; library=root/'library'
            source.write_text('Synthetic original', encoding='utf-8')
            original=add(library,'org/security',source,'test scope')
            view(library,['org/security'],root/'before')
            source.write_text('Synthetic revision', encoding='utf-8')
            revised=add(library,'org/security',source,'test scope',replaces=original['id'],source_ref='operator document version 2')
            again=add(library,'org/security',source,'test scope',replaces=original['id'],source_ref='operator document version 2')
            self.assertEqual(revised,again)
            self.assertEqual(view(library,['org/security'],root/'after')['documents'],1)
            self.assertEqual(next((root/'before').rglob('content.md')).read_text(),'Synthetic original')
            self.assertEqual(next((root/'after').rglob('content.md')).read_text(),'Synthetic revision')
            self.assertTrue((Path(original['path'])/'source.md').exists())
            statuses={r['id']:r['selection'] for r in inventory(library,'org/security')}
            self.assertEqual(statuses,{original['id']:'replaced',revised['id']:'active'})
            source.write_text('Synthetic third revision',encoding='utf-8')
            with self.assertRaises(ValueError):
                add(library,'org/security',source,'test scope',replaces=original['id'])
            last=add(library,'org/security',source,None,replaces=revised['id'])
            self.assertEqual(last['scope'],'test scope')
            self.assertEqual(view(library,['org/security'],root/'third')['documents'],1)

    def test_newer_import_is_not_automatic_precedence(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            root=Path(d); source=root/'note.md'
            source.write_text('Synthetic baseline',encoding='utf-8')
            add(root/'library','org/security',source,'test scope')
            source.write_text('Synthetic conflicting claim',encoding='utf-8')
            add(root/'library','org/security',source,'test scope')
            self.assertEqual(view(root/'library',['org/security'],root/'view')['documents'],2)

    def test_unknown_or_other_collection_replacement_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            root=Path(d); source=root/'note.md'
            source.write_text('Synthetic note',encoding='utf-8')
            record=add(root/'library','org/a',source,'test scope')
            with self.assertRaises(ValueError):
                add(root/'library','org/b',source,'test scope',replaces=record['id'])


if __name__=='__main__': unittest.main()
