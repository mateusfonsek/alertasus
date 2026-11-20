### ADR 0004 — Docker Compose para desenvolvimento e CI

**Status:** Aceito — padrão de execução local e validação contínua.

**Contexto e problema:** O projeto possui quatro microsserviços Python e três componentes de infraestrutura. Instalar e configurar tudo manualmente em cada máquina produziria diferenças de ambiente, problemas de dependência e uma entrada mais difícil para novos integrantes. O pipeline também precisa verificar se a composição continua válida.

**Forças que influenciaram a decisão:**

- execução local com um comando padronizado;
- isolamento de dependências entre serviços;
- rede interna reproduzível;
- healthchecks para controlar a ordem de inicialização;
- validação automatizada no GitHub Actions;
- baixo custo operacional para o estágio acadêmico do projeto.

**Decisão:** Utilizar Docker Compose v2 para orquestrar RabbitMQ, PostgreSQL, Redis e os quatro microsserviços em uma rede comum. Cada microsserviço possui seu próprio `Dockerfile` e `requirements.txt`. O Compose usa `depends_on` com `service_healthy`; o CI executa `docker compose config -q`, além de lint e testes em uma matriz por serviço.

**Alternativas consideradas:**

1. **Execução manual com Python local:** exigiria instalação e configuração repetidas, além de aumentar diferenças entre ambientes.
2. **Um único Dockerfile para toda a aplicação:** reduziria arquivos, mas eliminaria o isolamento de dependências e processos.
3. **Kubernetes desde o início:** seria mais próximo de uma operação de produção, porém desproporcional à escala e ao objetivo desta entrega.
4. **Máquinas virtuais ou scripts específicos por sistema operacional:** aumentariam a manutenção e reduziriam a portabilidade.

**Consequências positivas:**

- ambiente local reproduzível para toda a equipe;
- containers isolados e conectados por nomes de serviço;
- infraestrutura e serviços podem ser iniciados, verificados e encerrados de forma uniforme;
- o CI detecta erros de sintaxe e de qualidade antes da integração;
- o volume `pg_data` preserva os dados do PostgreSQL entre reinicializações comuns.

**Consequências negativas e riscos:**

- Docker passa a ser um pré-requisito para execução completa;
- os containers consomem memória, CPU e portas locais;
- credenciais no Compose são aceitáveis apenas para desenvolvimento local;
- o volume do PostgreSQL exige limpeza consciente com `docker compose down -v`;
- Compose não fornece, sozinho, alta disponibilidade, autoscaling ou observabilidade de produção.

**Relação com a implementação:** O ambiente é iniciado com `docker compose up --build -d` e contém sete containers: RabbitMQ, PostgreSQL, Redis, Ingestão, Agregação, Alertas e Consulta. Os healthchecks usam `rabbitmq-diagnostics`, `pg_isready` e `redis-cli ping`; o workflow do GitHub Actions valida o Compose e executa `ruff` e `pytest` para os quatro serviços.
