"""Contrato da notificação de agravo (versão 1).

Implementação de referência de docs/contratos/evento-notificacao.md.
Qualquer mudança aqui exige atualizar o documento e regerar os esquemas JSON:

    python -m app.contrato ../../docs/contratos
"""

import json
import sys
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.semana_epidemiologica import formatar_semana

VERSAO_EVENTO = 1
TIPO_EVENTO = "notificacao.recebida"


class Agravo(StrEnum):
    DENGUE = "dengue"
    CHIKUNGUNYA = "chikungunya"
    SINDROME_GRIPAL = "sindrome_gripal"


class NotificacaoEntrada(BaseModel):
    """Corpo de POST /api/v1/notificacoes."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        title="NotificacaoEntrada",
    )

    notificacao_id: UUID = Field(
        description="UUID gerado pela unidade; chave de idempotência."
    )
    agravo: Agravo
    municipio_ibge: str = Field(
        pattern=r"^\d{7}$", description="Código IBGE do município (7 dígitos)."
    )
    bairro: str = Field(min_length=1, max_length=100)
    data_inicio_sintomas: date
    data_notificacao: date
    enviado_em: AwareDatetime = Field(
        description="Instante do envio pela unidade, com fuso horário."
    )

    @model_validator(mode="after")
    def _datas_coerentes(self) -> "NotificacaoEntrada":
        if self.data_inicio_sintomas > self.data_notificacao:
            raise ValueError(
                "data_inicio_sintomas deve ser anterior ou igual a data_notificacao"
            )
        return self


class EventoNotificacao(BaseModel):
    """Evento publicado na exchange 'notificacoes' do RabbitMQ."""

    model_config = ConfigDict(frozen=True, title="EventoNotificacao")

    evento_id: UUID
    tipo: Literal["notificacao.recebida"] = TIPO_EVENTO
    versao: Literal[1] = VERSAO_EVENTO
    notificacao_id: UUID
    unidade_id: str = Field(min_length=1)
    agravo: Agravo
    municipio_ibge: str = Field(pattern=r"^\d{7}$")
    bairro: str = Field(min_length=1, max_length=100)
    semana_epidemiologica: str = Field(
        pattern=r"^\d{4}-\d{2}$", description="Formato AAAA-SS."
    )
    data_inicio_sintomas: date
    data_notificacao: date
    enviado_em: AwareDatetime
    recebido_em: AwareDatetime

    @classmethod
    def a_partir_de(
        cls,
        notificacao: NotificacaoEntrada,
        unidade_id: str,
        recebido_em: datetime,
        evento_id: UUID | None = None,
    ) -> "EventoNotificacao":
        return cls(
            evento_id=evento_id or uuid4(),
            notificacao_id=notificacao.notificacao_id,
            unidade_id=unidade_id,
            agravo=notificacao.agravo,
            municipio_ibge=notificacao.municipio_ibge,
            bairro=notificacao.bairro,
            semana_epidemiologica=formatar_semana(notificacao.data_inicio_sintomas),
            data_inicio_sintomas=notificacao.data_inicio_sintomas,
            data_notificacao=notificacao.data_notificacao,
            enviado_em=notificacao.enviado_em,
            recebido_em=recebido_em,
        )


ESQUEMAS = {
    "notificacao-entrada.schema.json": NotificacaoEntrada,
    "evento-notificacao.schema.json": EventoNotificacao,
}


def esquema_json(modelo: type[BaseModel]) -> str:
    """Esquema JSON do modelo, serializado de forma estável."""
    return json.dumps(modelo.model_json_schema(), ensure_ascii=False, indent=2) + "\n"


def gravar_esquemas(destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for nome, modelo in ESQUEMAS.items():
        (destino / nome).write_text(esquema_json(modelo), encoding="utf-8")


if __name__ == "__main__":
    gravar_esquemas(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
