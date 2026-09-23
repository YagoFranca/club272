"""272 Club - Sistema Integrado de Reconhecimento Facial."""

import faulthandler
import os
import sys

__version__ = "4.1.1"


def _ativar_diagnostico_de_falha():
    """Faz o Python imprimir a pilha nativa em caso de segmentation fault.

    Um crash em código C (OpenCV, dlib, Tcl) mata o processo sem exceção e sem
    traceback — some sem deixar rastro. Com isto, a pilha das threads é
    gravada em `data/ultima_falha.txt` e no stderr, apontando qual biblioteca
    estava executando.
    """
    faulthandler.enable()
    try:
        destino = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "ultima_falha.txt",
        )
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        # Mantido aberto de propósito: o handler escreve nele durante o crash.
        _ativar_diagnostico_de_falha.arquivo = open(destino, "w", encoding="utf-8")
        faulthandler.enable(file=_ativar_diagnostico_de_falha.arquivo, all_threads=True)
    except OSError:
        pass


def _preparar_console():
    """Garante que `print` com emoji/acento não derrube a aplicação.

    No Windows, quando a saída não é um console (redirecionada para arquivo ou
    pipe, ou executável empacotado sem console), o Python usa a codificação da
    localidade — cp1252 aqui — e qualquer emoji levanta UnicodeEncodeError,
    matando o programa na partida. O código imprime emoji em dezenas de
    pontos, então normalizamos a saída uma única vez.
    """
    for nome in ("stdout", "stderr"):
        fluxo = getattr(sys, nome, None)

        # Sem console (ex.: .exe empacotado com --noconsole): qualquer print()
        # falharia por não haver stream.
        if fluxo is None:
            setattr(sys, nome, open(os.devnull, "w", encoding="utf-8"))
            continue

        reconfigure = getattr(fluxo, "reconfigure", None)
        if reconfigure is None:
            continue

        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # Stream já fechado ou não reconfigurável: segue sem quebrar.
            pass


_preparar_console()
_ativar_diagnostico_de_falha()
