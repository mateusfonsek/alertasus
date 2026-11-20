"""Implementações falsas do Redis e do RabbitMQ para os testes unitários."""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.config import Config
from app.idempotencia import RegistroIdempotencia
from app.main import create_app
from app.publicador import FalhaPublicacao


class RedisFalso:
    """Subconjunto dos comandos do Redis usados pelo RegistroIdempotencia."""

    def __init__(self) -> None:
        self.dados: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.indisponivel = False

    def _verificar(self) -> None:
        if self.indisponivel:
            raise RedisConnectionError("Redis fora do ar (simulado)")

    async def set(self, name, value, *, ex=None, nx=False, xx=False):
        self._verificar()
        if nx and name in self.dados:
            return None
        if xx and name not in self.dados:
            return None
        self.dados[name] = value
        if ex is not None:
            self.ttls[name] = ex
        return True

    async def get(self, name):
        self._verificar()
        return self.dados.get(name)

    async def delete(self, *names):
        self._verificar()
        removidos = 0
        for name in names:
            removidos += self.dados.pop(name, None) is not None
            self.ttls.pop(name, None)
        return removidos

    async def ping(self):
        self._verificar()
        return True

    async def aclose(self):
        pass


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos = []
        self.falhar = False

    async def publicar(self, evento) -> None:
        if self.falhar:
            raise FalhaPublicacao("broker fora do ar (simulado)")
        self.eventos.append(evento)

    def pronto(self) -> bool:
        return not self.falhar

    async def fechar(self) -> None:
        pass


CONFIG_TESTE = Config(idempotencia_ttl_s=86_400, idempotencia_pendente_ttl_s=30)


@pytest.fixture
def redis_falso() -> RedisFalso:
    return RedisFalso()


@pytest.fixture
def registro(redis_falso) -> RegistroIdempotencia:
    return RegistroIdempotencia(
        redis_falso,
        ttl_s=CONFIG_TESTE.idempotencia_ttl_s,
        pendente_ttl_s=CONFIG_TESTE.idempotencia_pendente_ttl_s,
    )


@pytest.fixture
def publicador() -> PublicadorFalso:
    return PublicadorFalso()


@pytest.fixture
def cliente(publicador, registro):
    app = create_app(CONFIG_TESTE, publicador=publicador, registro=registro)
    with TestClient(app) as cliente_http:
        yield cliente_http


@pytest.fixture
def cabecalhos() -> dict:
    return {"X-Consumer-Username": "unidade-001"}


def nova_notificacao(**alteracoes) -> dict:
    """Corpo válido segundo o contrato; alterações sobrescrevem campos."""
    hoje = date(2026, 11, 17)
    corpo = {
        "notificacao_id": str(uuid4()),
        "agravo": "dengue",
        "municipio_ibge": "2507507",
        "bairro": "Mangabeira",
        "data_inicio_sintomas": (hoje - timedelta(days=2)).isoformat(),
        "data_notificacao": hoje.isoformat(),
        "enviado_em": datetime(2026, 11, 17, 14, 3, 12, tzinfo=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    corpo.update(alteracoes)
    return corpo
