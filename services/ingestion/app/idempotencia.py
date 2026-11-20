"""Registro de notificações já vistas, no Redis (primeira camada da idempotência).

Cada notificacao_id passa por dois estados (ADR 0006):

- "pendente": reservado enquanto a publicação no broker está em andamento,
  com prazo curto para não travar o ID se o serviço cair no meio;
- "publicada": o broker confirmou a publicação; reenvios são respondidos
  como duplicados até o prazo longo expirar.

A segunda camada fica nos consumidores, com chave primária em notificacao_id.
"""

from enum import StrEnum
from typing import Protocol
from uuid import UUID

import redis.asyncio as aioredis
from redis.exceptions import RedisError

PENDENTE = "pendente"
PUBLICADA = "publicada"


class Reserva(StrEnum):
    NOVA = "nova"
    DUPLICADA = "duplicada"
    EM_PROCESSAMENTO = "em_processamento"


class ClienteRedis(Protocol):
    async def set(self, name, value, *, ex=None, nx=False, xx=False): ...
    async def get(self, name): ...
    async def delete(self, *names): ...
    async def ping(self): ...
    async def aclose(self): ...


class RegistroIdempotencia:
    def __init__(
        self,
        cliente: ClienteRedis,
        ttl_s: int,
        pendente_ttl_s: int,
        prefixo: str = "alertasus:notificacao:",
    ) -> None:
        self._redis = cliente
        self._ttl_s = ttl_s
        self._pendente_ttl_s = pendente_ttl_s
        self._prefixo = prefixo

    @classmethod
    def do_url(cls, url: str, ttl_s: int, pendente_ttl_s: int) -> "RegistroIdempotencia":
        cliente = aioredis.from_url(
            url,
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
        return cls(cliente, ttl_s, pendente_ttl_s)

    def _chave(self, notificacao_id: UUID) -> str:
        return f"{self._prefixo}{notificacao_id}"

    async def _tentar_reservar(self, chave: str) -> bool:
        return bool(
            await self._redis.set(chave, PENDENTE, ex=self._pendente_ttl_s, nx=True)
        )

    async def reservar(self, notificacao_id: UUID) -> Reserva:
        """Reserva o ID para publicação. Erros do Redis são propagados."""
        chave = self._chave(notificacao_id)
        if await self._tentar_reservar(chave):
            return Reserva.NOVA

        estado = await self._redis.get(chave)
        if estado == PUBLICADA:
            return Reserva.DUPLICADA
        if estado is None:
            # A reserva anterior expirou entre o SET e o GET: tenta de novo uma vez.
            if await self._tentar_reservar(chave):
                return Reserva.NOVA
        return Reserva.EM_PROCESSAMENTO

    async def confirmar(self, notificacao_id: UUID) -> None:
        """Marca o ID como publicado, com o prazo longo."""
        await self._redis.set(self._chave(notificacao_id), PUBLICADA, ex=self._ttl_s)

    async def liberar(self, notificacao_id: UUID) -> None:
        """Desfaz a reserva para que o reenvio da unidade seja aceito."""
        await self._redis.delete(self._chave(notificacao_id))

    async def pronto(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except (RedisError, OSError):
            return False

    async def fechar(self) -> None:
        await self._redis.aclose()
