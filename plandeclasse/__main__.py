# plandeclasse/__main__.py
from __future__ import annotations

import argparse
import sys


def _run_exemple() -> int:
    # importe tardivement pour éviter d’imposer des dépendances quand on affiche juste l’aide
    try:
        from .exemples import run_exemple
    except ImportError as e:
        print("Impossible d’importer plandeclasse.exemples.run_exemple :", e, file=sys.stderr)
        return 1
    run_exemple()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plandeclasse",
        description="Outils et exemples pour plan de classe."
    )
    sub = parser.add_subparsers(dest="cmd")

    p_ex = sub.add_parser("exemple", help="Exécute le scénario d’exemple.")
    p_ex.set_defaults(func=lambda: _run_exemple())

    # défaut: si aucune sous-commande n’est fournie, on lance l’exemple
    args = parser.parse_args(argv)
    if not args.cmd:
        return _run_exemple()

    return args.func()


if __name__ == "__main__":
    raise SystemExit(main())
