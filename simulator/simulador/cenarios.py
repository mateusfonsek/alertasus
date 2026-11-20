"""Cenários de envio do simulador.

Cada cenário gera uma lista de `Envio`: qual unidade envia, o corpo e uma
categoria que diz qual resposta é esperada (tabela RESPOSTA_ESPERADA).
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from simulador.dados import MUNICIPIO_INEXISTENTE, nome_unidade, nova_notificacao

# Região que recebe a concentração de casos no cenário de surto.
FOCO_SURTO = {"municipio_ibge": "2507507", "bairro": "Mangabeira", "agravo": "dengue"}

RESPOSTA_ESPERADA = {
    "normal": "202",
    "surto": "202 (casos concentrados no foco; deve disparar alerta)",
    "original": "202",
    "reenvio": "200 duplicada (a notificação não é contada de novo)",
    "invalida-esquema": "422 (rejeitada pela Ingestão)",
    "invalida-dominio": "202 na Ingestão; deve terminar na DLQ dos consumidores",
    "abusiva": "429 a partir do limite da unidade (só com o Gateway)",
}


@dataclass(frozen=True)
class Envio:
    unidade_id: str
    corpo: dict
    categoria: str


def _unidade_aleatoria(rng: random.Random, unidades: int, primeira: int = 1) -> str:
    return nome_unidade(rng.randint(primeira, unidades))


def cenario_normal(total, unidades, rng, hoje) -> list[Envio]:
    return [
        Envio(_unidade_aleatoria(rng, unidades), nova_notificacao(rng, hoje), "normal")
        for _ in range(total)
    ]


def cenario_surto(total, unidades, rng, hoje) -> list[Envio]:
    """A fração de casos no foco cresce de 20% para 80% ao longo da execução."""
    envios = []
    for i in range(total):
        proporcao_no_foco = 0.2 + 0.6 * i / max(total - 1, 1)
        if rng.random() < proporcao_no_foco:
            envios.append(
                Envio(
                    _unidade_aleatoria(rng, unidades),
                    nova_notificacao(rng, hoje, **FOCO_SURTO),
                    "surto",
                )
            )
        else:
            envios.append(
                Envio(
                    _unidade_aleatoria(rng, unidades),
                    nova_notificacao(rng, hoje),
                    "normal",
                )
            )
    return envios


def cenario_duplicadas(total, unidades, rng, hoje) -> list[Envio]:
    """Cada notificação é enviada 3 vezes seguidas pela mesma unidade."""
    envios = []
    for _ in range(max(total // 3, 1)):
        unidade = _unidade_aleatoria(rng, unidades)
        corpo = nova_notificacao(rng, hoje)
        envios.append(Envio(unidade, corpo, "original"))
        envios.extend(Envio(unidade, dict(corpo), "reenvio") for _ in range(2))
    return envios


def _invalidar_esquema(corpo: dict, variante: int) -> dict:
    corpo = dict(corpo)
    if variante == 0:
        corpo["agravo"] = "covid"
    elif variante == 1:
        corpo["municipio_ibge"] = "25AB507"
    elif variante == 2:
        corpo["bairro"] = ""
    elif variante == 3:
        notificacao = date.fromisoformat(corpo["data_notificacao"])
        corpo["data_inicio_sintomas"] = (notificacao + timedelta(days=1)).isoformat()
    elif variante == 4:
        corpo["paciente_nome"] = "campo fora do contrato"
    else:
        del corpo["notificacao_id"]
    return corpo


VARIANTES_ESQUEMA = 6


def cenario_invalidas(total, unidades, rng, hoje) -> list[Envio]:
    """Metade válida, 1/4 fora do esquema (422) e 1/4 com município inexistente."""
    envios = []
    for i in range(total):
        unidade = _unidade_aleatoria(rng, unidades)
        corpo = nova_notificacao(rng, hoje)
        tipo = i % 4
        if tipo == 2:
            variante = (i // 4) % VARIANTES_ESQUEMA
            envios.append(
                Envio(unidade, _invalidar_esquema(corpo, variante), "invalida-esquema")
            )
        elif tipo == 3:
            corpo["municipio_ibge"] = MUNICIPIO_INEXISTENTE
            corpo["bairro"] = "Centro"
            envios.append(Envio(unidade, corpo, "invalida-dominio"))
        else:
            envios.append(Envio(unidade, corpo, "normal"))
    return envios


def cenario_unidade_abusiva(total, unidades, rng, hoje) -> list[Envio]:
    """Metade do tráfego vem da unidade-001; o resto, das demais unidades."""
    envios = []
    for i in range(total):
        if i % 2 == 0:
            envios.append(
                Envio(nome_unidade(1), nova_notificacao(rng, hoje), "abusiva")
            )
        else:
            unidade = _unidade_aleatoria(rng, max(unidades, 2), primeira=2)
            envios.append(Envio(unidade, nova_notificacao(rng, hoje), "normal"))
    return envios


Cenario = Callable[[int, int, random.Random, date], list[Envio]]

CENARIOS: dict[str, Cenario] = {
    "normal": cenario_normal,
    "surto": cenario_surto,
    "duplicadas": cenario_duplicadas,
    "invalidas": cenario_invalidas,
    "unidade-abusiva": cenario_unidade_abusiva,
}


def gerar(
    nome: str,
    total: int,
    unidades: int = 50,
    semente: int | None = None,
    hoje: date | None = None,
) -> list[Envio]:
    if nome not in CENARIOS:
        raise ValueError(f"cenário desconhecido: {nome}. Opções: {', '.join(CENARIOS)}")
    rng = random.Random(semente)
    return CENARIOS[nome](total, unidades, rng, hoje or date.today())
