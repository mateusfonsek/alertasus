"""Configuração do Serviço de Ingestão, lida de variáveis de ambiente."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    nome_servico: str = "ingestion"
    nivel_log: str = "INFO"
    rabbitmq_url: str = "amqp://alertasus:alertasus@rabbitmq:5672/"
    redis_url: str = "redis://redis:6379/0"
    exchange_notificacoes: str = "notificacoes"
    # Cabeçalho que o Kong injeta depois de validar o JWT da unidade (ADR 0005).
    cabecalho_unidade: str = "X-Consumer-Username"
    # Por quanto tempo um notificacao_id aceito continua sendo reconhecido como reenvio.
    idempotencia_ttl_s: int = 86_400
    # Prazo da reserva enquanto a publicação no broker está em andamento.
    idempotencia_pendente_ttl_s: int = 30
    publicacao_timeout_s: float = 5.0
    conexao_tentativas: int = 30
    conexao_intervalo_s: float = 2.0

    @classmethod
    def do_ambiente(cls) -> "Config":
        return cls(
            nome_servico=os.getenv("SERVICE_NAME", cls.nome_servico),
            nivel_log=os.getenv("LOG_LEVEL", cls.nivel_log),
            rabbitmq_url=os.getenv("RABBITMQ_URL", cls.rabbitmq_url),
            redis_url=os.getenv("REDIS_URL", cls.redis_url),
            exchange_notificacoes=os.getenv(
                "EXCHANGE_NOTIFICACOES", cls.exchange_notificacoes
            ),
            cabecalho_unidade=os.getenv("CABECALHO_UNIDADE", cls.cabecalho_unidade),
            idempotencia_ttl_s=int(
                os.getenv("IDEMPOTENCIA_TTL_S", cls.idempotencia_ttl_s)
            ),
            idempotencia_pendente_ttl_s=int(
                os.getenv(
                    "IDEMPOTENCIA_PENDENTE_TTL_S", cls.idempotencia_pendente_ttl_s
                )
            ),
            publicacao_timeout_s=float(
                os.getenv("PUBLICACAO_TIMEOUT_S", cls.publicacao_timeout_s)
            ),
            conexao_tentativas=int(
                os.getenv("CONEXAO_TENTATIVAS", cls.conexao_tentativas)
            ),
            conexao_intervalo_s=float(
                os.getenv("CONEXAO_INTERVALO_S", cls.conexao_intervalo_s)
            ),
        )
