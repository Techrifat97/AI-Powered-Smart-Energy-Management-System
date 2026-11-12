"""S1-only at-least-once transport with a durable, atomic building-minute batch.

Database outbox payloads are immutable through this service. A batch is the unit
of Kafka ordering and database commit: never half a building-minute. S2/S3 still
read PostgreSQL. Kafka libraries are imported lazily for direct-mode tooling.
"""
import json
import os
from datetime import datetime, timedelta
from math import isfinite
from uuid import UUID, uuid5, NAMESPACE_URL

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from monitoring.models import Building, Meter, EnergyReading, TelemetryBatch
from monitoring.services.ingestion import ingest_reading
from monitoring.validators import validate_interval_timestamp

RAW_TOPIC = 'energy.readings.raw'
DEAD_TOPIC = 'energy.readings.dead-letter'
MAX_BYTES = 900_000


def batch_id(building_id, timestamp):
    return uuid5(NAMESPACE_URL, f'smart-energy:v1:{building_id}:{timestamp.isoformat()}')


def encode_event(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def decode_event(raw):
    """Strict schema v1: one complete, ordered building-minute inventory snapshot."""
    def invalid(message):
        raise ValidationError(message)
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        invalid('Event must be bytes within the 900000-byte limit.')
    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                invalid('Duplicate JSON field.')
            obj[key] = value
        return obj
    try:
        event = json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError):
        invalid('Invalid JSON event.')
    fields = {'schema_version', 'batch_id', 'building_id', 'timestamp', 'interval_seconds',
              'has_solar_installation', 'readings'}
    if not isinstance(event, dict) or set(event) != fields or type(event['schema_version']) is not int or event['schema_version'] != 1:
        invalid('Unsupported event schema/version.')
    if type(event['building_id']) is not int or event['building_id'] <= 0:
        invalid('Invalid building identifier.')
    if type(event['interval_seconds']) is not int or event['interval_seconds'] != 60:
        invalid('Telemetry duration must be 60 seconds.')
    if type(event['has_solar_installation']) is not bool:
        invalid('Explicit solar installation metadata is required.')
    try:
        timestamp = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        validate_interval_timestamp(timestamp)
        if event['timestamp'] != timestamp.isoformat():
            invalid('Timestamp must use canonical UTC ISO format (+00:00).')
        if UUID(event['batch_id']) != batch_id(event['building_id'], timestamp):
            invalid('Batch identifier does not match building/minute.')
    except (ValueError, TypeError, AttributeError, OverflowError):
        invalid('Invalid timestamp or batch identifier.')
    readings = event['readings']
    if not isinstance(readings, list) or not readings:
        invalid('A batch needs meter readings.')
    row_fields = {'meter_id','device_id','meter_type','energy_kwh','power_kw','voltage'}
    seen = []
    for row in readings:
        if not isinstance(row, dict) or set(row) != row_fields:
            invalid('Invalid reading fields.')
        if type(row['meter_id']) is not int or row['meter_id'] <= 0:
            invalid('Invalid meter identifier.')
        if not isinstance(row['device_id'],str) or not row['device_id'] or row['meter_type'] not in ('ELECTRICITY','HVAC','LIGHTING','SOLAR'):
            invalid('Invalid meter identity/type.')
        for name in ('energy_kwh','power_kw','voltage'):
            value = row[name]
            try:
                valid = type(value) in (int,float) and isfinite(value) and value >= 0
            except OverflowError:
                valid = False
            if not valid:
                invalid('Measurements must be finite nonnegative numbers.')
        seen.append(row['meter_id'])
    if seen != sorted(set(seen)):
        invalid('Meter identifiers must be unique and ordered.')
    return event, timestamp


def stage_batch(building, minute, plan):
    """Called under generator inventory locks; persist before network publication."""
    payload = dict(schema_version=1, batch_id=str(batch_id(building.pk,minute)),
        building_id=building.pk, timestamp=minute.isoformat(), interval_seconds=60,
        has_solar_installation=building.has_solar_installation, readings=[dict(
            meter_id=p['meter'].pk, device_id=p['meter'].device_id, meter_type=p['meter'].meter_type,
            energy_kwh=p['energy_kwh'],power_kw=p['power_kw'],voltage=p['voltage']) for p in plan])
    decode_event(encode_event(payload))
    batch, created = TelemetryBatch.objects.get_or_create(id=payload['batch_id'], defaults={
        'building':building,'timestamp':minute,'payload':payload})
    if batch.payload != payload:
        raise ValidationError('Frozen batch conflicts with the current inventory or values.')
    return batch, created


def make_producer():
    from confluent_kafka import Producer
    return Producer({'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP_SERVERS','kafka:9092'),
        'enable.idempotence':True, 'acks':'all', 'delivery.timeout.ms':15000,
        'request.timeout.ms':5000, 'message.max.bytes':2000000, 'client.id':'s1-telemetry-producer'})


def send(producer, topic, key, value):
    """Return only after broker acknowledgment; failures leave the outbox pending."""
    errors = []
    delivered = []
    def ack(error, message):
        if error: errors.append(str(error))
        else: delivered.append(True)
    producer.produce(topic, key=key if isinstance(key,bytes) else str(key).encode(), value=value, on_delivery=ack)
    remaining = producer.flush(20)
    if remaining or errors or not delivered:
        raise RuntimeError('Kafka publication was not acknowledged; durable batch remains pending.')


