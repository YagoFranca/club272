"""
Tela de Eventos — histórico, lista de presença e exportação.

Existe porque o relatório de um evento encerrado não tinha como ser
alcançado: a exportação partia sempre do evento aberto, e as presenças dos
eventos passados ficavam no banco sem nenhuma tela que chegasse até elas.
"""

import csv
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

from club272.core.database import DatabaseManager
from club272.ui.components import Badge, Botao, Card, EstadoVazio, Metrica, Tabela
from club272.ui.shell import Tela
from club272.ui.theme import Cor, Espaco, Fonte


def _data_curta(iso):
    """'2026-09-22T18:49:57' -> '22/09/2026 18:49'."""
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso[:16]


class TelaEventos(Tela):
    titulo = "Eventos"
    subtitulo = "Histórico, presenças e relatórios"

    def __init__(self, master, app):
        self.db = DatabaseManager()
        self.eventos = []
        self.selecionado = None
        self._confirmando_remocao = False
        super().__init__(master, app)

    # ===== LAYOUT =====
    def construir(self):
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(1, weight=1)

        self._construir_indicadores()
        self._construir_lista()
        self._construir_detalhe()

    def _construir_indicadores(self):
        faixa = ctk.CTkFrame(self, fg_color="transparent")
        faixa.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, Espaco.LG))
        faixa.grid_columnconfigure((0, 1, 2), weight=1, uniform="m")

        self.m_total = Metrica(faixa, "eventos", 0, Cor.ACENTO)
        self.m_total.grid(row=0, column=0, sticky="ew", padx=(0, Espaco.SM))

        self.m_presencas = Metrica(faixa, "presenças no total", 0, Cor.SUCESSO)
        self.m_presencas.grid(row=0, column=1, sticky="ew", padx=Espaco.XS)

        self.m_media = Metrica(faixa, "média por evento", "0", Cor.TEXTO_SECUNDARIO)
        self.m_media.grid(row=0, column=2, sticky="ew", padx=(Espaco.SM, 0))

    def _construir_lista(self):
        card = Card(self, titulo="Todos os eventos")
        card.grid(row=1, column=0, sticky="nsew", padx=(0, Espaco.LG))

        self.area_lista = ctk.CTkFrame(card.corpo, fg_color="transparent")
        self.area_lista.pack(fill="both", expand=True)
        self.tabela = None

    def _construir_detalhe(self):
        card = Card(self, titulo="Lista de presença")
        card.grid(row=1, column=1, sticky="nsew")
        self.area_detalhe = card.corpo
        self._mostrar_sem_selecao()

    # ===== CICLO DE VIDA =====
    def ao_entrar(self):
        self.eventos = self.db.listar_eventos()

        total_presencas = sum(e["total_presencas"] for e in self.eventos)
        self.m_total.definir(len(self.eventos))
        self.m_presencas.definir(total_presencas)
        self.m_media.definir(
            f"{total_presencas / len(self.eventos):.1f}" if self.eventos else "0"
        )

        aberto = next((e for e in self.eventos if e["status"] == "aberto"), None)
        if aberto:
            self.app.badge(f"{aberto['nome']} em andamento", "sucesso")
        else:
            self.app.badge(f"{len(self.eventos)} eventos", "acento")
        self.app.status_direita("")

        self._preencher_lista()
        # Mantém a seleção viva entre visitas, se o evento ainda existir.
        if self.selecionado and self.db.buscar_evento(self.selecionado["id"]):
            self._selecionar(self.db.buscar_evento(self.selecionado["id"]))
        else:
            self.selecionado = None
            self._mostrar_sem_selecao()

    # ===== LISTA =====
    def _preencher_lista(self):
        for widget in self.area_lista.winfo_children():
            widget.destroy()

        if not self.eventos:
            EstadoVazio(
                self.area_lista, "📅", "Nenhum evento ainda",
                "Abra um evento na tela de Presença para começar a registrar.",
            ).pack(fill="both", expand=True)
            self.tabela = None
            self.app.status("Nenhum evento registrado")
            return

        self.tabela = Tabela(
            self.area_lista, ["Evento", "Início", "Presenças", "Situação"],
            [4, 3, 2, 2], ao_selecionar=self._selecionar,
        )
        self.tabela.pack(fill="both", expand=True)

        for e in self.eventos:
            aberto = e["status"] == "aberto"
            self.tabela.adicionar(
                [e["nome"], _data_curta(e["data_inicio"]),
                 e["total_presencas"], "em andamento" if aberto else "encerrado"],
                dado=e,
                tons={3: Cor.SUCESSO if aberto else Cor.TEXTO_APAGADO},
            )

        self.app.status(f"{len(self.eventos)} evento(s)")

    # ===== DETALHE =====
    def _limpar_detalhe(self):
        for widget in self.area_detalhe.winfo_children():
            widget.destroy()
        self._confirmando_remocao = False

    def _mostrar_sem_selecao(self):
        self._limpar_detalhe()
        EstadoVazio(
            self.area_detalhe, "📋", "Nenhum evento selecionado",
            "Clique num evento da lista para ver quem esteve presente.",
        ).pack(fill="both", expand=True)

    def _selecionar(self, evento):
        self.selecionado = evento
        self._limpar_detalhe()

        aberto = evento["status"] == "aberto"
        presencas = self.db.listar_presencas_evento(evento["id"])

        cabecalho = ctk.CTkFrame(self.area_detalhe, fg_color="transparent")
        cabecalho.pack(fill="x", pady=(0, Espaco.MD))

        ctk.CTkLabel(
            cabecalho, text=evento["nome"], font=Fonte.SUBTITULO,
            text_color=Cor.TEXTO, anchor="w",
        ).pack(side="left")

        Badge(cabecalho, "em andamento" if aberto else "encerrado",
              "sucesso" if aberto else "neutro").pack(side="right")

        periodo = ctk.CTkFrame(self.area_detalhe, fg_color="transparent")
        periodo.pack(fill="x", pady=(0, Espaco.LG))
        for rotulo, valor in (
            ("Início", _data_curta(evento["data_inicio"])),
            ("Término", _data_curta(evento["data_fim"]) if not aberto else "—"),
            ("Presentes", str(len(presencas))),
        ):
            linha = ctk.CTkFrame(periodo, fg_color="transparent")
            linha.pack(fill="x", pady=1)
            ctk.CTkLabel(linha, text=rotulo, font=Fonte.MICRO,
                         text_color=Cor.TEXTO_APAGADO).pack(side="left")
            ctk.CTkLabel(linha, text=valor, font=Fonte.PEQUENO,
                         text_color=Cor.TEXTO_SECUNDARIO).pack(side="right")

        lista = ctk.CTkScrollableFrame(
            self.area_detalhe, fg_color="transparent",
            scrollbar_button_color=Cor.BORDA,
        )
        lista.pack(fill="both", expand=True)

        if presencas:
            tabela = Tabela(lista, ["Nome", "ID", "Hora"], [4, 2, 2])
            tabela.pack(fill="both", expand=True)
            for p in presencas:
                tabela.adicionar([
                    p["nome_usuario"], p["usuario_id"],
                    self.db.formatar_hora_presenca(p["hora_presenca"]),
                ])
        else:
            EstadoVazio(lista, "🕳️", "Ninguém registrado",
                        "Este evento não teve presenças.").pack(
                fill="both", expand=True)

        acoes = ctk.CTkFrame(self.area_detalhe, fg_color="transparent")
        acoes.pack(fill="x", pady=(Espaco.LG, 0))

        Botao(acoes, "Exportar lista (CSV)", "primario",
              command=self._exportar).pack(fill="x", pady=(0, Espaco.SM))

        self.botao_remover = Botao(
            acoes, "Apagar evento", "fantasma", command=self._remover
        )
        self.botao_remover.pack(fill="x")

    # ===== AÇÕES =====
    def _exportar(self):
        evento = self.selecionado
        presencas = self.db.listar_presencas_evento(evento["id"])
        if not presencas:
            self.app.status("Este evento não tem presenças para exportar",
                            Cor.ALERTA)
            return

        # O nome do evento vira parte do arquivo, limpo do que o Windows
        # rejeita em nome de arquivo.
        seguro = "".join(c if c.isalnum() or c in " -_" else "_"
                         for c in evento["nome"]).strip() or "evento"
        sugerido = f"presencas_{seguro}_{datetime.now():%Y%m%d}.csv"

        caminho = filedialog.asksaveasfilename(
            title="Salvar lista de presença", defaultextension=".csv",
            initialfile=sugerido, filetypes=[("CSV", "*.csv")],
        )
        if not caminho:
            return

        membros = {u["id"]: u for u in self.db.listar_usuarios()}

        # utf-8-sig: sem o BOM, o Excel em português abre os acentos errados.
        with open(caminho, "w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.writer(arquivo)
            escritor.writerow(["evento", evento["nome"]])
            escritor.writerow(["inicio", _data_curta(evento["data_inicio"])])
            escritor.writerow(["termino", _data_curta(evento["data_fim"])])
            escritor.writerow([])
            escritor.writerow(["id", "nome", "grupo", "hora"])
            for p in presencas:
                membro = membros.get(p["usuario_id"], {})
                escritor.writerow([
                    p["usuario_id"], p["nome_usuario"],
                    membro.get("group_name") or "",
                    self.db.formatar_hora_presenca(p["hora_presenca"]),
                ])

        self.app.status(f"{len(presencas)} presença(s) exportada(s)", Cor.SUCESSO)

    def _remover(self):
        """Dois cliques: o primeiro pede confirmação no próprio botão."""
        if not self._confirmando_remocao:
            self._confirmando_remocao = True
            self.botao_remover.configure(
                text="Confirmar exclusão?", fg_color=Cor.PERIGO,
                hover_color=Cor.PERIGO_HOVER, text_color=Cor.TEXTO_SOBRE_ACENTO,
                border_width=0,
            )
            self.app.status(
                "Clique de novo para apagar o evento e as presenças dele",
                Cor.ALERTA,
            )
            return

        nome = self.selecionado["nome"]
        self.db.remover_evento(self.selecionado["id"])
        self.selecionado = None
        self.app.status(f"Evento '{nome}' apagado", Cor.TEXTO_SECUNDARIO)
        self._mostrar_sem_selecao()
        self.ao_entrar()
