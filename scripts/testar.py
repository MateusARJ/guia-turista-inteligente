"""Demonstrações manuais: execute com python -m scripts.testar ou task."""

import argparse
import json
import sys
import time
from unittest.mock import patch

import httpx

import planejamento
from services import obter_clima, obter_percurso


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "comando", choices=["fallback", "ia", "clima", "percurso", "demo"]
    )
    parser.add_argument(
        "--destino", default="Recife, PE", help="Destino textual usado pela IA"
    )
    parser.add_argument(
        "--lat",
        type=float,
        default=-8.05,
        help="Latitude para clima/origem (padrão: Recife)",
    )
    parser.add_argument(
        "--lon", type=float, default=-34.9, help="Longitude para clima/origem"
    )
    parser.add_argument(
        "--lat-d",
        type=float,
        default=-7.12,
        help="Latitude de chegada (padrão: João Pessoa)",
    )
    parser.add_argument(
        "--lon-d", type=float, default=-34.86, help="Longitude de chegada"
    )
    args = parser.parse_args(argv)
    comandos = (
        ["fallback", "ia", "clima", "percurso"]
        if args.comando == "demo"
        else [args.comando]
    )
    falhou = False
    for comando in comandos:
        print(f"\n--- {comando.upper()} ---", flush=True)
        inicio = time.monotonic()
        if comando in ("fallback", "ia"):
            if comando == "fallback":
                # Mudança apenas neste processo, restaurada ao sair do contexto.
                with patch.object(planejamento, "GEMINI_KEY", ""):
                    texto, diagnostico = (
                        planejamento.obter_guia_destino_com_diagnostico(args.destino)
                    )
            else:
                texto, diagnostico = planejamento.obter_guia_destino_com_diagnostico(
                    args.destino
                )
                falhou |= diagnostico["fallback_utilizado"]
            print(texto)
            print(json.dumps(diagnostico, ensure_ascii=False, indent=2))
        else:
            with httpx.Client() as client:
                if comando == "clima":
                    resultado = obter_clima(client, args.lat, args.lon)
                    falhou |= resultado["temperatura"] == "N/D"
                else:
                    resultado = obter_percurso(
                        client, args.lat, args.lon, args.lat_d, args.lon_d
                    )
                    falhou |= resultado["modal"] != "carro"
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
        print(f"Tempo: {time.monotonic() - inicio:.2f} s", flush=True)
    return 1 if falhou else 0


if __name__ == "__main__":
    # Mantém emojis legíveis inclusive no terminal Windows e em saída redirecionada.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
