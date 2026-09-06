#!/usr/bin/env python
"""
Restaura o banco a partir de um backup em `data/backups/`.

    python restaurar_backup.py              # lista os backups disponíveis
    python restaurar_backup.py <arquivo>    # restaura o backup indicado

O banco atual nunca é descartado: antes de sobrescrever, ele vira mais um
backup (`antes_de_restaurar_*.db`).
"""

import shutil
import sqlite3
import sys
from datetime import datetime

from club272 import config
from club272.core.encoding import deserialize_encoding


def resumir(caminho):
    """Conta usuários, encodings e eventos de um arquivo .db."""
    try:
        con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        tabelas = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        tabela = "usuarios" if "usuarios" in tabelas else "registrations"
        if tabela not in tabelas:
            return "sem tabela de usuários"

        usuarios = [dict(r) for r in con.execute(f"SELECT * FROM {tabela}")]
        encodings = sum(
            1 for u in usuarios if deserialize_encoding(u.get("encoding")) is not None
        )
        eventos = (
            con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
            if "eventos" in tabelas else 0
        )
        con.close()
        return f"{len(usuarios):3d} usuários · {encodings:3d} encodings · {eventos} eventos"
    except sqlite3.Error as e:
        return f"ilegível ({e})"


def listar():
    backups = sorted(
        config.BACKUPS_DIR.glob("*.db"),
        key=lambda b: b.stat().st_mtime,
        reverse=True,
    )
    if not backups:
        print("Nenhum backup em data/backups/")
        return

    print(f"Banco atual: {resumir(config.DB_PATH)}\n")
    print("Backups disponíveis (mais recente primeiro):\n")
    for b in backups:
        quando = datetime.fromtimestamp(b.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        print(f"  {b.name}")
        print(f"      {quando}  ·  {resumir(b)}")
    print("\nPara restaurar:  python restaurar_backup.py <nome-do-arquivo>")


def restaurar(nome):
    origem = config.BACKUPS_DIR / nome
    if not origem.exists():
        print(f"Backup não encontrado: {origem}")
        return 1

    print(f"Restaurando  : {nome}")
    print(f"  conteúdo   : {resumir(origem)}")
    print(f"  substituirá: {resumir(config.DB_PATH)}")

    # O banco atual vira backup antes de ser sobrescrito.
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    guardado = config.BACKUPS_DIR / f"antes_de_restaurar_{marca}.db"
    shutil.copy2(config.DB_PATH, guardado)
    print(f"\nbanco atual salvo em: {guardado.name}")

    shutil.copy2(origem, config.DB_PATH)
    print(f"restaurado          : {resumir(config.DB_PATH)}")
    return 0


def main():
    config.ensure_directories()
    if len(sys.argv) < 2:
        listar()
        return 0
    return restaurar(sys.argv[1])


if __name__ == "__main__":
    sys.exit(main())
