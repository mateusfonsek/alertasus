"""Regras do contrato (docs/contratos/evento-notificacao.md)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.contrato import ESQUEMAS, EventoNotificacao, NotificacaoEntrada, esquema_json
from tests.conftest import nova_notificacao

def _pasta_contratos() -> Path | None:
    """docs/contratos na raiz do repositório; None dentro do container (/app)."""
    ancestrais = Path(__file__).resolve().parents
    if len(ancestrais) < 4:
        return None
    return ancestrais[3] / "docs" / "contratos"


PASTA_CONTRATOS = _pasta_contratos()


def test_notificacao_valida():
    notificacao = NotificacaoEntrada.model_validate(nova_notificacao())
    assert notificacao.agravo == "dengue"


def test_bairro_tem_espacos_removidos():
    notificacao = NotificacaoEntrada.model_validate(nova_notificacao(bairro="  Torre "))
    assert notificacao.bairro == "Torre"


@pytest.mark.parametrize(
    "alteracao",
    [
        {"agravo": "covid"},
        {"municipio_ibge": "250750"},
        {"municipio_ibge": "25075AB"},
        {"bairro": "   "},
        {"bairro": "x" * 101},
        {"notificacao_id": "nao-e-uuid"},
        {"data_inicio_sintomas": "2026-11-18", "data_notificacao": "2026-11-17"},
        {"enviado_em": "2026-11-17T14:03:12"},  # sem fuso horário
        {"campo_extra": "nao permitido"},
    ],
)
def test_notificacao_invalida(alteracao):
    with pytest.raises(ValidationError):
        NotificacaoEntrada.model_validate(nova_notificacao(**alteracao))


@pytest.mark.parametrize("campo", list(nova_notificacao().keys()))
def test_todos_os_campos_sao_obrigatorios(campo):
    corpo = nova_notificacao()
    del corpo[campo]
    with pytest.raises(ValidationError):
        NotificacaoEntrada.model_validate(corpo)


def test_evento_copia_campos_e_calcula_semana():
    notificacao = NotificacaoEntrada.model_validate(
        nova_notificacao(data_inicio_sintomas="2026-11-15")
    )
    recebido_em = datetime(2026, 11, 17, 14, 3, 13, tzinfo=timezone.utc)
    evento = EventoNotificacao.a_partir_de(notificacao, "unidade-007", recebido_em)

    assert evento.tipo == "notificacao.recebida"
    assert evento.versao == 1
    assert evento.unidade_id == "unidade-007"
    assert evento.notificacao_id == notificacao.notificacao_id
    assert evento.semana_epidemiologica == "2026-46"
    assert evento.recebido_em == recebido_em
    assert isinstance(evento.evento_id, UUID)


def test_evento_serializado_tem_exatamente_os_campos_do_contrato():
    notificacao = NotificacaoEntrada.model_validate(nova_notificacao())
    evento = EventoNotificacao.a_partir_de(
        notificacao, "unidade-001", datetime.now(timezone.utc)
    )
    corpo = json.loads(evento.model_dump_json())
    assert set(corpo) == {
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
    # O evento serializado volta a ser um evento válido (consumidores em Python).
    assert EventoNotificacao.model_validate_json(evento.model_dump_json()) == evento


@pytest.mark.parametrize("nome", list(ESQUEMAS))
def test_esquemas_json_versionados_estao_atualizados(nome):
    """Se falhar: rode `python -m app.contrato ../../docs/contratos`."""
    if PASTA_CONTRATOS is None or not (PASTA_CONTRATOS / nome).exists():
        pytest.skip("docs/contratos não está disponível (ex.: dentro do container)")
    arquivo = PASTA_CONTRATOS / nome
    assert arquivo.read_text(encoding="utf-8") == esquema_json(ESQUEMAS[nome])
