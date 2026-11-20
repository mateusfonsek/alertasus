# Contrato: notificação de agravo

**Versão do contrato:** 1
**Status:** Vigente
**Dono:** Frente 1 (Ingestão). Mudanças só por pull request revisado pelos donos dos serviços afetados (seção 6).

Este documento é a **fonte de verdade** do formato das notificações. Ele define:

1. a API HTTP que as unidades de saúde (e o simulador) usam para enviar notificações;
2. o evento que o Serviço de Ingestão publica no RabbitMQ e que a Agregação e os Alertas consomem;
3. as obrigações de quem consome o evento.

Os esquemas JSON gerados a partir do código ficam ao lado deste arquivo e são verificados por teste a cada alteração:

| Arquivo | Conteúdo |
|---|---|
| [`notificacao-entrada.schema.json`](notificacao-entrada.schema.json) | Corpo aceito por `POST /api/v1/notificacoes` |
| [`evento-notificacao.schema.json`](evento-notificacao.schema.json) | Corpo do evento publicado no RabbitMQ |

A implementação de referência está em [`services/ingestion/app/contrato.py`](../../services/ingestion/app/contrato.py).

```text
Unidade / Simulador ──POST + JWT──► API Gateway ──POST + X-Consumer-Username──► Ingestão
                                                                                   │ evento (AMQP)
                                                                                   ▼
                                                             exchange "notificacoes" (fanout)
                                                               ├──► fila da Agregação
                                                               └──► fila dos Alertas
```

---

## 1. API HTTP de notificação

### 1.1 Endpoint

```http
POST /api/v1/notificacoes
Content-Type: application/json
Authorization: Bearer <JWT da unidade>      ← validado pelo API Gateway (ADR 0005)
```

O caminho é o mesmo no Gateway e no Serviço de Ingestão, então o Gateway encaminha a requisição sem reescrever a rota.

### 1.2 Identificação da unidade

A unidade **não** é informada no corpo. Depois de validar o JWT, o Kong injeta o cabeçalho `X-Consumer-Username` com o nome do *consumer* (por exemplo, `unidade-001`), e a Ingestão usa esse valor como `unidade_id`. Assim, uma unidade não consegue notificar em nome de outra.

| Situação | Comportamento |
|---|---|
| Requisição pelo Gateway com JWT válido | O Kong preenche `X-Consumer-Username`; a Ingestão aceita |
| Requisição pelo Gateway sem JWT ou com JWT inválido | O Kong responde `401` e a requisição não chega à Ingestão |
| Requisição direta à Ingestão sem o cabeçalho | A Ingestão responde `401` |
| Desenvolvimento local, antes do Gateway | Quem chama envia `X-Consumer-Username` diretamente na porta 8001 (o simulador faz isso no modo direto) |

A Ingestão confia no cabeçalho porque, no ambiente final, só o Gateway alcança o serviço pela rede interna. Enquanto as portas 8001 a 8004 estiverem publicadas no host, esse cabeçalho pode ser forjado; isso é aceitável apenas em desenvolvimento (ver ADR 0005).

### 1.3 Corpo da requisição

```json
{
  "notificacao_id": "3f1c9a2e-5b7d-4e8a-9c1f-2a6b8d4e0f11",
  "agravo": "dengue",
  "municipio_ibge": "2507507",
  "bairro": "Mangabeira",
  "data_inicio_sintomas": "2026-11-15",
  "data_notificacao": "2026-11-17",
  "enviado_em": "2026-11-17T14:03:12.123Z"
}
```

| Campo | Tipo | Obrigatório | Regra |
|---|---|---|---|
| `notificacao_id` | string (UUID) | Sim | Gerado pela unidade. É a chave de idempotência: reenviar o mesmo ID não cria um novo caso |
| `agravo` | string | Sim | Um de `dengue`, `chikungunya`, `sindrome_gripal` |
| `municipio_ibge` | string | Sim | Exatamente 7 dígitos (código IBGE). A existência do município é verificada pelos consumidores (seção 3) |
| `bairro` | string | Sim | 1 a 100 caracteres após remover espaços nas pontas |
| `data_inicio_sintomas` | string (data, `AAAA-MM-DD`) | Sim | Menor ou igual a `data_notificacao` |
| `data_notificacao` | string (data, `AAAA-MM-DD`) | Sim | — |
| `enviado_em` | string (data e hora ISO 8601) | Sim | **Com fuso horário** (`Z` ou `-03:00`). Usado para medir o atraso fim a fim |

Campos não listados são **rejeitados** (`422`). O contrato é estrito na entrada para que erros de digitação em nomes de campos não passem despercebidos.

### 1.4 Respostas

