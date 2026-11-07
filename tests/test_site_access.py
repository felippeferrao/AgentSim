import hashlib
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import auth
import native_images
import server
import site_access


class SiteAccessTests(unittest.TestCase):
    def test_login_gates_api_and_artifacts_and_logout_invalidates_cookie(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'login.json'
            salt = 'ab' * 16
            path.write_text(json.dumps({'username': 'owner', 'salt': salt, 'password_hash': hashlib.scrypt(b'fixture-password', salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()}))
            with patch.dict(os.environ, {'AGENTSIM_LOGIN_FILE': str(path), 'AGENTSIM_PUBLIC_URL': 'https://agentsim.example.com'}):
                http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
                threading.Thread(target=http.serve_forever, daemon=True).start()
                base = f'http://127.0.0.1:{http.server_port}'
                def request(route, body=None, cookie='', origin='https://agentsim.example.com'):
                    req = urllib.request.Request(base + route, data=json.dumps(body).encode() if body is not None else None, headers={'Cookie': cookie, 'Origin': origin, 'Content-Type': 'application/json'})
                    try:
                        return urllib.request.urlopen(req)
                    except urllib.error.HTTPError as e:
                        return e
                try:
                    for route in ['/api/state', '/artifacts/example/file.png', '/api/jobs/anything']:
                        self.assertEqual(request(route).code, 401)
                    self.assertEqual(request('/api/site/login', {'username':'owner','password':'wrong'}).code,401)
                    self.assertEqual(request('/api/site/login', {'username':'owner','password':'fixture-password'}, origin='https://evil.example').code,403)
                    response = request('/api/site/login', {'username':'owner','password':'fixture-password'})
                    self.assertEqual(response.code,200)
                    cookie = response.headers['Set-Cookie']
                    self.assertIn('Secure',cookie)
                    self.assertIn('HttpOnly',cookie)
                    self.assertEqual(request('/api/site/session',cookie=cookie).code,200)
                    self.assertEqual(request('/api/site/logout',{},cookie).code,200)
                    self.assertEqual(request('/api/site/session',cookie=cookie).code,401)
                finally:
                    http.shutdown()
                    http.server_close()

    def test_public_mode_requires_config(self):
        with patch.dict(os.environ, {'AGENTSIM_PUBLIC_URL':'https://agentsim.example.com'}, clear=True):
            with self.assertRaises(ValueError):
                site_access.config()

    def test_disconnect_clears_only_agentsim_credentials_and_keeps_artifacts(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(auth,'LOCAL',Path(folder)):
            for name in ('oauth','registration','provider','image-provider'):
                auth.store(name, {'fixture':'secret'})
            image = native_images.runtime_home() / 'auth.json'
            image.write_text('{"fixture":"secret"}')
            artifact = Path(folder) / 'artifacts' / 'keep.pdf'
            artifact.parent.mkdir()
            artifact.write_bytes(b'fixture')
            auth.disconnect()
            self.assertFalse(image.exists())
            self.assertTrue(artifact.exists())
            self.assertTrue(all(not auth.load(n) for n in ('oauth','registration','provider','image-provider')))

    def test_remote_native_login_uses_device_flow_and_returns_code(self):
        import io
        from unittest.mock import MagicMock
        process = MagicMock()
        process.stdout = io.StringIO('https://auth.openai.com/codex/device\nABCD-EFGH\n')
        process.poll.return_value = None
        with patch.dict(os.environ, {'AGENTSIM_PUBLIC_URL':'https://agentsim.example.com'}), patch('native_images.shutil.which', return_value='/usr/bin/codex'), patch('native_images.subprocess.Popen',return_value=process) as spawn, patch('native_images.threading.Timer'):
            native_images._LOGIN.clear()
            result = native_images.ChatGPTImageRuntime.login()
            self.assertEqual(result, {'url':'https://auth.openai.com/codex/device','code':'ABCD-EFGH'})
            self.assertIn('--device-auth',spawn.call_args.args[0])
            native_images._LOGIN.clear()

    def test_multiple_accounts_and_legacy_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'login.json'
            users = []
            for name in ('owner', 'colleague'):
                salt = os.urandom(16).hex()
                users.append({'username': name, 'salt': salt, 'password_hash': hashlib.scrypt(b'fixture-shared-password', salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()})
            with patch.dict(os.environ, {'AGENTSIM_LOGIN_FILE': str(path)}):
                path.write_text(json.dumps({'users': users}))
                first = site_access.login('owner', 'fixture-shared-password')
                second = site_access.login('colleague', 'fixture-shared-password')
                self.assertTrue(first and second and first != second)
                self.assertIsNone(site_access.login('missing', 'fixture-shared-password'))
                self.assertIsNone(site_access.login('colleague', 'wrong'))
                self.assertTrue(site_access.authenticated('agentsim_session=' + second))
                site_access.logout('agentsim_session=' + first)
                self.assertFalse(site_access.authenticated('agentsim_session=' + first))
                self.assertTrue(site_access.authenticated('agentsim_session=' + second))
                path.write_text(json.dumps(users[0]))
                self.assertTrue(site_access.login('owner', 'fixture-shared-password'))
                path.write_text(json.dumps({'users': [users[0], users[0]]}))
                with self.assertRaises(ValueError): site_access.config()
