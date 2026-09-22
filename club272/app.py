"""
Montagem da aplicação: uma janela, todas as telas.

Substitui o modelo antigo, em que a tela inicial abria cada módulo como um
processo e uma janela separada do sistema operacional. Aqui as telas dividem a
mesma janela, o mesmo banco e a mesma barra de status.
"""

import os
import sys

import customtkinter as ctk

from club272 import config
from club272.ui.screens.attendance import TelaPresenca
from club272.ui.screens.batch import TelaLote
from club272.ui.screens.events import TelaEventos
from club272.ui.screens.members import TelaMembros
from club272.ui.screens.register import TelaCadastro
from club272.ui.screens.sync import TelaSincronizacao
from club272.ui.shell import Shell

# Ordem da barra lateral: (chave, nome do ícone, classe, grupo)
TELAS = (
    ("presenca", "camera", TelaPresenca, None),
    ("eventos", "calendario", TelaEventos, None),
    ("membros", "pessoas", TelaMembros, None),
    ("cadastro", "adicionar-pessoa", TelaCadastro, "cadastro"),
    ("lote", "upload", TelaLote, None),
    ("sync", "sincronizar", TelaSincronizacao, "sistema"),
)


def montar():
    """Cria o shell com todas as telas registradas."""
    config.ensure_directories()
    ctk.set_appearance_mode("dark")

    app = Shell("272 Club")
    for chave, icone, classe, grupo in TELAS:
        if grupo:
            app.separador_nav(grupo)
        app.registrar(chave, icone, classe)

    app.navegar("presenca")
    return app


def main():
    """Ponto de entrada da aplicação."""
    print("=" * 60)
    print("272 CLUB - Sistema Integrado de Reconhecimento Facial")
    print("=" * 60)

    if not config.supabase_configurado():
        print("Supabase não configurado — rodando offline.")
        print("Para sincronizar, preencha SUPABASE_URL e SUPABASE_KEY no .env.")

    perfil = "leve (máquina antiga)" if config.PERFIL_LEVE else "normal"
    print(f"Perfil de desempenho: {perfil}")
    print(f"Câmera: {config.CAMERA_LARGURA}x{config.CAMERA_ALTURA} @ "
          f"{config.FPS_EXIBICAO} fps")
    print("=" * 60)

    montar().mainloop()
    _encerrar_processo()


def _encerrar_processo():
    """Termina sem passar pela finalização do interpretador.

    O shell já parou as câmeras, esperou as threads de trabalho e encerrou o
    processo do encoder. Mesmo assim, uma thread daemon que ainda esteja
    dentro do OpenCV ou do dlib é interrompida pela finalização em pleno
    código nativo — e o processo morre com segmentation fault depois de a
    janela já ter fechado, o que aparece para o usuário como "fechou dando
    erro".

    `os._exit` pula essa etapa. Nada fica pendente porque a limpeza que
    importa (banco, arquivos) já aconteceu; só garantimos a descarga dos
    buffers de saída antes.
    """
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.flush()
        except (ValueError, OSError):
            pass
    os._exit(0)


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
