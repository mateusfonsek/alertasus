"""Linha de comando do simulador.

Exemplos:
    python -m simulador --cenario normal --taxa 10 --duracao 30
    python -m simulador --cenario surto --taxa 20 --duracao 120
    python -m simulador --cenario unidade-abusiva --url http://localhost:8000 \
        --tokens tokens.json
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from simulador.cenarios import CENARIOS, gerar
from simulador.executor import Autenticacao, executar


def _argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="simulador",
        description="Gera notificações sintéticas de unidades de saúde.",
    )
    parser.add_argument("--cenario", choices=list(CENARIOS), default="normal")
    parser.add_argument(
        "--taxa", type=float, default=10.0, help="notificações por segundo (total)"
    )
    parser.add_argument("--duracao", type=float, default=30.0, help="segundos")
    parser.add_argument("--unidades", type=int, default=50)
    parser.add_argument("--concorrencia", type=int, default=100)
    parser.add_argument(
        "--url",
        default=os.getenv("ALVO_URL", "http://localhost:8001"),
        help="Ingestão (modo direto) ou Gateway (com --tokens)",
    )
    parser.add_argument(
        "--tokens",
        type=Path,
        help='JSON {"unidade-001": "<jwt>", ...}; ativa o modo Gateway',
    )
    parser.add_argument("--semente", type=int, help="torna os sorteios reprodutíveis")
    parser.add_argument("--saida-json", type=Path, help="grava o relatório em JSON")
    args = parser.parse_args(argv)
    if args.taxa <= 0 or args.duracao <= 0 or args.unidades < 1:
        parser.error("--taxa, --duracao e --unidades devem ser positivos")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    tokens = (
        json.loads(args.tokens.read_text(encoding="utf-8")) if args.tokens else None
    )
    autenticacao = Autenticacao(tokens)
    total = max(int(args.taxa * args.duracao), 1)
    envios = gerar(args.cenario, total, args.unidades, args.semente)

    print(
        f"Cenário: {args.cenario} | alvo: {args.url} | modo: {autenticacao.modo} | "
        f"{len(envios)} envios a {args.taxa}/s"
    )
    try:
        relatorio = asyncio.run(
            executar(envios, args.url, args.taxa, autenticacao, args.concorrencia)
        )
    except ValueError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 2

    print()
    print(relatorio.tabela())
    if args.saida_json:
        args.saida_json.parent.mkdir(parents=True, exist_ok=True)
        args.saida_json.write_text(
            json.dumps(
                {"cenario": args.cenario, **relatorio.como_dict()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
