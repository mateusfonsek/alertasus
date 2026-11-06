# Diagramas C4: AlertaSUS

Diagramas de arquitetura no modelo [C4](https://c4model.com/), níveis 1 e 2, entregues no Projeto 02.

| Nível | Arquivo | Pergunta que responde |
|---|---|---|
| 1. Contexto | [nivel-1-contexto.md](nivel-1-contexto.md) | Quem usa o AlertaSUS e com o que ele se comunica? |
| 2. Containers | [nivel-2-containers.md](nivel-2-containers.md) | Quais aplicações e bancos compõem o sistema e como conversam? |

Os diagramas estão em Mermaid, que o GitHub renderiza direto no navegador. Para editar, use o [Mermaid Live Editor](https://mermaid.live) ou a extensão "Markdown Preview Mermaid Support" do VS Code.

## Legenda

Os diagramas seguem as cores usuais do C4.

| Elemento | Aparência |
|---|---|
| Pessoa | Azul-escuro, cantos arredondados |
| Sistema em foco (AlertaSUS) | Azul |
| Container do AlertaSUS | Azul-claro |
| Banco de dados ou broker | Cilindro azul-claro |
| Sistema ou ferramenta externa | Cinza |
| Container **planejado**, ainda fora do `docker-compose.yml` | Borda tracejada |

Cada seta indica o sentido da chamada ou do envio de dados e traz o protocolo entre colchetes, por exemplo `[AMQP]`.

## Quando atualizar

O Projeto 03 exige "diagrama C4 atualizado". Atualize estes arquivos sempre que um container for adicionado ao `docker-compose.yml`, quando uma tecnologia em aberto for decidida em ADR ou quando um fluxo mudar. Os pontos em aberto estão listados no fim de [nivel-2-containers.md](nivel-2-containers.md#pontos-em-aberto).
