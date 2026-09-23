#!/usr/bin/env python
"""
Gera o pacote distribuível do 272 Club.

    python empacotar.py

Faz, em ordem:

1. PyInstaller -> `dist/272Club/` (pasta com o executável)
2. Autoverificação dentro do executável recém-gerado — é o que pega o
   arquivo de dados que ficou de fora do pacote, coisa que falha em silêncio
3. Instalador com o Inno Setup, se estiver instalado
4. Sem o Inno Setup, um .zip da pasta, que já serve para distribuir

Modo pasta, e não arquivo único: o `--onefile` extrai ~450 MB para o disco a
cada abertura, e o alvo é um Core 2 Duo.
"""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DIST = RAIZ / "dist"
PASTA = DIST / "272Club"
EXECUTAVEL = PASTA / "272Club.exe"

CAMINHOS_INNO = (
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
)


def etapa(texto):
    print(f"\n{'=' * 64}\n{texto}\n{'=' * 64}")


def construir():
    etapa("1/4  Empacotando com o PyInstaller")
    resultado = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "empacotar.spec",
         "--noconfirm", "--clean"],
        cwd=RAIZ,
    )
    if resultado.returncode != 0:
        raise SystemExit("PyInstaller falhou.")
    if not EXECUTAVEL.exists():
        raise SystemExit(f"Executável não foi gerado: {EXECUTAVEL}")

    tamanho = sum(f.stat().st_size for f in PASTA.rglob("*") if f.is_file())
    print(f"\nPacote: {PASTA}  ({tamanho / 1e6:.0f} MB)")


def verificar():
    """Roda `--verificar` dentro do executável gerado.

    É a etapa que importa: um arquivo de dados esquecido no `.spec` não quebra
    a construção nem a abertura — só some na hora de reconhecer um rosto.
    """
    etapa("2/4  Verificando o executável gerado")
    resultado = subprocess.run(
        [str(EXECUTAVEL), "--verificar"],
        capture_output=True, text=True, timeout=300,
    )
    saida = (resultado.stdout or "") + (resultado.stderr or "")
    for linha in saida.splitlines():
        if linha.startswith(("  ok", "  FALHA", "[", "Tudo certo", "0 problema")):
            print(linha)

    if resultado.returncode != 0:
        raise SystemExit(
            "\nA verificação encontrou problemas — veja acima. "
            "O pacote foi gerado, mas não está pronto para distribuir."
        )
    print("\nVerificação passou.")


def _achar_inno():
    for caminho in CAMINHOS_INNO:
        if os.path.exists(caminho):
            return caminho
    return shutil.which("ISCC")


def instalador():
    etapa("3/4  Gerando o instalador")
    inno = _achar_inno()
    if not inno:
        print("Inno Setup não encontrado — pulando.")
        print("Para gerar o instalador .exe, instale de https://jrsoftware.org/"
              "isdl.php e rode este script de novo.")
        return None

    resultado = subprocess.run([inno, "instalador.iss"], cwd=RAIZ)
    if resultado.returncode != 0:
        raise SystemExit("Inno Setup falhou.")

    gerados = sorted(DIST.glob("272Club-*-instalador.exe"))
    if gerados:
        print(f"\nInstalador: {gerados[-1]}")
        return gerados[-1]
    return None


def compactar():
    etapa("4/4  Compactando a pasta")
    destino = DIST / "272Club-portatil.zip"
    if destino.exists():
        destino.unlink()

    arquivos = [f for f in PASTA.rglob("*") if f.is_file()]
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for indice, arquivo in enumerate(arquivos, start=1):
            z.write(arquivo, arquivo.relative_to(DIST))
            if indice % 200 == 0:
                print(f"  {indice}/{len(arquivos)} arquivos...")

    print(f"\nZip: {destino}  ({destino.stat().st_size / 1e6:.0f} MB)")
    return destino


def main():
    construir()
    verificar()
    pronto = instalador()
    if pronto is None:
        compactar()

    etapa("Concluído")
    for arquivo in sorted(DIST.glob("272Club-*")):
        print(f"  {arquivo.name}  ({arquivo.stat().st_size / 1e6:.0f} MB)")
    print(f"  272Club/  (pasta, {sum(f.stat().st_size for f in PASTA.rglob('*') if f.is_file()) / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
