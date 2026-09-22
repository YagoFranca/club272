"""
Tela de Sincronização — estado da nuvem, envio/recebimento e relatórios.

As chamadas HTTP vivem em `club272.core.supabase`; aqui só há interface.

Toda operação de rede roda em thread — uma chamada travada não pode congelar
a janela, e é justamente o que acontece quando o projeto Supabase está fora do
ar.
"""

import threading
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

from club272 import config
from club272.core import exportacao
from club272.core.database import DatabaseManager
from club272.core.supabase import SupabaseManager
from club272.ui.components import Abas, Badge, Botao, Card, EstadoVazio, Metrica, Tabela
from club272.ui.shell import Tela
from club272.ui.theme import Cor, Espaco, Fonte


class TelaSincronizacao(Tela):
    titulo = "Sincronização"
    subtitulo = "Integração com o Supabase"

    def __init__(self, master, app):
        self.db = DatabaseManager()
        self.nuvem = None
        self.ocupado = False
        super().__init__(master, app)

    # ===== LAYOUT =====
    def construir(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._construir_indicadores()

        abas = Abas(self, ["Situação", "Membros na nuvem", "Relatórios"])
        abas.grid(row=1, column=0, sticky="nsew")
        self.abas = abas

        self._construir_situacao(abas.painel("Situação"))
        self._construir_membros(abas.painel("Membros na nuvem"))
        self._construir_relatorios(abas.painel("Relatórios"))

    def _construir_indicadores(self):
        faixa = ctk.CTkFrame(self, fg_color="transparent")
        faixa.grid(row=0, column=0, sticky="ew", pady=(0, Espaco.LG))
        faixa.grid_columnconfigure((0, 1, 2), weight=1, uniform="m")

        self.m_local = Metrica(faixa, "no banco local", 0, Cor.ACENTO)
        self.m_local.grid(row=0, column=0, sticky="ew", padx=(0, Espaco.SM))

        self.m_pendentes = Metrica(faixa, "a enviar", 0, Cor.ALERTA)
        self.m_pendentes.grid(row=0, column=1, sticky="ew", padx=Espaco.XS)

        self.m_nuvem = Metrica(faixa, "na nuvem", "—", Cor.TEXTO_SECUNDARIO)
        self.m_nuvem.grid(row=0, column=2, sticky="ew", padx=(Espaco.SM, 0))

    def _construir_situacao(self, painel):
        card = Card(painel, titulo="Conexão")
        card.pack(fill="x", pady=(0, Espaco.LG))

        linha = ctk.CTkFrame(card.corpo, fg_color="transparent")
        linha.pack(fill="x")

        self.label_url = ctk.CTkLabel(
            linha, text="—", font=Fonte.CODIGO,
            text_color=Cor.TEXTO_SECUNDARIO, anchor="w",
        )
        self.label_url.pack(side="left")

        self.badge_conexao = Badge(linha, "verificando", "neutro")
        self.badge_conexao.pack(side="right")

        self.label_diagnostico = ctk.CTkLabel(
            card.corpo, text="", font=Fonte.PEQUENO,
            text_color=Cor.TEXTO_APAGADO, anchor="w", justify="left",
            wraplength=700,
        )
        self.label_diagnostico.pack(fill="x", pady=(Espaco.MD, 0))

        acoes = Card(painel, titulo="Ações")
        acoes.pack(fill="x")

        botoes = ctk.CTkFrame(acoes.corpo, fg_color="transparent")
        botoes.pack(fill="x")

        self.botao_testar = Botao(botoes, "Testar conexão", "fantasma", width=150,
                                  command=self._testar)
        self.botao_testar.pack(side="left")

        self.botao_enviar = Botao(botoes, "Enviar pendentes", "primario", width=170,
                                  command=self._enviar)
        self.botao_enviar.pack(side="left", padx=Espaco.SM)

        self.botao_baixar = Botao(botoes, "Baixar da nuvem", "fantasma", width=160,
                                  command=self._baixar)
        self.botao_baixar.pack(side="left")

        card_log = Card(painel, titulo="Histórico")
        card_log.pack(fill="both", expand=True, pady=(Espaco.LG, 0))

        self.tabela_log = Tabela(card_log.corpo, ["Quando", "Tipo", "Detalhe"],
                                 [2, 2, 6])
        self.tabela_log.pack(fill="both", expand=True)

    def _construir_membros(self, painel):
        card = Card(painel, titulo="Cadastros no Supabase")
        card.pack(fill="both", expand=True)

        self.area_nuvem = ctk.CTkFrame(card.corpo, fg_color="transparent")
        self.area_nuvem.pack(fill="both", expand=True)

        EstadoVazio(self.area_nuvem, "☁️", "Nada carregado",
                    "Use “Testar conexão” para consultar a nuvem.").pack(
            fill="both", expand=True)

    def _construir_relatorios(self, painel):
        card = Card(painel, titulo="Exportar")
        card.pack(fill="x", pady=(0, Espaco.LG))

        linha = ctk.CTkFrame(card.corpo, fg_color="transparent")
        linha.pack(fill="x")

        Botao(linha, "Exportar membros", "fantasma", width=170,
              command=self._exportar_membros).pack(side="left")

        ctk.CTkLabel(
            linha, text="Listas de presença ficam na tela de Eventos",
            font=Fonte.PEQUENO, text_color=Cor.TEXTO_APAGADO,
        ).pack(side="left", padx=Espaco.LG)

        card_grupos = Card(painel, titulo="Membros por grupo")
        card_grupos.pack(fill="both", expand=True)

        self.tabela_grupos = Tabela(card_grupos.corpo,
                                    ["Grupo", "Membros", "Presenças"], [4, 2, 2])
        self.tabela_grupos.pack(fill="both", expand=True)

    # ===== CICLO DE VIDA =====
    def ao_entrar(self):
        self._atualizar_locais()
        self._atualizar_log()
        self._atualizar_grupos()

        self.label_url.configure(text=config.SUPABASE_URL or "(não configurado)")

        if not config.supabase_configurado():
            self.badge_conexao.atualizar("não configurado", "alerta")
            self.label_diagnostico.configure(
                text="Preencha SUPABASE_URL e SUPABASE_KEY no arquivo .env. "
                     "Sem isso o sistema funciona normalmente offline: os "
                     "cadastros ficam marcados como pendentes até haver destino."
            )
            self.app.badge("Offline", "alerta")
        else:
            self._testar()

    # ===== REDE (sempre em thread) =====
    def _em_thread(self, trabalho, rotulo):
        """Roda `trabalho()` fora da interface e devolve o resultado a ela."""
        if self.ocupado:
            return
        self.ocupado = True
        self.app.status(rotulo, Cor.ALERTA)

        def executar():
            try:
                resultado, erro = trabalho(), None
            except Exception as e:
                resultado, erro = None, e
            self.entregar(self._concluir, resultado, erro)

        threading.Thread(target=executar, daemon=True).start()

    def _concluir(self, resultado, erro):
        self.ocupado = False
        if erro is not None:
            self.app.status(f"Falha: {erro}", Cor.PERIGO)
            self.badge_conexao.atualizar("erro", "perigo")
            return
        if callable(resultado):
            resultado()

    def _testar(self):
        def trabalho():
            self.nuvem = SupabaseManager()
            conectado = self.nuvem.connected
            usuarios = self.nuvem.get_all_users() if conectado else []

            def aplicar():
                if conectado:
                    self.badge_conexao.atualizar("conectado", "sucesso")
                    self.label_diagnostico.configure(text="")
                    self.app.badge("Conectado", "sucesso")
                    self.m_nuvem.definir(len(usuarios))
                    self._preencher_nuvem(usuarios)
                    self.app.status(f"{len(usuarios)} cadastros na nuvem", Cor.SUCESSO)
                else:
                    self.badge_conexao.atualizar("inacessível", "perigo")
                    self.label_diagnostico.configure(
                        text="O endereço não respondeu. Se o projeto Supabase foi "
                             "removido, o subdomínio deixa de existir no DNS — "
                             "crie um projeto novo e troque SUPABASE_URL e "
                             "SUPABASE_KEY no .env. O sistema segue funcionando "
                             "offline."
                    )
                    self.app.badge("Sem conexão", "perigo")
                    self.m_nuvem.definir("—")
                    self.app.status("Supabase inacessível", Cor.PERIGO)

            return aplicar

        self._em_thread(trabalho, "Testando conexão...")

    def _enviar(self):
        def trabalho():
            sucessos, falhas = self.db.sync_todos_usuarios_pendentes()

            def aplicar():
                tom = Cor.PERIGO if falhas else Cor.SUCESSO
                self.app.status(f"{sucessos} enviado(s), {falhas} falha(s)", tom)
                self._atualizar_locais()
                self._atualizar_log()

            return aplicar

        self._em_thread(trabalho, "Enviando pendentes...")

    def _baixar(self):
        def trabalho():
            baixados = self.db.download_usuarios_supabase()

            def aplicar():
                self.app.status(f"{baixados} cadastro(s) baixado(s)", Cor.SUCESSO)
                self._atualizar_locais()
                self._atualizar_log()

            return aplicar

        self._em_thread(trabalho, "Baixando da nuvem...")

    # ===== EXIBIÇÃO =====
    def _atualizar_locais(self):
        estatisticas = self.db.get_database_stats()
        self.m_local.definir(estatisticas["total_registrations"])
        self.m_pendentes.definir(estatisticas["pending_sync"])
        self.app.status_direita(
            f"{estatisticas['total_registrations']} membros cadastrados"
        )

    def _atualizar_log(self):
        self.tabela_log.limpar()
        registros = self.db.listar_logs(limite=30)
        if not registros:
            return
        tons = {"success": Cor.SUCESSO, "error": Cor.PERIGO}
        for tipo, detalhes, situacao, marca in registros:
            self.tabela_log.adicionar(
                [self.db.formatar_hora_presenca(marca), tipo, detalhes],
                tons={2: tons.get(situacao, Cor.TEXTO_SECUNDARIO)},
            )

    def _preencher_nuvem(self, usuarios):
        for widget in self.area_nuvem.winfo_children():
            widget.destroy()

        if not usuarios:
            EstadoVazio(self.area_nuvem, "☁️", "Nuvem vazia",
                        "Nenhum cadastro no Supabase ainda.").pack(
                fill="both", expand=True)
            return

        tabela = Tabela(self.area_nuvem, ["ID", "Nome", "Grupo", "Presenças"],
                        [2, 4, 2, 2])
        tabela.pack(fill="both", expand=True)
        for u in usuarios:
            tabela.adicionar([
                u.get("id", "—"), u.get("name", "—"),
                u.get("group", "—"), u.get("total_attendance", 0),
            ])

    def _atualizar_grupos(self):
        self.tabela_grupos.limpar()
        grupos = {}
        for usuario in self.db.listar_usuarios():
            nome = usuario["group_name"] or "sem grupo"
            membros, presencas = grupos.get(nome, (0, 0))
            grupos[nome] = (membros + 1, presencas + (usuario["total_attendance"] or 0))

        if not grupos:
            return
        for nome, (membros, presencas) in sorted(
            grupos.items(), key=lambda item: -item[1][0]
        ):
            self.tabela_grupos.adicionar([nome, membros, presencas])

    # ===== EXPORTAÇÃO =====
    def _exportar_membros(self):
        usuarios = self.db.listar_usuarios()
        if not usuarios:
            self.app.status("Nenhum membro para exportar", Cor.ALERTA)
            return

        sugerido = f"membros_{datetime.now():%Y%m%d}.xlsx"
        caminho = filedialog.asksaveasfilename(
            title="Salvar lista de membros", defaultextension=".xlsx",
            initialfile=sugerido,
            filetypes=[("Planilha do Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not caminho:
            return

        linhas = []
        com_rosto = 0
        for posicao, u in enumerate(sorted(usuarios, key=lambda x: x["name"] or ""),
                                    start=1):
            tem_rosto = u["encoding"] is not None
            com_rosto += tem_rosto
            linhas.append([
                posicao,
                u["name"],
                u["group_name"] or "—",
                u["phone"] or "—",
                u["id"],
                u["total_attendance"] or 0,
                self.db.formatar_hora_presenca(u["last_attendance_time"]) or "nunca",
                "sim" if tem_rosto else "não",
            ])

        try:
            exportacao.exportar(
                caminho,
                titulo="Membros cadastrados",
                colunas=["#", "Nome", "Grupo", "Telefone", "ID",
                         "Presenças", "Última presença", "Rosto"],
                linhas=linhas,
                metadados=[("Gerado em",
                            datetime.now().strftime("%d/%m/%Y %H:%M"))],
                resumo=[
                    ("Total de membros", len(usuarios)),
                    ("Com rosto cadastrado", com_rosto),
                    ("Sem rosto", len(usuarios) - com_rosto),
                ],
            )
        except Exception as e:
            self.app.status(f"Falha ao exportar: {e}", Cor.PERIGO)
            return

        self.app.status(f"{len(usuarios)} membro(s) exportado(s)", Cor.SUCESSO)
