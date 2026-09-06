"""
Gerenciador do banco SQLite local, com sincronização Supabase.

Unifica as três classes que existiam antes — `DatabaseManager`
(sistema_integrado_completo), `RegisterDatabaseManager` (register) e
`BatchDatabaseManager` (batch_register) — que compartilhavam o mesmo banco e
repetiam o mesmo schema e as mesmas operações.
"""

import os
import sqlite3
import time
from datetime import datetime

import requests

from club272 import config

# ===== SCHEMA =====
SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        group_name TEXT,
        phone TEXT,
        event TEXT,
        total_attendance INTEGER DEFAULT 0,
        last_attendance_time TEXT,
        image_path TEXT,
        encoding BLOB,
        sync_status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        data_inicio TEXT NOT NULL,
        data_fim TEXT,
        status TEXT DEFAULT 'fechado',
        sync_status TEXT DEFAULT 'pending'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS presencas_evento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER,
        usuario_id TEXT,
        nome_usuario TEXT,
        hora_presenca TEXT,
        sync_status TEXT DEFAULT 'pending',
        FOREIGN KEY (evento_id) REFERENCES eventos(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT,
        detalhes TEXT,
        status TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
)

# Índices que aceleram as consultas mais frequentes.
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_usuarios_sync ON usuarios(sync_status)",
    "CREATE INDEX IF NOT EXISTS idx_presencas_evento ON presencas_evento(evento_id)",
    "CREATE INDEX IF NOT EXISTS idx_eventos_status ON eventos(status)",
)


