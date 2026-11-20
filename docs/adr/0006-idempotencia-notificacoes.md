### ADR 0006 — Idempotência das notificações em duas camadas

**Status:** Aceito — primeira camada implementada no Serviço de Ingestão; segunda camada a cargo dos consumidores (Agregação e Alertas).

**Contexto e problema:** Uma unidade de saúde pode enviar a mesma notificação mais de uma vez: quando a resposta se perde por timeout, quando o Gateway responde `429` ou quando o broker está indisponível e a unidade tenta de novo. Além disso, o RabbitMQ entrega mensagens *at-least-once*: um consumidor que cai antes de confirmar (`ack`) recebe a mesma mensagem outra vez. O critério de sucesso do projeto exige que o reenvio **não duplique casos**. No Projeto 02, ficou em aberto onde guardar os IDs já vistos, porque a Ingestão só tinha acesso ao RabbitMQ.

**Forças que influenciaram a decisão:**

- a contagem de casos é a informação central do painel e dos alertas, então uma duplicata distorce diretamente o resultado;
- a duplicação pode surgir em dois pontos diferentes: na entrada (reenvio da unidade) e no consumo (redelivery do broker);
- a Ingestão precisa responder rápido (meta de p95 abaixo de 200 ms), então a verificação não pode pesar no caminho de escrita;
- a unidade deve saber quando um reenvio foi reconhecido, para parar de reenviar;
- o caminho de escrita não deve parar só porque um componente auxiliar caiu;
- uma falha na publicação não pode deixar o ID "preso", impedindo o reenvio legítimo.

**Decisão:** Tratar a idempotência em duas camadas, sempre pela chave `notificacao_id`, um UUID gerado pela unidade e definido no [contrato](../contratos/evento-notificacao.md).

**Camada 1 — Ingestão, no Redis.** Cada `notificacao_id` passa por dois estados:

1. `SET alertasus:notificacao:<id> pendente NX EX 30`: reserva o ID enquanto o evento é publicado. Se a reserva falha e o estado é `publicada`, a Ingestão responde `200` com `"status": "duplicada"` e não publica de novo. Se o estado é `pendente`, outra requisição com o mesmo ID está em andamento, e a resposta é `409` com `Retry-After`.
2. Depois que o RabbitMQ confirma a publicação, o estado passa a `publicada` com prazo de 24 horas.
3. Se a publicação falha, a reserva é removida e a unidade recebe `503`; o reenvio dela será aceito.
4. Se o próprio Redis estiver indisponível, a notificação é aceita e publicada sem a verificação (*fail-open*), e o evento é registrado na métrica `alertasus_idempotencia_indisponivel_total`.

**Camada 2 — consumidores, no PostgreSQL.** Cada consumidor grava o `notificacao_id` em uma tabela com chave primária (`casos` na Agregação; `alertas_processadas` nos Alertas) com `INSERT … ON CONFLICT DO NOTHING`, **na mesma transação** que aplica o efeito (contar o caso, atualizar o contador do alerta). Um evento repetido não altera nada e é confirmado normalmente.

**Alternativas consideradas:**

1. **Somente nos consumidores (restrição `UNIQUE`):** é a garantia mais forte e não depende do Redis, mas os reenvios entrariam no broker e seriam processados por todos os consumidores, e a unidade não teria como saber que o reenvio foi reconhecido.
2. **Somente na Ingestão (Redis):** evita duplicatas na entrada, mas não cobre o redelivery do broker, nem o período em que o Redis estiver fora do ar ou tiver perdido dados.
3. **Tabela de IDs no PostgreSQL, consultada pela Ingestão:** seria durável, mas colocaria uma escrita no banco compartilhado em toda requisição do caminho de escrita, aumentando a latência e acoplando a Ingestão ao esquema dos outros serviços.
4. **Redis com *fail-closed* (responder `503` sem o Redis):** evitaria qualquer duplicata no broker durante a falha, mas tornaria o Redis uma dependência obrigatória para aceitar notificações, justamente o que a separação entre recebimento e processamento quer evitar.
5. **Um único estado (`publicada`) gravado antes de publicar:** é mais simples, mas, se a publicação falhasse, o ID ficaria marcado como aceito sem que o evento existisse, e o reenvio seria respondido como duplicado. A notificação se perderia.
6. **Deduplicar pelo conteúdo (hash dos campos):** dispensaria o ID, mas dois casos legítimos com os mesmos dados (mesmo agravo, bairro e datas) seriam tratados como um só.

**Consequências positivas:**

- o critério "reenvio não duplica casos" fica garantido mesmo com redelivery do broker e com o Redis fora do ar;
- reenvios são descartados antes do broker na operação normal, sem custo para Agregação e Alertas;
- a unidade recebe uma resposta clara para cada situação (`202`, `200 duplicada`, `409`, `503`);
- uma falha na publicação não bloqueia o ID, então o reenvio legítimo é aceito;
- o Redis continua sendo um componente de aceleração, e não um ponto único de falha da escrita.

**Consequências negativas e riscos:**

- há duas implementações da mesma regra para manter coerentes; o contrato (seção 3) torna a segunda camada uma obrigação explícita dos consumidores;
- a janela da camada 1 é de 24 horas; um reenvio depois disso passa pela Ingestão e só é barrado nos consumidores;
- durante uma falha do Redis, reenvios chegam ao broker e geram trabalho repetido (sem alterar as contagens);
- o estado `409` é mais uma resposta que a unidade e o simulador precisam tratar;
- o Redis passa a guardar dois tipos de dado, cache da Consulta e IDs da Ingestão. Se uma política de descarte por memória for configurada, ela deve ser do tipo `volatile-*` (as duas chaves têm prazo de expiração) e, mesmo que um ID seja descartado, a camada 2 impede a duplicata;
- o volume de chaves cresce com a taxa de envio: a 500 notificações/s, cada minuto adiciona 30 mil chaves. O prazo de 24 horas atende à demonstração e aos testes; com tráfego contínuo nesse nível, seria preciso reduzir o prazo ou dimensionar a memória.

**Relação com a implementação:** A camada 1 está em [`services/ingestion/app/idempotencia.py`](../../services/ingestion/app/idempotencia.py) e é usada em [`app/main.py`](../../services/ingestion/app/main.py); o `docker-compose.yml` passou a dar à Ingestão acesso ao Redis. Os testes unitários cobrem os estados, a liberação após falha de publicação e o *fail-open*. O teste de integração T4 ([`tests/integration/test_ingestao.py`](../../tests/integration/test_ingestao.py)) confere que três envios geram um único evento no broker e, quando o Serviço de Agregação existir, uma única linha em `casos`. A camada 2 será implementada pelas Frentes 2 e 3.
