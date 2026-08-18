import json
import pathlib
import tempfile
import unittest

from roy_config import PROFILES, VERSION, load_config, save_config, validate_config


class TestConfiguration(unittest.TestCase):
    def test_version_and_profiles(self):
        self.assertEqual(VERSION, '1.1.0')
        self.assertEqual(PROFILES, {'personal','developer','company_managed','developer_company_managed'})

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'config.json'; expected={'safe': True}
            save_config(expected, path)
            self.assertEqual(load_config(path), expected)

    def test_missing_config_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_config(pathlib.Path(tmp)/'missing.json'), {})

    def test_early_preview_requires_planning_only(self):
        config={'machine_profile':'personal','scan_paths':['/tmp'],
                'safety':{'planning_only':False}}
        self.assertIn('planning_only must remain true for Early Preview', validate_config(config))

    def test_valid_configuration(self):
        config={'machine_profile':'developer_company_managed','scan_paths':['/tmp'],
                'safety':{'planning_only':True}}
        self.assertEqual(validate_config(config), [])


if __name__ == '__main__': unittest.main()
