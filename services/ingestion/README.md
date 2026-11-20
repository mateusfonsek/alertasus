# Serviço de Ingestão

Recebe as notificações das unidades de saúde, valida o [contrato](../../docs/contratos/evento-notificacao.md), descarta reenvios pelo `notificacao_id` ([ADR 0006](../../docs/adr/0006-idempotencia-notificacoes.md)) e publica o evento na exchange fanout `notificacoes` do RabbitMQ.

## Endpoints

| Método e rota | Uso |
|---|---|
| `POST /api/v1/notificacoes` | Recebe uma notificação. Respostas na seção 1.4 do contrato |
| `GET /health` | *Liveness*: o processo está de pé |
| `GET /ready` | *Readiness*: `200` quando o RabbitMQ está conectado. O Redis é informado, mas não derruba o serviço (*fail-open*) |
| `GET /metrics` | Métricas no formato do Prometheus |
| `GET /docs` | Documentação interativa (OpenAPI) gerada pelo FastAPI |

## Fluxo de uma notificação

```text
POST ─► valida o contrato ──inválido──► 422
          │
          ├─ sem X-Consumer-Username ──► 401
          ▼
        Redis: SET pendente NX ──já publicada──► 200 duplicada
          │                     └─pendente────► 409 em_processamento
          │  (Redis fora do ar: segue sem verificar)
          ▼
        publica no RabbitMQ (confirmação do broker)
          │ falhou ──► remove a reserva ──► 503
          ▼
        Redis: publicada (24 h) ──► 202 aceita
```

## Configuração

| Variável | Padrão | Descrição |
|---|---|---|
| `RABBITMQ_URL` | `amqp://alertasus:alertasus@rabbitmq:5672/` | Conexão com o broker |
| `REDIS_URL` | `redis://redis:6379/0` | Registro de idempotência |
| `EXCHANGE_NOTIFICACOES` | `notificacoes` | Exchange fanout de destino |
| `CABECALHO_UNIDADE` | `X-Consumer-Username` | Cabeçalho com a unidade, injetado pelo Kong |
| `IDEMPOTENCIA_TTL_S` | `86400` | Por quanto tempo um ID aceito é reconhecido como reenvio |
| `IDEMPOTENCIA_PENDENTE_TTL_S` | `30` | Prazo da reserva durante a publicação |
| `PUBLICACAO_TIMEOUT_S` | `5` | Tempo máximo para o broker confirmar |
| `CONEXAO_TENTATIVAS` / `CONEXAO_INTERVALO_S` | `30` / `2` | Tentativas de conexão com o RabbitMQ na partida |
| `LOG_LEVEL` | `INFO` | Use `WARNING` nos testes de carga para não registrar cada notificação |
| `SERVICE_NAME` | `ingestion` | Nome nos logs e no `/health` |

## Métricas

| Métrica | Tipo | Descrição |
|---|---|---|
| `alertasus_notificacoes_recebidas_total{resultado}` | contador | `aceita`, `duplicada`, `em_processamento`, `invalida`, `nao_autenticada`, `falha_publicacao` |
| `alertasus_idempotencia_indisponivel_total` | contador | Notificações aceitas sem consultar o Redis |
| `alertasus_publicacao_duracao_segundos` | histograma | Tempo até o broker confirmar a publicação |
| `http_request_duration_seconds{method,route,status}` | histograma | Latência das requisições; os buckets incluem 0,1 s e 0,2 s (metas de p95) |

## Logs

Uma linha JSON por evento, com `notificacao_id` e `unidade_id`, para seguir uma notificação pelos serviços:

```json
{"ts": "2026-11-17T14:03:12.141+00:00", "nivel": "INFO", "servico": "ingestion", "logger": "alertasus.ingestao", "msg": "notificação aceita", "notificacao_id": "3f1c…", "unidade_id": "unidade-001", "evento_id": "9b2e…"}
```

## Testes

Os testes unitários não precisam de Redis nem de RabbitMQ (usam implementações falsas em `tests/conftest.py`):

```bash
cd services/ingestion
pip install -r requirements.txt
ruff check . && pytest -q
```

O teste `test_esquemas_json_versionados_estao_atualizados` falha se `app/contrato.py` mudar sem que os esquemas JSON sejam regerados:

```bash
python -m app.contrato ../../docs/contratos
```

Os testes de integração (Redis e RabbitMQ reais) estão em [`tests/integration/`](../../tests/integration/).
