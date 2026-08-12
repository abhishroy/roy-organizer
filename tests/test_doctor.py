import unittest
from unittest.mock import patch

from roy_doctor import diagnose


class TestDoctor(unittest.TestCase):
    def config(self):
        return {'machine_profile':'personal','scan_paths':['/tmp'],
                'safety':{'planning_only':True,'protected_paths':['~/.ssh'],
                          'skip_open_files':True}}

    @patch('roy_doctor.shutil.which', return_value=None)
    @patch('roy_safety.subprocess.run')
    def test_read_only_diagnostics(self, run, which):
        run.return_value.returncode=0; run.return_value.stdout='p1\n'
        results=diagnose(self.config())
        names={item['name'] for item in results}
        self.assertIn('Open-file detection', names)
        self.assertIn('Real execution', names)
        self.assertIn('Ollama (optional)', names)

    @patch('roy_safety.subprocess.run')
    def test_unknown_open_state_is_warning(self, run):
        run.return_value.returncode=1; run.return_value.stdout=''
        result=next(item for item in diagnose(self.config()) if item['name']=='Open-file detection')
        self.assertFalse(result['ok'])
        self.assertEqual(result['detail'], 'OPEN_FILE_STATE_UNKNOWN')

    def test_invalid_config_reported(self):
        result=next(item for item in diagnose({}) if item['name']=='Configuration')
        self.assertFalse(result['ok'])


if __name__ == '__main__': unittest.main()
