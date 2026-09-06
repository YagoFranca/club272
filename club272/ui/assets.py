"""
Carregamento de imagens da interface.

O arquivo da logo é um PNG quadrado de 150x150 com os cantos brancos e sem
transparência real. Sobre o fundo escuro do app isso apareceria como um
quadrado branco, então recortamos o círculo aqui, uma vez, em vez de pedir uma
nova arte.
"""

from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageDraw

from club272 import config

# Recorta numa resolução maior e reduz depois: a borda do círculo sai suave
# sem precisar de filtro extra.
_SUPERAMOSTRAGEM = 4


@lru_cache(maxsize=8)
def logo_circular(tamanho=40):
    """Devolve a logo recortada em círculo, como `CTkImage`.

    Retorna None se o arquivo não existir — a interface cai no texto da marca.
    """
    imagem = _abrir_logo_circular(tamanho)
    if imagem is None:
        return None
    return ctk.CTkImage(light_image=imagem, dark_image=imagem,
                        size=(tamanho, tamanho))


def _abrir_logo_circular(tamanho):
    """Versão PIL do recorte, reaproveitada pelo ícone da janela."""
    if not config.ASSETS_DIR.exists():
        return None

    caminho = config.LOGO_PATH
    try:
        original = Image.open(caminho).convert("RGBA")
    except (FileNotFoundError, OSError):
        return None

    grande = tamanho * _SUPERAMOSTRAGEM
    original = original.resize((grande, grande), Image.Resampling.LANCZOS)

    mascara = Image.new("L", (grande, grande), 0)
    ImageDraw.Draw(mascara).ellipse((0, 0, grande - 1, grande - 1), fill=255)
    original.putalpha(mascara)

    return original.resize((tamanho, tamanho), Image.Resampling.LANCZOS)


def aplicar_icone_janela(janela, tamanho=64):
    """Usa a logo como ícone da janela (barra de título e barra de tarefas)."""
    imagem = _abrir_logo_circular(tamanho)
    if imagem is None:
        return

    from PIL import ImageTk

    try:
        foto = ImageTk.PhotoImage(imagem)
        janela.iconphoto(True, foto)
        # Sem manter a referência, o Tk descarta a imagem e o ícone some.
        janela._icone = foto
    except Exception:
        pass
