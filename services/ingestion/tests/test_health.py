"""Endpoints de saúde, prontidão e métricas."""


def test_health_returns_ok(cliente):
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "service": "ingestion"}


def test_root_returns_message(cliente):
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert "service" in resposta.json()


def test_ready_com_dependencias_disponiveis(cliente):
    resposta = cliente.get("/ready")
    assert resposta.status_code == 200
    assert resposta.json() == {
        "status": "pronto",
        "dependencias": {"rabbitmq": True, "redis": True},
    }


def test_ready_sem_rabbitmq_fica_indisponivel(cliente, publicador):
    publicador.falhar = True
    resposta = cliente.get("/ready")
    assert resposta.status_code == 503
    assert resposta.json()["dependencias"]["rabbitmq"] is False


def test_ready_sem_redis_continua_pronto(cliente, redis_falso):
    """Sem Redis a Ingestão segue aceitando notificações (fail-open)."""
    redis_falso.indisponivel = True
    resposta = cliente.get("/ready")
    assert resposta.status_code == 200
    assert resposta.json()["dependencias"]["redis"] is False


def test_metrics_expoe_contadores_de_negocio(cliente):
    resposta = cliente.get("/metrics")
    assert resposta.status_code == 200
    assert "alertasus_notificacoes_recebidas_total" in resposta.text
    assert "http_request_duration_seconds" in resposta.text
