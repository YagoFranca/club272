"""
Autoverificação da instalação.

    272Club.exe --verificar

Roda sem abrir janela e grava um relatório em `verificacao.txt`, ao lado dos
dados do usuário. Serve para saber, numa máquina onde nada abre ou o
reconhecimento não acha ninguém, qual peça está faltando — especialmente no
executável empacotado, onde um arquivo de dados que ficou de fora falha em
silêncio.
"""

import sys
import time


def _verificar_dependencias(anotar):
    for modulo, rotulo in (
        ("cv2", "OpenCV"),
        ("numpy", "NumPy"),
        ("PIL", "Pillow"),
        ("openpyxl", "openpyxl"),
        ("requests", "requests"),
        ("customtkinter", "CustomTkinter"),
        ("face_recognition", "face_recognition"),
        ("dlib", "dlib"),
    ):
        try:
            __import__(modulo)
            anotar(True, f"{rotulo} disponível")
        except Exception as e:
            anotar(False, f"{rotulo} ausente: {e}")


def _verificar_modelos(anotar):
    """Os modelos do dlib são ~130 MB de dados; se ficarem de fora do pacote,
    o programa abre e só falha ao codificar um rosto."""
    try:
        import face_recognition_models as frm
        import os

        for nome, obtem in (
            ("detector de pontos", frm.pose_predictor_model_location),
            ("codificador facial", frm.face_recognition_model_location),
        ):
            caminho = obtem()
            if os.path.exists(caminho):
                tamanho = os.path.getsize(caminho) / 1e6
                anotar(True, f"modelo {nome} ({tamanho:.0f} MB)")
            else:
                anotar(False, f"modelo {nome} não encontrado: {caminho}")
    except Exception as e:
        anotar(False, f"modelos do dlib: {e}")


def _verificar_cascata(anotar):
    try:
        import cv2

        caminho = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        vazia = cv2.CascadeClassifier(caminho).empty()
        anotar(not vazia,
               "cascata Haar carregada" if not vazia
               else f"cascata Haar vazia ({caminho}) — usará o HOG, mais lento")
    except Exception as e:
        anotar(False, f"cascata Haar: {e}")


def _verificar_banco(anotar):
    try:
        from club272.core.database import DatabaseManager

        db = DatabaseManager()
        estatisticas = db.get_database_stats()
        anotar(True, f"banco acessível ({estatisticas['total_registrations']} "
                     f"membros, {len(db.listar_eventos())} eventos)")
    except Exception as e:
        anotar(False, f"banco: {e}")


def _verificar_escrita(anotar):
    from club272 import config

    try:
        config.ensure_directories()
        teste = config.DATA_DIR / ".escrita_teste"
        teste.write_text("ok", encoding="utf-8")
        teste.unlink()
        anotar(True, f"pasta de dados gravável ({config.DATA_DIR})")
    except Exception as e:
        anotar(False, f"pasta de dados não é gravável: {e}")


def _verificar_encoder(anotar):
    """O processo separado do encoder é o ponto mais frágil do executável: o
    `multiprocessing` precisa reabrir o próprio .exe."""
    try:
        import numpy as np
        from club272.core.recognition import EncoderRemoto

        encoder = EncoderRemoto()
        if not encoder.iniciar():
            anotar(False, "processo do encoder não iniciou")
            return

        time.sleep(3)  # o filho carrega os modelos do dlib
        recorte = np.random.randint(0, 255, (120, 120, 3), dtype=np.uint8)
        encoder.enviar(recorte)
        resposta = encoder.receber(espera=30)
        encoder.parar()

        # Ruído não tem rosto: a resposta certa é None, sem travar nem morrer.
        anotar(True, "processo do encoder responde")
        del resposta
    except Exception as e:
        anotar(False, f"processo do encoder: {e}")


def _verificar_camera(anotar):
    try:
        from club272.core.recognition import Camera

        camera = Camera()
        if camera.iniciar(espera=20):
            quadro = camera.ler()
            camera.parar()
            if quadro is None:
                anotar(False, "câmera abriu mas não entregou quadro")
            else:
                anotar(True, f"câmera {camera.indice_em_uso} entregando "
                             f"{quadro.shape[1]}x{quadro.shape[0]}")
        else:
            anotar(False, "nenhuma câmera utilizável encontrada")
    except Exception as e:
        anotar(False, f"câmera: {e}")


def _verificar_fonte_icones(anotar):
    try:
        import tkinter as tk
        from club272.ui.components import familia_de_icones

        raiz = tk.Tk()
        raiz.withdraw()
        familia = familia_de_icones()
        raiz.destroy()
        anotar(bool(familia),
               f"fonte de ícones: {familia}" if familia
               else "nenhuma fonte de ícones — será usado um marcador simples")
    except Exception as e:
        anotar(False, f"fonte de ícones: {e}")


VERIFICACOES = (
    ("Dependências", _verificar_dependencias),
    ("Modelos do dlib", _verificar_modelos),
    ("Detector Haar", _verificar_cascata),
    ("Pasta de dados", _verificar_escrita),
    ("Banco de dados", _verificar_banco),
    ("Fonte de ícones", _verificar_fonte_icones),
    ("Processo do encoder", _verificar_encoder),
    ("Câmera", _verificar_camera),
)


def executar():
    """Roda tudo e devolve (relatório, houve_falha)."""
    from club272 import config, __version__

    linhas = [
        "VERIFICAÇÃO DA INSTALAÇÃO — 272 Club",
        f"versão {__version__}",
        f"empacotado: {'sim' if config.EMPACOTADO else 'não'}",
        f"python {sys.version.split()[0]}",
        f"recursos: {config.RECURSOS_DIR}",
        f"dados:    {config.DADOS_DIR}",
        "=" * 60,
    ]
    problemas = []

    for titulo, verificar in VERIFICACOES:
        linhas.append(f"\n[{titulo}]")

        def anotar(ok, mensagem, _linhas=linhas, _problemas=problemas):
            _linhas.append(f"  {'ok   ' if ok else 'FALHA'} {mensagem}")
            if not ok:
                _problemas.append(mensagem)

        try:
            verificar(anotar)
        except Exception as e:
            anotar(False, f"erro inesperado: {e}")

    linhas.append("\n" + "=" * 60)
    linhas.append(
        f"{len(problemas)} problema(s) encontrado(s)" if problemas
        else "Tudo certo: a instalação está completa."
    )
    for problema in problemas:
        linhas.append(f"  - {problema}")

    return "\n".join(linhas), bool(problemas)


def main():
    """Ponto de entrada de `--verificar`. Devolve o código de saída."""
    from club272 import config

    relatorio, houve_falha = executar()
    print(relatorio)

    try:
        config.ensure_directories()
        destino = config.DADOS_DIR / "verificacao.txt"
        destino.write_text(relatorio, encoding="utf-8")
        print(f"\nRelatório salvo em {destino}")

        # Sem console (executável de janela), o relatório precisa aparecer
        # de alguma forma para quem clicou.
        if config.EMPACOTADO:
            import os

            os.startfile(destino)  # noqa: S606
    except Exception as e:
        print(f"Não foi possível salvar o relatório: {e}")

    return 1 if houve_falha else 0
