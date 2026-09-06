"""
Tela de Cadastro em Lote — importa uma planilha, vincula fotos e processa.

Toda a lógica — leitura da planilha, geração de IDs, vínculo de fotos e
encodings — vive em `club272.core.importacao`; aqui só há interface.
"""

import os
import threading
from tkinter import filedialog

import customtkinter as ctk

from club272 import config
from club272.core import importacao
from club272.core.database import DatabaseManager
from club272.ui.components import (
    Badge,
    Botao,
    Card,
    EstadoVazio,
    Metrica,
    Progresso,
    Tabela,
)
from club272.ui.shell import Tela
from club272.ui.theme import Cor, Espaco, Fonte


class TelaLote(Tela):
    titulo = "Cadastro em lote"
    subtitulo = "Importação por CSV ou Excel"

    def __init__(self, master, app):
        self.db = DatabaseManager()
        self.cadastros = []
        self.caminho_planilha = None
        self.processando = False
        super().__init__(master, app)

    # ===== LAYOUT =====
    def construir(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._construir_acoes()
        self._construir_indicadores()
        self._construir_tabela()
        self._construir_rodape()

    def _construir_acoes(self):
        card = Card(self)
        card.grid(row=0, column=0, sticky="ew", pady=(0, Espaco.MD))

        linha = ctk.CTkFrame(card.corpo, fg_color="transparent")
        linha.pack(fill="x")

        Botao(linha, "Importar planilha", "primario", width=170,
              command=self._importar).pack(side="left")

        Botao(linha, "Vincular fotos", "fantasma", width=150,
              command=self._vincular).pack(side="left", padx=Espaco.SM)

        Botao(linha, "Baixar modelo", "fantasma", width=140,
              command=self._baixar_modelo).pack(side="left")

        self.label_arquivo = ctk.CTkLabel(
            linha, text="Nenhuma planilha carregada", font=Fonte.PEQUENO,
            text_color=Cor.TEXTO_APAGADO,
        )
        self.label_arquivo.pack(side="right")

    def _construir_indicadores(self):
        faixa = ctk.CTkFrame(self, fg_color="transparent")
        faixa.grid(row=1, column=0, sticky="ew", pady=(0, Espaco.MD))
        faixa.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="m")

        self.m_linhas = Metrica(faixa, "linhas", 0, Cor.ACENTO)
        self.m_linhas.grid(row=0, column=0, sticky="ew", padx=(0, Espaco.SM))

        self.m_com_foto = Metrica(faixa, "com foto", 0, Cor.SUCESSO)
        self.m_com_foto.grid(row=0, column=1, sticky="ew", padx=Espaco.XS)

        self.m_sem_foto = Metrica(faixa, "sem foto", 0, Cor.ALERTA)
        self.m_sem_foto.grid(row=0, column=2, sticky="ew", padx=Espaco.XS)

        self.m_novos = Metrica(faixa, "id gerado", 0, Cor.TEXTO_SECUNDARIO)
        self.m_novos.grid(row=0, column=3, sticky="ew", padx=(Espaco.SM, 0))

    def _construir_tabela(self):
        card = Card(self, titulo="Cadastros a importar")
        card.grid(row=2, column=0, sticky="nsew")

        self.area_tabela = ctk.CTkFrame(card.corpo, fg_color="transparent")
        self.area_tabela.pack(fill="both", expand=True)

        self.tabela = None
        self._mostrar_vazio()

    def _construir_rodape(self):
        card = Card(self)
        card.grid(row=3, column=0, sticky="ew", pady=(Espaco.MD, 0))

        opcoes = ctk.CTkFrame(card.corpo, fg_color="transparent")
        opcoes.pack(fill="x", pady=(0, Espaco.MD))

        self.validar_rosto = ctk.CTkCheckBox(
            opcoes, text="Exigir rosto detectável na foto", font=Fonte.PEQUENO,
            text_color=Cor.TEXTO_SECUNDARIO, fg_color=Cor.ACENTO,
            hover_color=Cor.ACENTO_HOVER, checkmark_color=Cor.TEXTO_SOBRE_ACENTO,
            border_color=Cor.BORDA,
        )
        self.validar_rosto.select()
        self.validar_rosto.pack(side="left")

        self.pular_existentes = ctk.CTkCheckBox(
            opcoes, text="Pular quem já está cadastrado", font=Fonte.PEQUENO,
            text_color=Cor.TEXTO_SECUNDARIO, fg_color=Cor.ACENTO,
            hover_color=Cor.ACENTO_HOVER, checkmark_color=Cor.TEXTO_SOBRE_ACENTO,
            border_color=Cor.BORDA,
        )
        self.pular_existentes.select()
        self.pular_existentes.pack(side="left", padx=Espaco.XL)

        self.botao_processar = Botao(
            opcoes, "Processar cadastros", "sucesso", width=190,
            command=self._processar, state="disabled",
        )
        self.botao_processar.pack(side="right")

        self.progresso = Progresso(card.corpo)
        self.progresso.pack(fill="x")

    # ===== CICLO DE VIDA =====
    def ao_entrar(self):
        self.app.badge(f"{len(self.cadastros)} na fila" if self.cadastros
                       else "Nenhuma planilha", "acento" if self.cadastros else "neutro")
        self.app.status_direita(f"{len(self.db.listar_usuarios())} membros cadastrados")

    # ===== AÇÕES =====
    def _importar(self):
        caminho = filedialog.askopenfilename(
            title="Selecionar planilha",
            filetypes=[("Planilhas", "*.csv *.xlsx *.xls"),
                       ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            return

        try:
            df = importacao.ler_planilha(caminho)
            self.cadastros = importacao.montar_cadastros(df, self.db, caminho)
        except Exception as e:
            self.app.status(f"Erro ao ler a planilha: {e}", Cor.PERIGO)
            return

        self.caminho_planilha = caminho
        self.label_arquivo.configure(text=os.path.basename(caminho))
        self.app.status(f"{len(self.cadastros)} linhas carregadas", Cor.SUCESSO)
        self._atualizar()

    def _vincular(self):
        if not self.cadastros:
            self.app.status("Importe uma planilha primeiro", Cor.ALERTA)
            return

        pasta = filedialog.askdirectory(title="Pasta com as fotos")
        if not pasta:
            return

        vinculadas = importacao.vincular_fotos(self.cadastros, pasta)
        self.app.status(
            f"{vinculadas} foto(s) vinculada(s) por ID ou nome",
            Cor.SUCESSO if vinculadas else Cor.ALERTA,
        )
        self._atualizar()

    def _baixar_modelo(self):
        caminho = importacao.escrever_modelo()
        self.app.status(f"Modelo disponível em {caminho}", Cor.TEXTO_SECUNDARIO)
        try:
            os.startfile(config.TEMPLATES_DIR)  # noqa: S606 (abre o explorador)
        except (AttributeError, OSError):
            pass

    def _processar(self):
        if self.processando or not self.cadastros:
            return

        self.processando = True
        self.botao_processar.configure(state="disabled", text="Processando...")
        self.app.badge("Processando", "alerta")

        validar = bool(self.validar_rosto.get())
        pular = bool(self.pular_existentes.get())
        self.db.backup(prefixo="antes_do_lote")

        def progresso(indice, total, cadastro, situacao):
            self.entregar(self.progresso.atualizar, indice, total,
                          f"{cadastro.id} · {cadastro.nome}")

        def trabalho():
            resultado = importacao.processar(
                self.cadastros, self.db,
                validar_rosto=validar, pular_existentes=pular,
                progresso=progresso,
            )
            self.entregar(self._concluido, resultado)

        threading.Thread(target=trabalho, daemon=True).start()

    def _concluido(self, resultado):
        self.processando = False
        self.botao_processar.configure(state="normal", text="Processar cadastros")
        self.progresso.zerar()

        partes = [f"{resultado.sucessos} cadastrado(s)"]
        if resultado.ignorados:
            partes.append(f"{resultado.ignorados} ignorado(s)")
        if resultado.erros:
            partes.append(f"{resultado.erros} com erro")

        tom = Cor.PERIGO if resultado.erros else Cor.SUCESSO
        self.app.status(" · ".join(partes), tom)
        self.app.badge("Concluído", "perigo" if resultado.erros else "sucesso")
        self.app.status_direita(f"{len(self.db.listar_usuarios())} membros cadastrados")

        # Os erros importam mais que o resumo: ficam listados na própria tabela.
        if resultado.mensagens:
            self._mostrar_erros(resultado.mensagens)
        else:
            self._atualizar()

    # ===== EXIBIÇÃO =====
    def _mostrar_vazio(self):
        for widget in self.area_tabela.winfo_children():
            widget.destroy()
        EstadoVazio(
            self.area_tabela, "📄", "Nenhuma planilha carregada",
            "Importe um CSV ou Excel com as colunas id, nome, grupo, "
            "telefone e foto.",
        ).pack(fill="both", expand=True)

    def _nova_tabela(self, colunas, pesos):
        for widget in self.area_tabela.winfo_children():
            widget.destroy()
        self.tabela = Tabela(self.area_tabela, colunas, pesos)
        self.tabela.pack(fill="both", expand=True)

    def _atualizar(self):
        if not self.cadastros:
            self._mostrar_vazio()
            self.botao_processar.configure(state="disabled")
            return

        com_foto = sum(1 for c in self.cadastros if c.tem_foto)
        gerados = sum(1 for c in self.cadastros if c.id_gerado)

        self.m_linhas.definir(len(self.cadastros))
        self.m_com_foto.definir(com_foto)
        self.m_sem_foto.definir(len(self.cadastros) - com_foto)
        self.m_novos.definir(gerados)

        self._nova_tabela(
            ["ID", "Nome", "Grupo", "Telefone", "Foto"], [2, 4, 2, 2, 2]
        )
        for c in self.cadastros:
            tem = c.tem_foto
            self.tabela.adicionar(
                [c.id, c.nome, c.grupo, c.telefone or "—",
                 "vinculada" if tem else "faltando"],
                dado=c,
                tons={4: Cor.SUCESSO if tem else Cor.ALERTA},
            )

        self.botao_processar.configure(state="normal")
        self.app.badge(f"{len(self.cadastros)} na fila", "acento")

    def _mostrar_erros(self, mensagens):
        """Lista o que falhou, para o problema não ficar num alerta que some."""
        self._nova_tabela(["Cadastro", "Motivo"], [2, 5])
        for mensagem in mensagens:
            alvo, _, motivo = mensagem.partition(": ")
            self.tabela.adicionar([alvo, motivo], tons={1: Cor.PERIGO})

        rodape = Badge(self.area_tabela, f"{len(mensagens)} com erro", "perigo")
        rodape.pack(pady=(Espaco.SM, 0))
