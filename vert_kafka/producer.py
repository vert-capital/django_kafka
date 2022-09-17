from types import FunctionType
from uuid import uuid4

from confluent_kafka import Producer
from confluent_kafka.serialization import StringSerializer
from django.conf import settings


def producer(
    topic: str, message: str, key: str = None, on_delivery: FunctionType = None
) -> None:

    if key is None:
        string_serializer: StringSerializer = StringSerializer("utf_8")
        key: str = string_serializer(str(uuid4()))

    conf = {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVER,
        "client.id": settings.KAFKA_CLIENT_ID,
    }

    producer = Producer(conf)

    producer.produce(
        topic, key=key, value=message, on_delivery=on_delivery or delivery_report
    )
    producer.flush()


def delivery_report(err, msg):
    """
    Reports the success or failure of a message delivery.
    Args:
        err (KafkaError): The error that occurred on None on success.
        msg (Message): The message that was produced or failed.
    """

    if err is not None:
        print("Delivery failed for User record {}: {}".format(msg.key(), err))
        return
    print(
        "User record {} successfully produced to {} [{}] at offset {}".format(
            msg.key(), msg.topic(), msg.partition(), msg.offset()
        )
    )
