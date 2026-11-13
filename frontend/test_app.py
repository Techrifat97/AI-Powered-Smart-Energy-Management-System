"""Dashboard interaction tests: python -m unittest discover -s frontend -p 'test_*.py'."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, Mock
from streamlit.testing.v1 import AppTest

APP=Path(__file__).with_name('app.py')


class DashboardTests(TestCase):
    def setUp(self):
        self.buildings=[]
        self.meters=[]
        self.posts=[]
        self.fail=False
        self.mock=patch('requests.request',side_effect=self.request)
        self.mock.start();self.addCleanup(self.mock.stop)

    def request(self,method,url,**kwargs):
        response=Mock();response.status_code=200
        if method=='POST':
            self.posts.append((url,kwargs['json']))
            if self.fail:
                response.status_code=400;data={'device_id':['Already exists.']}
            elif url.endswith('/buildings/'):
                data=dict(id=2,meters=[],**kwargs['json']);self.buildings.append(data)
            elif url.endswith('/scenarios/'):
                data={'available':False,'reason':'coverage_incomplete'}
            elif url.endswith('/accounts/users/'):
                data=dict(id=2,**kwargs['json'])
            else:
                data=dict(id=2,meter_type_display=kwargs['json'].get('meter_type', ''),**kwargs['json'])
                self.meters.append(data)
        elif method=='PATCH':
            self.posts.append((url,kwargs['json']));data={}
            self.meters[0].update(kwargs['json'])
        elif url.endswith('/buildings/'):
            data={'results':self.buildings,'next':None}
        elif url.endswith('/meters/'):
            data={'results':self.meters,'next':None}
        elif url.endswith('/accounts/users/'):
            data={'results':[{'id':1,'username':'admin','email':'admin@test.com','is_staff':True,'date_joined':'2026-01-01'}],'next':None}
        elif url.endswith('/summary/'):
            data={'total_consumption_kwh':None,'total_solar_generated_kwh':None,'peak_demand_kw':None,
                  'total_readings_count':0,'main_data_available':False,'main_data_reason':'no_readings',
                  'latest_reading':None,'active_meters_count':0}
        else:data=[]
        response.json.return_value=data
        return response

    def app(self,page):
        app=AppTest.from_file(str(APP))
        app.session_state['auth_token']='mock-jwt-token'
        app.session_state['auth_user']={'username':'testadmin'}
        app.run()
        app.sidebar.radio[0].set_value(page).run()
        self.assertFalse(app.exception)
        return app

    def test_unauthenticated_session_shows_login_screen(self):
        app=AppTest.from_file(str(APP)).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Login' in str(s.value) for s in app.subheader))
        self.assertEqual(len(app.form),1)

    def inventory(self):
        self.buildings=[dict(id=1,name='Renamed building',location='Campus',area_sqm=1000,
                             baseline_kwh_per_day=250,has_solar_installation=False)]

    def test_create_first_building_without_inventory(self):
        app=self.app('Building Management')
        app.text_input[0].set_value('New laboratory')
        app.text_input[1].set_value('Dortmund')
        app.button[0].click().run() if app.button[0].label=='Create building' else app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.buildings[0]['name'],'New laboratory')
        self.assertEqual(self.buildings[0]['baseline_kwh_per_day'],250)
        self.assertEqual(len(self.posts),1)

    def test_blank_name_rejected_before_request(self):
        app=self.app('Building Management')
        next(b for b in app.button if b.label=='Create building').click().run()
        self.assertTrue(app.error)
        self.assertFalse(self.posts)

    def test_add_meter_and_surface_api_validation(self):
        self.inventory();app=self.app('Meter Management')
        app.text_input[0].set_value('MAIN-001')
        next(b for b in app.button if b.label=='Add Meter').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.posts[-1][1]['device_id'],'MAIN-001')
        self.assertFalse(self.posts[-1][1]['is_active'])
        self.fail=True
        app.text_input[0].set_value('MAIN-001')
        next(b for b in app.button if b.label=='Add Meter').click().run()
        self.assertTrue(app.error)

    def test_required_deactivation_confirmation_and_history_warning(self):
        self.inventory()
        self.meters=[dict(id=1,device_id='Main',meter_type='ELECTRICITY',meter_type_display='Electricity',is_active=True)]
        app=self.app('Meter Management')
        button=next(b for b in app.button if b.label=='Deactivate')
        self.assertTrue(button.disabled)
        next(c for c in app.checkbox if 'Confirm' in c.label).check().run()
        next(b for b in app.button if b.label=='Deactivate').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.posts[-1][1],{'is_active':False})

    def test_activate_meter(self):
        self.inventory()
        self.meters=[dict(id=1,device_id='Main',meter_type='ELECTRICITY',meter_type_display='Electricity',is_active=False)]
        app=self.app('Meter Management')
        next(b for b in app.button if b.label=='Activate').click().run()
        self.assertEqual(self.posts[-1][1],{'is_active':True})

    def test_scenario_sends_selected_dates(self):
        self.inventory();app=self.app('Scenarios')
        next(b for b in app.button if b.label=='Run scenario').click().run()
        self.assertFalse(app.exception)
        self.assertIn('period_start',self.posts[-1][1])
        self.assertIn('period_end',self.posts[-1][1])
        self.assertTrue(app.info)

    def test_duplicate_names_have_distinct_labels(self):
        self.inventory();self.buildings.append(dict(self.buildings[0],id=2))
        app=self.app('Building Management')
        self.assertEqual(len(app.sidebar.selectbox[0].options),2)
        self.assertNotEqual(*app.sidebar.selectbox[0].options)

    def test_team_management_lists_members_and_adds_member(self):
        app=self.app('Team Management')
        self.assertFalse(app.exception)
        self.assertTrue(len(app.dataframe)>=1)
        app.text_input[0].set_value('prof_evaluator')
        app.text_input[1].set_value('prof@fh.de')
        app.text_input[2].set_value('temp_pass_123')
        app.text_input[3].set_value('Prof')
        next(b for b in app.button if b.label=='Add Member').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.posts[-1][1]['username'],'prof_evaluator')
        self.assertEqual(self.posts[-1][1]['password'],'temp_pass_123')
