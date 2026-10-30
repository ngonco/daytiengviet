import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import store
from backend.app import app,Options

class EditApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.patch=patch('backend.store.data_root',return_value=Path(self.tmp.name))
        self.patch.start();store.init()
        self.id='0123456789abcdef'
        self.plan={'captions':[{'id':'c','start':1,'end':3,'vi':'Xin chào.','en':'Hello.','locked':False}],'cuts':[],'visuals':[]}
        store.save({'id':self.id,'metadata':{'duration':10},'options':Options(style='education').model_dump(),'plan':self.plan,'revision':1,'assets':{}})
        self.client=TestClient(app)
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def test_save_and_version_conflict(self):
        body={'revision':1,'plan':self.plan,'options':Options(style='education').model_dump()}
        response=self.client.put(f'/api/projects/{self.id}/plan',json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['revision'],2)
        self.assertTrue((store.folder(self.id)/'versions/v00001.json').exists())
        for job in store.jobs(self.id):store.job_update(job['id'],status='succeeded')
        response=self.client.put(f'/api/projects/{self.id}/plan',json=body)
        self.assertEqual(response.status_code,409)
    def test_cancel_in_progress_still_blocks_edits(self):
        job=store.job_create(self.id,'preview')
        store.job_update(job['id'],status='running')
        response=self.client.post(f"/api/jobs/{job['id']}/cancel")
        self.assertEqual(response.json()['status'],'cancelling')
        response=self.client.put(f'/api/projects/{self.id}/plan',json={'revision':1,'plan':self.plan,'options':Options().model_dump()})
        self.assertEqual(response.status_code,409)
    def test_media_traversal_rejected(self):
        response=self.client.get(f'/api/projects/{self.id}/media/%2E%2E%2F%2E%2E%2F.env')
        self.assertEqual(response.status_code,404)
    def test_retry_converted_project_only_queues_render(self):
        project=store.read(self.id)
        project['options']['layout_mode']='lesson'
        store.save(project)
        response=self.client.post(f'/api/projects/{self.id}/reframe')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['kind'],'preview')
        self.assertEqual(store.read(self.id)['revision'],1)

if __name__=='__main__':unittest.main()
