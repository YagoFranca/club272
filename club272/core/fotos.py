"""
Localização das fotos dos membros.

A foto de alguém é sempre `<id>.<extensão>` dentro da pasta de imagens. Essa
convenção é o que torna o acervo portátil: o campo `image_path` do banco
guarda um caminho absoluto da máquina onde o cadastro foi feito, e esse
caminho não existe em nenhuma outra — ao levar o banco para outro computador,
todos apontariam para o vazio.

Por isso a busca é pelo ID primeiro, e só cai no caminho gravado como último
recurso.
"""

import os

from club272 import config

EXTENSOES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def caminho_da_foto(usuario):
    """Caminho da foto do membro, ou None se não houver.

    Aceita o dicionário do banco ou o próprio ID.
    """
    if isinstance(usuario, dict):
        usuario_id = usuario.get("id")
        gravado = usuario.get("image_path")
    else:
        usuario_id = usuario
        gravado = None

    if usuario_id:
        for extensao in EXTENSOES:
            candidato = config.IMAGES_DIR / f"{usuario_id}{extensao}"
            if candidato.exists():
                return str(candidato)

    # Só agora o caminho do banco, que pode ser de outra máquina.
    if gravado and os.path.exists(gravado):
        return gravado
    return None


def tem_foto(usuario):
    return caminho_da_foto(usuario) is not None
