import subprocess
import sys
import time
import unittest
from unittest.mock import Mock,patch
from backend.media import run,MediaStalled,Cancelled
from backend.automation import failure


class MediaProgressTests(unittest.TestCase):
    def launch(self,code,context=None,timeout=.7):
        original=subprocess.Popen;children=[]
        def spawn(*args,**kwargs):
            child=original(*args,**kwargs);children.append(child);return child
        try:
            with patch('backend.media.subprocess.Popen',side_effect=spawn):
                return run([sys.executable,'-u','-c',code],context,progress_timeout=timeout)
        finally:
            self.assertTrue(children)
            self.assertIsNotNone(children[0].poll(),'owned child must not be left running')

    def test_stagnant_repeated_progress_is_killed_and_retryable(self):
        started=time.monotonic()
        with self.assertRaises(MediaStalled) as caught:
            self.launch("import time\nwhile True:\n print('frame=1\\nout_time_us=100000\\nprogress=continue',flush=True)\n time.sleep(.05)")
        self.assertLess(time.monotonic()-started,5)
        row={'attempts':0}
        with patch('backend.automation.put'):failure(row,caught.exception)
        self.assertEqual(row['state'],'retry_wait')

    def test_real_progress_can_run_longer_than_the_stall_threshold(self):
        self.launch("import time\nfor i in range(15):\n print('frame='+str(i)+'\\nout_time_us='+str(i*100000)+'\\nprogress=continue',flush=True)\n time.sleep(.1)")

    def test_cancel_still_terminates_owned_child(self):
        context=Mock();context.check.side_effect=[None,Cancelled()]
        with self.assertRaises(Cancelled):self.launch('import time; time.sleep(20)',context)

    def test_failed_process_preserves_bounded_diagnostic(self):
        with self.assertRaisesRegex(RuntimeError,'test media failure'):
            self.launch("import sys; sys.stderr.write('test media failure'); sys.exit(1)")


if __name__=='__main__':unittest.main()
