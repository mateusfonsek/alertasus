"""Cálculo da semana epidemiológica (calendário usado pelo SINAN).

Regras:
- a semana vai de domingo a sábado;
- a semana 1 de um ano é a que contém o dia 4 de janeiro, ou seja, a primeira
  semana com pelo menos 4 dias no ano.

Por isso, alguns dias do início de janeiro pertencem à última semana do ano
anterior, e alguns anos epidemiológicos têm 53 semanas.
"""

from datetime import date, timedelta


def _inicio_do_ano_epidemiologico(ano: int) -> date:
    """Domingo que abre a semana 1 do ano epidemiológico."""
    quatro_de_janeiro = date(ano, 1, 4)
    # weekday(): segunda = 0 … domingo = 6. Dias desde o domingo anterior:
    dias_desde_domingo = (quatro_de_janeiro.weekday() + 1) % 7
    return quatro_de_janeiro - timedelta(days=dias_desde_domingo)


def semana_epidemiologica(dia: date) -> tuple[int, int]:
    """Retorna (ano epidemiológico, número da semana) da data informada."""
    ano = dia.year
    inicio = _inicio_do_ano_epidemiologico(ano + 1)
    if dia >= inicio:
        ano += 1
    else:
        inicio = _inicio_do_ano_epidemiologico(ano)
        if dia < inicio:
            ano -= 1
            inicio = _inicio_do_ano_epidemiologico(ano)
    semana = (dia - inicio).days // 7 + 1
    return ano, semana


def formatar_semana(dia: date) -> str:
    """Semana epidemiológica no formato do contrato: AAAA-SS (ex.: 2026-46)."""
    ano, semana = semana_epidemiologica(dia)
    return f"{ano}-{semana:02d}"
