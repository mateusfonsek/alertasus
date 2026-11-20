"""Logs estruturados em JSON, uma linha por evento.

Campos extras vão em extra={"contexto": {...}}, por exemplo o notificacao_id,
para que um mesmo evento possa ser seguido pelos serviços.
"""

import json
import logging
from datetime import datetime, timezone


class FormatadorJSON(logging.Formatter):
    def __init__(self, servico: str) -> None:
        super().__init__()
        self._servico = servico

    def format(self, record: logging.LogRecord) -> str:
        dados = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "nivel": record.levelname,
            "servico": self._servico,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        contexto = getattr(record, "contexto", None)
        if isinstance(contexto, dict):
            dados.update(contexto)
        if record.exc_info:
            dados["erro"] = self.formatException(record.exc_info)
        return json.dumps(dados, ensure_ascii=False, default=str)


def configurar_logs(servico: str, nivel: str = "INFO") -> None:
    manipulador = logging.StreamHandler()
    manipulador.setFormatter(FormatadorJSON(servico))
    raiz = logging.getLogger()
    raiz.handlers[:] = [manipulador]
    raiz.setLevel(nivel.upper())
