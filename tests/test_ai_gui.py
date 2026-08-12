import pathlib
import pickle
import tempfile
import unittest
from unittest.mock import patch

from roy_ai import LocalAI
from roy_classify import Category, FileInfo
from roy_gui import GUIController
from roy_scan import ScanStats


class TestLocalAI(unittest.TestCase):
    def test_disabled_by_default(self):
        ai = LocalAI({})
        self.assertFalse(ai.enabled)
        self.assertIsNone(ai.suggest_filename(pathlib.Path('photo.jpg')))

    @patch('roy_ai.shutil.which', return_value=None)
    def test_missing_ollama_is_optional(self, which):
        self.assertEqual(LocalAI({'ai_classification': {'enabled': True}}).available_models(), [])

    @patch('roy_ai.subprocess.run')
    @patch('roy_ai.shutil.which', return_value='/usr/bin/ollama')
    def test_lists_only_local_models(self, which, run):
        run.return_value.returncode = 0
        run.return_value.stdout = 'NAME ID SIZE\nllama3:latest abc 4GB\n'
        self.assertEqual(LocalAI({}).available_models(), ['llama3:latest'])
        self.assertEqual(run.call_args.args[0], ['ollama', 'list'])

    @patch.object(LocalAI, 'available_models', return_value=['local:latest'])
    @patch('roy_ai.subprocess.run')
    def test_suggestion_uses_filename_not_contents(self, run, models):
        run.return_value.returncode = 0; run.return_value.stdout = 'Travel\n'
        ai = LocalAI({'ai_classification': {'enabled': True, 'model': 'local:latest'}})
        result = ai.suggest_filename(pathlib.Path('/tmp/Norway-photo.jpg'))
        self.assertEqual(result.category, 'Travel')
        command = run.call_args.args[0]
        self.assertIn('Norway-photo.jpg', command[-1])


class TestGUIController(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = pathlib.Path(self.tmp.name)
        item = FileInfo(path=self.root/'Desktop/a.png', filename='a.png', extension='.png',
                        category=Category.IMAGES, confidence=.9, reason='test', size=1)
        stats = ScanStats(total_files=1, by_category={'Images': 1})
        self.scan = self.root/'scan.pkl'
        with self.scan.open('wb') as handle: pickle.dump(([item], stats), handle)

    def tearDown(self): self.tmp.cleanup()

    def test_counts_reuse_scan_model(self):
        self.assertEqual(GUIController({}, self.scan).counts(), {'Images': 1})

    def test_gui_plan_is_planning_only(self):
        config = {'destinations': {'Images': str(self.root/'Pictures')}, 'safety': {'planning_only': True}}
        plan = GUIController(config, self.scan).create_plan([Category.IMAGES])
        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(plan.operations[0].decision, 'pending')


if __name__ == '__main__': unittest.main()
