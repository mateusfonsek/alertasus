"""Executor: ritmo, autenticação e relatório, contra um servidor HTTP falso."""

import asyncio
import json
from collections import Counter

import httpx
import pytest

from simulador.__main__ import main
from simulador.cenarios import gerar
from simulador.executor import Autenticacao, Relatorio, executar


def _cliente_falso(respostas_por_categoria=None, recebidos=None):
    """Responde 202 a ids novos e 200 a ids repetidos, e guarda as requisições."""
    vistos = set()
    recebidos = recebidos if recebidos is not None else []

    def responder(request: httpx.Request) -> httpx.Response:
        corpo = json.loads(request.content)
        recebidos.append((request, corpo))
        notificacao_id = corpo.get("notificacao_id")
        if notificacao_id in vistos:
            return httpx.Response(200, json={"status": "duplicada"})
        vistos.add(notificacao_id)
        return httpx.Response(202, json={"status": "aceita"})

    return httpx.AsyncClient(
        transport=httpx.MockTransport(responder), base_url="http://teste"
    )


def test_modo_direto_envia_cabecalho_da_unidade():
    recebidos = []
    envios = gerar("normal", 20, unidades=3, semente=1)
    cliente = _cliente_falso(recebidos=recebidos)
    relatorio = asyncio.run(
        executar(envios, "http://teste", 1000, Autenticacao(), cliente=cliente)
    )

    assert relatorio.total == 20
    assert relatorio.por_categoria["normal"]["202"] == 20
    request, corpo = recebidos[0]
    assert request.url.path == "/api/v1/notificacoes"
    assert request.headers["X-Consumer-Username"].startswith("unidade-")
    assert "Authorization" not in request.headers
    assert corpo["enviado_em"] is not None  # preenchido na hora do envio


def test_modo_gateway_envia_jwt_da_unidade():
    recebidos = []
    envios = gerar("normal", 10, unidades=2, semente=2)
    tokens = {"unidade-001": "token-1", "unidade-002": "token-2"}
    asyncio.run(
        executar(
            envios,
            "http://teste",
            1000,
            Autenticacao(tokens),
            cliente=_cliente_falso(recebidos=recebidos),
        )
    )
    for request, _ in recebidos:
        assert request.headers["Authorization"] in {"Bearer token-1", "Bearer token-2"}
        assert "X-Consumer-Username" not in request.headers


def test_modo_gateway_exige_token_de_todas_as_unidades():
    envios = gerar("normal", 30, unidades=5, semente=3)
    with pytest.raises(ValueError, match="sem token"):
        asyncio.run(
            executar(
                envios,
                "http://teste",
                1000,
                Autenticacao({"unidade-001": "t"}),
                cliente=_cliente_falso(),
            )
        )


def test_relatorio_do_cenario_de_duplicadas():
    envios = gerar("duplicadas", 30, semente=4)
    relatorio = asyncio.run(
        executar(envios, "http://teste", 1000, Autenticacao(), cliente=_cliente_falso())
    )
    assert relatorio.por_categoria["original"] == {"202": 10}
    assert relatorio.por_categoria["reenvio"] == {"200": 20}
    assert "reenvio" in relatorio.tabela()


def test_reenvio_espera_a_tentativa_anterior_terminar():
    """A primeira tentativa de cada notificação atrasa no caminho (como a que
    abre a conexão); sem a espera, o reenvio seria processado antes e ficaria
    com o 202 no lugar do original."""
    chegadas = Counter()
    vistos = set()

    async def responder(request: httpx.Request) -> httpx.Response:
        notificacao_id = json.loads(request.content)["notificacao_id"]
        chegadas[notificacao_id] += 1
        if chegadas[notificacao_id] == 1:
            await asyncio.sleep(0.05)  # atraso de rede só na primeira tentativa
        if notificacao_id in vistos:
            return httpx.Response(200)
        vistos.add(notificacao_id)
        return httpx.Response(202)

    cliente = httpx.AsyncClient(
        transport=httpx.MockTransport(responder), base_url="http://teste"
    )
    envios = gerar("duplicadas", 30, semente=7)
    relatorio = asyncio.run(
        executar(envios, "http://teste", 1000, Autenticacao(), cliente=cliente)
    )
    assert relatorio.por_categoria["original"] == {"202": 10}
    assert relatorio.por_categoria["reenvio"] == {"200": 20}


def test_falha_de_conexao_vira_erro_no_relatorio():
    def recusar(request):
        raise httpx.ConnectError("recusada", request=request)

    cliente = httpx.AsyncClient(transport=httpx.MockTransport(recusar), base_url="http://x")
    envios = gerar("normal", 5, semente=5)
    relatorio = asyncio.run(
        executar(envios, "http://x", 1000, Autenticacao(), cliente=cliente)
    )
    assert relatorio.por_categoria["normal"] == {"erro": 5}


def test_ritmo_respeita_a_taxa():
    envios = gerar("normal", 11, semente=6)
    relatorio = asyncio.run(
        executar(envios, "http://teste", 50, Autenticacao(), cliente=_cliente_falso())
    )
    # 11 envios a 50/s: o último sai em ~0,2 s.
    assert relatorio.duracao_s >= 0.19


def test_percentis():
    relatorio = Relatorio(latencias_s=[i / 1000 for i in range(1, 101)])
    assert relatorio.percentil_ms(50) == 50.0
    assert relatorio.percentil_ms(95) == 95.0
    assert Relatorio().percentil_ms(95) is None


def test_cli_rejeita_taxa_invalida():
    with pytest.raises(SystemExit):
        main(["--taxa", "0"])
