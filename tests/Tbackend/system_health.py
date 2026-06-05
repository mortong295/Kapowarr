import unittest
from types import SimpleNamespace

from frontend import api as api_module


class system_health(unittest.TestCase):
    def setUp(self):
        self.original_settings = api_module.Settings
        self.original_root_folders = api_module.RootFolders
        self.original_external_clients = api_module.ExternalClients
        self.original_get_providers = api_module.get_providers
        self.original_isdir = api_module.isdir

    def tearDown(self):
        api_module.Settings = self.original_settings
        api_module.RootFolders = self.original_root_folders
        api_module.ExternalClients = self.original_external_clients
        api_module.get_providers = self.original_get_providers
        api_module.isdir = self.original_isdir

    def test_health_reports_configuration_gaps(self):
        api_module.Settings = lambda: SimpleNamespace(
            sv=SimpleNamespace(
                comicvine_api_key='',
                download_folder='/missing/downloads'
            )
        )
        api_module.RootFolders = lambda: SimpleNamespace(
            get_folder_list=lambda: []
        )
        api_module.ExternalClients = SimpleNamespace(
            get_clients=lambda: [{'download_type': 2}]
        )
        api_module.get_providers = lambda feature: {
            'indexers': [{'enabled': True}],
            'connections': [],
            'importlists': []
        }[feature]
        api_module.isdir = lambda path: False

        result = api_module._system_health()

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['counts']['root_folders'], 0)
        self.assertEqual(result['counts']['torrent_clients'], 1)
        self.assertEqual(result['counts']['usenet_clients'], 0)
        self.assertEqual(
            {
                check['key']: check['status']
                for check in result['checks']
            }['root_folders'],
            'error'
        )


if __name__ == '__main__':
    unittest.main()
