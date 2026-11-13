"""Dashboard interaction tests: python -m unittest discover -s frontend -p 'test_*.py'."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, Mock
from streamlit.testing.v1 import AppTest

APP=Path(__file__).with_name('app.py')


class DashboardTests(TestCase):
    def setUp(self):
        import streamlit as st
        st.cache_resource.clear()
        st.cache_data.clear()
        self.buildings=[]
        self.meters=[]
        self.users=[{'id':1,'username':'admin','email':'admin@test.com','is_staff':True,'date_joined':'2026-01-01'}]
        self.posts=[]
        self.tariffs=[]
        self.cost=None
        self.alerts=[]
        self.scenario_result={'available':False,'reason':'coverage_incomplete'}
        self.simulate_api_error=False
        self.mock=patch('requests.request',side_effect=self.request)
        self.mock.start();self.addCleanup(self.mock.stop)

    def request(self,method,url,**kwargs):
        response=Mock();response.status_code=200
        if method=='POST':
            self.posts.append((url,kwargs['json']))
            if self.simulate_api_error:
                response.status_code=400;data={'device_id':['Already exists.']}
            elif url.endswith('/auth/token/'):
                data={'access':'jwt-test-access-token','refresh':'jwt-test-refresh-token'}
            elif url.endswith('/buildings/'):
                data=dict(id=2,meters=[],**kwargs['json']);self.buildings.append(data)
            elif url.endswith('/scenarios/'):
                data=self.scenario_result
            elif url.endswith('/accounts/users/'):
                data=dict(id=2,**kwargs['json'])
            else:
                data=dict(id=2,meter_type_display=kwargs['json'].get('meter_type', ''),**kwargs['json'])
                self.meters.append(data)
        elif method=='PATCH':
            self.posts.append((url,kwargs['json']));data={}
            if '/meters/' in url:self.meters[0].update(kwargs['json'])
        elif method=='DELETE':
            self.posts.append((url,{}))
            response.status_code=204
            response.json.side_effect=ValueError("No JSON")
            return response
        elif url.endswith('/accounts/me/'):
            data={'id':1,'username':'admin','email':'admin@test.com','is_staff':True}
        elif url.endswith('/buildings/'):
            data={'results':self.buildings,'next':None}
        elif url.endswith('/meters/'):
            data={'results':self.meters,'next':None}
        elif url.endswith('/accounts/users/'):
            data={'results':self.users,'next':None}
        elif url.endswith('/tariffs/'):
            data={'results':self.tariffs,'next':None}
        elif url.endswith('/cost/') and self.cost is not None:
            data=self.cost
        elif url.endswith('/alerts/'):
            data={'results':self.alerts,'next':None}
        elif url.endswith('/summary/'):
            data={'total_consumption_kwh':None,'total_solar_generated_kwh':None,'peak_demand_kw':None,
                  'total_readings_count':0,'main_data_available':False,'main_data_reason':'no_readings',
                  'latest_reading':None,'active_meters_count':0}
        else:data=[]
        response.json.return_value=data
        return response

    def app(self,page):
        app=AppTest.from_file(str(APP),default_timeout=30)
        app.session_state['auth_token']='mock-jwt-token'
        app.session_state['auth_user']={'username':'testadmin'}
        app.run()
        if page and page != "Overview":
            target_hash = [h for h, info in app._registered_pages.items() if info['page_name'] == page][0]
            app._page_hash = target_hash
            app.run()
        self.assertFalse(app.exception)
        return app

    def test_unauthenticated_session_shows_login_screen(self):
        app=AppTest.from_file(str(APP),default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Smart Energy' in str(t.value) for t in app.title))
        self.assertEqual(len(app.form), 1)
        self.assertEqual(len(app.text_input), 2)

    def test_session_restored_from_query_params_on_page_reload(self):
        app = AppTest.from_file(str(APP),default_timeout=30).run()
        app.text_input[0].set_value('admin')
        app.text_input[1].set_value('admin123')
        next(b for b in app.button if b.label == 'Log In').click().run()
        self.assertFalse(app.exception)
        sid = app.query_params.get('sid')
        self.assertTrue(sid)
        token = app.session_state.get('auth_token')
        self.assertTrue(token)

        reloaded_app = AppTest.from_file(str(APP),default_timeout=30)
        reloaded_app.query_params['sid'] = sid
        reloaded_app.run()
        self.assertFalse(reloaded_app.exception)
        self.assertEqual(reloaded_app.session_state.get('auth_token'), token)
        self.assertEqual(len(reloaded_app.form), 0)
        self.assertTrue(any(b.label == 'Log out' for b in reloaded_app.button))

    def test_session_restored_on_tab_reload_even_without_query_params(self):
        app = AppTest.from_file(str(APP),default_timeout=30).run()
        app.text_input[0].set_value('admin')
        app.text_input[1].set_value('admin123')
        next(b for b in app.button if b.label == 'Log In').click().run()
        self.assertFalse(app.exception)
        token = app.session_state.get('auth_token')

        # Simulate F5 on tabbed page without sid in URL
        tab_reloaded_app = AppTest.from_file(str(APP),default_timeout=30)
        tab_reloaded_app.run()
        self.assertFalse(tab_reloaded_app.exception)
        self.assertEqual(tab_reloaded_app.session_state.get('auth_token'), token)
        self.assertEqual(len(tab_reloaded_app.form), 0)
        self.assertTrue(any(b.label == 'Log out' for b in tab_reloaded_app.button))

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
        self.simulate_api_error=True
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

    TARIFF=dict(id=1,name='Demo',is_active=True,rate_standard_eur_per_kwh=0.3,rate_peak_eur_per_kwh=0.4,
                peak_start_hour=9,peak_end_hour=17,solar_feed_in_eur_per_kwh=0.08)

    def test_scenario_without_tariff_explains_next_step(self):
        self.inventory();app=self.app('Scenarios')
        self.assertTrue(app.warning)
        self.assertFalse([p for p in self.posts if p[0].endswith('/scenarios/')])

    def test_scenario_runs_immediately_with_simple_default(self):
        self.inventory();self.tariffs=[self.TARIFF];app=self.app('Scenarios')
        body=self.posts[-1][1]
        self.assertEqual(body['consumption_change_pct'],-10)
        self.assertNotIn('period_start',body)
        self.assertNotIn('tariff',body)
        self.assertTrue(any('missing measurements' in w.value for w in app.warning))

    def test_more_solar_idea_sends_solar_change(self):
        self.inventory();self.tariffs=[self.TARIFF];app=self.app('Scenarios')
        app.segmented_control(key='sc_idea').set_value('Get more solar power').run()
        self.assertFalse(app.exception)
        body=self.posts[-1][1]
        self.assertEqual((body['consumption_change_pct'],body['solar_change_pct']),(0,20))

    def test_cheaper_tariff_keeps_active_hours_and_feed_in(self):
        self.inventory();self.tariffs=[self.TARIFF];app=self.app('Scenarios')
        app.segmented_control(key='sc_idea').set_value('Switch to a cheaper tariff').run()
        app.number_input(key='sc_price').set_value(0.2).run()
        tariff=self.posts[-1][1]['tariff']
        self.assertEqual((tariff['rate_standard_eur_per_kwh'],tariff['rate_peak_eur_per_kwh']),(0.2,0.2))
        self.assertEqual((tariff['peak_start_hour'],tariff['peak_end_hour']),(9,17))
        self.assertEqual(tariff['solar_feed_in_eur_per_kwh'],0.08)

    def test_scenario_result_is_explained_in_plain_words(self):
        self.inventory();self.tariffs=[self.TARIFF]
        self.scenario_result={'available':True,'reason':'available','difference_net_cost_eur':-12.5,
            'baseline':{'net_cost_eur':100.0},'scenario':{'net_cost_eur':87.5}}
        app=self.app('Scenarios')
        self.assertTrue(any('saved 12.50 EUR' in s.value and '% of your bill' in s.value for s in app.success))

    def test_scenario_custom_dates_are_sent(self):
        self.inventory();self.tariffs=[self.TARIFF];app=self.app('Scenarios')
        app.segmented_control(key='sc_mode').set_value('Choose dates').run()
        self.assertFalse(app.exception)
        self.assertIn('period_start',self.posts[-1][1])
        self.assertIn('period_end',self.posts[-1][1])

    def test_costs_page_guides_user_without_tariff(self):
        self.inventory();app=self.app('Costs')
        self.assertTrue(any('electricity price' in i.proto.title.lower() for i in app.info))
        next(b for b in app.button if b.label=='Save price').click().run()
        self.assertFalse(app.exception)
        url,body=self.posts[-1]
        self.assertTrue(url.endswith('/tariffs/'))
        self.assertTrue(body['is_active'])
        self.assertEqual(body['rate_standard_eur_per_kwh'],body['rate_peak_eur_per_kwh'])

    def test_costs_page_shows_total_and_breakdown(self):
        self.inventory();self.tariffs=[self.TARIFF]
        self.cost={'cost_estimates_available':True,'estimated_net_cost_eur':491.48,'estimated_import_cost_eur':491.97,
                   'estimated_export_credit_eur':0.49,'estimated_grid_import_kwh':1639.9,'estimated_grid_export_kwh':6.2}
        app=self.app('Costs')
        self.assertFalse(app.exception)
        self.assertTrue(any('491.48 EUR' in m.value for m in app.markdown))

    def test_changing_price_switches_off_old_tariff(self):
        self.inventory();self.tariffs=[self.TARIFF];app=self.app('Costs')
        app.number_input(key='tf_price').set_value(0.25).run()
        next(b for b in app.button if b.label=='Save price').click().run()
        self.assertFalse(app.exception)
        created=[b for u,b in self.posts if u.endswith('/tariffs/')][-1]
        self.assertFalse(created['is_active'])
        patches=[(u,b) for u,b in self.posts if '/tariffs/' in u and not u.endswith('/tariffs/')]
        self.assertEqual(patches[0],(patches[0][0],{'is_active':False}))
        self.assertTrue(patches[0][0].endswith('/tariffs/1/'))
        self.assertEqual(patches[-1][1],{'is_active':True})

    def test_alerts_page_explains_and_resolves(self):
        self.inventory()
        self.alerts=[dict(id=5,severity='CRITICAL',alert_type='METER_OFFLINE',alert_type_display='Meter offline',
                          message='No reading from meter M1 for 30 minutes.',is_resolved=False,created_at='2026-11-01T10:00:00Z')]
        app=self.app('Alerts')
        self.assertFalse(app.exception)
        next(b for b in app.button if b.label=='Mark resolved').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.posts[-1][1],{'is_resolved':True})

    def test_duplicate_names_have_distinct_labels(self):
        self.inventory();self.buildings.append(dict(self.buildings[0],id=2))
        app=self.app('Building Management')
        self.assertEqual(len(app.sidebar.selectbox[0].options),2)
        self.assertNotEqual(*app.sidebar.selectbox[0].options)

    def test_team_management_lists_members_and_adds_member(self):
        app=self.app('Team Management')
        self.assertFalse(app.exception)
        app.text_input[0].set_value('prof_evaluator')
        app.text_input[1].set_value('prof@fh.de')
        app.text_input[2].set_value('temp_pass_123')
        app.text_input[3].set_value('Prof')
        next(b for b in app.button if b.label=='Add Member').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.posts[-1][1]['username'],'prof_evaluator')
        self.assertEqual(self.posts[-1][1]['password'],'temp_pass_123')

    def test_team_management_deletes_member_with_confirmation(self):
        self.users.append({'id':2,'username':'colleague','email':'c@test.com','is_staff':False,'date_joined':'2026-01-01'})
        app=self.app('Team Management')
        app.session_state['auth_user']={'username':'admin'}
        app.run()
        self.assertFalse(app.exception)
        del_btn = next(b for b in app.button if b.label=='Delete')
        del_btn.click().run()
        self.assertFalse(app.exception)
        yes_btn = next(b for b in app.button if b.label=='Yes')
        yes_btn.click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('/accounts/users/2/' in p[0] for p in self.posts))
