"""Dados sintéticos das notificações.

Os municípios seguem a seção 4 de docs/contratos/evento-notificacao.md
(mesma lista usada no seed da tabela `municipios`). Os bairros são apenas
rótulos sintéticos.
"""

import random
from datetime import date, timedelta
from uuid import uuid4

MUNICIPIOS: dict[str, tuple[str, tuple[str, ...]]] = {
    "2507507": (
        "João Pessoa",
        ("Mangabeira", "Bancários", "Manaíra", "Cristo Redentor", "Valentina",
         "Torre", "Centro", "Cruz das Armas"),
    ),
    "2504009": (
        "Campina Grande",
        ("Bodocongó", "Catolé", "Liberdade", "Centro", "Malvinas", "José Pinheiro"),
    ),
    "2513703": ("Santa Rita", ("Centro", "Tibiri", "Várzea Nova")),
    "2501807": ("Bayeux", ("Centro", "Mário Andreazza", "Alto da Boa Vista")),
    "2503209": ("Cabedelo", ("Centro", "Intermares", "Camboinha")),
    "2510808": ("Patos", ("Centro", "Jatobá", "Belo Horizonte")),
    "2516201": ("Sousa", ("Centro", "Gato Preto", "Estreito")),
    "2503704": ("Cajazeiras", ("Centro", "Remédios", "Cristo Rei")),
}

# Formato válido, mas fora da tabela de referência: deve terminar na DLQ.
MUNICIPIO_INEXISTENTE = "9999999"

AGRAVOS = ("dengue", "sindrome_gripal", "chikungunya")
PESOS_AGRAVOS = (0.5, 0.35, 0.15)


def nome_unidade(numero: int) -> str:
    return f"unidade-{numero:03d}"


def datas_na_semana_corrente(hoje: date, rng: random.Random) -> tuple[date, date]:
    """(início dos sintomas, data da notificação) dentro da semana de `hoje`.

    O início dos sintomas fica entre 0 e 3 dias antes, sem voltar para a
    semana epidemiológica anterior. Assim, as notificações de um surto caem
    todas na mesma semana e somam para o mesmo limiar.
    """
    dias_desde_domingo = (hoje.weekday() + 1) % 7
    atraso = rng.randint(0, min(3, dias_desde_domingo))
    return hoje - timedelta(days=atraso), hoje


def nova_notificacao(
    rng: random.Random,
    hoje: date,
    municipio_ibge: str | None = None,
    bairro: str | None = None,
    agravo: str | None = None,
) -> dict:
    """Corpo válido segundo o contrato.

    `enviado_em` fica None: o executor preenche com o instante real do envio,
    para que o atraso fim a fim seja medido a partir dele.
    """
    if municipio_ibge is None:
        municipio_ibge = rng.choice(list(MUNICIPIOS))
    if bairro is None:
        bairros = MUNICIPIOS.get(municipio_ibge, ("", ("Centro",)))[1]
        bairro = rng.choice(bairros)
    if agravo is None:
        agravo = rng.choices(AGRAVOS, weights=PESOS_AGRAVOS)[0]
    inicio_sintomas, data_notificacao = datas_na_semana_corrente(hoje, rng)
    return {
        "notificacao_id": str(uuid4()),
        "agravo": agravo,
        "municipio_ibge": municipio_ibge,
        "bairro": bairro,
        "data_inicio_sintomas": inicio_sintomas.isoformat(),
        "data_notificacao": data_notificacao.isoformat(),
        "enviado_em": None,
    }
