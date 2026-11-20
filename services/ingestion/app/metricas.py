"""Métricas Prometheus do Serviço de Ingestão (expostas em GET /metrics)."""

from prometheus_client import Counter, Histogram

RESULTADOS = (
    "aceita",
    "duplicada",
    "em_processamento",
    "invalida",
    "nao_autenticada",
    "falha_publicacao",
)

NOTIFICACOES = Counter(
    "alertasus_notificacoes_recebidas_total",
    "Notificações recebidas pela Ingestão, por resultado.",
    ["resultado"],
)
for _resultado in RESULTADOS:
    NOTIFICACOES.labels(_resultado)

IDEMPOTENCIA_INDISPONIVEL = Counter(
    "alertasus_idempotencia_indisponivel_total",
    "Notificações aceitas sem consultar o Redis, porque ele estava indisponível.",
)

PUBLICACAO_SEGUNDOS = Histogram(
    "alertasus_publicacao_duracao_segundos",
    "Tempo até o RabbitMQ confirmar a publicação do evento.",
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

# Buckets incluem 0,1 s e 0,2 s, que são as metas de p95 do projeto.
REQUISICOES_SEGUNDOS = Histogram(
    "http_request_duration_seconds",
    "Duração das requisições HTTP.",
    ["method", "route", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2.5, 5),
)
