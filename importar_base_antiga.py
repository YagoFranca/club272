#!/usr/bin/env python
"""
Importa uma base do sistema antigo (o do tablet) para o banco atual.

    python importar_base_antiga.py <arquivo.db> [--fotos PASTA] [opções]

O formato antigo guarda tudo numa tabela `registrations`, com as mesmas
colunas que hoje vivem em `usuarios`. Os encodings faciais são compatíveis:
mesmo dlib, mesmos 128 valores — então quem já estava cadastrado continua
sendo reconhecido sem precisar tirar foto de novo.

Por padrão nada é sobrescrito e nada é alterado: quem já existe no banco atual
é ignorado, e os nomes de grupo entram exatamente como estão. Veja `--ajuda`
para as opções que mudam isso.
"""

import argparse
import os
import re
import shutil
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from club272 import config  # noqa: E402
from club272.core.database import DatabaseManager  # noqa: E402
from club272.core.encoding import deserialize_encoding  # noqa: E402

EXTENSOES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def ler_base(caminho):
    """Lê a tabela `registrations` em modo somente leitura."""
    if not os.path.exists(caminho):
        raise SystemExit(f"Arquivo não encontrado: {caminho}")

    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        tabelas = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "registrations" not in tabelas:
            raise SystemExit(
                f"Sem tabela `registrations` em {caminho}. "
                f"Tabelas encontradas: {sorted(tabelas)}"
            )
        return [dict(r) for r in con.execute("SELECT * FROM registrations")]
    finally:
        con.close()


def indexar_fotos(pasta):
    """Mapa id -> caminho da foto, pelo nome do arquivo."""
    if not pasta or not os.path.isdir(pasta):
        return {}
    indice = {}
    for arquivo in os.listdir(pasta):
        base, extensao = os.path.splitext(arquivo)
        if extensao.lower() in EXTENSOES:
            indice[base] = os.path.join(pasta, arquivo)
    return indice


def _chave_grupo(nome):
    """Reduz variações de escrita a uma chave comum.

    'G 19', 'G19' -> G19;  'Oficial 0', 'OF 0', 'oficial 0' -> OF0
    """
    limpo = re.sub(r"[\s.]", "", (nome or "")).upper()
    return limpo.replace("OFICIAL", "OF")


def mapear_grupos(registros):
    """Para cada chave, a grafia mais frequente entre as variantes."""
    ocorrencias = defaultdict(list)
    for registro in registros:
        nome = (registro["group_name"] or "").strip()
        if nome:
            ocorrencias[_chave_grupo(nome)].append(nome)

    escolha = {}
    for chave, nomes in ocorrencias.items():
        # A grafia usada por mais gente vira a oficial.
        contagem = defaultdict(int)
        for nome in nomes:
            contagem[nome] += 1
        escolha[chave] = max(contagem, key=lambda n: (contagem[n], len(n)))
    return escolha


