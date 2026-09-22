"""
Tela de Eventos — histórico, lista de presença e exportação.

Existe porque o relatório de um evento encerrado não tinha como ser
alcançado: a exportação partia sempre do evento aberto, e as presenças dos
eventos passados ficavam no banco sem nenhuma tela que chegasse até elas.
"""

from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

from club272.core import exportacao
from club272.core.database import DatabaseManager
from club272.ui.components import Badge, Botao, Card, EstadoVazio, Metrica, Tabela
from club272.ui.shell import Tela
from club272.ui.theme import Cor, Espaco, Fonte, Raio


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
        self.grid_rowconfigure(2, weight=1)

        self._construir_controle()
        self._construir_indicadores()
        self._construir_lista()
        self._construir_detalhe()

    def _construir_controle(self):
        """Abrir e encerrar evento. Fica aqui, junto do histórico, e não no
        meio da tela de captura."""
        faixa = ctk.CTkFrame(self, fg_color=Cor.SUPERFICIE, corner_radius=Raio.LG)
        faixa.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, Espaco.LG))

        interno = ctk.CTkFrame(faixa, fg_color="transparent")
        interno.pack(fill="x", padx=Espaco.XL, pady=Espaco.LG)

        esquerda = ctk.CTkFrame(interno, fg_color="transparent")
        esquerda.pack(side="left")

        ctk.CTkLabel(
            esquerda, text="EVENTO EM CURSO", font=Fonte.MICRO,
            text_color=Cor.TEXTO_APAGADO, anchor="w",
        ).pack(anchor="w")

        self.label_atual = ctk.CTkLabel(
            esquerda, text="—", font=Fonte.SUBTITULO, text_color=Cor.TEXTO,
            anchor="w",
        )
        self.label_atual.pack(anchor="w")

        self.entrada_nome = ctk.CTkEntry(
            interno, placeholder_text="Nome do novo evento", width=260, height=40,
            corner_radius=Raio.MD, fg_color=Cor.SUPERFICIE_ALTA,
            border_color=Cor.BORDA, font=Fonte.CORPO,
        )
        self.entrada_nome.pack(side="left", padx=Espaco.XL)
        self.entrada_nome.bind("<Return>", lambda _: self._alternar_evento())

        self.botao_evento = Botao(
            interno, "Abrir evento", "primario", width=160,
            command=self._alternar_evento,
        )
        self.botao_evento.pack(side="right")

    def _alternar_evento(self):
        aberto = self.db.buscar_evento_aberto()
        if aberto:
            self.db.fechar_evento(aberto["id"])
            self.app.status(f"Evento '{aberto['nome']}' encerrado", Cor.SUCESSO)
            self.selecionado = self.db.buscar_evento(aberto["id"])
        else:
            nome = self.entrada_nome.get().strip()
            if not nome:
                self.app.status("Informe um nome para o evento", Cor.ALERTA)
                return
            self.db.criar_evento(nome)
            self.entrada_nome.delete(0, "end")
            self.app.status(f"Evento '{nome}' aberto", Cor.SUCESSO)
            self.selecionado = self.db.buscar_evento_aberto()

        self.ao_entrar()

    def _atualizar_controle(self, aberto):
        if aberto:
            self.label_atual.configure(text=aberto["nome"], text_color=Cor.TEXTO)
            self.botao_evento.configure(text="Encerrar evento", fg_color=Cor.PERIGO,
                                        hover_color=Cor.PERIGO_HOVER)
            self.entrada_nome.configure(state="disabled")
        else:
            self.label_atual.configure(text="Nenhum evento aberto",
                                       text_color=Cor.TEXTO_APAGADO)
            self.botao_evento.configure(text="Abrir evento", fg_color=Cor.ACENTO,
                                        hover_color=Cor.ACENTO_HOVER)
            self.entrada_nome.configure(state="normal")

    def _construir_indicadores(self):
        faixa = ctk.CTkFrame(self, fg_color="transparent")
        faixa.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, Espaco.LG))
        faixa.grid_columnconfigure((0, 1, 2), weight=1, uniform="m")

        self.m_total = Metrica(faixa, "eventos", 0, Cor.ACENTO)
        self.m_total.grid(row=0, column=0, sticky="ew", padx=(0, Espaco.SM))

        self.m_presencas = Metrica(faixa, "presenças no total", 0, Cor.SUCESSO)
        self.m_presencas.grid(row=0, column=1, sticky="ew", padx=Espaco.XS)

        self.m_media = Metrica(faixa, "média por evento", "0", Cor.TEXTO_SECUNDARIO)
        self.m_media.grid(row=0, column=2, sticky="ew", padx=(Espaco.SM, 0))

    def _construir_lista(self):
        card = Card(self, titulo="Todos os eventos")
        card.grid(row=2, column=0, sticky="nsew", padx=(0, Espaco.LG))

        self.area_lista = ctk.CTkFrame(card.corpo, fg_color="transparent")
        self.area_lista.pack(fill="both", expand=True)
        self.tabela = None

    def _construir_detalhe(self):
        card = Card(self, titulo="Lista de presença")
        card.grid(row=2, column=1, sticky="nsew")
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
        self._atualizar_controle(aberto)
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
                self.area_lista, "calendario", "Nenhum evento ainda",
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
            self.area_detalhe, "lista", "Nenhum evento selecionado",
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
            EstadoVazio(lista, "caixa-vazia", "Ninguém registrado",
                        "Este evento não teve presenças.").pack(
                fill="both", expand=True)

        acoes = ctk.CTkFrame(self.area_detalhe, fg_color="transparent")
        acoes.pack(fill="x", pady=(Espaco.LG, 0))

        # Relatório só depois de encerrar: enquanto o evento corre, a lista
        # ainda vai mudar, e um arquivo exportado no meio vira um número
        # errado circulando por aí.
        self.botao_exportar = Botao(
            acoes,
            "Exportar lista de presença" if not aberto
            else "Encerre o evento para exportar",
            "primario",
            command=self._exportar,
            state="disabled" if aberto else "normal",
        )
        self.botao_exportar.pack(fill="x", pady=(0, Espaco.SM))

        if aberto:
            ctk.CTkLabel(
                acoes,
                text="O evento está em andamento — a lista ainda pode mudar.",
                font=Fonte.MICRO, text_color=Cor.TEXTO_APAGADO,
            ).pack(pady=(0, Espaco.SM))

        self.botao_remover = Botao(
            acoes, "Apagar evento", "fantasma", command=self._remover
        )
        self.botao_remover.pack(fill="x")

    # ===== AÇÕES =====
    def _exportar(self):
        evento = self.selecionado

        # Rede de segurança: o botão já fica desabilitado com o evento aberto.
        if evento["status"] == "aberto":
            self.app.status("Encerre o evento antes de exportar o relatório",
                            Cor.ALERTA)
            return

        presencas = self.db.listar_presencas_evento(evento["id"])
        if not presencas:
            self.app.status("Este evento não tem presenças para exportar",
                            Cor.ALERTA)
            return

        # O nome do evento entra no arquivo, limpo do que o Windows rejeita.
        seguro = "".join(c if c.isalnum() or c in " -_" else "_"
                         for c in evento["nome"]).strip() or "evento"
        sugerido = f"presencas_{seguro}_{datetime.now():%Y%m%d}.xlsx"

        caminho = filedialog.asksaveasfilename(
            title="Salvar lista de presença", defaultextension=".xlsx",
            initialfile=sugerido,
            filetypes=[("Planilha do Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not caminho:
            return

        membros = {u["id"]: u for u in self.db.listar_usuarios()}
        linhas = []
        for posicao, p in enumerate(presencas, start=1):
            membro = membros.get(p["usuario_id"], {})
            linhas.append([
                posicao,
                p["nome_usuario"],
                membro.get("group_name") or "—",
                p["usuario_id"],
                self.db.formatar_hora_presenca(p["hora_presenca"]),
            ])

        aberto = evento["status"] == "aberto"
        total_membros = len(membros)

        try:
            exportacao.exportar(
                caminho,
                titulo=f"Lista de presença — {evento['nome']}",
                colunas=["#", "Nome", "Grupo", "ID", "Hora"],
                linhas=linhas,
                metadados=[
                    ("Início", _data_curta(evento["data_inicio"])),
                    ("Término", "em andamento" if aberto
                     else _data_curta(evento["data_fim"])),
                    ("Gerado em", _data_curta(datetime.now().isoformat())),
                ],
                resumo=[
                    ("Total de presentes", len(presencas)),
                    ("Membros cadastrados", total_membros),
                    ("Taxa de presença",
                     f"{100 * len(presencas) / total_membros:.0f}%"
                     if total_membros else "—"),
                ],
            )
        except Exception as e:
            self.app.status(f"Falha ao exportar: {e}", Cor.PERIGO)
            return

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
