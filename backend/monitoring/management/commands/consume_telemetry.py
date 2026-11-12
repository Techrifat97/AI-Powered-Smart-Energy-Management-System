"""Dedicated S1 Kafka ingestion worker with manual offset commits."""
import signal
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from monitoring.services.kafka_pipeline import RAW_TOPIC, make_consumer, make_producer, handle_message


class Command(BaseCommand):
    help = 'Consume synthetic S1 Kafka batches; persist atomically before committing offsets.'

    def handle(self, *args, **options):
        def stop(signum, frame):
            raise KeyboardInterrupt
        previous=signal.signal(signal.SIGTERM,stop)
        consumer=make_consumer()
        producer=make_producer()
        try:
            consumer.subscribe([RAW_TOPIC])
            self.stdout.write('S1 Kafka consumer started; manual offset commits, PostgreSQL source of truth.')
            while True:
                message=consumer.poll(1.0)
                if message is not None:
                    self.stdout.write(f'partition={message.partition()} offset={message.offset()} '+
                                      handle_message(message,consumer,producer))
        except KeyboardInterrupt:
            self.stdout.write('Stopped Kafka consumer.')
        except (RuntimeError,DatabaseError) as error:
            raise CommandError(f'Consumer stopped ({type(error).__name__}); source offset not advanced on failed processing.') from error
        finally:
            consumer.close()
            signal.signal(signal.SIGTERM,previous)
