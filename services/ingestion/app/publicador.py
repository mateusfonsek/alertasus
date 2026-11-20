"""Publicação dos eventos de notificação no RabbitMQ (exchange fanout)."""

import asyncio
import logging
from datetime import datetime, timezone
from time import perf_counter

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractRobustConnection

from app.contrato import TIPO_EVENTO, EventoNotificacao
from app.metricas import PUBLICACAO_SEGUNDOS

log = logging.getLogger("alertasus.ingestao.publicador")


class FalhaPublicacao(Exception):
    """O broker não confirmou a publicação (indisponível, timeout ou sem fila)."""


def montar_mensagem(evento: EventoNotificacao) -> aio_pika.Message:
    """Mensagem AMQP conforme a seção 2.2 do contrato."""
    return aio_pika.Message(
        body=evento.model_dump_json().encode("utf-8"),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        message_id=str(evento.notificacao_id),
        type=TIPO_EVENTO,
        timestamp=datetime.now(timezone.utc),
    )


class PublicadorRabbitMQ:
    def __init__(self, url: str, exchange: str, timeout_s: float) -> None:
        self._url = url
        self._nome_exchange = exchange
        self._timeout_s = timeout_s
        self._conexao: AbstractRobustConnection | None = None
        self._exchange: AbstractExchange | None = None

    async def conectar(self, tentativas: int, intervalo_s: float) -> None:
        """Conecta com novas tentativas; depois disso, a reconexão é automática."""
        for tentativa in range(1, tentativas + 1):
            try:
                self._conexao = await aio_pika.connect_robust(self._url)
                break
            except (aio_pika.exceptions.AMQPConnectionError, OSError) as erro:
                if tentativa == tentativas:
                    raise
                log.warning(
                    "RabbitMQ indisponível; nova tentativa",
                    extra={"contexto": {"tentativa": tentativa, "erro": str(erro)}},
                )
                await asyncio.sleep(intervalo_s)

        # publisher confirms + on_return_raises: a publicação só é considerada
        # concluída quando o broker confirma, e uma mensagem que não chega a
        # nenhuma fila (mandatory) vira erro em vez de ser descartada em silêncio.
        canal = await self._conexao.channel(
            publisher_confirms=True, on_return_raises=True
        )
        self._exchange = await canal.declare_exchange(
            self._nome_exchange, aio_pika.ExchangeType.FANOUT, durable=True
        )

    async def publicar(self, evento: EventoNotificacao) -> None:
        if self._exchange is None:
            raise FalhaPublicacao("publicador não conectado ao RabbitMQ")
        inicio = perf_counter()
        try:
            await asyncio.wait_for(
                self._exchange.publish(
                    montar_mensagem(evento), routing_key="", mandatory=True
                ),
                timeout=self._timeout_s,
            )
        except Exception as erro:  # qualquer falha vira 503 para a unidade
            raise FalhaPublicacao(f"{type(erro).__name__}: {erro}") from erro
        finally:
            PUBLICACAO_SEGUNDOS.observe(perf_counter() - inicio)

    def pronto(self) -> bool:
        return (
            self._conexao is not None
            and not self._conexao.is_closed
            and self._exchange is not None
        )

    async def fechar(self) -> None:
        if self._conexao is not None:
            await self._conexao.close()
