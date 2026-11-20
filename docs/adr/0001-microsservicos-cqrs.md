### ADR 0001 — Microsserviços com CQRS

**Status:** Aceito — arquitetura-base do Projeto 02.

**Contexto e problema:** O AlertaSUS recebe notificações de várias unidades de saúde e precisa continuar aceitando novos eventos mesmo quando há um pico de volume. Ao mesmo tempo, a equipe de vigilância precisa consultar agregações e alertas com baixa latência. Se o mesmo componente recebesse, validasse, processasse, agregasse e consultasse todos os dados de forma síncrona, uma carga elevada de escrita poderia degradar o painel e dificultar a evolução independente das funcionalidades.

**Forças que influenciaram a decisão:**

- separar o recebimento rápido das notificações do processamento mais pesado;
- permitir escalabilidade independente dos fluxos de escrita e leitura;
- reduzir o acoplamento entre ingestão, agregação, alertas e consulta;
- manter o caminho de leitura otimizado para as necessidades do painel;
- facilitar a evolução dos serviços sem transformar uma alteração em um deploy monolítico.

**Decisão:** Adotar uma arquitetura de microsserviços com CQRS. O Serviço de Ingestão representa a entrada de comandos e notificações; Agregação e Alertas processam os eventos de forma assíncrona; e o Serviço de Consulta representa o lado de leitura, acessando dados agregados e cache. A separação é lógica e também estrutural: cada serviço possui seu próprio diretório, `Dockerfile`, `requirements.txt`, aplicação FastAPI e testes.

**Alternativas consideradas:**

1. **Aplicação monolítica síncrona:** seria mais simples no início, mas concentraria os picos de escrita e leitura no mesmo processo e dificultaria o isolamento dos componentes.
2. **Serviço único com módulos internos:** reduziria a complexidade operacional, porém manteria maior acoplamento de implantação e de escala.
3. **Separação completa com bancos independentes desde o início:** ofereceria isolamento maior, mas aumentaria a complexidade de consistência, migrações e operação para o estágio inicial do projeto.

**Consequências positivas:**

- ingestão, processamento e consulta podem ser dimensionados separadamente;
- uma falha ou lentidão no processamento não precisa interromper imediatamente a entrada de notificações;
- as responsabilidades ficam explícitas e alinhadas aos limites dos serviços;
- o modelo de leitura pode ser otimizado para consultas agregadas.

**Consequências negativas e riscos:**

- surge consistência eventual entre a notificação recebida e o dado exibido no painel;
- rastreamento, observabilidade e diagnóstico ficam mais complexos;
- eventos podem ser duplicados ou processados fora de ordem, exigindo idempotência;
- a solução depende de contratos estáveis entre serviços e de mecanismos de retry.

**Relação com a implementação:** A decisão já aparece na separação dos quatro serviços FastAPI e no Compose. Nesta entrega, eles ainda possuem endpoints básicos de health check; consumidores, comandos, consultas e persistência de negócio serão implementados nas próximas etapas.
