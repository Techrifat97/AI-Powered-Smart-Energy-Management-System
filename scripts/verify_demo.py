"""Acceptance checks with writes: ONLY run against a dedicated disposable demo.

Run: python scripts/verify_demo.py --isolated-api http://127.0.0.1:18000/api
It creates a labeled test building/meters and stored S2/S3 artifacts, deletes
nothing, and waits for real Kafka cycles. Never use against your working demo.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from time import monotonic, sleep
from urllib.request import Request, urlopen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolated-api',required=True,choices=['http://127.0.0.1:18000/api'])
    args=parser.parse_args();api=args.isolated_api
    def request(method,path,body=None):
        req=Request(api+path,data=json.dumps(body).encode() if body is not None else None,
                    headers={'Content-Type':'application/json'},method=method)
        with urlopen(req,timeout=30) as response:return json.load(response)
    buildings=request('GET','/buildings/')['results']
    demo=next(b for b in buildings if b['name']=='Campus Sonnenstraße Dortmund');bid=demo['id']
    summary=request('GET',f'/buildings/{bid}/summary/')
    assert summary['main_data_available'] and summary['grid_estimates_available']
    forecast=request('GET',f'/buildings/{bid}/forecast/')
    assert len(forecast['forecast'])==7
    recs=request('POST','/recommendations/generate/',{'building_id':bid})
    assert recs['availability']['available'] and recs['recommendations']
    assert recs['engine_telemetry']['source']=='RULE_BASED', recs['engine_telemetry']['source']
    cost=request('GET',f'/buildings/{bid}/cost/')
    assert cost['cost_estimates_available']
    yesterday=datetime.now(timezone.utc).date()-timedelta(days=1)
    period={'period_start':str(yesterday-timedelta(days=13)),'period_end':str(yesterday)}
    scenario=request('POST',f'/buildings/{bid}/scenarios/',dict(period,consumption_change_pct=-10))
    assert scenario['available'],scenario
    report=request('POST',f'/buildings/{bid}/reports/',period)
    assert report['total_grid_kwh']>0
    print('PASS: overview, seven-day forecast, rule-based recommendations/assessment, costs, report, dated scenario.',flush=True)
    building=request('POST','/buildings/',{'name':'Isolated Kafka acceptance '+datetime.now(timezone.utc).isoformat(),
        'location':'Synthetic acceptance','area_sqm':1000,'baseline_kwh_per_day':250,'has_solar_installation':False})
    nid=building['id']
    assert request('GET',f'/buildings/{nid}/readings/')['count']==0
    meters=[]
    for kind in ('ELECTRICITY','HVAC'):
        meter=request('POST',f'/buildings/{nid}/meters/',{'device_id':f'ACCEPTANCE-{nid}-{kind}',
                      'meter_type':kind,'unit':'kWh','is_active':False})
        request('PATCH',f"/meters/{meter['id']}/",{'is_active':True});meters.append(meter)
    print(f'Created building={nid}, activated main/HVAC. Waiting for real completed Kafka interval...',flush=True)
    deadline=monotonic()+200
    while monotonic()<deadline:
        history=request('GET',f'/buildings/{nid}/readings/')['results']
        if {r['meter'] for r in history}=={m['id'] for m in meters}:break
        sleep(5)
    else:raise AssertionError('No complete live main/HVAC batch arrived within 200 seconds.')
    main_id,hvac_id=[m['id'] for m in meters]
    old=request('GET',f'/buildings/{nid}/readings/?meter_id={hvac_id}')['count']
    main_before=request('GET',f'/buildings/{nid}/readings/?meter_id={main_id}')['count']
    request('PATCH',f'/meters/{hvac_id}/',{'is_active':False})
    print(f'PASS: Kafka persisted live batch. Deactivated HVAC; verifying main continues and history remains...',flush=True)
    deadline=monotonic()+150
    while monotonic()<deadline:
        main_after=request('GET',f'/buildings/{nid}/readings/?meter_id={main_id}')['count']
        if main_after>main_before:break
        sleep(5)
    else:raise AssertionError('Main did not continue after HVAC deactivation.')
    assert request('GET',f'/buildings/{nid}/readings/?meter_id={hvac_id}')['count']==old
    print('PASS: deactivation retains HVAC history and subsequent main-only Kafka telemetry continues.',flush=True)
    print(json.dumps({'demo_building_id':bid,'management_building_id':nid,'report_id':report['id'],
                      'forecast_days':len(forecast['forecast']),'scenario_available':scenario['available']}),flush=True)


if __name__=='__main__':main()
