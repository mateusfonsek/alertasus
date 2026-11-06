"""Testes básicos do serviço."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_returns_service_name():
    response = client.get("/health")
    assert "service" in response.json()


def test_root_returns_message():
    response = client.get("/")
    assert response.status_code == 200
    assert "service" in response.json()
