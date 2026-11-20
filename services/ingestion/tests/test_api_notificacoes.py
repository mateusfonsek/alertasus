"""POST /api/v1/notificacoes: respostas da seção 1.4 do contrato."""

import asyncio
import json
from uuid import UUID

from app.publicador import montar_mensagem
from tests.conftest import nova_notificacao

ROTA = "/api/v1/notificacoes"


def test_notificacao_nova_e_aceita_e_publicada(cliente, cabecalhos, publicador):
    corpo = nova_notificacao(data_inicio_sintomas="2026-11-15")
    resposta = cliente.post(ROTA, json=corpo, headers=cabecalhos)

    assert resposta.status_code == 202
    dados = resposta.json()
    assert dados["status"] == "aceita"
    assert dados["notificacao_id"] == corpo["notificacao_id"]
    assert dados["semana_epidemiologica"] == "2026-46"

    assert len(publicador.eventos) == 1
    evento = publicador.eventos[0]
    assert str(evento.notificacao_id) == corpo["notificacao_id"]
    assert str(evento.evento_id) == dados["evento_id"]
    assert evento.unidade_id == "unidade-001"


def test_unidade_vem_do_cabecalho_do_gateway(cliente, publicador):
    cliente.post(
        ROTA, json=nova_notificacao(), headers={"X-Consumer-Username": "unidade-042"}
    )
    assert publicador.eventos[0].unidade_id == "unidade-042"


def test_reenvio_e_duplicado_e_nao_publica_de_novo(cliente, cabecalhos, publicador):
    corpo = nova_notificacao()
    respostas = [cliente.post(ROTA, json=corpo, headers=cabecalhos) for _ in range(3)]

    assert [r.status_code for r in respostas] == [202, 200, 200]
    assert respostas[1].json() == {
        "status": "duplicada",
        "notificacao_id": corpo["notificacao_id"],
    }
    assert len(publicador.eventos) == 1


def test_mesmo_id_em_processamento_responde_409(cliente, cabecalhos, registro):
    corpo = nova_notificacao()
    asyncio.run(registro.reservar(UUID(corpo["notificacao_id"])))
    resposta = cliente.post(ROTA, json=corpo, headers=cabecalhos)

    assert resposta.status_code == 409
    assert resposta.json()["status"] == "em_processamento"
    assert resposta.headers["Retry-After"] == "5"


def test_sem_cabecalho_da_unidade_responde_401(cliente, publicador):
    resposta = cliente.post(ROTA, json=nova_notificacao())
    assert resposta.status_code == 401
    assert publicador.eventos == []


def test_cabecalho_em_branco_responde_401(cliente):
    resposta = cliente.post(
        ROTA, json=nova_notificacao(), headers={"X-Consumer-Username": "  "}
    )
    assert resposta.status_code == 401


def test_corpo_fora_do_contrato_responde_422(cliente, cabecalhos, publicador):
    resposta = cliente.post(
        ROTA, json=nova_notificacao(agravo="covid"), headers=cabecalhos
    )
    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["loc"] == ["body", "agravo"]
    assert publicador.eventos == []


def test_json_malformado_responde_422(cliente, cabecalhos):
    resposta = cliente.post(
        ROTA,
        content=b'{"notificacao_id": ',
        headers={**cabecalhos, "Content-Type": "application/json"},
    )
    assert resposta.status_code == 422


def test_falha_no_broker_responde_503_e_libera_o_id(cliente, cabecalhos, publicador):
    corpo = nova_notificacao()
    publicador.falhar = True
    resposta = cliente.post(ROTA, json=corpo, headers=cabecalhos)

    assert resposta.status_code == 503
    assert resposta.headers["Retry-After"] == "5"

    # O reenvio da unidade, com o broker de volta, deve ser aceito.
    publicador.falhar = False
    resposta = cliente.post(ROTA, json=corpo, headers=cabecalhos)
    assert resposta.status_code == 202
    assert len(publicador.eventos) == 1


def test_redis_fora_do_ar_aceita_sem_verificar_reenvio(
    cliente, cabecalhos, publicador, redis_falso
):
    """Fail-open: sem Redis, aceita e publica; os consumidores deduplicam."""
    redis_falso.indisponivel = True
    corpo = nova_notificacao()
    respostas = [cliente.post(ROTA, json=corpo, headers=cabecalhos) for _ in range(2)]

    assert [r.status_code for r in respostas] == [202, 202]
    assert len(publicador.eventos) == 2
    assert publicador.eventos[0].notificacao_id == publicador.eventos[1].notificacao_id


def test_contadores_de_resultado(cliente, cabecalhos):
    corpo = nova_notificacao()
    cliente.post(ROTA, json=corpo, headers=cabecalhos)
    cliente.post(ROTA, json=corpo, headers=cabecalhos)
    cliente.post(ROTA, json=nova_notificacao(agravo="x"), headers=cabecalhos)

    metricas = cliente.get("/metrics").text
    for resultado in ("aceita", "duplicada", "invalida"):
        assert f'alertasus_notificacoes_recebidas_total{{resultado="{resultado}"}}' in (
            metricas
        )


def test_mensagem_amqp_segue_o_contrato(cliente, cabecalhos, publicador):
    corpo = nova_notificacao()
    cliente.post(ROTA, json=corpo, headers=cabecalhos)
    mensagem = montar_mensagem(publicador.eventos[0])

    assert mensagem.content_type == "application/json"
    assert mensagem.delivery_mode == 2
    assert mensagem.message_id == corpo["notificacao_id"]
    assert mensagem.type == "notificacao.recebida"
    assert json.loads(mensagem.body)["notificacao_id"] == corpo["notificacao_id"]
