"""PostgreSQL tests with broker I/O mocked; real broker smoke test is documented."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from monitoring.models import Building, Meter, EnergyReading, TelemetryBatch
from monitoring.services.generator import generate_minute, latest_completed_minute
from monitoring.services.kafka_pipeline import (encode_event,decode_event,process_event,
    publish_pending,send,handle_message,RAW_TOPIC)


class KafkaPipelineTests(TestCase):
    def setUp(self):
        self.minute=latest_completed_minute()-timedelta(minutes=2)
        self.building=Building.objects.create(name='Batch test',has_solar_installation=True)
        self.main=Meter.objects.create(building=self.building,device_id='main',meter_type='ELECTRICITY')
        self.solar=Meter.objects.create(building=self.building,device_id='solar',meter_type='SOLAR')
        self.hvac=Meter.objects.create(building=self.building,device_id='hvac',meter_type='HVAC')
        Meter.objects.update(created_at=self.minute-timedelta(days=1))
        generate_minute(self.minute,outbox=True)
        self.batch=TelemetryBatch.objects.get()
        self.raw=encode_event(self.batch.payload)

    def test_stage_only_then_atomic_persistence_and_retry(self):
        self.assertFalse(EnergyReading.objects.exists())
        self.assertEqual(process_event(self.raw),'created')
        self.assertEqual(EnergyReading.objects.count(),3)
        self.assertEqual(process_event(self.raw),'already_processed')
        # Crash after DB commit / before offset commit still replays after deactivate.
        Meter.objects.filter(pk=self.main.pk).update(is_active=False)
        self.assertEqual(process_event(self.raw),'already_processed')
        self.assertEqual(EnergyReading.objects.count(),3)

    def test_conflict_never_overwrites(self):
        process_event(self.raw)
        payload=json.loads(self.raw);payload['readings'][0]['energy_kwh']+=1
        with self.assertRaises(ValidationError):process_event(encode_event(payload))
        self.assertEqual(EnergyReading.objects.count(),3)

    def test_conflicting_complete_database_set_never_overwritten(self):
        for row in self.batch.payload['readings']:
            EnergyReading.objects.create(meter_id=row['meter_id'],timestamp=self.minute,
                interval_seconds=60,energy_kwh=row['energy_kwh']+1,
                power_kw=row['power_kw'],voltage=row['voltage'])
        original=list(EnergyReading.objects.order_by('pk').values())
        with self.assertRaises(ValidationError): process_event(self.raw)
        self.assertEqual(original,list(EnergyReading.objects.order_by('pk').values()))
        self.batch.refresh_from_db();self.assertIsNone(self.batch.processed_at)

    def test_complete_identical_existing_set_creates_only_receipt(self):
        for row in self.batch.payload['readings']:
            EnergyReading.objects.create(meter_id=row['meter_id'],timestamp=self.minute,
                interval_seconds=60,energy_kwh=row['energy_kwh'],
                power_kw=row['power_kw'],voltage=row['voltage'])
        process_event(self.raw)
        self.assertEqual(EnergyReading.objects.count(),3)
        self.batch.refresh_from_db();self.assertIsNotNone(self.batch.processed_at)

    def test_cross_building_meter_identity_rejected(self):
        other=Building.objects.create(name='Other',has_solar_installation=False)
        foreign=Meter.objects.create(building=other,device_id='foreign',meter_type='ELECTRICITY')
        # Simulate a producer defect; even a matching malformed outbox cannot pass inventory checks.
        payload=json.loads(self.raw)
        payload['readings'][-1].update(meter_id=foreign.pk,device_id=foreign.device_id,meter_type='ELECTRICITY')
        self.batch.payload=payload;self.batch.save(update_fields=['payload'])
        with self.assertRaises(ValidationError):process_event(encode_event(payload))
        self.assertFalse(EnergyReading.objects.exists())

    def test_inventory_change_deactivation_rejects_entire_batch(self):
        Meter.objects.filter(pk=self.solar.pk).update(is_active=False)
        with self.assertRaises(ValidationError):process_event(self.raw)
        self.assertFalse(EnergyReading.objects.exists())

    def test_new_active_meter_invalidates_snapshot(self):
        extra=Meter.objects.create(building=self.building,device_id='new',meter_type='LIGHTING')
        Meter.objects.filter(pk=extra.pk).update(created_at=self.minute-timedelta(minutes=1))
        with self.assertRaises(ValidationError):process_event(self.raw)
        self.assertFalse(EnergyReading.objects.exists())

    def test_later_meter_waits_until_eligible_minute(self):
        extra=Meter.objects.create(building=self.building,device_id='later',meter_type='LIGHTING')
        self.assertEqual(process_event(self.raw),'created')
        later=latest_completed_minute()
        Meter.objects.filter(pk=extra.pk).update(created_at=later-timedelta(minutes=1))
        generate_minute(later,outbox=True)
        next_batch=TelemetryBatch.objects.get(timestamp=later)
        self.assertIn(extra.pk,[r['meter_id'] for r in next_batch.payload['readings']])
        process_event(encode_event(next_batch.payload))
        self.assertEqual(extra.readings.count(),1)

    def test_partial_or_overlap_rolls_back_all_rows(self):
        EnergyReading.objects.create(meter=self.solar,timestamp=self.minute-timedelta(minutes=30),
                                     interval_seconds=3600,energy_kwh=2)
        with self.assertRaises(ValidationError):process_event(self.raw)
        self.assertEqual(EnergyReading.objects.count(),1)
        self.batch.refresh_from_db();self.assertIsNone(self.batch.processed_at)

    def test_partial_existing_minute_rejected(self):
        EnergyReading.objects.create(meter=self.main,timestamp=self.minute,interval_seconds=60,energy_kwh=1)
        with self.assertRaises(ValidationError):process_event(self.raw)
        self.assertEqual(EnergyReading.objects.count(),1)

    def test_schema_invalid_variations(self):
        for field,value in [('schema_version',2),('interval_seconds',3600),('building_id',True),
                            ('timestamp','2026-11-12T00:00:01+00:00'),('batch_id','bad'),
                            ('has_solar_installation',None),('readings',[])]:
            with self.subTest(field=field):
                payload=json.loads(self.raw);payload[field]=value
                with self.assertRaises(ValidationError):decode_event(encode_event(payload))
        payload=json.loads(self.raw);payload['readings'][0]['power_kw']='12'
        with self.assertRaises(ValidationError):decode_event(encode_event(payload))
        with self.assertRaises(ValidationError):decode_event(b'{broken')
        with self.assertRaises(ValidationError):decode_event(b'{"a":1,"a":2}')
        with self.assertRaises(ValidationError):decode_event(b'x'*900001)

    def test_unknown_outbox_or_wrong_building_rejected(self):
        self.batch.delete()
        with self.assertRaises(ValidationError):process_event(self.raw)
        self.assertFalse(EnergyReading.objects.exists())

    def test_publish_ack_and_replay_unprocessed(self):
        producer=Mock()
        with patch('monitoring.services.kafka_pipeline.send') as mocked:
            self.assertEqual(publish_pending(producer),1)
            self.assertEqual(publish_pending(producer),1)
            self.assertEqual(mocked.call_args.args[1:3],(RAW_TOPIC,self.building.pk))
        process_event(self.raw)
        with patch('monitoring.services.kafka_pipeline.send') as mocked:
            self.assertEqual(publish_pending(producer),0)
            mocked.assert_not_called()

    def test_publish_failure_leaves_durable_batch(self):
        with patch('monitoring.services.kafka_pipeline.send',side_effect=RuntimeError('broker down')):
            with self.assertRaises(RuntimeError):publish_pending(Mock())
        self.batch.refresh_from_db()
        self.assertIsNone(self.batch.published_at)
        self.assertIsNone(self.batch.processed_at)
        self.assertEqual(TelemetryBatch.objects.count(),1)

    def test_delivery_ack_required(self):
        producer=Mock();producer.flush.return_value=0
        producer.produce.side_effect=lambda *a,**kw: kw['on_delivery'](None,Mock())
        send(producer,RAW_TOPIC,1,b'{}')
        producer.produce.side_effect=lambda *a,**kw: kw['on_delivery']('unavailable',Mock())
        with self.assertRaises(RuntimeError):send(producer,RAW_TOPIC,1,b'{}')

    def test_offset_commit_after_success_and_acknowledged_deadletter(self):
        consumer=Mock();producer=Mock();message=Mock()
        message.error.return_value=None;message.value.return_value=self.raw
        message.topic.return_value=RAW_TOPIC;message.partition.return_value=0;message.offset.return_value=1
        handle_message(message,consumer,producer)
        consumer.commit.assert_called_once_with(message=message,asynchronous=False)
        message.value.return_value=b'broken';consumer.reset_mock()
        with patch('monitoring.services.kafka_pipeline.send') as delivery:
            handle_message(message,consumer,producer)
            delivery.assert_called_once()
        consumer.commit.assert_called_once()
        consumer.reset_mock()
        with patch('monitoring.services.kafka_pipeline.send',side_effect=RuntimeError('no broker')):
            with self.assertRaises(RuntimeError):handle_message(message,consumer,producer)
        consumer.commit.assert_not_called()

    def test_transient_database_error_does_not_commit(self):
        from django.db import OperationalError
        consumer=Mock();message=Mock();message.error.return_value=None
        with patch('monitoring.services.kafka_pipeline.process_event',side_effect=OperationalError('offline')):
            with self.assertRaises(OperationalError):handle_message(message,consumer,Mock())
        consumer.commit.assert_not_called()

    def test_permanent_rejection_not_republished(self):
        Meter.objects.filter(pk=self.main.pk).update(is_active=False)
        message=Mock();message.value.return_value=self.raw;message.error.return_value=None
        message.topic.return_value=RAW_TOPIC;message.partition.return_value=0;message.offset.return_value=1
        with patch('monitoring.services.kafka_pipeline.send'):
            handle_message(message,Mock(),Mock())
        self.batch.refresh_from_db();self.assertIsNotNone(self.batch.rejected_at)
        self.assertEqual(publish_pending(Mock()),0)

    def test_frozen_snapshot_retry_is_not_recalculated(self):
        Meter.objects.filter(pk=self.hvac.pk).update(is_active=False)
        generate_minute(self.minute,outbox=True)
        self.batch.refresh_from_db();self.assertEqual(encode_event(self.batch.payload),self.raw)


class ConcurrentBatchTests(TransactionTestCase):
    def test_two_consumers_one_atomic_receipt(self):
        minute=latest_completed_minute()-timedelta(minutes=1)
        building=Building.objects.create(name='Concurrent',has_solar_installation=False)
        meter=Meter.objects.create(building=building,device_id='concurrent',meter_type='ELECTRICITY')
        Meter.objects.filter(pk=meter.pk).update(created_at=minute-timedelta(days=1))
        generate_minute(minute,outbox=True)
        raw=encode_event(TelemetryBatch.objects.get().payload)
        def run():
            close_old_connections()
            try:return process_event(raw)
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(lambda _:run(),range(2)))
        self.assertCountEqual(outcomes,['created','already_processed'])
        self.assertEqual(EnergyReading.objects.count(),1)
