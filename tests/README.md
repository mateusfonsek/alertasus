# Testes de integração e de carga

Os testes unitários ficam dentro de cada serviço (`services/*/tests`) e rodam no CI. Esta pasta reúne os testes que precisam do ambiente completo no ar.

| Pasta | Tipo | Ferramenta |
|---|---|---|
| [`integration/`](integration/) | Integração, contra o Docker Compose em execução | pytest |
| [`load/`](load/) | Carga | k6 |

Os resultados de cada execução vão para `docs/testes/dados/` (saídas brutas) e são consolidados em `docs/testes/resultados.md`.

## Integração

```bash
docker compose up --build -d
pip install -r tests/integration/requirements.txt
pytest -q tests/integration
```

Sem o ambiente no ar, os testes são **pulados** (não falham) e informam o motivo.

| Teste | Critério | O que verifica |
|---|---|---|
| `test_t4_reenvio_nao_gera_novo_evento` | T4 | 3 envios iguais: `202`, `200`, `200` e um único evento no broker |
| `test_evento_publicado_segue_o_contrato` | Contrato | Campos, semana epidemiológica, unidade e propriedades AMQP do evento |
| `test_corpo_fora_do_contrato_nao_e_publicado` | Contrato | `422` e nenhum evento |
| `test_requisicao_sem_identificacao_da_unidade_e_recusada` | Segurança | `401` |
| `test_t4_caso_contado_uma_unica_vez_no_banco` | T4 | Uma linha em `casos`; pulado até a tabela existir (Frente 3) |

Os eventos são observados por uma **fila espiã**: uma fila temporária ligada à exchange `notificacoes`. Como a exchange é fanout, ela recebe uma cópia sem interferir nas filas dos consumidores.

Variáveis de ambiente: `INGESTAO_URL` (padrão `http://localhost:8001`), `RABBITMQ_URL`, `DATABASE_URL`. Quando o Gateway existir, defina `INGESTAO_URL` com a URL do Kong, `TOKEN_UNIDADE` com o JWT de uma unidade e `UNIDADE_ESPERADA` com o nome dela.

## Carga (k6)

### T1 — Vazão de ingestão

Meta: ≥ 500 notificações/s com p95 da API < 200 ms. O script [`load/ingestao.js`](load/ingestao.js) tem três fases:

| Fase | Duração | Taxa | Avaliação |
|---|---|---|---|
| `aquecimento` | 60 s | 50 → 500/s | — |
| `patamar` | 120 s | 500/s constante | **p95 < 200 ms e > 99% de `202`** |
| `acima_da_meta` | 90 s | 500 → 700/s | Procura o limite; sem meta |

Antes de rodar:

1. Subir o ambiente com `LOG_LEVEL=WARNING` na Ingestão, para que o log de cada notificação não pese na medição.
2. Garantir que **existe ao menos uma fila ligada à exchange** `notificacoes` (topologia da Frente 2). Sem fila, a Ingestão responde `503` de propósito, para não perder notificações.
3. Anotar a máquina (CPU, memória, sistema operacional). O k6 roda na mesma máquina e disputa CPU com o ambiente.

Forma recomendada: k6 em container, **na mesma rede do Compose**, acessando a Ingestão pelo nome do serviço. No Windows e no macOS, passar pelas portas publicadas no host (`localhost:8001`) acrescenta o encaminhamento de portas do Docker Desktop à latência medida.

```bash
docker run --rm --network alertasus_alertasus-net \
  -v "$PWD/tests/load:/scripts" -v "$PWD/docs/testes/dados:/dados" \
  -e ALVO_URL=http://ingestion:8000 grafana/k6:0.54.0 \
  run --summary-export /dados/t1-ingestao.json /scripts/ingestao.js
```

No Git Bash do Windows, prefixe o comando com `MSYS_NO_PATHCONV=1` para os caminhos `/scripts` e `/dados` não serem convertidos.

Com o k6 instalado na máquina (passa pela porta publicada):

```bash
cd tests/load
k6 run --summary-export ../../docs/testes/dados/t1-ingestao.json ingestao.js
```

Variáveis: `ALVO_URL`, `TAXA_META` (500), `TAXA_MAX` (700), `UNIDADES` (50) e `TOKENS_ARQUIVO` (JSON de tokens; ativa o modo Gateway).

**Como ler o resultado:**

- `http_req_duration{scenario:patamar}` p(95): é a meta;
- `http_reqs{scenario:patamar}`: a taxa efetiva; deve ficar perto de 500/s;
- `dropped_iterations` maior que zero: o k6 não conseguiu gerar a carga pedida, e a medição não vale para a meta. Aumente `maxVUs` ou rode o k6 em outra máquina;
- `checks{scenario:patamar}` abaixo de 99%: veja quais códigos voltaram (`503` indica broker sem fila ou fora do ar).
