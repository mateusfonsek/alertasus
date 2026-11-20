"""Serviço de Ingestão do AlertaSUS.

Nesta fase (Projeto 02), apenas expõe endpoint de health check.
Funcionalidades de negócio entram no Projeto 03.
"""
import os

from fastapi import FastAPI

SERVICE_NAME = os.getenv("SERVICE_NAME", "query")

app = FastAPI(
    title=f"AlertaSUS - {SERVICE_NAME.capitalize()} Service",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    """Health check usado pelo docker-compose e pelo CI."""
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/")
def root() -> dict:
    """Endpoint raiz apenas informativo."""
    return {
        "service": SERVICE_NAME,
        "message": "Esqueleto do Projeto 02. Funcionalidades no Projeto 03.",
    }
