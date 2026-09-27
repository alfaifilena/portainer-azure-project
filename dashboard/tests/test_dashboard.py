import io
import json
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError
from streamlit.testing.v1 import AppTest


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.busy = False
        self.report = {'checked_at':datetime.now(timezone.utc).isoformat(), 'collection_status':'ok',
            'collector':{'status':'ok'}, 'ai_status':{'status':'on_demand'},
            'telegram_status':{'status':'ready'}, 'notices':[],
            'containers':[{'id':'abc123','name':'demo-web','state':'running','health':'healthy',
                'collection_status':'ok','restart_count':0,'findings':[],'log_sample':[]}]}

    def request(self, request, **kwargs):
        url = request.full_url
        self.calls.append((request.get_method(), url))
        if url.endswith('/login'):
            result = {'token':'test-only','username':'tester'}
        elif '/environments' in url:
            result = {'username':'tester','environments':[{'id':1,'name':'Test environment'}]}
        elif '/report?' in url:
            result = self.report
        elif '/analysis?' in url:
            if self.busy:
                raise HTTPError(url,409,'',{},io.BytesIO(b'{"message":"Another analysis is running. Your request was not saved."}'))
            result = {'job_id':'job-123'}
        elif '/job?' in url:
            result = {'status':'ready','result':{'model':'test','created_at':datetime.now(timezone.utc).isoformat(),
                'output':{'summary':'No confirmed outage.','possible_cause':'No evidence.',
                    'suggested_checks':'Check application responses.','uncertainty':'Bounded sample.'}}}
        else:
            result = {'ok':True}
        return io.BytesIO(json.dumps(result).encode())

    def app(self):
        app = AppTest.from_file(str(Path(__file__).parents[1]/'app.py'), default_timeout=15)
        app.session_state['token']='test-only'
        app.session_state['username']='tester'
        return app

    def test_login_and_logout(self):
        with patch('urllib.request.urlopen',side_effect=self.request):
            app = AppTest.from_file(str(Path(__file__).parents[1]/'app.py'), default_timeout=15).run()
            self.assertFalse(app.exception)
            app.text_input[0].input('tester')
            app.text_input[1].input('password')
            app.button[0].click().run()
            self.assertFalse(app.exception)
            app.button(key='header_sign_out').click().run()
            self.assertFalse(app.exception)
            self.assertEqual([x.label for x in app.text_input],['Username','Password'])
            self.assertTrue(any(url.endswith('/logout') for _,url in self.calls))

    def test_refresh_does_not_analyze_and_click_does(self):
        with patch('urllib.request.urlopen',side_effect=self.request):
            app = self.app().run()
            self.assertFalse(app.exception)
            app.button(key='refresh').click().run()
            self.assertFalse(any('/analysis?' in url for _,url in self.calls))
            app.button(key='analyze:1:abc123').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(sum('/analysis?' in url for _,url in self.calls),1)
            self.assertIn('No confirmed outage.',[x.value for x in app.text])

    def test_busy_does_not_poll_a_saved_job(self):
        self.busy=True
        with patch('urllib.request.urlopen',side_effect=self.request):
            app=self.app().run()
            app.button(key='analyze:1:abc123').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('not saved' in x.value for x in app.error))
            self.assertFalse(any('/job?' in url for _,url in self.calls))

    def test_failed_collection_disables_analysis(self):
        self.report['collection_status']='failed'
        with patch('urllib.request.urlopen',side_effect=self.request):
            app=self.app().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key='analyze:1:abc123').disabled)


if __name__ == '__main__':
    unittest.main()
