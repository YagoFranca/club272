"""Permite executar o sistema com `python -m club272`."""

import multiprocessing

from club272.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
