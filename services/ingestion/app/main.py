"""Serviço de Ingestão do AlertaSUS.

Recebe as notificações das unidades de saúde, valida o contrato
(docs/contratos/evento-notificacao.md), descarta reenvios pelo
notificacao_id e publica o evento na exchange fanout do RabbitMQ.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.exceptions import RedisError

from app.config import Config
from app.contrato import EventoNotificacao, NotificacaoEntrada
from app.idempotencia import RegistroIdempotencia, Reserva
from app.logs import configurar_logs
from app.metricas import IDEMPOTENCIA_INDISPONIVEL, NOTIFICACOES, REQUISICOES_SEGUNDOS
from app.publicador import FalhaPublicacao, PublicadorRabbitMQ

ROTA_NOTIFICACOES = "/api/v1/notificacoes"
RETRY_AFTER_S = "5"

log = logging.getLogger("alertasus.ingestao")


def _respostas_documentadas() -> dict:
    return {
        200: {"description": "Reenvio de uma notificação já aceita (duplicada)."},
        401: {"description": "Unidade não identificada."},
        409: {"description": "O mesmo notificacao_id está sendo publicado agora."},
        422: {"description": "Corpo fora do contrato."},
        503: {"description": "Broker indisponível ou publicação não confirmada."},
    }


def create_app(
    config: Config | None = None,
    publicador=None,
    registro=None,
) -> FastAPI:
    """Cria a aplicação.

    Em produção, publicador e registro são criados no lifespan. Os testes
    injetam implementações falsas e nenhuma conexão externa é aberta.
    """
    config = config or Config.do_ambiente()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        abertos = []
        if app.state.registro is None or app.state.publicador is None:
            configurar_logs(config.nome_servico, config.nivel_log)
        if app.state.registro is None:
            app.state.registro = RegistroIdempotencia.do_url(
                config.redis_url,
                config.idempotencia_ttl_s,
                config.idempotencia_pendente_ttl_s,
            )
            abertos.append(app.state.registro)
        if app.state.publicador is None:
            publicador_real = PublicadorRabbitMQ(
                config.rabbitmq_url,
                config.exchange_notificacoes,
                config.publicacao_timeout_s,
            )
            await publicador_real.conectar(
                config.conexao_tentativas, config.conexao_intervalo_s
            )
            app.state.publicador = publicador_real
            abertos.append(publicador_real)
        log.info("serviço de ingestão iniciado")
        try:
            yield
        finally:
            for recurso in reversed(abertos):
                await recurso.fechar()

    app = FastAPI(
        title="AlertaSUS - Serviço de Ingestão",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.publicador = publicador
    app.state.registro = registro

    @app.middleware("http")
    async def medir_requisicoes(request: Request, call_next):
        inicio = perf_counter()
        resposta = await call_next(request)
        rota = request.scope.get("route")
        REQUISICOES_SEGUNDOS.labels(
            request.method,
            getattr(rota, "path", "desconhecida"),
            str(resposta.status_code),
        ).observe(perf_counter() - inicio)
        return resposta

    @app.exception_handler(RequestValidationError)
    async def notificacao_invalida(request: Request, erro: RequestValidationError):
        if request.url.path == ROTA_NOTIFICACOES:
            NOTIFICACOES.labels("invalida").inc()
        return await request_validation_exception_handler(request, erro)

    @app.post(
        ROTA_NOTIFICACOES,
        status_code=202,
        summary="Recebe uma notificação de agravo",
        responses=_respostas_documentadas(),
    )
    async def receber_notificacao(notificacao: NotificacaoEntrada, request: Request):
        unidade_id = (request.headers.get(config.cabecalho_unidade) or "").strip()
        if not unidade_id:
            NOTIFICACOES.labels("nao_autenticada").inc()
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Unidade não identificada. A requisição deve passar "
                    "pelo API Gateway com um JWT válido."
                },
            )

        recebido_em = datetime.now(timezone.utc)
        notificacao_id = notificacao.notificacao_id
        contexto = {"notificacao_id": str(notificacao_id), "unidade_id": unidade_id}
        registro = request.app.state.registro
        publicador = request.app.state.publicador

        # 1ª camada da idempotência. Se o Redis cair, a notificação é aceita
        # mesmo assim (fail-open): a chave primária nos consumidores impede a
        # contagem em dobro (ADR 0006).
        idempotencia_ativa = True
        try:
            reserva = await registro.reservar(notificacao_id)
        except (RedisError, OSError) as erro:
            idempotencia_ativa = False
            reserva = Reserva.NOVA
            IDEMPOTENCIA_INDISPONIVEL.inc()
            log.warning(
                "Redis indisponível; notificação seguirá sem verificação de reenvio",
                extra={"contexto": {**contexto, "erro": str(erro)}},
            )

        if reserva is Reserva.DUPLICADA:
            NOTIFICACOES.labels("duplicada").inc()
            log.info("reenvio ignorado", extra={"contexto": contexto})
            return JSONResponse(
                status_code=200,
                content={"status": "duplicada", "notificacao_id": str(notificacao_id)},
            )
        if reserva is Reserva.EM_PROCESSAMENTO:
            NOTIFICACOES.labels("em_processamento").inc()
            return JSONResponse(
                status_code=409,
                content={
                    "status": "em_processamento",
                    "notificacao_id": str(notificacao_id),
                },
                headers={"Retry-After": RETRY_AFTER_S},
            )

        evento = EventoNotificacao.a_partir_de(notificacao, unidade_id, recebido_em)
        try:
            await publicador.publicar(evento)
        except FalhaPublicacao as erro:
            NOTIFICACOES.labels("falha_publicacao").inc()
            if idempotencia_ativa:
                await _sem_falhar(registro.liberar(notificacao_id), contexto)
            log.error(
                "falha ao publicar notificação",
                extra={"contexto": {**contexto, "erro": str(erro)}},
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Não foi possível registrar a notificação agora. "
                    "Reenvie o mesmo corpo em alguns segundos."
                },
                headers={"Retry-After": RETRY_AFTER_S},
            )

        if idempotencia_ativa:
            await _sem_falhar(registro.confirmar(notificacao_id), contexto)
        NOTIFICACOES.labels("aceita").inc()
        log.info(
            "notificação aceita",
            extra={"contexto": {**contexto, "evento_id": str(evento.evento_id)}},
        )
        return {
            "status": "aceita",
            "notificacao_id": str(notificacao_id),
            "evento_id": str(evento.evento_id),
            "semana_epidemiologica": evento.semana_epidemiologica,
        }

    @app.get("/health")
    def health() -> dict:
        """Liveness: o processo está de pé."""
        return {"status": "ok", "service": config.nome_servico}

    @app.get("/ready")
    async def ready(request: Request) -> JSONResponse:
        """Readiness: só depende do RabbitMQ.

        Sem o Redis o serviço continua aceitando notificações (fail-open),
        então o Redis é informado, mas não torna o serviço indisponível.
        """
        publicador = request.app.state.publicador
        registro = request.app.state.registro
        dependencias = {
            "rabbitmq": bool(publicador is not None and publicador.pronto()),
            "redis": bool(registro is not None and await registro.pronto()),
        }
        pronto = dependencias["rabbitmq"]
        return JSONResponse(
            status_code=200 if pronto else 503,
            content={
                "status": "pronto" if pronto else "indisponivel",
                "dependencias": dependencias,
            },
        )

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/")
    def root() -> dict:
        return {
            "service": config.nome_servico,
            "message": f"Envie notificações para POST {ROTA_NOTIFICACOES}.",
            "contrato": "docs/contratos/evento-notificacao.md",
        }

    return app


async def _sem_falhar(operacao, contexto: dict) -> None:
    """Executa uma operação no Redis sem deixar a falha chegar à unidade."""
    try:
        await operacao
    except (RedisError, OSError) as erro:
        log.warning(
            "falha ao atualizar o registro de idempotência",
            extra={"contexto": {**contexto, "erro": str(erro)}},
        )


app = create_app()
