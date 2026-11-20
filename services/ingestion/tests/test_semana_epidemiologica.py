"""Semana epidemiológica: domingo a sábado; semana 1 contém o dia 4 de janeiro."""

from datetime import date, timedelta

import pytest

from app.semana_epidemiologica import formatar_semana, semana_epidemiologica


@pytest.mark.parametrize(
    ("dia", "esperado"),
    [
        (date(2026, 11, 15), "2026-46"),  # domingo: abre a semana 46
        (date(2026, 11, 21), "2026-46"),  # sábado: fecha a semana 46
        (date(2026, 11, 22), "2026-47"),  # domingo seguinte
        (date(2026, 1, 4), "2026-01"),  # 4 de janeiro de 2026 é domingo
        (date(2026, 1, 3), "2025-53"),  # sábado anterior: ainda é 2025
        (date(2026, 1, 1), "2025-53"),  # 1º de janeiro pertence ao ano anterior
        (date(2024, 12, 29), "2025-01"),  # fim de dezembro já é o ano seguinte
        (date(2026, 12, 31), "2026-52"),
        (date(2027, 1, 3), "2027-01"),  # 4/1/2027 é segunda; semana 1 começa em 3/1
    ],
)
def test_datas_de_referencia(dia, esperado):
    assert formatar_semana(dia) == esperado


def test_semana_sempre_entre_1_e_53_e_sem_saltos():
    """Percorre vários anos dia a dia: a semana só avança de 1 em 1."""
    dia = date(2019, 12, 1)
    anterior = semana_epidemiologica(dia)
    while dia < date(2031, 1, 31):
        dia += timedelta(days=1)
        atual = semana_epidemiologica(dia)
        assert 1 <= atual[1] <= 53
        if dia.weekday() == 6:  # domingo: nova semana
            ano_ant, sem_ant = anterior
            assert atual in {(ano_ant, sem_ant + 1), (ano_ant + 1, 1)}
        else:
            assert atual == anterior
        anterior = atual


def test_formato_ordena_cronologicamente():
    dias = [date(2025, 12, 28) + timedelta(weeks=n) for n in range(10)]
    semanas = [formatar_semana(d) for d in dias]
    assert semanas == sorted(semanas)
