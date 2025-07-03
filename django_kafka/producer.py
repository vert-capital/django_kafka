import logging
import socket
from types import FunctionType
from typing import Callable, Optional
from uuid import uuid4

from confluent_kafka import Producer
from django.conf import settings

# Configura o logger específico para a sua biblioteca
logger = logging.getLogger(__name__)

# Producer singleton para reutilizar conexões
_producer_instance = None


def get_producer():
    """
    Retorna uma instância singleton do producer para reutilizar conexões.
    Útil para evitar overhead de criação de conexão a cada mensagem.
    """
    global _producer_instance

    if _producer_instance is None:
        conf = {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVER,  # Lista de brokers Kafka para conexão inicial
            "client.id": socket.gethostname(),  # Identificador único do cliente para logs e métricas
            # Configurações otimizadas para reutilização
            "api.version.request.timeout.ms": 60000,  # Timeout para requisições de versão da API (60s)
            "socket.timeout.ms": 60000,  # Timeout para operações de socket (60s)
            "request.timeout.ms": 30000,  # Timeout para requisições gerais (30s)
            "metadata.request.timeout.ms": 30000,  # Timeout para requisições de metadata (30s)
            "retries": 2147483647,  # Número máximo de tentativas de reenvio (valor máximo int32)
            "retry.backoff.ms": 1000,  # Tempo de espera entre tentativas de reenvio (1s)
            "reconnect.backoff.ms": 1000,  # Tempo inicial de espera para reconexão (1s)
            "reconnect.backoff.max.ms": 10000,  # Tempo máximo de espera para reconexão (10s)
            "acks": "all",  # Confirma escrita quando todas as réplicas in-sync recebem a mensagem
            "enable.idempotence": True,  # Garante que mensagens duplicadas sejam evitadas
            "max.in.flight.requests.per.connection": 5,  # Máximo de requisições não confirmadas por conexão
            "batch.size": 16384,  # Tamanho do lote em bytes para envio em batch (16KB)
            "linger.ms": 100,  # Tempo de espera para formar lotes maiores (100ms)
            # "compression.type": "snappy",  # Algoritmo de compressão das mensagens
            "topic.metadata.refresh.interval.ms": 300000,  # Intervalo para atualização de metadata dos tópicos (5min)
            "api.version.request": True,  # Solicita versão da API do broker na conexão
            "broker.version.fallback": "2.8.0",  # Versão fallback caso não consiga detectar a versão do broker
        }

        if hasattr(settings, "KAFKA_SECURITY_PROTOCOL"):
            conf["security.protocol"] = settings.KAFKA_SECURITY_PROTOCOL
        if hasattr(settings, "KAFKA_SASL_MECHANISM"):
            conf["sasl.mechanism"] = settings.KAFKA_SASL_MECHANISM

        _producer_instance = Producer(conf)

    return _producer_instance


def producer(
    topic: str,
    message: str,
    key: Optional[str] = None,
    on_delivery: Optional[Callable] = None,
) -> None:

    if key is None:
        key = str(uuid4())

    headers = {
        "producer_id": settings.KAFKA_CLIENT_ID,
        "hostname": socket.gethostname(),
    }

    producer_instance = get_producer()

    try:
        producer_instance.produce(
            topic,
            key=key,
            value=message,
            on_delivery=on_delivery or delivery_report,
            headers=headers,
        )

        # Poll para processar callbacks de delivery
        producer_instance.poll(0)

    except Exception as e:
        logger.error(f"Erro ao produzir mensagem (persistent): {e}")
        raise


def flush_producer():
    """
    Força o flush do producer persistente.
    Útil para garantir que todas as mensagens foram enviadas.
    """
    global _producer_instance
    if _producer_instance is not None:
        remaining = _producer_instance.flush(timeout=30)
        if remaining > 0:
            logger.warning(f"Ainda há {remaining} mensagens não enviadas após flush")
        return remaining
    return 0


def delivery_report(err, msg):
    """
    Reports the success or failure of a message delivery.
    Args:
        err (KafkaError): The error that occurred on None on success.
        msg (Message): The message that was produced or failed.
    """

    if err is not None:
        logger.error(f"Delivery failed for record {msg.key()}: {err}")
        logger.error(f"Topic: {msg.topic()}, Partition: {msg.partition()}")
        return

    logger.info(
        f"Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}"
    )