def importar(caminho_base, pasta_fotos, substituir, normalizar_grupos,
             pular_sem_rosto):
    db = DatabaseManager()
    registros = ler_base(caminho_base)
    fotos = indexar_fotos(pasta_fotos)
    grupos = mapear_grupos(registros) if normalizar_grupos else {}

    print(f"Origem : {caminho_base}  ({len(registros)} cadastros)")
    print(f"Fotos  : {pasta_fotos or '(nenhuma pasta informada)'}"
          f"  ({len(fotos)} arquivos)")
    print(f"Destino: {config.DB_PATH}")

    if os.path.exists(config.DB_PATH):
        print(f"Backup : {db.backup(prefixo='antes_da_importacao')}")

    config.ensure_directories()

    importados = atualizados = ignorados = sem_rosto = 0
    fotos_copiadas = 0
    avisos = []

    for registro in registros:
        usuario_id = str(registro["id"])
        nome = (registro["name"] or "").strip() or f"Sem nome {usuario_id}"
        encoding = registro["encoding"]

        if deserialize_encoding(encoding) is None:
            sem_rosto += 1
            avisos.append(f"{usuario_id} ({nome}): sem encoding facial")
            if pular_sem_rosto:
                ignorados += 1
                continue

        existente = db.buscar_usuario(usuario_id)
        if existente and not substituir:
            ignorados += 1
            avisos.append(f"{usuario_id} ({nome}): já existe, mantido como está")
            continue

        grupo = (registro["group_name"] or "").strip()
        if normalizar_grupos and grupo:
            grupo = grupos.get(_chave_grupo(grupo), grupo)

        caminho_foto = None
        origem = fotos.get(usuario_id)
        if origem:
            extensao = os.path.splitext(origem)[1] or ".png"
            destino = config.IMAGES_DIR / f"{usuario_id}{extensao}"
            shutil.copy2(origem, destino)
            caminho_foto = str(destino)
            fotos_copiadas += 1

        db.adicionar_usuario(
            usuario_id=usuario_id,
            nome=nome,
            grupo=grupo,
            telefone=(registro["phone"] or "").strip(),
            encoding=encoding,
            imagem_path=caminho_foto,
        )

        # `adicionar_usuario` não mexe no histórico de presenças: preserva o
        # acumulado do tablet, que é o número que o cliente conhece.
        _preservar_presencas(db, usuario_id, registro)

        if existente:
            atualizados += 1
        else:
            importados += 1

    return {
        "importados": importados,
        "atualizados": atualizados,
        "ignorados": ignorados,
        "sem_rosto": sem_rosto,
        "fotos": fotos_copiadas,
        "avisos": avisos,
        "grupos": grupos,
        "total_origem": len(registros),
    }


def _preservar_presencas(db, usuario_id, registro):
    """Mantém o total de presenças e a última data vindos do sistema antigo."""
    total = registro["total_attendance"] or 0
    ultima = registro["last_attendance_time"]
    if not total and not ultima:
        return

    with sqlite3.connect(db.db_path) as con:
        con.execute(
            "UPDATE usuarios SET total_attendance = ?, last_attendance_time = ? "
            "WHERE id = ?",
            (total, ultima, usuario_id),
        )
        con.commit()


def main():
    analisador = argparse.ArgumentParser(
        description="Importa uma base do sistema antigo para o banco atual.",
    )
    analisador.add_argument("base", help="arquivo .db do sistema antigo")
    analisador.add_argument("--fotos", help="pasta com as fotos (uma por ID)")
    analisador.add_argument(
        "--substituir", action="store_true",
        help="sobrescreve quem já existe no banco atual (padrão: mantém)",
    )
    analisador.add_argument(
        "--normalizar-grupos", action="store_true",
        help="unifica grafias como 'G 19' e 'G19' na mais usada",
    )
    analisador.add_argument(
        "--pular-sem-rosto", action="store_true",
        help="não importa quem está sem encoding facial",
    )
    argumentos = analisador.parse_args()

    resultado = importar(
        argumentos.base, argumentos.fotos, argumentos.substituir,
        argumentos.normalizar_grupos, argumentos.pular_sem_rosto,
    )

    print("\n" + "=" * 60)
    print(f"  importados      : {resultado['importados']}")
    print(f"  atualizados     : {resultado['atualizados']}")
    print(f"  ignorados       : {resultado['ignorados']}")
    print(f"  sem rosto       : {resultado['sem_rosto']}")
    print(f"  fotos copiadas  : {resultado['fotos']}")

    if resultado["grupos"]:
        print("\n  grupos unificados:")
        for chave, oficial in sorted(resultado["grupos"].items()):
            print(f"    {chave} -> {oficial}")

    if resultado["avisos"]:
        print("\n  avisos:")
        for aviso in resultado["avisos"]:
            print(f"    - {aviso}")

    db = DatabaseManager()
    usuarios = db.listar_usuarios()
    com_rosto = sum(
        1 for u in usuarios if deserialize_encoding(u["encoding"]) is not None
    )
    print(f"\n  banco agora: {len(usuarios)} membros, {com_rosto} com rosto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