| Código | Quando | Corpo |
|---|---|---|
| `202 Accepted` | Notificação nova, publicada e confirmada pelo broker | `{"status": "aceita", "notificacao_id": "…", "evento_id": "…", "semana_epidemiologica": "2026-46"}` |
| `200 OK` | O `notificacao_id` já foi aceito antes (reenvio) | `{"status": "duplicada", "notificacao_id": "…"}` |
| `401 Unauthorized` | Unidade não identificada (seção 1.2) | `{"detail": "…"}` |
| `409 Conflict` | O mesmo `notificacao_id` está sendo publicado neste instante por outra requisição | `{"status": "em_processamento", "notificacao_id": "…"}` + cabeçalho `Retry-After: 5` |
| `422 Unprocessable Entity` | Corpo fora do contrato (JSON malformado, campo ausente, extra ou inválido) | Formato padrão do FastAPI: `{"detail": [{"loc": […], "msg": "…", "type": "…"}]}` |
| `429 Too Many Requests` | A unidade passou do próprio limite (emitido pelo Gateway) | Definido pelo Kong |
| `503 Service Unavailable` | O broker está indisponível ou não confirmou a publicação | `{"detail": "…"}` + cabeçalho `Retry-After: 5` |

**Como a unidade deve reagir:** `202` e `200` significam que a notificação está registrada; não reenviar. `409`, `429` e `503` são temporários; reenviar **o mesmo corpo, com o mesmo `notificacao_id`**, depois do tempo indicado. `401` e `422` exigem correção antes de reenviar.

---

## 2. Evento publicado no RabbitMQ

### 2.1 Destino

| Item | Valor |
|---|---|
| Exchange | `notificacoes` |
| Tipo | `fanout`, durável |
| Routing key | vazia (ignorada pelo fanout) |
| Publicação | `mandatory`, com *publisher confirms* |

A Ingestão declara a exchange ao iniciar, com exatamente esses parâmetros. As **filas** de cada consumidor, com retry e DLQ, são declaradas pela topologia do RabbitMQ (Frente 2, ADR 0007), e não pela Ingestão.

Como a publicação é `mandatory`, se nenhuma fila estiver ligada à exchange o broker devolve a mensagem e a Ingestão responde `503` em vez de perder a notificação em silêncio.

### 2.2 Propriedades AMQP

| Propriedade | Valor |
|---|---|
| `content_type` | `application/json` |
| `delivery_mode` | `2` (persistente) |
| `message_id` | igual a `notificacao_id` |
| `type` | `notificacao.recebida` |
| `timestamp` | instante da publicação |

### 2.3 Corpo (versão 1)

```json
{
  "evento_id": "9b2e4f60-1c3a-4d7e-8f90-5a6b7c8d9e01",
  "tipo": "notificacao.recebida",
  "versao": 1,
  "notificacao_id": "3f1c9a2e-5b7d-4e8a-9c1f-2a6b8d4e0f11",
  "unidade_id": "unidade-001",
  "agravo": "dengue",
  "municipio_ibge": "2507507",
  "bairro": "Mangabeira",
  "semana_epidemiologica": "2026-46",
  "data_inicio_sintomas": "2026-11-15",
  "data_notificacao": "2026-11-17",
  "enviado_em": "2026-11-17T14:03:12.123000Z",
  "recebido_em": "2026-11-17T14:03:12.140512Z"
}
```

| Campo | Origem | Descrição |
|---|---|---|
| `evento_id` | Ingestão | UUID novo a cada publicação. Serve para rastrear a mensagem, **não** para idempotência |
| `tipo` | Ingestão | Sempre `notificacao.recebida` nesta versão |
| `versao` | Ingestão | Versão do contrato do evento (seção 5) |
| `notificacao_id` | Unidade | **Chave de idempotência dos consumidores** |
| `unidade_id` | Gateway | Valor de `X-Consumer-Username` |
| `agravo`, `municipio_ibge`, `bairro`, `data_inicio_sintomas`, `data_notificacao`, `enviado_em` | Unidade | Copiados da requisição, já validados |
| `semana_epidemiologica` | Ingestão | Calculada a partir de `data_inicio_sintomas` (seção 2.4) |
| `recebido_em` | Ingestão | Instante em que a Ingestão recebeu a requisição, em UTC |

Datas e horas usam ISO 8601. Os instantes (`enviado_em`, `recebido_em`) sempre têm fuso horário. O atraso fim a fim é medido a partir de `enviado_em`.

### 2.4 Semana epidemiológica

Formato `AAAA-SS`, por exemplo `2026-46`. É calculada **uma única vez, na Ingestão**, para que Agregação e Alertas nunca divirjam.

Regra (a mesma do calendário epidemiológico usado pelo SINAN):

