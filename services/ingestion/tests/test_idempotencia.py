"""Estados do registro de idempotência no Redis (ADR 0006)."""

import asyncio
from uuid import uuid4

from app.idempotencia import PENDENTE, PUBLICADA, Reserva


def _rodar(corrotina):
    return asyncio.run(corrotina)


def test_primeira_reserva_e_nova_com_prazo_curto(registro, redis_falso):
    notificacao_id = uuid4()
    assert _rodar(registro.reservar(notificacao_id)) is Reserva.NOVA
    chave = f"alertasus:notificacao:{notificacao_id}"
    assert redis_falso.dados[chave] == PENDENTE
    assert redis_falso.ttls[chave] == 30


def test_reserva_em_andamento_responde_em_processamento(registro):
    notificacao_id = uuid4()
    _rodar(registro.reservar(notificacao_id))
    assert _rodar(registro.reservar(notificacao_id)) is Reserva.EM_PROCESSAMENTO


def test_confirmada_vira_duplicada_com_prazo_longo(registro, redis_falso):
    notificacao_id = uuid4()
    _rodar(registro.reservar(notificacao_id))
    _rodar(registro.confirmar(notificacao_id))
    chave = f"alertasus:notificacao:{notificacao_id}"
    assert redis_falso.dados[chave] == PUBLICADA
    assert redis_falso.ttls[chave] == 86_400
    assert _rodar(registro.reservar(notificacao_id)) is Reserva.DUPLICADA


def test_liberada_pode_ser_reservada_de_novo(registro):
    notificacao_id = uuid4()
    _rodar(registro.reservar(notificacao_id))
    _rodar(registro.liberar(notificacao_id))
    assert _rodar(registro.reservar(notificacao_id)) is Reserva.NOVA


def test_reserva_expirada_entre_set_e_get_e_retomada(registro, redis_falso):
    """Simula a chave expirando entre o SET NX que falhou e o GET."""
    notificacao_id = uuid4()
    chave = f"alertasus:notificacao:{notificacao_id}"
    redis_falso.dados[chave] = PENDENTE
    get_original = redis_falso.get

    async def get_que_expira(nome):
        redis_falso.dados.pop(nome, None)
        return await get_original(nome)

    redis_falso.get = get_que_expira
    assert _rodar(registro.reservar(notificacao_id)) is Reserva.NOVA


def test_pronto_reflete_disponibilidade(registro, redis_falso):
    assert _rodar(registro.pronto()) is True
    redis_falso.indisponivel = True
    assert _rodar(registro.pronto()) is False
