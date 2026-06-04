import unittest
from tempfile import TemporaryDirectory

from flask import Flask

from backend.implementations import arr_features
from backend.implementations.arr_features import (save_provider,
                                                  send_connection_event)
from backend.internals.db import close_db, set_db_location, setup_db
from backend.internals.server import Server


class FakeResponse:
    status_code = 204
    text = ''

    def raise_for_status(self):
        return None


class FakeSession:
    calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, headers=None):
        self.calls.append({
            'url': url,
            'json': json,
            'headers': headers or {}
        })
        return FakeResponse()


class connection_events(unittest.TestCase):
    def setUp(self):
        self.tempdir = TemporaryDirectory()
        set_db_location(self.tempdir.name)
        Server.url_base = ''
        self.app = Flask(__name__)
        self.ctx = self.app.app_context()
        self.ctx.push()
        setup_db()
        FakeSession.calls = []
        self.original_session = arr_features.Session
        arr_features.Session = FakeSession

    def tearDown(self):
        arr_features.Session = self.original_session
        close_db()
        self.ctx.pop()
        self.tempdir.cleanup()

    def test_webhook_connection_receives_matching_event_payload(self):
        save_provider('connections', {
            'name': 'Automation Webhook',
            'implementation': 'webhook',
            'enabled': True,
            'events': ['download_imported'],
            'settings': {'url': 'https://hooks.invalid/kapowarr'}
        })

        results = send_connection_event('download_imported', {
            'title': 'Download imported',
            'message': 'Batman imported',
            'volume_id': 1
        })

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['success'])
        self.assertEqual(FakeSession.calls[0]['url'], 'https://hooks.invalid/kapowarr')
        self.assertEqual(FakeSession.calls[0]['json']['event'], 'download_imported')
        self.assertEqual(FakeSession.calls[0]['json']['volume_id'], 1)

    def test_connection_event_filter_skips_unselected_events(self):
        save_provider('connections', {
            'name': 'Failures Only',
            'implementation': 'webhook',
            'enabled': True,
            'events': ['download_failed'],
            'settings': {'url': 'https://hooks.invalid/kapowarr'}
        })

        results = send_connection_event('download_imported', {
            'title': 'Download imported',
            'message': 'Batman imported'
        })

        self.assertEqual(results, [])
        self.assertEqual(FakeSession.calls, [])

    def test_discord_connection_formats_webhook_payload(self):
        save_provider('connections', {
            'name': 'Discord',
            'implementation': 'discord',
            'enabled': True,
            'settings': {'webhook_url': 'https://discord.invalid/webhook'}
        })

        send_connection_event('download_failed', {
            'title': 'Download failed',
            'message': 'Batman failed',
            'volume_id': 2
        })

        payload = FakeSession.calls[0]['json']
        self.assertEqual(FakeSession.calls[0]['url'], 'https://discord.invalid/webhook')
        self.assertEqual(payload['content'], 'Batman failed')
        self.assertEqual(payload['embeds'][0]['title'], 'Download failed')


if __name__ == '__main__':
    unittest.main()
