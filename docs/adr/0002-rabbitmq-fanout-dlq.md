### ADR 0002 — RabbitMQ com fanout e Dead-Letter Queue

**Status:** Aceito — infraestrutura preparada; topologia de negócio pendente.

**Contexto e problema:** Cada notificação deve alimentar pelo menos dois processamentos independentes: a atualização das agregações e a verificação de limiares para geração de alertas. O produtor não deve precisar conhecer a implementação ou a disponibilidade de cada consumidor. Além disso, uma falha temporária não deve descartar o evento, enquanto uma mensagem inválida não deve ser repetida indefinidamente e bloquear a fila.

**Forças que influenciaram a decisão:**

- distribuição de um mesmo evento para múltiplos consumidores;
- desacoplamento temporal entre produtor e consumidores;
- possibilidade de cada consumidor ter sua própria fila e ritmo de processamento;
- confirmação de entrega e retenção durante indisponibilidades;
- tratamento explícito de falhas permanentes por meio da DLQ.

**Decisão:** Adotar RabbitMQ como broker assíncrono. O Serviço de Ingestão publicará notificações em uma exchange `fanout`; essa exchange distribuirá cópias para uma fila de Agregação e uma fila de Alertas. Mensagens com falhas transitórias deverão passar por retry controlado. Mensagens inválidas ou que excederem o limite de tentativas deverão ser encaminhadas para uma Dead-Letter Queue, preservando o conteúdo para investigação e possível reprocessamento.

**Alternativas consideradas:**

1. **Chamadas HTTP síncronas entre Ingestão, Agregação e Alertas:** simplificariam o fluxo inicial, mas aumentariam o acoplamento e fariam a disponibilidade do produtor depender dos consumidores.
2. **Redis Streams:** poderia atender a parte do fluxo, mas RabbitMQ oferece recursos mais diretamente alinhados a exchanges, filas, confirmações e DLQs.
3. **Kafka:** seria adequado para alto volume e retenção de eventos, porém adicionaria complexidade operacional desnecessária para o escopo atual.
4. **Uma única fila compartilhada:** não permitiria que Agregação e Alertas recebessem independentemente a mesma notificação.

**Consequências positivas:**

- Agregação e Alertas podem parar ou escalar de forma independente;
- mensagens podem aguardar enquanto um consumidor está indisponível;
- a DLQ evita perda silenciosa e facilita diagnóstico;
- o produtor permanece desacoplado da lógica dos consumidores.

**Consequências negativas e riscos:**

- a topologia precisa ser configurada corretamente, incluindo exchange, filas, bindings e políticas;
- retry mal configurado pode causar tempestade de mensagens ou reprocessamento infinito;
- consumidores precisam ser idempotentes para lidar com redelivery;
- é necessário monitorar tamanho das filas, idade das mensagens e volume da DLQ;
- a ordem global dos eventos não é garantida entre consumidores independentes.

**Relação com a implementação:** O container RabbitMQ, suas portas e sua URL interna já estão definidos no `docker-compose.yml`. A exchange, as filas, os consumidores, as confirmações e a DLQ ainda não foram implementados nesta base.
