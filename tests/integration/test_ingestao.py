"""Integração da Ingestão com Redis e RabbitMQ (T4 do plano de testes)."""

import time

import pytest

from conftest import (
    DATABASE_URL,
    ROTA,
    UNIDADE_ESPERADA,
    cabecalhos_da_unidade,
    nova_notificacao,
)

CAMPOS_DO_EVENTO = {
    "evento_id",
    "tipo",
    "versao",
    "notificacao_id",
    "unidade_id",
    "agravo",
    "municipio_ibge",
    "bairro",
    "semana_epidemiologica",
    "data_inicio_sintomas",
    "data_notificacao",
    "enviado_em",
    "recebido_em",
}


def test_t4_reenvio_nao_gera_novo_evento(ingestao, espia):
    """Mesma notificação enviada 3 vezes: 1×202, 2×200 e um único evento."""
    corpo = nova_notificacao()
    respostas = [
        ingestao.post(ROTA, json=corpo, headers=cabecalhos_da_unidade())
        for _ in range(3)
    ]

    assert [r.status_code for r in respostas] == [202, 200, 200]
    assert respostas[0].json()["status"] == "aceita"
    assert all(r.json()["status"] == "duplicada" for r in respostas[1:])

    eventos = espia.coletar(corpo["notificacao_id"])
    assert len(eventos) == 1


def test_evento_publicado_segue_o_contrato(ingestao, espia):
    corpo = nova_notificacao(data_inicio_sintomas="2026-11-15", data_notificacao="2026-11-17")
    resposta = ingestao.post(ROTA, json=corpo, headers=cabecalhos_da_unidade())
    assert resposta.status_code == 202

    [(propriedades, evento)] = espia.coletar(corpo["notificacao_id"])
    assert set(evento) == CAMPOS_DO_EVENTO
    assert evento["tipo"] == "notificacao.recebida"
    assert evento["versao"] == 1
    assert evento["unidade_id"] == UNIDADE_ESPERADA
    assert evento["semana_epidemiologica"] == "2026-46"
    assert evento["evento_id"] == resposta.json()["evento_id"]
    assert propriedades.message_id == corpo["notificacao_id"]
    assert propriedades.content_type == "application/json"
    assert propriedades.delivery_mode == 2


def test_corpo_fora_do_contrato_nao_e_publicado(ingestao, espia):
    corpo = nova_notificacao(agravo="covid")
    resposta = ingestao.post(ROTA, json=corpo, headers=cabecalhos_da_unidade())
    assert resposta.status_code == 422
    assert espia.coletar(corpo["notificacao_id"], espera_s=1.0) == []


def test_requisicao_sem_identificacao_da_unidade_e_recusada(ingestao):
    resposta = ingestao.post(ROTA, json=nova_notificacao())
    assert resposta.status_code == 401


def test_t4_caso_contado_uma_unica_vez_no_banco(ingestao, espia):
    """Fecha o T4 ponta a ponta quando a Agregação (Frente 3) estiver pronta."""
    psycopg = pytest.importorskip("psycopg")
    try:
        conexao = psycopg.connect(DATABASE_URL, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL fora do ar")
    with conexao:
        existe = conexao.execute("SELECT to_regclass('public.casos')").fetchone()[0]
        if existe is None:
            pytest.skip("tabela casos ainda não existe (Serviço de Agregação pendente)")

        corpo = nova_notificacao()
        for _ in range(3):
            ingestao.post(ROTA, json=corpo, headers=cabecalhos_da_unidade())

        consulta = "SELECT count(*) FROM casos WHERE notificacao_id = %s"
        fim = time.monotonic() + 15
        total = 0
        while time.monotonic() < fim:
            total = conexao.execute(consulta, (corpo["notificacao_id"],)).fetchone()[0]
            if total:
                break
            time.sleep(0.5)
        time.sleep(2)  # dá tempo de uma eventual duplicata aparecer
        total = conexao.execute(consulta, (corpo["notificacao_id"],)).fetchone()[0]
        assert total == 1
