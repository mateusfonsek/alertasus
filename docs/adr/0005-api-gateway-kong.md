### ADR 0005 — API Gateway com Kong em modo DB-less

**Status:** Aceito — tecnologia definida; container e configuração serão implementados no Projeto 03.

**Contexto e problema:** O AlertaSUS recebe notificações de várias unidades de saúde e expõe uma API de leitura para o painel. A proposta prevê um ponto único de entrada que autentique cada unidade com seu próprio token e limite o volume de envios de cada uma, para que uma unidade com excesso de requisições não degrade as demais (critério de sucesso "isolamento por unidade": a unidade abusiva recebe HTTP 429 e as outras mantêm o p95). Até o Projeto 02, a escolha entre Kong e Traefik estava em aberto. Os dois requisitos centrais, autenticação e limite, são **por unidade**: o Gateway precisa saber qual unidade fez a requisição antes de aplicar o limite e precisa repassar essa identidade aos serviços.

**Forças que influenciaram a decisão:**

- validação de JWT no Gateway, sem duplicar essa lógica em cada microsserviço;
- rate limiting contado por unidade autenticada, e não por IP ou por um cabeçalho que a própria unidade poderia falsificar;
- repasse da identidade da unidade à Ingestão, para que uma unidade não se passe por outra no corpo da notificação;
- exposição de métricas ao Prometheus, para medir requisições, respostas 401 e 429 por unidade;
- configuração versionada no repositório e reproduzível com o Docker Compose;
- poucas rotas fixas (notificações e consultas), sem necessidade de descoberta dinâmica de serviços.

**Decisão:** Adotar o **Kong Gateway em modo DB-less**, com a configuração declarada em um arquivo versionado (`gateway/kong.yml`) e sem banco de dados próprio. Cada unidade de saúde será um *consumer* do Kong com credencial JWT própria; o painel (Grafana) terá um *consumer* dedicado. Serão usados três plugins nativos:

- `jwt` nas rotas de notificação e de consulta, para validar o token de cada unidade;
- `rate-limiting` com contagem por consumidor, devolvendo HTTP 429 quando a unidade excede o próprio limite;
- `prometheus`, para expor as métricas do Gateway.

O roteamento será `POST /api/v1/notificacoes` → Serviço de Ingestão e `GET /api/v1/casos*` e `GET /api/v1/alertas*` → Serviço de Consulta. Depois de validar o token, o Kong injeta o cabeçalho `X-Consumer-Username` na requisição; a Ingestão usa esse valor como identificador da unidade, em vez de confiar em um campo enviado no corpo.

**Alternativas consideradas:**

1. **Traefik:** é mais leve e descobre serviços automaticamente pelas labels do Docker, mas a versão gratuita não valida JWT nativamente. Seria necessário usar `forwardAuth` apontando para um serviço de autenticação escrito pela equipe ou um plugin da comunidade. Seu middleware de rate limiting conta por IP ou por cabeçalho; sem autenticação resolvida antes, a unidade poderia informar outro identificador. A descoberta automática, seu principal ponto forte, traz pouco ganho com apenas duas rotas fixas.
2. **Autenticação e limite dentro de cada serviço FastAPI:** dispensaria um container a mais, porém duplicaria a lógica de segurança na Ingestão e na Consulta, misturaria responsabilidades de borda com regras de negócio e deixaria o limite por unidade sem um ponto central de controle.
3. **NGINX ou Envoy configurados manualmente:** são proxies robustos, mas a validação de JWT e o limite por consumidor exigiriam módulos adicionais ou scripts próprios, com mais configuração e menos recursos prontos do que o Kong.
4. **Kong com banco de dados (PostgreSQL):** permitiria alterar consumidores pela Admin API em tempo de execução, mas adicionaria um banco e migrações ao ambiente. No projeto, os consumidores são conhecidos de antemão e podem ser gerados por script.

**Consequências positivas:**

- autenticação, limite por unidade e roteamento ficam concentrados na borda, fora do código de negócio;
- o critério de isolamento por unidade passa a ser testável diretamente: o excesso de uma unidade recebe HTTP 429 sem afetar o limite das outras;
- a Ingestão recebe a identidade da unidade já validada, o que impede que uma unidade notifique em nome de outra;
- a configuração declarativa é revisável por pull request e sobe junto com o Compose;
- as métricas do Gateway complementam as dos serviços no Prometheus e no painel técnico.

**Consequências negativas e riscos:**

- o Kong consome mais memória e tem mais conceitos (serviços, rotas, consumers, plugins) do que o Traefik, o que aumenta a curva de aprendizado;
- em modo DB-less, consumidores e credenciais ficam no arquivo declarativo; o arquivo precisa ser gerado por script e os segredos das credenciais não podem ser versionados em texto aberto;
- com a política `local`, os contadores de rate limiting ficam na memória de cada instância do Kong; se o Gateway for replicado, será necessário trocar para a política `redis`, aproveitando o Redis existente;
- o Gateway passa a ser um ponto único de falha da entrada e precisa de health check no Compose;
- os serviços deixam de dever ser acessados diretamente pela rede do host, o que exige ajustar as portas publicadas no Compose e os testes que hoje chamam as portas 8001 a 8004;
- ao fixar a tag da imagem, é preciso confirmar que os plugins `jwt`, `rate-limiting` e `prometheus` estão disponíveis na edição gratuita da versão escolhida.

**Relação com a implementação:** Nesta etapa, a decisão está registrada e refletida nos diagramas C4 e no stack. O Gateway ainda não faz parte do `docker-compose.yml`, e os serviços continuam expostos diretamente nas portas 8001 a 8004 para o desenvolvimento local. No Projeto 03 serão criados o container do Kong, o arquivo `gateway/kong.yml`, o script de geração dos tokens das unidades e os testes de autenticação (HTTP 401) e de isolamento por unidade (HTTP 429).
