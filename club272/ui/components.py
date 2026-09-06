"""
Componentes reutilizáveis construídos sobre o design system.

A ideia é que as telas montem interface combinando estas peças, sem tocar em
cor, fonte ou espaçamento diretamente.
"""

import customtkinter as ctk

from club272.ui.theme import Cor, Espaco, Fonte, Raio


class Card(ctk.CTkFrame):
    """Bloco de conteúdo com superfície elevada e borda sutil.

    Passe `titulo` para ganhar um cabeçalho pronto; o conteúdo entra em
    `card.corpo`.
    """

    def __init__(self, master, titulo=None, acao=None, **kwargs):
        kwargs.setdefault("fg_color", Cor.SUPERFICIE)
        kwargs.setdefault("corner_radius", Raio.LG)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", Cor.BORDA_SUAVE)
        super().__init__(master, **kwargs)

        if titulo:
            cabecalho = ctk.CTkFrame(self, fg_color="transparent")
            cabecalho.pack(fill="x", padx=Espaco.XL, pady=(Espaco.LG, 0))

            ctk.CTkLabel(
                cabecalho, text=titulo, font=Fonte.SUBTITULO,
                text_color=Cor.TEXTO, anchor="w",
            ).pack(side="left")

            if acao:
                acao(cabecalho)

        self.corpo = ctk.CTkFrame(self, fg_color="transparent")
        self.corpo.pack(
            fill="both", expand=True,
            padx=Espaco.XL,
            pady=(Espaco.MD if titulo else Espaco.XL, Espaco.XL),
        )


class Botao(ctk.CTkButton):
    """Botão com variantes semânticas.

    `variante`: primario | sucesso | perigo | neutro | fantasma
    """

    PALETA = {
        "primario": (Cor.ACENTO, Cor.ACENTO_HOVER, Cor.TEXTO_SOBRE_ACENTO),
        "sucesso": (Cor.SUCESSO, Cor.SUCESSO_HOVER, Cor.TEXTO_SOBRE_ACENTO),
        "perigo": (Cor.PERIGO, Cor.PERIGO_HOVER, Cor.TEXTO_SOBRE_ACENTO),
        "neutro": (Cor.NEUTRO, Cor.NEUTRO_HOVER, Cor.TEXTO),
        "fantasma": ("transparent", Cor.SUPERFICIE_HOVER, Cor.TEXTO_SECUNDARIO),
    }

    def __init__(self, master, texto, variante="primario", **kwargs):
        fundo, hover, texto_cor = self.PALETA.get(variante, self.PALETA["primario"])

        kwargs.setdefault("fg_color", fundo)
        kwargs.setdefault("hover_color", hover)
        kwargs.setdefault("text_color", texto_cor)
        kwargs.setdefault("corner_radius", Raio.MD)
        kwargs.setdefault("font", Fonte.CORPO_FORTE)
        kwargs.setdefault("height", 40)
        if variante == "fantasma":
            kwargs.setdefault("border_width", 1)
            kwargs.setdefault("border_color", Cor.BORDA)

        super().__init__(master, text=texto, **kwargs)


class Badge(ctk.CTkLabel):
    """Etiqueta compacta de estado (online, pendente, erro...)."""

    PALETA = {
        "sucesso": (Cor.SUCESSO_FUNDO, Cor.SUCESSO),
        "alerta": (Cor.ALERTA_FUNDO, Cor.ALERTA),
        "perigo": (Cor.PERIGO_FUNDO, Cor.PERIGO),
        "acento": (Cor.ACENTO_FUNDO, Cor.ACENTO),
        "neutro": (Cor.SUPERFICIE_ALTA, Cor.TEXTO_SECUNDARIO),
    }

    def __init__(self, master, texto, tom="neutro", **kwargs):
        fundo, frente = self.PALETA.get(tom, self.PALETA["neutro"])
        kwargs.setdefault("fg_color", fundo)
        kwargs.setdefault("text_color", frente)
        kwargs.setdefault("corner_radius", Raio.PILULA)
        kwargs.setdefault("font", Fonte.PEQUENO)
        kwargs.setdefault("padx", Espaco.MD)
        kwargs.setdefault("height", 24)
        super().__init__(master, text=texto, **kwargs)

    def atualizar(self, texto, tom):
        fundo, frente = self.PALETA.get(tom, self.PALETA["neutro"])
        self.configure(text=texto, fg_color=fundo, text_color=frente)


class Metrica(ctk.CTkFrame):
    """Número grande com rótulo — para as faixas de indicadores."""

    def __init__(self, master, rotulo, valor="—", tom=Cor.TEXTO, **kwargs):
        kwargs.setdefault("fg_color", Cor.SUPERFICIE_ALTA)
        kwargs.setdefault("corner_radius", Raio.MD)
        super().__init__(master, **kwargs)

        self.label_valor = ctk.CTkLabel(
            self, text=str(valor), font=Fonte.TITULO, text_color=tom, anchor="w",
        )
        self.label_valor.pack(fill="x", padx=Espaco.LG, pady=(Espaco.MD, 0))

        ctk.CTkLabel(
            self, text=rotulo.upper(), font=Fonte.MICRO,
            text_color=Cor.TEXTO_APAGADO, anchor="w",
        ).pack(fill="x", padx=Espaco.LG, pady=(0, Espaco.MD))

    def definir(self, valor):
        self.label_valor.configure(text=str(valor))


