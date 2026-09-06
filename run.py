#!/usr/bin/env python
"""Ponto de entrada do 272 Club.

Uso:
    python run.py
"""

import multiprocessing

from club272.app import main

if __name__ == "__main__":
    # Necessário no Windows: o processo do encoder facial reimporta o módulo
    # principal, e sem isso o executável empacotado entraria em recursão.
    multiprocessing.freeze_support()
    main()
