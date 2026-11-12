import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock,patch
import httpx
from backend.providers import request,ProviderError,transcribe
from backend.automation import failure
from backend.media import Cancelled


class ProviderRetryTests(unittest.TestCase):
    def setUp(self):
        self.client=Mock()
        self.client.__enter__=Mock(return_value=self.client)
        self.client.__exit__=Mock(return_value=False)
        self.factory=patch('backend.providers.httpx.Client',return_value=self.client)
        self.factory.start();self.addCleanup(self.factory.stop)
        self.sleep=patch('backend.providers.time.sleep');self.sleep.start();self.addCleanup(self.sleep.stop)
        self.context=Mock()

    def test_remote_disconnect_recovers_and_reports_provider_and_retry(self):
        response=httpx.Response(200,json={'ok':True})
        self.client.request.side_effect=[httpx.RemoteProtocolError('Server disconnected without sending a response.'),response]
        self.assertIs(request('POST','https://example.invalid','Groq',self.context),response)
        self.assertEqual(self.client.request.call_count,2)
        message=self.context.progress.call_args.args[1]
        self.assertIn('Groq',message);self.assertIn('2/3',message)

    def test_transport_exhaustion_is_sanitized_and_automatically_retryable(self):
        for error in [httpx.RemoteProtocolError('private endpoint/token'),httpx.ReadTimeout('private endpoint/token'),httpx.ConnectError('private endpoint/token'),httpx.ProxyError('private endpoint/token')]:
            with self.subTest(error=type(error).__name__):
                self.client.request.reset_mock();self.client.request.side_effect=error
                with self.assertRaises(ProviderError) as caught:request('POST','https://example.invalid','Groq',self.context)
                self.assertEqual(self.client.request.call_count,3)
                self.assertIsNone(caught.exception.status)
                self.assertIn('Groq',str(caught.exception));self.assertNotIn('private',str(caught.exception))
                row={'attempts':0}
                with patch('backend.automation.put'),patch('backend.automation.time.time',return_value=100):failure(row,caught.exception)
                self.assertEqual(row['state'],'retry_wait');self.assertEqual(row['retry_at'],130)

    def test_auth_and_invalid_requests_do_not_retry_or_expose_response(self):
        self.client.request.return_value=httpx.Response(401,text='private credential')
        with self.assertRaises(ProviderError) as caught:request('POST','https://example.invalid','Groq',self.context)
        self.assertEqual(caught.exception.status,401)
        self.assertEqual(self.client.request.call_count,1);self.assertNotIn('private',str(caught.exception))
        self.client.request.reset_mock();self.client.request.side_effect=httpx.LocalProtocolError('invalid request')
        with self.assertRaises(httpx.LocalProtocolError):request('POST','https://example.invalid','Groq')
        self.assertEqual(self.client.request.call_count,1)

    def test_cancel_during_backoff_stops_before_second_request(self):
        self.client.request.side_effect=httpx.RemoteProtocolError('disconnected')
        self.context.check.side_effect=[None,Cancelled()]
        with self.assertRaises(Cancelled):request('POST','https://example.invalid','Groq',self.context)
        self.assertEqual(self.client.request.call_count,1)

    def test_http_rate_limit_still_recovers_with_bounded_attempts(self):
        response=httpx.Response(200,json={'ok':True})
        self.client.request.side_effect=[httpx.Response(429),httpx.Response(503),response]
        self.assertIs(request('POST','https://example.invalid','Vilao',self.context),response)
        self.assertEqual(self.client.request.call_count,3)

    def test_stt_resume_keeps_source_and_reuses_committed_response(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'audio').mkdir();(folder/'source.mp4').write_bytes(b'original source')
            (folder/'audio/000.flac').write_bytes(b'extracted audio')
            project={'source_file':'source.mp4','metadata':{'duration':2},'options':{'language':'auto'}}
            context=Mock();context.folder=folder
            self.client.request.side_effect=httpx.RemoteProtocolError('disconnected')
            with patch('backend.providers.settings',return_value={'GROQ_API_KEY':'unit-test-placeholder'}),patch('backend.providers.ffmpeg'):
                with self.assertRaises(ProviderError):transcribe(project,context)
                self.assertFalse((folder/'transcript.json').exists())
                self.client.request.side_effect=None
                self.client.request.return_value=httpx.Response(200,json={'words':[{'word':'Hello','start':0,'end':1}],'segments':[]})
                result=transcribe(project,context)
                calls=self.client.request.call_count
                self.assertTrue((folder/'audio/000.json').is_file())
                (folder/'transcript.json').unlink()
                self.assertEqual(transcribe(project,context),result)
                self.assertEqual(self.client.request.call_count,calls)
                self.assertEqual((folder/'source.mp4').read_bytes(),b'original source')
                self.assertEqual(json.loads((folder/'transcript.json').read_text(encoding='utf-8')),result)


if __name__=='__main__':unittest.main()