class ItemLista(ctk.CTkFrame):
    """Linha de lista com avatar textual, título, subtítulo e valor à direita."""

    def __init__(self, master, titulo, subtitulo="", valor="", inicial=None,
                 tom_valor=Cor.SUCESSO, **kwargs):
        kwargs.setdefault("fg_color", Cor.SUPERFICIE_ALTA)
        kwargs.setdefault("corner_radius", Raio.MD)
        kwargs.setdefault("height", 56)
        super().__init__(master, **kwargs)
        self.pack_propagate(False)

        avatar = ctk.CTkLabel(
            self, text=(inicial or titulo[:1]).upper(),
            font=Fonte.CORPO_FORTE, text_color=Cor.ACENTO,
            fg_color=Cor.ACENTO_FUNDO, corner_radius=Raio.PILULA,
            width=34, height=34,
        )
        avatar.pack(side="left", padx=(Espaco.MD, Espaco.MD))

        textos = ctk.CTkFrame(self, fg_color="transparent")
        textos.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            textos, text=titulo, font=Fonte.CORPO,
            text_color=Cor.TEXTO, anchor="w",
        ).pack(fill="x", pady=(Espaco.SM, 0))

        if subtitulo:
            ctk.CTkLabel(
                textos, text=subtitulo, font=Fonte.MICRO,
                text_color=Cor.TEXTO_APAGADO, anchor="w",
            ).pack(fill="x")

        if valor:
            ctk.CTkLabel(
                self, text=valor, font=Fonte.CORPO_FORTE, text_color=tom_valor,
            ).pack(side="right", padx=Espaco.LG)


