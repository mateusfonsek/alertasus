# Stack tecnológica

Este documento descreve a stack que está configurada no repositório e separa o que já pode ser executado localmente das tecnologias previstas para a arquitetura-alvo. A referência para a configuração executável é o [`docker-compose.yml`](../docker-compose.yml); decisões ainda em aberto devem ser registradas em ADRs em [`docs/adr/`](adr/).

> **Estado atual:** base do Projeto 02. Os quatro serviços Python estão implementados como esqueletos com endpoints de health check. Os fluxos de negócio descritos na arquitetura ainda não estão implementados.

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
| Testes | pytest 8.3.3 e HTTPX 0.27.2 | Testes automatizados dos endpoints básicos. |
| Lint | Ruff 0.7.4 | Verificação estática dos serviços. |
| CI | GitHub Actions | Executa lint e testes por serviço e valida a configuração do Compose. |

As dependências Python acima estão declaradas nos `requirements.txt` dos serviços. Atualmente, os quatro arquivos de dependências têm o mesmo conteúdo.

### Serviços e portas locais

| Serviço | Porta local | Dependências declaradas no Compose |
|---|---:|---|
| `ingestion` | 8001 | RabbitMQ |
| `aggregation` | 8002 | RabbitMQ e PostgreSQL |
| `alerts` | 8003 | RabbitMQ e PostgreSQL |
| `query` | 8004 | PostgreSQL e Redis |
| `rabbitmq` | 5672, 15672 | — |
| `postgres` | 5432 | — |
| `redis` | 6379 | — |

As dependências com `condition: service_healthy` aguardam os health checks dos serviços de infraestrutura. A configuração injeta URLs de conexão nos serviços, mas **os clientes de RabbitMQ, PostgreSQL e Redis e os respectivos fluxos de negócio ainda não estão implementados**. Neste estágio, cada API oferece `GET /health` e `GET /`.

O PostgreSQL persiste dados no volume nomeado `pg_data`. RabbitMQ e Redis não têm volumes configurados; não conte com a preservação de seus dados ao recriar os containers.

## Arquitetura-alvo e itens pendentes

As tecnologias e padrões abaixo fazem parte da proposta, mas não devem ser confundidos com funcionalidades já disponíveis no Compose:

| Item | Estado | Observação |
|---|---|---|
| RabbitMQ com fanout, filas de consumidores, retry e DLQ | Planejado | O broker está no Compose; topologia, consumidores e política de retry/DLQ ainda precisam ser implementados. |
| PostgreSQL com dados de domínio e Materialized Views | Planejado | O banco está no Compose; esquema, migrações e views não estão definidos no código atual. |
| Redis como cache-aside do serviço de consulta | Planejado | Redis está no Compose; integração e política de expiração ainda não foram implementadas. |
| API Gateway | Em aberto | Kong ou Traefik; autenticação JWT, rate limiting e roteamento estão previstos. |
| Painel | Planejado | Grafana é a tecnologia prevista; não há container configurado. |
| Coleta de métricas | Planejado | Prometheus é a tecnologia prevista; não há container nem endpoints `/metrics` configurados. |
| Carga e simulação | Planejado | k6 está previsto para carga; o simulador de unidades também não está no repositório atual. |
| Idempotência de notificações | Em aberto | Definir onde manter os IDs e qual serviço é responsável pela deduplicação. |
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
