# -*- mode: python ; coding: utf-8 -*-
"""
Empacotamento do 272 Club com PyInstaller.

    pyinstaller empacotar.spec --noconfirm

Gera `dist/272Club/` — pasta com o executável e tudo de que ele precisa.

Modo pasta, e não arquivo único, de propósito: o `--onefile` extrai ~400 MB
para uma pasta temporária a cada abertura. Num Core 2 Duo, que é o alvo, isso
são dezenas de segundos antes da janela aparecer. Em pasta, abre direto.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

NOME = "272Club"

# Os modelos do dlib (~130 MB) e os temas do CustomTkinter são arquivos de
# dados: sem coletá-los explicitamente, o programa empacotado sobe e só
# quebra na hora de reconhecer um rosto ou desenhar a janela.
dados = [
    ("club272/assets", "club272/assets"),
    ("templates", "templates"),
    (".env.example", "."),
]
dados += collect_data_files("face_recognition_models")
dados += collect_data_files("customtkinter")
# Os XML das cascatas Haar. `collect_dynamic_libs` traz só as DLLs — sem
# estes o classificador nasce vazio e nenhum rosto é detectado, em silêncio.
dados += collect_data_files("cv2", includes=["data/*.xml"])

binarios = collect_dynamic_libs("cv2")

ocultos = [
    "face_recognition_models",
    "PIL._tkinter_finder",
    "openpyxl.cell._writer",
    # O face_recognition_models localiza os modelos via `pkg_resources`, e o
    # hook do PyInstaller para ele depende destes. Sem isso o executável nem
    # chega a abrir a janela.
    "jaraco.text",
    "jaraco.functools",
    "jaraco.context",
]

# Peso morto: nada disso é usado, e cada um custa dezenas de MB.
excluir = [
    "matplotlib", "scipy", "IPython", "jupyter", "notebook",
    "pytest", "pip", "tkinter.test", "test",
    "pandas.tests", "numpy.random._examples",
]

analise = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binarios,
    datas=dados,
    hiddenimports=ocultos,
    hookspath=[],
    runtime_hooks=[],
    excludes=excluir,
    noarchive=False,
)

pyz = PYZ(analise.pure)

exe = EXE(
    pyz,
    analise.scripts,
    [],
    exclude_binaries=True,
    name=NOME,
    debug=False,
    strip=False,
    upx=False,          # UPX quebra DLLs do OpenCV com alguma frequência
    console=False,      # app de janela: sem console preto atrás
    icon="club272/assets/272club.ico",
)

COLLECT(
    exe,
    analise.binaries,
    analise.datas,
    strip=False,
    upx=False,
    name=NOME,
)