class EstadoVazio(ctk.CTkFrame):
    """Placeholder para listas sem conteúdo — evita a área morta e sem
    explicação que o sistema mostra hoje."""

    def __init__(self, master, icone, titulo, descricao="", **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        ctk.CTkLabel(self, text=icone, font=(Fonte.FAMILIA, 40)).pack(
            pady=(Espaco.XXL, Espaco.SM)
        )
        ctk.CTkLabel(
            self, text=titulo, font=Fonte.CORPO_FORTE, text_color=Cor.TEXTO_SECUNDARIO,
        ).pack()
        if descricao:
            ctk.CTkLabel(
                self, text=descricao, font=Fonte.PEQUENO,
                text_color=Cor.TEXTO_APAGADO, wraplength=260,
            ).pack(pady=(Espaco.XS, Espaco.XXL))


class Campo(ctk.CTkFrame):
    """Rótulo + entrada, com espaço de erro reservado embaixo.

    O espaço do erro fica sempre reservado para o formulário não "pular"
    quando uma validação aparece.
    """

    def __init__(self, master, rotulo, placeholder="", largura=280, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        ctk.CTkLabel(
            self, text=rotulo.upper(), font=Fonte.MICRO,
            text_color=Cor.TEXTO_APAGADO, anchor="w",
        ).pack(fill="x", pady=(0, Espaco.XS))

        self.entrada = ctk.CTkEntry(
            self, placeholder_text=placeholder, width=largura, height=40,
            corner_radius=Raio.MD, fg_color=Cor.SUPERFICIE_ALTA,
            border_color=Cor.BORDA, font=Fonte.CORPO, text_color=Cor.TEXTO,
        )
        self.entrada.pack(fill="x")

        self._erro = ctk.CTkLabel(
            self, text=" ", font=Fonte.MICRO, text_color=Cor.PERIGO, anchor="w",
        )
        self._erro.pack(fill="x", pady=(2, 0))

    def valor(self):
        return self.entrada.get().strip()

    def definir(self, texto):
        self.entrada.delete(0, "end")
        if texto:
            self.entrada.insert(0, texto)

    def limpar(self):
        self.definir("")
        self.erro("")

    def erro(self, mensagem):
        self._erro.configure(text=mensagem or " ")
        self.entrada.configure(border_color=Cor.PERIGO if mensagem else Cor.BORDA)


class Progresso(ctk.CTkFrame):
    """Barra de progresso com rótulo à esquerda e contador à direita."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        linha = ctk.CTkFrame(self, fg_color="transparent")
        linha.pack(fill="x")

        self.label = ctk.CTkLabel(
            linha, text="", font=Fonte.PEQUENO,
            text_color=Cor.TEXTO_SECUNDARIO, anchor="w",
        )
        self.label.pack(side="left")

        self.contador = ctk.CTkLabel(
            linha, text="", font=Fonte.PEQUENO, text_color=Cor.TEXTO_APAGADO,
        )
        self.contador.pack(side="right")

        self.barra = ctk.CTkProgressBar(
            self, height=6, corner_radius=Raio.SM,
            fg_color=Cor.SUPERFICIE_ALTA, progress_color=Cor.ACENTO,
        )
        self.barra.pack(fill="x", pady=(Espaco.SM, 0))
        self.barra.set(0)

    def atualizar(self, feito, total, mensagem=""):
        self.barra.set((feito / total) if total else 0)
        self.label.configure(text=mensagem)
        self.contador.configure(text=f"{feito}/{total}" if total else "")

    def zerar(self):
        self.barra.set(0)
        self.label.configure(text="")
        self.contador.configure(text="")


class Tabela(ctk.CTkScrollableFrame):
    """Tabela com cabeçalho e linhas clicáveis.

    O `ttk.Treeview` usado no sistema antigo não aceita o tema do design
    system — ele pinta com as cores próprias do Tk. Esta versão é montada com
    frames, então obedece aos tokens como qualquer outro componente.
    """

    def __init__(self, master, colunas, pesos=None, ao_selecionar=None, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("scrollbar_button_color", Cor.BORDA)
        super().__init__(master, **kwargs)

        self.colunas = colunas
        self.pesos = pesos or [1] * len(colunas)
        self.ao_selecionar = ao_selecionar
        self._linhas = []
        self._selecionada = None

        cabecalho = ctk.CTkFrame(self, fg_color="transparent", height=26)
        cabecalho.pack(fill="x", pady=(0, Espaco.XS))
        for indice, titulo in enumerate(colunas):
            cabecalho.grid_columnconfigure(indice, weight=self.pesos[indice])
            ctk.CTkLabel(
                cabecalho, text=titulo.upper(), font=Fonte.MICRO,
                text_color=Cor.TEXTO_APAGADO, anchor="w",
            ).grid(row=0, column=indice, sticky="ew", padx=Espaco.MD)

    def limpar(self):
        for linha in self._linhas:
            linha.destroy()
        self._linhas = []
        self._selecionada = None

    def adicionar(self, valores, dado=None, tons=None):
        """Acrescenta uma linha. `tons` colore células específicas por índice."""
        linha = ctk.CTkFrame(
            self, fg_color=Cor.SUPERFICIE_ALTA, corner_radius=Raio.SM, height=34,
        )
        linha.pack(fill="x", pady=1)
        linha.pack_propagate(False)
        linha.dado = dado

        for indice, valor in enumerate(valores):
            linha.grid_columnconfigure(indice, weight=self.pesos[indice])
            ctk.CTkLabel(
                linha, text=str(valor), font=Fonte.PEQUENO,
                text_color=(tons or {}).get(indice, Cor.TEXTO), anchor="w",
            ).grid(row=0, column=indice, sticky="ew", padx=Espaco.MD, pady=Espaco.SM)

        if self.ao_selecionar:
            def clicar(_, alvo=linha):
                self._selecionar(alvo)

            for widget in [linha] + list(linha.winfo_children()):
                widget.bind("<Button-1>", clicar)
                widget.configure(cursor="hand2")

        self._linhas.append(linha)
        return linha

    def _selecionar(self, linha):
        if self._selecionada is not None and self._selecionada.winfo_exists():
            self._selecionada.configure(fg_color=Cor.SUPERFICIE_ALTA)
        self._selecionada = linha
        linha.configure(fg_color=Cor.ACENTO_FUNDO)
        if self.ao_selecionar:
            self.ao_selecionar(linha.dado)


class Abas(ctk.CTkFrame):
    """Navegação por abas dentro de uma tela.

    Use `abas.painel(nome)` para obter o container onde montar o conteúdo.
    """

    def __init__(self, master, nomes, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self._paineis = {}
        self._botoes = {}
        self._atual = None

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", pady=(0, Espaco.LG))

        self._area = ctk.CTkFrame(self, fg_color="transparent")
        self._area.pack(fill="both", expand=True)

        for nome in nomes:
            botao = ctk.CTkButton(
                barra, text=nome, height=34, corner_radius=Raio.MD,
                font=Fonte.CORPO, fg_color="transparent",
                hover_color=Cor.SUPERFICIE_HOVER, text_color=Cor.TEXTO_SECUNDARIO,
                command=lambda n=nome: self.mostrar(n),
            )
            botao.pack(side="left", padx=(0, Espaco.XS))
            self._botoes[nome] = botao
            self._paineis[nome] = ctk.CTkFrame(self._area, fg_color="transparent")

        if nomes:
            self.mostrar(nomes[0])

    def painel(self, nome):
        return self._paineis[nome]

    def mostrar(self, nome):
        if self._atual == nome:
            return
        if self._atual:
            self._paineis[self._atual].pack_forget()
            self._botoes[self._atual].configure(
                fg_color="transparent", text_color=Cor.TEXTO_SECUNDARIO,
                font=Fonte.CORPO,
            )
        self._paineis[nome].pack(fill="both", expand=True)
        self._botoes[nome].configure(
            fg_color=Cor.ACENTO_FUNDO, text_color=Cor.ACENTO, font=Fonte.CORPO_FORTE,
        )
        self._atual = nome
