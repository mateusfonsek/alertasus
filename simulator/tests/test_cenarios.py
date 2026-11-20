"""Cenários do simulador."""

from collections import Counter
from datetime import date, timedelta

import pytest

from simulador.cenarios import CENARIOS, FOCO_SURTO, RESPOSTA_ESPERADA, gerar
from simulador.dados import MUNICIPIO_INEXISTENTE, MUNICIPIOS

QUARTA = date(2026, 11, 18)  # semana epidemiológica de 15/11 (dom) a 21/11 (sáb)
CAMPOS = {
    "notificacao_id",
    "agravo",
    "municipio_ibge",
    "bairro",
    "data_inicio_sintomas",
    "data_notificacao",
    "enviado_em",
}


@pytest.mark.parametrize("nome", list(CENARIOS))
def test_todo_cenario_gera_categorias_conhecidas(nome):
    envios = gerar(nome, 60, unidades=10, semente=1, hoje=QUARTA)
    assert envios
    assert {e.categoria for e in envios} <= set(RESPOSTA_ESPERADA)


def test_normal_gera_corpos_completos_na_semana_corrente():
    for envio in gerar("normal", 200, unidades=10, semente=2, hoje=QUARTA):
        corpo = envio.corpo
        assert set(corpo) == CAMPOS
        assert corpo["municipio_ibge"] in MUNICIPIOS
        assert corpo["bairro"] in MUNICIPIOS[corpo["municipio_ibge"]][1]
        inicio = date.fromisoformat(corpo["data_inicio_sintomas"])
        assert date(2026, 11, 15) <= inicio <= QUARTA
        assert corpo["data_notificacao"] == QUARTA.isoformat()
        assert corpo["enviado_em"] is None


def test_domingo_nao_volta_para_a_semana_anterior():
    domingo = date(2026, 11, 15)
    for envio in gerar("normal", 100, semente=3, hoje=domingo):
        assert envio.corpo["data_inicio_sintomas"] == domingo.isoformat()


def test_unidades_ficam_no_intervalo():
    unidades = {e.unidade_id for e in gerar("normal", 500, unidades=5, semente=4)}
    assert unidades <= {f"unidade-{n:03d}" for n in range(1, 6)}


def test_ids_sao_unicos_mesmo_com_a_mesma_semente():
    """A semente controla os sorteios, não os IDs: rodar de novo não gera reenvios."""
    primeira = {e.corpo["notificacao_id"] for e in gerar("normal", 50, semente=5)}
    segunda = {e.corpo["notificacao_id"] for e in gerar("normal", 50, semente=5)}
    assert len(primeira) == 50
    assert primeira.isdisjoint(segunda)


def test_surto_concentra_cada_vez_mais_casos_no_foco():
    envios = gerar("surto", 1000, semente=6, hoje=QUARTA)

    def no_foco(trecho):
        return sum(
            all(e.corpo[k] == v for k, v in FOCO_SURTO.items()) for e in trecho
        ) / len(trecho)

    inicio, fim = no_foco(envios[:200]), no_foco(envios[-200:])
    assert inicio < 0.45
    assert fim > 0.6
    for envio in envios:
        if envio.categoria == "surto":
            assert all(envio.corpo[k] == v for k, v in FOCO_SURTO.items())


def test_duplicadas_reenviam_o_mesmo_corpo_tres_vezes():
    envios = gerar("duplicadas", 30, semente=7)
    assert len(envios) == 30
    for i in range(0, 30, 3):
        trio = envios[i : i + 3]
        assert [e.categoria for e in trio] == ["original", "reenvio", "reenvio"]
        assert len({e.corpo["notificacao_id"] for e in trio}) == 1
        assert len({e.unidade_id for e in trio}) == 1


def test_invalidas_misturam_validas_esquema_e_dominio():
    envios = gerar("invalidas", 400, semente=8, hoje=QUARTA)
    categorias = Counter(e.categoria for e in envios)
    assert categorias == {"normal": 200, "invalida-esquema": 100, "invalida-dominio": 100}

    for envio in envios:
        if envio.categoria == "invalida-dominio":
            assert envio.corpo["municipio_ibge"] == MUNICIPIO_INEXISTENTE
            assert set(envio.corpo) == CAMPOS


def test_cada_invalida_de_esquema_quebra_uma_regra_do_contrato():
    envios = [e for e in gerar("invalidas", 48, semente=9, hoje=QUARTA)
              if e.categoria == "invalida-esquema"]
    problemas = set()
    for envio in envios:
        corpo = envio.corpo
        if "notificacao_id" not in corpo:
            problemas.add("sem_id")
        elif set(corpo) - CAMPOS:
            problemas.add("campo_extra")
        elif corpo["agravo"] not in {"dengue", "chikungunya", "sindrome_gripal"}:
            problemas.add("agravo")
        elif not corpo["municipio_ibge"].isdigit():
            problemas.add("municipio")
        elif not corpo["bairro"]:
            problemas.add("bairro")
        elif corpo["data_inicio_sintomas"] > corpo["data_notificacao"]:
            problemas.add("datas")
    assert problemas == {"sem_id", "campo_extra", "agravo", "municipio", "bairro", "datas"}


def test_unidade_abusiva_concentra_metade_do_trafego():
    envios = gerar("unidade-abusiva", 100, unidades=10, semente=10)
    da_abusiva = [e for e in envios if e.unidade_id == "unidade-001"]
    assert len(da_abusiva) == 50
    assert all(e.categoria == "abusiva" for e in da_abusiva)
    assert all(e.unidade_id != "unidade-001" for e in envios if e.categoria == "normal")


def test_cenario_desconhecido():
    with pytest.raises(ValueError):
        gerar("inexistente", 10)


def test_datas_validas_em_qualquer_dia_da_semana():
    for deslocamento in range(7):
        hoje = date(2026, 11, 15) + timedelta(days=deslocamento)
        for envio in gerar("normal", 50, semente=deslocamento, hoje=hoje):
            assert envio.corpo["data_inicio_sintomas"] <= envio.corpo["data_notificacao"]
