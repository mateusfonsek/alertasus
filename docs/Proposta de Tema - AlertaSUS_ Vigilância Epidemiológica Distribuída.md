# **Proposta de Tema \- AlertaSUS: Vigilância Epidemiológica Distribuída**

**Disciplina:** Engenharia de Sistemas Distribuídos \- 2026.2

**Entrega:** Projeto 01 (09/10/2026)

**Equipe:** Ana Clara Ferreira Epaminondas, Gleice Heloise de Araujo Silva, Icaro Oliveira de Andrade Fernandes Velasquez Solis, João Victor Dias Gonçalves, Mateus Fonseca Ferreira e Silva

**Repositório:** [https\://github.com/mateusfonsek/alertasus](https://github.com/mateusfonsek/alertasus)

## **1\. Problema**

Notificações de agravos (dengue, chikungunya, síndrome gripal) chegam de muitas unidades de saúde e são consolidadas com atraso, o que retarda a detecção de surtos. Em epidemias, o volume de notificações dispara justamente quando o sistema mais precisa responder. O AlertaSUS recebe notificações em tempo quase real, desacopla recebimento de processamento e agrega os casos por região e semana epidemiológica em painéis. Todos os dados serão sintéticos, sem informação real de pacientes.

## **2\. Solução proposta**

Arquitetura de microsserviços orientada a eventos, com escrita e leitura separadas:

•       **API Gateway:** autenticação das unidades (JWT) e rate limiting por unidade.  
•       **Serviço de Ingestão:** valida a notificação, garante idempotência pelo ID da notificação e publica o evento no broker.  
•       **Serviço de Agregação:** consome os eventos e atualiza as Materialized Views por município, bairro e semana epidemiológica.  
•       **Serviço de Alertas:** assina o mesmo tópico (fan-out) e dispara alerta quando uma região passa de um limiar configurável.  
•       **Serviço de Consulta \+ Painel:** lê apenas as views agregadas, com cache.  
•       **Simulador de unidades de saúde:** gera notificações sintéticas para demo e testes de carga.

## **3\. Padrões arquiteturais e áreas técnicas**

Cinco padrões da Seção 5, cobrindo quatro áreas (mínimo exigido: 3 padrões e 2 áreas):

| Padrão (Seção 5\) | Área | Aplicação no projeto |
| :---- | :---- | :---- |
| Queues, PubSub e Messaging Fanout | Escalabilidade | Um evento de notificação alimenta Agregação e Alertas de forma independente |
| Materialized View | Desempenho | Contagens pré-agregadas por região e semana para o painel |
| CQRS | Desempenho | Ingestão (escrita) separada da consulta (leitura) |
| Retry Pattern e DLQ | Confiabilidade | Reprocessamento de falhas transitórias; mensagens inválidas vão para a DLQ |
| API Gateway (autenticação, rate limiting) | Segurança | Uma unidade com excesso de envios não degrada as demais |

## **4\. Tecnologias previstas**

•       **Serviços:** Python com FastAPI.  
•       **Mensageria:** RabbitMQ, com fanout exchange e DLQ nativas.  
•       **Dados:** PostgreSQL (Materialized Views) e Redis (cache de consultas).  
•       **Gateway:** Kong ou Traefik.  
•       **Painel e observabilidade:** Grafana e Prometheus.  
•       **Infra e CI:** Docker Compose e GitHub Actions.  
•       **Testes de carga:** k6.

## **5\. Critérios de sucesso e plano de testes**

| Critério | Meta | Teste que valida |
| :---- | :---- | :---- |
| Vazão de ingestão | ≥ 500 notificações/s com p95 da API \< 200 ms | Carga progressiva com k6 |
| Atraso fim a fim (notificação → painel) | p95 ≤ 10 s | Timestamps de envio vs. atualização da view |
| Zero perda de mensagens | Contagem agregada \= total enviado | Resiliência: derrubar o Serviço de Agregação durante a carga |
| Idempotência | Reenvio não duplica casos | Integração: mesma notificação enviada 3 vezes |
| Tratamento de inválidas | 100% das inválidas na DLQ | Integração com payloads malformados |
| Isolamento por unidade | Excesso recebe HTTP 429; demais mantêm p95 | Carga com uma unidade abusiva |
| Leitura do painel | p95 \< 100 ms sob carga | k6 nas consultas durante a ingestão |

 