def publish_pending(producer=None):
    """Replay unprocessed outbox rows in time order, including acknowledged rows.

    Re-publication closes the broker-ack/database-mark crash window. It is safe
    through consumer receipts; it does not invent intervals missed in downtime.
    """
    producer = producer or make_producer()
    count = 0
    for batch in TelemetryBatch.objects.filter(processed_at__isnull=True,rejected_at__isnull=True).order_by('timestamp','building_id').iterator():
        send(producer,RAW_TOPIC,batch.building_id,encode_event(batch.payload))
        TelemetryBatch.objects.filter(pk=batch.pk).update(published_at=timezone.now(),last_error='')
        count += 1
    return count


@transaction.atomic
def process_event(raw):
    """Return 'created' or 'already_processed'; validation errors change no readings.

    Lock order matches inventory/generator: building, all meters, then batch.
    Receipt and all readings commit together. Bypassing services bypasses these
    inventory/overlap guarantees, but never the database uniqueness constraint.
    """
    event, minute = decode_event(raw)
    if minute >= timezone.now().replace(second=0,microsecond=0):
        raise ValidationError('Only completed telemetry intervals can be ingested.')
    try:
        building=Building.objects.select_for_update().get(pk=event['building_id'])
    except Building.DoesNotExist:
        raise ValidationError('Building does not exist.') from None
    meters=list(Meter.objects.select_for_update(no_key=True).filter(building=building).order_by('pk'))
    try:
        batch=TelemetryBatch.objects.select_for_update().get(pk=event['batch_id'])
    except TelemetryBatch.DoesNotExist:
        raise ValidationError('No matching durable producer outbox exists.') from None
    if batch.payload != event or batch.building_id != building.pk or batch.timestamp != minute:
        raise ValidationError('Event conflicts with its immutable producer outbox.')
    if batch.processed_at:
        # A committed replay adds nothing, including after a meter deactivation.
        return 'already_processed'
    if batch.rejected_at:
        raise ValidationError('Batch was previously rejected; manual review required.')
    eligible=[m for m in meters if m.is_active and m.created_at <= minute]
    identity=[(m.pk,m.device_id,m.meter_type) for m in eligible]
    received=[(r['meter_id'],r['device_id'],r['meter_type']) for r in event['readings']]
    mains=[m for m in eligible if m.meter_type=='ELECTRICITY']
    solar=[m for m in eligible if m.meter_type=='SOLAR']
    if (identity != received or building.has_solar_installation is not event['has_solar_installation']
            or len(mains)!=1 or (building.has_solar_installation and len(solar)!=1)
            or (not building.has_solar_installation and any(m.meter_type=='SOLAR' for m in meters))):
        raise ValidationError('Inventory changed or is invalid; the entire building-minute is rejected.')
    existing=set(EnergyReading.objects.filter(meter__building=building,timestamp=minute).values_list('meter_id',flat=True))
    if existing and existing != {m.pk for m in eligible}:
        raise ValidationError('Existing building-minute has a partial or changed meter set.')
    for row in event['readings']:
        ingest_reading(row['meter_id'],timestamp=minute,interval_seconds=60,
            energy_kwh=row['energy_kwh'],power_kw=row['power_kw'],voltage=row['voltage'])
    batch.processed_at=timezone.now()
    batch.save(update_fields=['processed_at'])
    return 'created'


def dead_letter(producer, message, error):
    """ACK dead-letter before committing source offset. DLQ can contain duplicates."""
    import base64
    raw=message.value() or b''
    reason='; '.join(error.messages)[:2000]
    envelope=dict(reason=reason, source_topic=message.topic(),partition=message.partition(),
                  offset=message.offset(),raw_base64=base64.b64encode(raw[:MAX_BYTES]).decode(),
                  truncated=len(raw)>MAX_BYTES)
    # Base64 needs a larger DLQ limit than raw. Broker/client configured to 2MB.
    send(producer,DEAD_TOPIC,message.key() or b'invalid',encode_event(envelope))
    try:
        event,_=decode_event(raw)
    except ValidationError:
        return
    # A forged/conflicting payload must never poison the legitimate outbox.
    with transaction.atomic():
        batch=TelemetryBatch.objects.select_for_update().filter(pk=event['batch_id']).first()
        if batch and batch.payload==event and not batch.processed_at:
            batch.rejected_at=timezone.now();batch.last_error=reason
            batch.save(update_fields=['rejected_at','last_error'])


def handle_message(message, consumer, producer):
    """Commit synchronously only after DB success or acknowledged DLQ delivery."""
    if message.error():
        raise RuntimeError('Kafka consumer error: '+str(message.error()))
    try:
        outcome=process_event(message.value())
    except ValidationError as error:
        dead_letter(producer,message,error)
        outcome='dead_lettered: '+'; '.join(error.messages)
    consumer.commit(message=message,asynchronous=False)
    return outcome


def make_consumer():
    from confluent_kafka import Consumer
    return Consumer({'bootstrap.servers':os.environ.get('KAFKA_BOOTSTRAP_SERVERS','kafka:9092'),
        'group.id':os.environ.get('KAFKA_CONSUMER_GROUP','s1-ingestion-v1'),
        'enable.auto.commit':False,'enable.auto.offset.store':False,
        'auto.offset.reset':'earliest','client.id':'s1-ingestion-consumer'})
