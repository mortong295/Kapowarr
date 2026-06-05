import unittest

from backend.implementations.arr_features import test_provider


class provider_validation_messages(unittest.TestCase):
    def test_indexer_validation_names_missing_required_settings(self):
        result = test_provider('indexers', {
            'implementation': 'torznab',
            'settings': {'base_url': 'https://indexer.invalid'}
        })

        self.assertEqual(result['status'], 'failed')
        self.assertEqual(
            result['message'],
            'Missing required setting(s): api_key, categories.'
        )

    def test_connection_validation_names_missing_url_and_token(self):
        result = test_provider('connections', {
            'implementation': 'emby',
            'settings': {}
        })

        self.assertEqual(result['status'], 'failed')
        self.assertEqual(
            result['message'],
            'Missing required setting(s): base_url, api_key.'
        )

    def test_complete_provider_reports_required_settings_present(self):
        result = test_provider('indexers', {
            'implementation': 'torznab',
            'settings': {
                'base_url': 'https://indexer.invalid',
                'api_key': 'token',
                'categories': '7030'
            }
        })

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(
            result['message'],
            'Provider type is recognised and required settings are present.'
        )


if __name__ == '__main__':
    unittest.main()
