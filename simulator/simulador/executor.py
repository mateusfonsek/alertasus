"""Envio das notificações em ritmo controlado e relatório dos resultados."""

import asyncio
import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter

import httpx

from simulador.cenarios import RESPOSTA_ESPERADA, Envio

ROTA = "/api/v1/notificacoes"


class Autenticacao:
    """Modo direto (cabeçalho da unidade) ou modo Gateway (JWT por unidade)."""

    def __init__(
        self,
        tokens: dict[str, str] | None = None,
        cabecalho_unidade: str = "X-Consumer-Username",
    ) -> None:
        self._tokens = tokens
        self._cabecalho_unidade = cabecalho_unidade

    @property
    def modo(self) -> str:
        return "gateway (JWT)" if self._tokens is not None else "direto (cabeçalho)"

    def verificar(self, unidades: set[str]) -> None:
        if self._tokens is None:
            return
        faltando = sorted(unidades - set(self._tokens))
        if faltando:
            raise ValueError(f"sem token para: {', '.join(faltando[:5])}")

    def cabecalhos(self, unidade_id: str) -> dict[str, str]:
        if self._tokens is None:
            return {self._cabecalho_unidade: unidade_id}
        return {"Authorization": f"Bearer {self._tokens[unidade_id]}"}


@dataclass
class Relatorio:
    por_categoria: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    latencias_s: list[float] = field(default_factory=list)
    duracao_s: float = 0.0

    @property
    def total(self) -> int:
        return sum(sum(c.values()) for c in self.por_categoria.values())

    def percentil_ms(self, p: float) -> float | None:
        if not self.latencias_s:
            return None
        ordenadas = sorted(self.latencias_s)
        indice = max(math.ceil(p / 100 * len(ordenadas)) - 1, 0)
        return round(ordenadas[indice] * 1000, 1)

    def como_dict(self) -> dict:
        return {
            "total": self.total,
            "duracao_s": round(self.duracao_s, 2),
            "taxa_efetiva_por_s": round(self.total / self.duracao_s, 1)
            if self.duracao_s
            else None,
            "latencia_ms": {
                "p50": self.percentil_ms(50),
                "p95": self.percentil_ms(95),
                "p99": self.percentil_ms(99),
            },
            "por_categoria": {
                categoria: {
                    "status": dict(sorted(contagem.items())),
                    "esperado": RESPOSTA_ESPERADA.get(categoria, "—"),
                }
                for categoria, contagem in sorted(self.por_categoria.items())
            },
        }

    def tabela(self) -> str:
        dados = self.como_dict()
        linhas = [
            f"Enviadas: {dados['total']} em {dados['duracao_s']} s "
            f"({dados['taxa_efetiva_por_s']}/s)",
            "Latência (ms): p50={p50} p95={p95} p99={p99}".format(**dados["latencia_ms"]),
            "",
            f"{'categoria':<18} {'respostas':<32} esperado",
        ]
        for categoria, info in dados["por_categoria"].items():
            respostas = ", ".join(f"{s}×{n}" for s, n in info["status"].items())
            linhas.append(f"{categoria:<18} {respostas:<32} {info['esperado']}")
        return "\n".join(linhas)


def _preparar_corpo(envio: Envio) -> dict:
    corpo = dict(envio.corpo)
    if "enviado_em" in corpo and corpo["enviado_em"] is None:
        corpo["enviado_em"] = datetime.now(timezone.utc).isoformat()
    return corpo


async def executar(
    envios: Sequence[Envio],
    url: str,
    taxa: float,
    autenticacao: Autenticacao,
    concorrencia: int = 100,
    cliente: httpx.AsyncClient | None = None,
) -> Relatorio:
    """Envia `envios` a `taxa` por segundo, com até `concorrencia` em paralelo."""
    autenticacao.verificar({e.unidade_id for e in envios})
    relatorio = Relatorio()
    semaforo = asyncio.Semaphore(concorrencia)
    proprio_cliente = cliente is None
    cliente = cliente or httpx.AsyncClient(
        base_url=url,
        timeout=10.0,
        limits=httpx.Limits(max_connections=concorrencia),
    )

    # Como uma unidade real, só reenvia uma notificação depois que a tentativa
    # anterior terminou. Sem isso, com envios em paralelo, o reenvio pode
    # chegar antes do original e o relatório troca as categorias.
    ultima_tentativa: dict[str, asyncio.Task] = {}

    async def enviar(envio: Envio, anterior: asyncio.Task | None) -> None:
        try:
            if anterior is not None:
                await asyncio.wait([anterior])
            inicio = perf_counter()
            try:
                resposta = await cliente.post(
                    ROTA,
                    json=_preparar_corpo(envio),
                    headers=autenticacao.cabecalhos(envio.unidade_id),
                )
                status = str(resposta.status_code)
            except httpx.HTTPError:
                status = "erro"
            relatorio.latencias_s.append(perf_counter() - inicio)
            relatorio.por_categoria[envio.categoria][status] += 1
        finally:
            semaforo.release()

    loop = asyncio.get_running_loop()
    inicio_execucao = loop.time()
    tarefas = []
    try:
        for i, envio in enumerate(envios):
            atraso = inicio_execucao + i / taxa - loop.time()
            if atraso > 0:
                await asyncio.sleep(atraso)
            await semaforo.acquire()
            notificacao_id = envio.corpo.get("notificacao_id")
            tarefa = asyncio.create_task(
                enviar(envio, ultima_tentativa.get(notificacao_id))
            )
            if notificacao_id:
                ultima_tentativa[notificacao_id] = tarefa
            tarefas.append(tarefa)
        await asyncio.gather(*tarefas)
    finally:
        relatorio.duracao_s = loop.time() - inicio_execucao
        if proprio_cliente:
            await cliente.aclose()
    return relatorio
