#!/usr/bin/env python
"""Ponto de entrada do 272 Club.

    python run.py              abre a aplicação
    python run.py --verificar  checa a instalação e grava um relatório
"""

import multiprocessing
import sys


def main():
    if "--verificar" in sys.argv:
        from club272.verificacao import main as verificar

        return verificar()

    from club272.app import main as abrir

    abrir()
    return 0


if __name__ == "__main__":
    # Necessário no Windows: o processo do encoder facial reimporta o módulo
    # principal, e sem isso o executável empacotado entraria em recursão.
    multiprocessing.freeze_support()
    sys.exit(main())
