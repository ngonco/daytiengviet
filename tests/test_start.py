import io
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch,Mock
import start


class LauncherTests(unittest.TestCase):
    def test_health_only_accepts_vietcut_not_another_app_or_invalid_json(self):
        for data,expected in [(b'{"app":"vietcut"}',True),(b'{"app":"other"}',False),(b'<html>other</html>',False),(b'[]',False)]:
            opener=Mock();opener.open.return_value=io.BytesIO(data)
            with patch('start.urllib.request.build_opener',return_value=opener):
                self.assertEqual(start.is_running('http://127.0.0.1:8876'),expected)

    def test_existing_app_opens_browser_without_starting_another_server(self):
        with patch('start.settings',return_value={'APP_PORT':'8876'}),patch('start.is_running',return_value=True),patch('start.webbrowser.open') as browser,patch('uvicorn.run') as server:
            start.main();browser.assert_called_once_with('http://127.0.0.1:8876');server.assert_not_called()

    def test_port_validation_and_missing_build_fail_before_server_start(self):
        for port in ['0','65536','invalid']:
            with patch('start.settings',return_value={'APP_PORT':port}),patch('uvicorn.run') as server:
                with self.assertRaises(ValueError):start.main()
                server.assert_not_called()
        with TemporaryDirectory() as tmp,patch('start.ROOT',Path(tmp)),patch('start.settings',return_value={}),patch('start.is_running',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'CAI_DAT.cmd'):start.main()

    def test_second_click_waits_for_first_launch_instead_of_binding_again(self):
        @contextmanager
        def locked(port):yield False
        with patch('start.settings',return_value={}),patch('start.is_running',return_value=False),patch('start.instance_lock',locked),patch('start.wait_ready',return_value=True),patch('start.webbrowser.open') as browser,patch('uvicorn.run') as server:
            start.main();browser.assert_called_once();server.assert_not_called()
        with patch('start.settings',return_value={}),patch('start.is_running',return_value=False),patch('start.instance_lock',locked),patch('start.wait_ready',return_value=False),patch('start.webbrowser.open') as browser:
            with self.assertRaisesRegex(RuntimeError,'chưa sẵn sàng'):start.main()
            browser.assert_not_called()

    def test_lock_excludes_another_launch_and_is_released(self):
        with TemporaryDirectory() as tmp,patch('start.data_root',return_value=Path(tmp)):
            with start.instance_lock(8876) as first:
                self.assertTrue(first)
                with start.instance_lock(8876) as second:self.assertFalse(second)
                with start.instance_lock(8877) as other:self.assertTrue(other)
            with start.instance_lock(8876) as retry:self.assertTrue(retry)

    def test_cold_start_uses_only_loopback_and_background_readiness_thread(self):
        with patch('start.settings',return_value={'APP_PORT':'8876'}),patch('start.is_running',return_value=False),patch('start.threading.Thread') as thread,patch('uvicorn.run') as server,TemporaryDirectory() as tmp,patch('start.data_root',return_value=Path(tmp)):
            start.main();thread.return_value.start.assert_called_once()
            server.assert_called_once_with('backend.app:app',host='127.0.0.1',port=8876,log_level='warning',access_log=False)


if __name__=='__main__':unittest.main()
