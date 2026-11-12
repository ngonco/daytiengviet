import json
import unittest
import io
from unittest.mock import patch,Mock
from scripts import restart_vietcut as restart


class RestartTests(unittest.TestCase):
    def row(self,path=None):
        return {'pid':123,'name':'pythonw.exe','created':'1234560','command':'"pythonw.exe" "'+str(path or restart.ROOT/'launch_vietcut.pyw')+'"'}

    def test_exact_workspace_ownership(self):
        self.assertTrue(restart.owned(self.row()))
        self.assertTrue(restart.owned(self.row(restart.ROOT/'start.py')))
        self.assertFalse(restart.owned(self.row(restart.ROOT.parent/'other'/'launch_vietcut.pyw')))
        self.assertFalse(restart.owned(self.row(str(restart.ROOT/'launch_vietcut.pyw')+'.other')))
        self.assertFalse(restart.owned({**self.row(),'name':'other.exe'}))
        self.assertFalse(restart.owned({**self.row(),'command':'python start.py'}))
        self.assertFalse(restart.owned({**self.row(),'created':None}))
        self.assertFalse(restart.owned({**self.row(),'command':'python.exe other.py "'+str(restart.ROOT/'launch_vietcut.pyw')+'"'}))
        self.assertFalse(restart.owned({**self.row(),'command':'python.exe -c "'+str(restart.ROOT/'launch_vietcut.pyw')+'"'}))

    def test_old_health_version_is_not_accepted_as_restarted(self):
        opener=Mock();opener.open.return_value=io.BytesIO(b'{"app":"vietcut","version":"1.5.1"}')
        with patch.object(restart.urllib.request,'build_opener',return_value=opener),patch.object(restart.time,'monotonic',side_effect=[0,1,46]),patch.object(restart.time,'sleep'):
            self.assertFalse(restart.ready(8876))

    def test_current_editor_marker_required(self):
        for marker,expected in [(1,False),(2,False),(3,True)]:
            opener=Mock();opener.open.return_value=io.BytesIO(json.dumps({'app':'vietcut','version':'1.5.3','provider_retry_version':1,'assembly_editor_version':marker}).encode())
            with patch.object(restart.urllib.request,'build_opener',return_value=opener),patch.object(restart.time,'monotonic',side_effect=[0,1,46]),patch.object(restart.time,'sleep'):
                self.assertEqual(restart.ready(8876),expected)

    def test_busy_jobs_never_stop_or_launch(self):
        with patch.object(restart,'busy',return_value=True),patch.object(restart,'owners') as owners,patch.object(restart,'stop_verified') as stop,patch.object(restart,'launch') as launch:
            with self.assertRaises(RuntimeError):restart.restart()
            owners.assert_not_called();stop.assert_not_called();launch.assert_not_called()

    def test_other_owner_refuses_all_before_any_stop(self):
        with patch.object(restart,'busy',return_value=False),patch.object(restart,'settings',return_value={'APP_PORT':'8876'}),patch.object(restart,'owners',return_value=[self.row(),{**self.row(),'name':'other.exe'}]),patch.object(restart,'stop_verified') as stop,patch.object(restart,'launch') as launch:
            with self.assertRaises(RuntimeError):restart.restart()
            stop.assert_not_called();launch.assert_not_called()

    def test_verified_idle_owner_is_restarted_and_new_version_checked(self):
        row=self.row()
        with patch.object(restart,'busy',return_value=False),patch.object(restart,'settings',return_value={'APP_PORT':'8876'}),patch.object(restart,'owners',return_value=[row]),patch.object(restart,'stop_verified') as stop,patch.object(restart,'launch') as launch,patch.object(restart,'ready',return_value=True) as ready:
            restart.restart();stop.assert_called_once_with(row);launch.assert_called_once();ready.assert_called_once_with(8876)

    def test_job_starting_during_lookup_blocks_restart(self):
        with patch.object(restart,'busy',side_effect=[False,True]),patch.object(restart,'settings',return_value={'APP_PORT':'8876'}),patch.object(restart,'owners',return_value=[self.row()]),patch.object(restart,'stop_verified') as stop:
            with self.assertRaises(RuntimeError):restart.restart()
            stop.assert_not_called()


if __name__=='__main__':unittest.main()