- a semana vai de **domingo a sábado**;
- a semana 1 de um ano é a que contém o dia **4 de janeiro**, ou seja, a primeira semana com pelo menos 4 dias no ano;
- por isso, alguns dias do início de janeiro pertencem à última semana do ano anterior, e alguns anos têm 53 semanas.

| Data | Semana epidemiológica |
|---|---|
| 2024-12-29 (domingo) | `2025-01` |
| 2026-01-01 (quinta-feira) | `2025-53` |
| 2026-01-04 (domingo) | `2026-01` |
| 2026-11-15 (domingo) | `2026-46` |
| 2026-12-31 (quinta-feira) | `2026-52` |

A ordenação alfabética de `AAAA-SS` coincide com a ordem cronológica, o que facilita filtros por intervalo (`se_de`, `se_ate`).

---

## 3. Obrigações dos consumidores

Valem para a Agregação, os Alertas e qualquer consumidor futuro.

1. **Idempotência por `notificacao_id`.** A entrega é *at-least-once*: a mesma notificação pode chegar mais de uma vez (redelivery do broker, reenvio da unidade quando o Redis da Ingestão estiver indisponível). Cada consumidor deve garantir que o mesmo `notificacao_id` só seja contado uma vez, por exemplo com chave primária e `INSERT … ON CONFLICT DO NOTHING` (ADR 0006).
2. **Sem garantia de ordem.** Não presumir que os eventos chegam na ordem de `enviado_em`.
3. **Validação de domínio.** A Ingestão valida o **formato**; o consumidor valida as **regras de domínio**. Um `municipio_ibge` fora da tabela de referência (seção 4) é falha definitiva: vai para a DLQ, sem retry.
4. **Mensagem fora do contrato vai para a DLQ.** JSON malformado, `tipo` diferente de `notificacao.recebida` ou `versao` desconhecida são falhas definitivas.
5. **Campos desconhecidos são ignorados.** O consumidor não deve rejeitar um evento por conter um campo a mais; isso permite evoluir o contrato sem quebrar quem já consome (seção 5).

---

## 4. Municípios de referência

Dados sintéticos com códigos IBGE de municípios da Paraíba. A tabela `municipios` do PostgreSQL (Frente 3) deve ser semeada com estes códigos, e o simulador sorteia notificações entre eles. Os nomes de bairro são apenas rótulos sintéticos.

| Código IBGE | Município |
|---|---|
| `2507507` | João Pessoa |
| `2504009` | Campina Grande |
| `2513703` | Santa Rita |
| `2501807` | Bayeux |
| `2503209` | Cabedelo |
| `2510808` | Patos |
| `2516201` | Sousa |
| `2503704` | Cajazeiras |

O código `9999999` é usado pelo simulador e pelos testes como **município inexistente**: tem formato válido (a Ingestão aceita), mas deve terminar na DLQ dos consumidores.

---

## 5. Versionamento

| Tipo de mudança | Exemplo | Versão |
|---|---|---|
| Compatível | Adicionar um campo **opcional** ao evento | Mantém `versao` |
| Incompatível | Remover ou renomear campo, mudar tipo ou significado | Nova `versao`; durante a transição, os consumidores aceitam as duas |

Na API HTTP, um campo novo **obrigatório** na entrada também é incompatível, porque as unidades já em uso deixariam de ser aceitas.

---

## 6. Como alterar este contrato

1. Abrir um pull request que altere, juntos, este documento, `services/ingestion/app/contrato.py` e os arquivos `*.schema.json` (regerados conforme a seção 7).
2. Pedir revisão aos donos dos consumidores afetados (Agregação e Alertas).
3. Registrar a mudança na tabela abaixo.

| Versão | Data | Mudança |
|---|---|---|
| 1 | 20/11/2026 | Versão inicial |

---

## 7. Exemplos e ferramentas

Enviar uma notificação direto à Ingestão, em desenvolvimento (antes do Gateway):

```bash
curl -i -X POST http://localhost:8001/api/v1/notificacoes \
  -H "Content-Type: application/json" \
  -H "X-Consumer-Username: unidade-001" \
  -d '{
        "notificacao_id": "3f1c9a2e-5b7d-4e8a-9c1f-2a6b8d4e0f11",
        "agravo": "dengue",
        "municipio_ibge": "2507507",
        "bairro": "Mangabeira",
        "data_inicio_sintomas": "2026-11-15",
        "data_notificacao": "2026-11-17",
        "enviado_em": "2026-11-17T14:03:12.123Z"
      }'
```

Regerar os esquemas JSON depois de alterar `contrato.py`:

```bash
cd services/ingestion
python -m app.contrato ../../docs/contratos
```

Validar um evento em um consumidor Python: copiar o modelo `EventoNotificacao` de `contrato.py` ou validar contra `evento-notificacao.schema.json`.
