### ADR 0003 — PostgreSQL e Redis com Materialized Views

**Status:** Aceito — componentes disponíveis; modelo de dados pendente.

**Contexto e problema:** O painel precisa consultar casos por município, bairro e semana epidemiológica, além de alertas disparados. Fazer agregações diretamente sobre todos os eventos a cada requisição aumentaria o custo da leitura e poderia comprometer a meta de p95 inferior a 100 ms. Também é necessário manter uma fonte persistente e consistente para os dados, sem transformar o cache na única fonte de verdade.

**Forças que influenciaram a decisão:**

- necessidade de consultas agregadas por dimensões epidemiológicas;
- persistência relacional e consistência transacional para os dados processados;
- redução do custo de recomputar agregações;
- baixa latência para consultas repetidas;
- possibilidade de reconstruir ou atualizar o cache a partir do PostgreSQL.

**Decisão:** Utilizar PostgreSQL como fonte persistente para notificações processadas, agregações e alertas. O Serviço de Agregação deverá manter Materialized Views por município, bairro e semana epidemiológica. O Serviço de Consulta deverá seguir o padrão cache-aside: primeiro consulta o Redis; em caso de cache miss, consulta as views no PostgreSQL e grava a resposta no Redis com TTL definido.

**Alternativas consideradas:**

1. **Calcular as agregações em cada requisição:** reduziria a necessidade de atualização de views, mas aumentaria a latência e o uso de CPU/banco sob carga.
2. **Usar somente Redis:** ofereceria baixa latência, porém não seria adequado como fonte principal durável para o histórico e dificultaria reconstrução dos dados.
3. **Usar somente PostgreSQL sem cache:** simplificaria a operação, mas perderia desempenho em consultas repetidas e concorrentes.
4. **Banco NoSQL:** poderia facilitar algumas escritas, mas não oferece vantagem suficiente para as consultas relacionais e agregações previstas nesta etapa.

**Consequências positivas:**

- as consultas leem resultados pré-agregados;
- o Redis reduz leituras repetidas no PostgreSQL;
- o PostgreSQL permanece como fonte de recuperação quando o cache expira;
- a combinação atende à meta de desempenho sem sacrificar a persistência relacional.

**Consequências negativas e riscos:**

- Materialized Views podem ficar desatualizadas até sua atualização;
- o cache pode devolver respostas temporariamente antigas;
- TTL e invalidação precisam ser definidos por tipo de consulta;
- alterações no modelo de dados exigirão migrações e possível reconstrução das views;
- o PostgreSQL compartilhado cria acoplamento entre Agregação, Alertas e Consulta.

**Relação com a implementação:** PostgreSQL, Redis, volume `pg_data` e variáveis de conexão já estão declarados no Compose. Ainda não existem schema, migrações, Materialized Views, consultas de negócio ou integração efetiva com Redis nesta entrega.