class DatabaseManager:
    """Acesso ao banco local + sincronização com o Supabase."""

    def __init__(self, db_path=None):
        self.db_path = db_path or config.DB_PATH
        self.supabase_headers = config.supabase_headers()
        config.ensure_directories()
        self.init_database()

    # ===== INFRAESTRUTURA =====
    def _connect(self, row_factory=False):
        conn = sqlite3.connect(self.db_path)
        if row_factory:
            conn.row_factory = sqlite3.Row
        return conn

    def init_database(self):
        """Cria as tabelas e índices caso ainda não existam."""
        with self._connect() as conn:
            cursor = conn.cursor()
            for ddl in SCHEMA:
                cursor.execute(ddl)
            for ddl in INDEXES:
                cursor.execute(ddl)
            conn.commit()

    def check_internet(self):
        """Verifica se o Supabase está acessível."""
        if not config.supabase_configurado():
            return False
        try:
            response = requests.get(
                f"{config.SUPABASE_URL}/rest/v1/",
                headers=self.supabase_headers,
                timeout=5,
            )
            return response.status_code in (200, 401, 403)
        except requests.RequestException:
            return False

    # ===== IDs =====
    def get_next_tsu_id(self):
        """Próximo ID sequencial no formato TSU_XXXXX (5 dígitos)."""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM usuarios WHERE id LIKE ?",
                    (f"{config.TSU_PREFIX}%",),
                )
                numeros = []
                for (id_str,) in cursor.fetchall():
                    sufixo = id_str[len(config.TSU_PREFIX):]
                    if sufixo.isdigit():
                        numeros.append(int(sufixo))

            proximo = max(numeros) + 1 if numeros else config.TSU_START
            return f"{config.TSU_PREFIX}{proximo:05d}"
        except sqlite3.Error as e:
            print(f"Erro ao obter próximo TSU_ID: {e}")
            # Fallback: deriva da hora atual, mantendo os 5 dígitos.
            return f"{config.TSU_PREFIX}{(int(time.time()) % 90000) + 10000:05d}"

    # ===== USUÁRIOS =====
    def adicionar_usuario(self, usuario_id, nome, grupo="", telefone="",
                          encoding=None, imagem_path=None):
        """Insere ou atualiza um usuário.

        Em atualizações, `encoding` e `imagem_path` só são sobrescritos quando
        um valor novo é informado — assim um sync vindo do Supabase (que não
        traz encoding) não apaga o encoding já gravado localmente.
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            agora = datetime.now().isoformat()

            cursor.execute("SELECT id FROM usuarios WHERE id = ?", (usuario_id,))
            if cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE usuarios SET
                        name = ?, group_name = ?, phone = ?,
                        encoding = COALESCE(?, encoding),
                        image_path = COALESCE(?, image_path),
                        sync_status = 'pending', updated_at = ?
                    WHERE id = ?
                    """,
                    (nome, grupo, telefone, encoding, imagem_path, agora, usuario_id),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO usuarios
                        (id, name, group_name, phone, encoding, image_path,
                         sync_status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (usuario_id, nome, grupo, telefone, encoding, imagem_path,
                     agora, agora),
                )
            conn.commit()
        return True

    def insert_registration(self, registration_data):
        """Insere/atualiza a partir de um dicionário no formato usado pelas
        telas de cadastro (chaves em inglês)."""
        try:
            return self.adicionar_usuario(
                usuario_id=registration_data.get("id"),
                nome=registration_data.get("name", ""),
                grupo=(registration_data.get("group_name")
                       or registration_data.get("group", "")),
                telefone=registration_data.get("phone", ""),
                encoding=registration_data.get("encoding"),
                imagem_path=registration_data.get("image_path"),
            )
        except sqlite3.Error as e:
            print(f"Erro ao inserir registro: {e}")
            return False

    def buscar_usuario(self, usuario_id):
        """Busca um usuário pelo ID. Retorna dict ou None."""
        with self._connect(row_factory=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def listar_usuarios(self):
        """Lista todos os usuários ordenados por nome."""
        with self._connect(row_factory=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    # Aliases mantidos para o vocabulário usado pelas telas de cadastro.
    get_registration = buscar_usuario
    get_all_registrations = listar_usuarios

    def atualizar_presenca(self, usuario_id):
        """Incrementa o contador de presenças. Retorna o novo total (0 se o
        usuário não existir)."""
        usuario = self.buscar_usuario(usuario_id)
        if not usuario:
            return 0

        novo_total = (usuario["total_attendance"] or 0) + 1
        agora = datetime.now().isoformat()

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE usuarios
                SET total_attendance = ?, last_attendance_time = ?,
                    sync_status = 'pending', updated_at = ?
                WHERE id = ?
                """,
                (novo_total, agora, agora, usuario_id),
            )
            conn.commit()

        if self.check_internet():
            self.sync_usuario_supabase(usuario_id)

        return novo_total

    def update_sync_status(self, usuario_id, status):
        """Marca o status de sincronização de um usuário."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE usuarios SET sync_status = ? WHERE id = ?",
                (status, usuario_id),
            )
            conn.commit()

    def atualizar_usuario(self, usuario_id, nome=None, grupo=None, telefone=None):
        """Edita os dados cadastrais. Campos não informados ficam como estão.

        Não mexe em encoding nem em foto: para trocar o rosto, use a tela de
        cadastro, que refaz a captura.
        """
        campos, valores = [], []
        for coluna, valor in (("name", nome), ("group_name", grupo),
                              ("phone", telefone)):
            if valor is not None:
                campos.append(f"{coluna} = ?")
                valores.append(valor)

        if not campos:
            return False

        campos.append("sync_status = 'pending'")
        campos.append("updated_at = ?")
        valores.extend([datetime.now().isoformat(), usuario_id])

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE usuarios SET {', '.join(campos)} WHERE id = ?", valores
            )
            conn.commit()
            return cursor.rowcount > 0

    def remover_usuario(self, usuario_id, remover_foto=False):
        """Apaga o usuário e as presenças dele. Devolve True se existia.

        A foto em `data/images/` só é removida quando pedido: normalmente vale
        manter, porque é a única forma de refazer o encoding sem chamar a
        pessoa de volta.
        """
        usuario = self.buscar_usuario(usuario_id)
        if usuario is None:
            return False

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM presencas_evento WHERE usuario_id = ?", (usuario_id,)
            )
            cursor.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
            conn.commit()

        if remover_foto and usuario.get("image_path"):
            try:
                os.remove(usuario["image_path"])
            except OSError:
                pass

        self.log_sync("usuario", f"Usuário {usuario_id} removido localmente", "success")
        return True

    # ===== EVENTOS =====
    def criar_evento(self, nome_evento):
        """Cria um evento aberto e devolve o ID."""
        agora = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO eventos (nome, data_inicio, status, sync_status)
                VALUES (?, ?, 'aberto', 'pending')
                """,
                (nome_evento, agora),
            )
            evento_id = cursor.lastrowid
            conn.commit()
        return evento_id

    def fechar_evento(self, evento_id):
        """Fecha um evento, gravando a data de término."""
        agora = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE eventos
                SET data_fim = ?, status = 'fechado', sync_status = 'pending'
                WHERE id = ?
                """,
                (agora, evento_id),
            )
            conn.commit()

    def buscar_evento_aberto(self):
        """Retorna o evento aberto no momento, ou None."""
        with self._connect(row_factory=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eventos WHERE status = 'aberto' LIMIT 1")
            row = cursor.fetchone()
            return dict(row) if row else None

    # ===== PRESENÇAS =====
    def registrar_presenca_evento(self, evento_id, usuario_id, nome_usuario):
        """Registra presença num evento. Retorna False se já houver registro
        do usuário nesse evento hoje.

        `hora_presenca` guarda data e hora em ISO. Gravar só "%H:%M:%S", como
        se fazia antes, quebrava a checagem de duplicata: o SQLite lê uma hora
        solta como horário de 2000-01-01, então `date(hora_presenca)` nunca
        batia com a data de hoje e todo reconhecimento virava uma linha nova.
        """
        agora = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id FROM presencas_evento
                WHERE evento_id = ? AND usuario_id = ?
                  AND date(hora_presenca) = date(?)
                """,
                (evento_id, usuario_id, agora),
            )
            if cursor.fetchone():
                return False

            cursor.execute(
                """
                INSERT INTO presencas_evento
                    (evento_id, usuario_id, nome_usuario, hora_presenca, sync_status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (evento_id, usuario_id, nome_usuario, agora),
            )
            conn.commit()
        return True

    @staticmethod
    def formatar_hora_presenca(valor):
        """Devolve HH:MM:SS a partir do que estiver gravado.

        Registros anteriores à correção guardam apenas a hora; os novos
        guardam a data e hora em ISO. Aceita os dois.
        """
        if not valor:
            return ""
        try:
            return datetime.fromisoformat(valor).strftime("%H:%M:%S")
        except ValueError:
            return valor

    def listar_presencas_evento(self, evento_id):
        """Lista as presenças de um evento, em ordem cronológica."""
        with self._connect(row_factory=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM presencas_evento
                WHERE evento_id = ?
                ORDER BY hora_presenca
                """,
                (evento_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # ===== SINCRONIZAÇÃO COM SUPABASE =====
    def sync_usuario_supabase(self, usuario_id):
        """Envia (upsert) um usuário para o Supabase."""
        if not self.check_internet():
            return False

        usuario = self.buscar_usuario(usuario_id)
        if not usuario:
            return False

        try:
            payload = {
                "id": usuario["id"],
                "name": usuario["name"],
                "group": usuario.get("group_name", ""),
                "phone": usuario.get("phone", ""),
                "total_attendance": usuario["total_attendance"],
                "last_attendance_time": usuario.get("last_attendance_time"),
            }
            payload = {k: v for k, v in payload.items() if v is not None}

            headers = dict(self.supabase_headers)
            headers["Prefer"] = "resolution=merge-duplicates"

            response = requests.post(
                f"{config.SUPABASE_URL}/rest/v1/{config.SUPABASE_TABLE}",
                headers=headers,
                json=payload,
                timeout=config.REQUEST_TIMEOUT,
            )

            if response.status_code in (200, 201, 204):
                self.update_sync_status(usuario_id, "synced")
                self.log_sync("usuario", f"Usuário {usuario_id} sincronizado", "success")
                return True

            self.log_sync(
                "usuario", f"Erro {response.status_code}: {response.text}", "error"
            )
            return False
        except Exception as e:
            self.log_sync("usuario", f"Exceção: {e}", "error")
            return False

    def sync_todos_usuarios_pendentes(self):
        """Envia todos os usuários pendentes. Retorna (sucessos, falhas)."""
        if not self.check_internet():
            return 0, 0

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE sync_status = 'pending'")
            pendentes = [row[0] for row in cursor.fetchall()]

        sucessos = falhas = 0
        for usuario_id in pendentes:
            if self.sync_usuario_supabase(usuario_id):
                sucessos += 1
            else:
                falhas += 1
            time.sleep(0.1)  # Evita sobrecarregar a API.

        return sucessos, falhas

    def download_usuarios_supabase(self):
        """Baixa usuários do Supabase. Retorna quantos foram adicionados."""
        if not self.check_internet():
            return 0

        try:
            response = requests.get(
                f"{config.SUPABASE_URL}/rest/v1/{config.SUPABASE_TABLE}",
                headers=self.supabase_headers,
                timeout=config.REQUEST_TIMEOUT,
            )

            if response.status_code != 200:
                self.log_sync("download", f"Erro {response.status_code}", "error")
                return 0

            adicionados = 0
            for usuario in response.json():
                usuario_id = usuario.get("id")
                if not usuario_id:
                    continue

                local = self.buscar_usuario(usuario_id)
                if local is None:
                    adicionados += 1
                elif (local["name"] == usuario.get("name")
                      and local.get("group_name") == usuario.get("group")):
                    continue  # Nada mudou.

                self.adicionar_usuario(
                    usuario_id=usuario_id,
                    nome=usuario.get("name", ""),
                    grupo=usuario.get("group", ""),
                    telefone=usuario.get("phone", ""),
                )

            self.log_sync("download", f"{adicionados} usuários baixados", "success")
            return adicionados
        except Exception as e:
            self.log_sync("download", f"Exceção: {e}", "error")
            return 0

    def sync_completo(self):
        """Upload dos pendentes + download das atualizações."""
        if not self.check_internet():
            return {"status": "offline", "message": "Sem conexão com internet"}

        try:
            sucessos, falhas = self.sync_todos_usuarios_pendentes()
            return {
                "status": "success",
                "uploads_success": sucessos,
                "uploads_failed": falhas,
                "downloads": self.download_usuarios_supabase(),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def log_sync(self, tipo, detalhes, status):
        """Grava uma linha no histórico de sincronização."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sync_log (tipo, detalhes, status, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (tipo, detalhes, status, datetime.now().isoformat()),
            )
            conn.commit()

    def listar_logs(self, limite=10):
        """Últimos registros do histórico de sincronização (mais recentes
        primeiro)."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tipo, detalhes, status, timestamp
                FROM sync_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limite,),
            )
            return cursor.fetchall()

    # ===== ESTATÍSTICAS =====
    def _contar(self, cursor, sql, params=()):
        cursor.execute(sql, params)
        return cursor.fetchone()[0]

    def get_stats(self):
        """Estatísticas gerais do sistema (usadas pelo painel principal)."""
        with self._connect() as conn:
            cursor = conn.cursor()
            return {
                "total_usuarios": self._contar(cursor, "SELECT COUNT(*) FROM usuarios"),
                "pendentes_sync": self._contar(
                    cursor, "SELECT COUNT(*) FROM usuarios WHERE sync_status = 'pending'"
                ),
                "sincronizados": self._contar(
                    cursor, "SELECT COUNT(*) FROM usuarios WHERE sync_status = 'synced'"
                ),
                "total_eventos": self._contar(cursor, "SELECT COUNT(*) FROM eventos"),
                "total_logs": self._contar(cursor, "SELECT COUNT(*) FROM sync_log"),
                "tem_internet": self.check_internet(),
            }

    def get_database_stats(self):
        """Estatísticas resumidas (usadas pelas telas de cadastro)."""
        with self._connect() as conn:
            cursor = conn.cursor()
            return {
                "total_registrations": self._contar(
                    cursor, "SELECT COUNT(*) FROM usuarios"
                ),
                "pending_sync": self._contar(
                    cursor, "SELECT COUNT(*) FROM usuarios WHERE sync_status = 'pending'"
                ),
                "synced": self._contar(
                    cursor, "SELECT COUNT(*) FROM usuarios WHERE sync_status = 'synced'"
                ),
            }

    # ===== BACKUP =====
    def backup(self, prefixo="backup"):
        """Copia o banco para `data/backups/`. Retorna o caminho gerado."""
        import shutil

        config.ensure_directories()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = config.BACKUPS_DIR / f"{prefixo}_{timestamp}.db"
        shutil.copy2(self.db_path, destino)
        return str(destino)
