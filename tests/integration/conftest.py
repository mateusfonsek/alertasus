"""Testes de integração: rodam contra o ambiente do Docker Compose em execução.

Variáveis de ambiente (padrões apontam para as portas publicadas no host):

- INGESTAO_URL: Ingestão (modo direto) ou Gateway (com TOKEN_UNIDADE)
- TOKEN_UNIDADE: JWT de uma unidade; se definido, usa o modo Gateway
- UNIDADE_ESPERADA: unidade_id esperado no evento (padrão: unidade-teste)
- RABBITMQ_URL, DATABASE_URL
"""

import json
import os
import time
from datetime import date, datetime, timezone
from uuid import uuid4

import httpx
import pika
import pytest

INGESTAO_URL = os.getenv("INGESTAO_URL", "http://localhost:8001")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://alertasus:alertasus@localhost:5672/")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://alertasus:alertasus@localhost:5432/alertasus"
)
TOKEN_UNIDADE = os.getenv("TOKEN_UNIDADE")
UNIDADE_ESPERADA = os.getenv("UNIDADE_ESPERADA", "unidade-teste")
EXCHANGE = "notificacoes"
ROTA = "/api/v1/notificacoes"


def cabecalhos_da_unidade() -> dict:
    if TOKEN_UNIDADE:
        return {"Authorization": f"Bearer {TOKEN_UNIDADE}"}
    return {"X-Consumer-Username": UNIDADE_ESPERADA}


def nova_notificacao(**alteracoes) -> dict:
    hoje = date.today()
    corpo = {
        "notificacao_id": str(uuid4()),
        "agravo": "dengue",
        "municipio_ibge": "2507507",
        "bairro": "Mangabeira",
        "data_inicio_sintomas": hoje.isoformat(),
        "data_notificacao": hoje.isoformat(),
        "enviado_em": datetime.now(timezone.utc).isoformat(),
    }
    corpo.update(alteracoes)
    return corpo


@pytest.fixture(scope="session")
def ingestao():
    with httpx.Client(base_url=INGESTAO_URL, timeout=10) as cliente:
        try:
            resposta = cliente.get("/ready")
        except httpx.HTTPError:
            pytest.skip(
                f"Ingestão fora do ar em {INGESTAO_URL}. Suba com: docker compose up -d"
            )
        if resposta.status_code != 200:
            pytest.skip(f"Ingestão não está pronta: {resposta.text}")
        yield cliente


class EspiaDeEventos:
    """Fila temporária ligada à exchange: recebe uma cópia de cada evento publicado.

    Como a exchange é fanout, a espiã não interfere nas filas dos consumidores.
    Ela também garante que a publicação (mandatory) tenha ao menos uma fila de
    destino, mesmo antes de a topologia da Frente 2 existir.
    """

    def __init__(self, canal, fila: str) -> None:
        self._canal = canal
        self._fila = fila

    def coletar(self, notificacao_id: str, espera_s: float = 3.0) -> list:
        """Eventos com esse notificacao_id recebidos durante toda a janela."""
        fim = time.monotonic() + espera_s
        encontrados = []
        while time.monotonic() < fim:
            metodo, propriedades, corpo = self._canal.basic_get(self._fila, auto_ack=True)
            if metodo is None:
                time.sleep(0.1)
                continue
            evento = json.loads(corpo)
            if evento.get("notificacao_id") == notificacao_id:
                encontrados.append((propriedades, evento))
        return encontrados


@pytest.fixture
def espia(ingestao):
    try:
        conexao = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    except pika.exceptions.AMQPConnectionError:
        pytest.skip(f"RabbitMQ fora do ar em {RABBITMQ_URL}")
    canal = conexao.channel()
    canal.exchange_declare(EXCHANGE, exchange_type="fanout", durable=True)
    fila = canal.queue_declare("", exclusive=True).method.queue
    canal.queue_bind(fila, EXCHANGE)
    yield EspiaDeEventos(canal, fila)
    conexao.close()
