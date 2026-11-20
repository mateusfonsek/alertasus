# Stack tecnológica

Este documento descreve a stack que está configurada no repositório e separa o que já pode ser executado localmente das tecnologias previstas para a arquitetura-alvo. A referência para a configuração executável é o [`docker-compose.yml`](../docker-compose.yml); decisões ainda em aberto devem ser registradas em ADRs em [`docs/adr/`](adr/).

> **Estado atual:** Projeto 03 em andamento. O Serviço de Ingestão e o simulador de unidades estão implementados, seguindo o [contrato da notificação](contratos/evento-notificacao.md). Agregação, Alertas e Consulta ainda são esqueletos com endpoints de health check.

## Stack executável

| Camada | Tecnologia e versão/imagem | Uso atual |
|---|---|---|
| Linguagem dos serviços | Python 3.12 (`python:3.12-slim`) | Runtime dos quatro serviços. |
| Framework HTTP | FastAPI 0.115.5 | API mínima dos serviços. |
| Servidor ASGI | Uvicorn 0.32.1 | Expõe cada API na porta 8000 do container. |
| Broker | RabbitMQ 3.13 (`rabbitmq:3.13-management`) | Serviço de infraestrutura no Compose; porta AMQP 5672 e interface de gerenciamento 15672. |
| Banco relacional | PostgreSQL 16 (`postgres:16-alpine`) | Serviço de infraestrutura; porta 5432 e volume persistente `pg_data`. |
| Cache | Redis 7 (`redis:7-alpine`) | Serviço de infraestrutura; porta 6379. |
| Orquestração local | Docker Compose v2 | Constrói e executa os serviços e a infraestrutura na rede `alertasus-net`. |
| Validação do contrato | Pydantic 2.14.4 | Modelos da notificação e do evento na Ingestão; também geram os esquemas JSON em `docs/contratos/`. Versão fixada para o esquema gerado ser o mesmo em qualquer máquina. |
| Cliente AMQP | aio-pika 9.4.3 | Publicação na exchange `notificacoes` com *publisher confirms* (Ingestão). |
| Cliente Redis | redis-py 5.2.0 | Registro de idempotência da Ingestão ([ADR 0006](adr/0006-idempotencia-notificacoes.md)). |
| Métricas | prometheus-client 0.21.0 | Endpoint `GET /metrics` da Ingestão. |
| Simulador | Python 3.12 + HTTPX 0.27.2 | Gera notificações sintéticas em ritmo controlado (`simulator/`). |
| Testes de carga | k6 | Scripts em `tests/load/` (T1 implementado). |
| Testes | pytest 8.3.3 e HTTPX 0.27.2 | Testes unitários de cada serviço e testes de integração em `tests/integration/` (estes também usam pika 1.3.2 e psycopg 3.2.3). |
| Lint | Ruff 0.7.4 | Verificação estática dos serviços. |
| CI | GitHub Actions | Executa lint e testes por serviço e valida a configuração do Compose. |

As dependências Python acima estão declaradas nos `requirements.txt` de cada serviço; cada serviço instala apenas as bibliotecas de que precisa.

### Serviços e portas locais

| Serviço | Porta local | Dependências declaradas no Compose |
|---|---:|---|
| `ingestion` | 8001 | RabbitMQ e Redis |
| `aggregation` | 8002 | RabbitMQ e PostgreSQL |
| `alerts` | 8003 | RabbitMQ e PostgreSQL |
| `query` | 8004 | PostgreSQL e Redis |
| `rabbitmq` | 5672, 15672 | — |
| `postgres` | 5432 | — |
| `redis` | 6379 | — |

As dependências com `condition: service_healthy` aguardam os health checks dos serviços de infraestrutura. A Ingestão já usa RabbitMQ e Redis, oferece `POST /api/v1/notificacoes`, `GET /health`, `GET /ready` e `GET /metrics`, e tem healthcheck próprio no Compose (baseado em `/ready`). Nos demais serviços, os clientes de RabbitMQ, PostgreSQL e Redis ainda não estão implementados; eles oferecem apenas `GET /health` e `GET /`.

O simulador fica no perfil `demo` do Compose e só sobe sob demanda: `docker compose run --rm simulator --cenario surto --taxa 20 --duracao 120`.

O PostgreSQL persiste dados no volume nomeado `pg_data`. RabbitMQ e Redis não têm volumes configurados; não conte com a preservação de seus dados ao recriar os containers.

## Arquitetura-alvo e itens pendentes

As tecnologias e padrões abaixo fazem parte da proposta, mas não devem ser confundidos com funcionalidades já disponíveis no Compose:

| Item | Estado | Observação |
|---|---|---|
| RabbitMQ com fanout, filas de consumidores, retry e DLQ | Planejado | O broker está no Compose; topologia, consumidores e política de retry/DLQ ainda precisam ser implementados. |
| PostgreSQL com dados de domínio e Materialized Views | Planejado | O banco está no Compose; esquema, migrações e views não estão definidos no código atual. |
| Redis como cache-aside do serviço de consulta | Planejado | Redis está no Compose; integração e política de expiração ainda não foram implementadas. |
| API Gateway | Decidido, não implementado | Kong em modo DB-less ([ADR 0005](adr/0005-api-gateway-kong.md)): plugins nativos de JWT e de rate limiting por consumidor; container e configuração entram no Projeto 03. |
| Painel | Planejado | Grafana é a tecnologia prevista; não há container configurado. |
| Coleta de métricas | Planejado | Prometheus é a tecnologia prevista; não há container nem endpoints `/metrics` configurados. |
| Carga e simulação | Parcial | Simulador implementado em `simulator/`; script k6 do T1 em `tests/load/`. Os demais testes de carga (T6, T7) pertencem às outras frentes. |
| Idempotência de notificações | Decidido; camada 1 implementada | Duas camadas ([ADR 0006](adr/0006-idempotencia-notificacoes.md)): Redis na Ingestão (implementado) e chave primária em `notificacao_id` nos consumidores (pendente). |
| Persistência por serviço | Decisão arquitetural pendente | O Compose atual prevê um PostgreSQL compartilhado; registrar o trade-off frente a database-per-service em ADR. |

Detalhes dos containers, fluxos e padrões estão no [diagrama C4 nível 2](c4/nivel-2-containers.md). Quando uma decisão pendente for tomada, registre contexto, alternativas, decisão e consequências em um ADR e atualize este documento e o diagrama.

## Configuração e segurança

- Os valores de configuração atuais estão declarados diretamente no Compose para execução local. Não são uma configuração adequada para produção.
- Não use credenciais de desenvolvimento fora de um ambiente local. Antes de qualquer implantação compartilhada, mova credenciais para variáveis de ambiente ou um gerenciador de segredos e evite registrá-las no controle de versão.
- As portas dos serviços de infraestrutura são publicadas no host para facilitar o desenvolvimento local. Restrinja ou remova essas publicações em ambientes que não precisem de acesso externo.
- Os dados do projeto devem ser sintéticos; não use dados pessoais ou dados reais de pacientes.

## Executar localmente

Requisitos: Docker e Docker Compose v2.

Na raiz do repositório:

```bash
docker compose up --build -d
docker compose ps
```

Verifique os endpoints básicos:

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
```

Para validar localmente o código Python, o CI usa Ruff e pytest em cada serviço:

```bash
for svc in ingestion aggregation alerts query; do
  (cd "services/$svc" && ruff check . && pytest -q)
done
```

Para encerrar os containers preservando o volume do PostgreSQL:

```bash
docker compose down
```

`docker compose down -v` também remove o volume `pg_data` e apaga os dados persistidos.
