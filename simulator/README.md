# Simulador de unidades de saúde

Gera notificações **sintéticas** e as envia em ritmo controlado, fazendo o papel das unidades de saúde na demonstração. Fica fora da fronteira do AlertaSUS (C4 nível 2). Para os testes de carga, use os scripts k6 em [`tests/load/`](../tests/load/).

> **Limite prático: cerca de 150 notificações/s.** O simulador é um único processo Python e satura um núcleo de CPU por volta dessa taxa (medido em 20/11/2026). Acima disso, ele não consegue manter o ritmo pedido, e as latências que reporta passam a incluir a espera dentro dele próprio. Para medir a capacidade da Ingestão, use o k6.

## Como rodar

Pelo Docker Compose, com o ambiente no ar (o simulador está no perfil `demo` e não sobe com `docker compose up`):

```bash
docker compose run --rm simulator --cenario surto --taxa 20 --duracao 120
```

Ou localmente, apontando para a porta publicada da Ingestão:

```bash
cd simulator
pip install -r requirements.txt
python -m simulador --cenario normal --taxa 10 --duracao 30 --url http://localhost:8001
```

Ao final, o simulador imprime quantas respostas de cada código recebeu por categoria, ao lado da resposta esperada. Exemplo do cenário `duplicadas` a 10/s, contra a Ingestão com Redis e RabbitMQ simulados em memória (por isso as latências são tão baixas):

```text
Enviadas: 120 em 11.91 s (10.1/s)
Latência (ms): p50=2.5 p95=3.4 p99=3.7

categoria          respostas                        esperado
original           202×40                           202
reenvio            200×80                           200 duplicada (a notificação não é contada de novo)
```

## Cenários

| Cenário | O que faz | Para demonstrar |
|---|---|---|
| `normal` | Notificações distribuídas entre os municípios de referência | Fluxo básico |
| `surto` | A fração de casos de dengue em Mangabeira (João Pessoa) cresce de 20% para 80% ao longo da execução | Painel mostrando o foco e alerta disparando |
| `duplicadas` | Cada notificação é enviada 3 vezes pela mesma unidade | Idempotência: 1×`202` e 2×`200 duplicada` |
| `invalidas` | Metade válida; 1/4 fora do esquema (6 variações); 1/4 com município inexistente (`9999999`) | `422` na Ingestão e mensagens na DLQ dos consumidores |
| `unidade-abusiva` | Metade do tráfego vem da `unidade-001` | Rate limiting por unidade: `429` só para ela (com o Gateway) |

Todas as notificações de um envio caem na **semana epidemiológica corrente**, para que o surto some no mesmo limiar.

## Opções

| Opção | Padrão | Descrição |
|---|---|---|
| `--cenario` | `normal` | Um dos cenários acima |
| `--taxa` | `10` | Notificações por segundo (total, somando as unidades) |
| `--duracao` | `30` | Segundos; o total enviado é `taxa × duração` |
| `--unidades` | `50` | Unidades simuladas (`unidade-001` …) |
| `--concorrencia` | `100` | Requisições simultâneas no máximo |
| `--url` | `$ALVO_URL` ou `http://localhost:8001` | Ingestão (modo direto) ou Gateway (com `--tokens`) |
| `--tokens` | — | Arquivo JSON `{"unidade-001": "<jwt>", …}`; ativa o modo Gateway |
| `--semente` | — | Torna os sorteios reprodutíveis (os IDs continuam únicos a cada execução) |
| `--saida-json` | — | Grava o relatório em JSON, por exemplo em `docs/testes/dados/` |

## Modos de autenticação

- **Direto** (padrão, antes do Gateway): envia o cabeçalho `X-Consumer-Username` com a unidade, como o Kong faria.
- **Gateway**: com `--tokens`, envia `Authorization: Bearer <jwt>` de cada unidade. Os tokens serão gerados pelo `scripts/gerar_tokens.py` (Frente 5).

## Testes

```bash
cd simulator
ruff check . && pytest -q
```
