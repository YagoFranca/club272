"""
Shell da aplicação: uma janela, sidebar de navegação, topbar e barra de status.

Substitui o modelo atual de abrir um processo e uma janela do sistema
operacional por módulo. As telas viram destinos de navegação dentro da mesma
janela, compartilhando banco, estado do evento e barra de status.
"""

import queue

import customtkinter as ctk

from club272.ui.assets import aplicar_icone_janela, logo_circular
from club272.ui.components import Badge, Icone
from club272.ui.theme import Cor, Espaco, Fonte, Raio


class ItemNav(ctk.CTkFrame):
    """Item da barra lateral, com estado ativo/inativo.

    É um frame, e não um botão: o ícone vem de uma fonte de ícones e o rótulo
    da fonte de texto, e um único `CTkButton` não mistura duas famílias no
    mesmo rótulo.
    """

    def __init__(self, master, icone, texto, comando, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("corner_radius", Raio.MD)
        kwargs.setdefault("height", 42)
        super().__init__(master, **kwargs)
        self.pack_propagate(False)

        self._comando = comando
        self._ativo = False

        self.icone = Icone(self, icone, tamanho=17, cor=Cor.TEXTO_SECUNDARIO)
        self.icone.pack(side="left", padx=(Espaco.MD, Espaco.MD))

        self.rotulo = ctk.CTkLabel(
            self, text=texto, font=Fonte.CORPO,
            text_color=Cor.TEXTO_SECUNDARIO, anchor="w",
        )
        self.rotulo.pack(side="left", fill="both", expand=True)

        for widget in (self, self.icone, self.rotulo):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _: self._comando())
            widget.bind("<Enter>", lambda _: self._pintar(hover=True))
            widget.bind("<Leave>", lambda _: self._pintar(hover=False))

    def _pintar(self, hover):
        if self._ativo:
            return
        self.configure(fg_color=Cor.SUPERFICIE_HOVER if hover else "transparent")

    def definir_ativo(self, ativo):
        self._ativo = ativo
        if ativo:
            self.configure(fg_color=Cor.ACENTO_FUNDO)
            self.icone.configure(text_color=Cor.ACENTO)
            self.rotulo.configure(text_color=Cor.ACENTO, font=Fonte.CORPO_FORTE)
        else:
            self.configure(fg_color="transparent")
            self.icone.configure(text_color=Cor.TEXTO_SECUNDARIO)
            self.rotulo.configure(text_color=Cor.TEXTO_SECUNDARIO, font=Fonte.CORPO)


class Tela(ctk.CTkFrame):
    """Base das telas do shell.

    `ao_entrar` e `ao_sair` permitem que uma tela ligue e desligue recursos
    (webcam, timers) conforme o usuário navega — o que o modelo de múltiplas
    janelas não conseguia coordenar.
    """

    titulo = "Tela"
    subtitulo = ""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.construir()

    def construir(self):
        """Monta os widgets. Sobrescrever nas subclasses."""

    def ao_entrar(self):
        """Chamado quando a tela passa a ser exibida."""

    def ao_sair(self):
        """Chamado quando o usuário sai da tela."""

    def entregar(self, funcao, *args):
        """Agenda `funcao(*args)` na thread da interface.

        Use isto — e nunca `self.after()` — a partir de uma thread de
        trabalho. Chamar `after()` de fora da thread principal mexe no
        interpretador Tcl sem sincronização, e ainda estoura se a janela já
        tiver sido fechada enquanto o trabalho corria.
        """
        self.app.entregar(funcao, *args)


class Shell(ctk.CTk):
    """Janela principal que hospeda todas as telas."""

    LARGURA = 1180
    ALTURA = 760

    def __init__(self, titulo="272 Club"):
        super().__init__()

        self.title(titulo)
        self.configure(fg_color=Cor.FUNDO)
        self.minsize(1024, 660)
        self._centralizar(self.LARGURA, self.ALTURA)
        aplicar_icone_janela(self)

        self._telas = {}
        self._itens_nav = {}
        self._tela_atual = None
        self._fila = queue.Queue()
        self._tique_fila = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._construir_sidebar()
        self._construir_area_principal()
        self._drenar()

        self.protocol("WM_DELETE_WINDOW", self.encerrar)

    # ===== ESTRUTURA =====
    def _centralizar(self, largura, altura):
        x = (self.winfo_screenwidth() // 2) - (largura // 2)
        y = (self.winfo_screenheight() // 2) - (altura // 2)
        self.geometry(f"{largura}x{altura}+{x}+{y}")

    def _construir_sidebar(self):
        barra = ctk.CTkFrame(
            self, width=232, fg_color=Cor.SUPERFICIE, corner_radius=0,
        )
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)

        # Marca: logo + wordmark
        marca = ctk.CTkFrame(barra, fg_color="transparent")
        marca.pack(fill="x", padx=Espaco.XL, pady=(Espaco.XL, Espaco.XXL))

        logo = logo_circular(42)
        if logo is not None:
            ctk.CTkLabel(marca, image=logo, text="").pack(
                side="left", padx=(0, Espaco.MD)
            )

        palavra = ctk.CTkFrame(marca, fg_color="transparent")
        palavra.pack(side="left")

        linha = ctk.CTkFrame(palavra, fg_color="transparent")
        linha.pack(anchor="w")

        ctk.CTkLabel(
            linha, text="272", font=(Fonte.FAMILIA, 22, "bold"),
            text_color=Cor.ACENTO,
        ).pack(side="left")
        ctk.CTkLabel(
            linha, text="CLUB", font=(Fonte.FAMILIA, 22),
            text_color=Cor.TEXTO,
        ).pack(side="left", padx=(Espaco.XS, 0))

        ctk.CTkLabel(
            palavra, text="reconhecimento facial", font=Fonte.MICRO,
            text_color=Cor.TEXTO_APAGADO, anchor="w",
        ).pack(anchor="w")

        self._area_nav = ctk.CTkFrame(barra, fg_color="transparent")
        self._area_nav.pack(fill="both", expand=True, padx=Espaco.MD)

        # Rodapé da barra lateral
        rodape = ctk.CTkFrame(barra, fg_color="transparent")
        rodape.pack(fill="x", padx=Espaco.XL, pady=Espaco.LG)

        from club272 import __version__

        ctk.CTkLabel(
            rodape, text=f"versão {__version__}", font=Fonte.MICRO,
            text_color=Cor.TEXTO_APAGADO,
        ).pack(anchor="w")

    def _construir_area_principal(self):
        area = ctk.CTkFrame(self, fg_color="transparent")
        area.grid(row=0, column=1, sticky="nsew")
        area.grid_rowconfigure(1, weight=1)
        area.grid_columnconfigure(0, weight=1)

        # Topbar
        topo = ctk.CTkFrame(area, height=76, fg_color="transparent")
        topo.grid(row=0, column=0, sticky="ew", padx=Espaco.XXL, pady=(Espaco.XL, 0))
        topo.grid_propagate(False)

        textos = ctk.CTkFrame(topo, fg_color="transparent")
        textos.pack(side="left", fill="y")

        self.label_titulo = ctk.CTkLabel(
            textos, text="", font=Fonte.TITULO, text_color=Cor.TEXTO, anchor="w",
        )
        self.label_titulo.pack(anchor="w")

        self.label_subtitulo = ctk.CTkLabel(
            textos, text="", font=Fonte.PEQUENO,
            text_color=Cor.TEXTO_APAGADO, anchor="w",
        )
        self.label_subtitulo.pack(anchor="w")

        self.badge_topo = Badge(topo, "", "neutro")
        self.badge_topo.pack(side="right")

        # Container das telas
        self._container = ctk.CTkFrame(area, fg_color="transparent")
        self._container.grid(
            row=1, column=0, sticky="nsew", padx=Espaco.XXL, pady=Espaco.LG
        )
        self._container.grid_rowconfigure(0, weight=1)
        self._container.grid_columnconfigure(0, weight=1)

        # Barra de status
        status = ctk.CTkFrame(area, height=38, fg_color=Cor.SUPERFICIE, corner_radius=0)
        status.grid(row=2, column=0, sticky="ew")
        status.grid_propagate(False)

        self.label_status = ctk.CTkLabel(
            status, text="Pronto", font=Fonte.PEQUENO, text_color=Cor.TEXTO_SECUNDARIO,
        )
        self.label_status.pack(side="left", padx=Espaco.XXL)

        self.label_status_direita = ctk.CTkLabel(
            status, text="", font=Fonte.PEQUENO, text_color=Cor.TEXTO_APAGADO,
        )
        self.label_status_direita.pack(side="right", padx=Espaco.XXL)

    # ===== NAVEGAÇÃO =====
    def registrar(self, chave, icone, classe_tela):
        """Adiciona uma tela ao shell e cria o item de navegação."""
        tela = classe_tela(self._container, self)
        self._telas[chave] = tela

        item = ItemNav(
            self._area_nav, icone, tela.titulo,
            comando=lambda c=chave: self.navegar(c),
        )
        item.pack(fill="x", pady=2)
        self._itens_nav[chave] = item
        return tela

    def separador_nav(self, rotulo=""):
        """Divide grupos de itens na barra lateral."""
        ctk.CTkFrame(self._area_nav, height=1, fg_color=Cor.BORDA_SUAVE).pack(
            fill="x", pady=(Espaco.LG, Espaco.SM), padx=Espaco.SM
        )
        if rotulo:
            ctk.CTkLabel(
                self._area_nav, text=rotulo.upper(), font=Fonte.MICRO,
                text_color=Cor.TEXTO_APAGADO, anchor="w",
            ).pack(fill="x", padx=Espaco.MD, pady=(0, Espaco.XS))

    def navegar(self, chave):
        """Troca a tela visível."""
        if chave == self._tela_atual:
            return

        if self._tela_atual:
            self._telas[self._tela_atual].ao_sair()
            self._telas[self._tela_atual].grid_forget()
            self._itens_nav[self._tela_atual].definir_ativo(False)

        tela = self._telas[chave]
        tela.grid(row=0, column=0, sticky="nsew")
        self._itens_nav[chave].definir_ativo(True)

        self.label_titulo.configure(text=tela.titulo)
        self.label_subtitulo.configure(text=tela.subtitulo)

        self._tela_atual = chave
        tela.ao_entrar()

    # ===== ENCERRAMENTO =====
    def encerrar(self):
        """Fecha a janela liberando o que as telas seguram.

        Sem isso, fechar com a câmera ligada deixa a thread de captura e o
        processo do encoder rodando — órfãos segurando a webcam e ~200 MB.
        """
        if self._tique_fila is not None:
            try:
                self.after_cancel(self._tique_fila)
            except Exception:
                pass
            self._tique_fila = None

        for tela in self._telas.values():
            try:
                tela.ao_sair()
            except Exception as e:
                print(f"Erro ao encerrar {tela.titulo}: {e}")

        self.destroy()

    # ===== PONTE ENTRE THREADS =====
    def entregar(self, funcao, *args):
        """Enfileira trabalho para a thread da interface. Seguro de qualquer
        thread: `queue.Queue` já é sincronizada."""
        self._fila.put((funcao, args))

    def _drenar(self):
        """Executa o que as threads deixaram na fila e reagenda a si mesmo."""
        while True:
            try:
                funcao, args = self._fila.get_nowait()
            except queue.Empty:
                break
            try:
                funcao(*args)
            except Exception as e:
                print(f"Erro ao aplicar resultado na interface: {e}")

        self._tique_fila = self.after(50, self._drenar)

    # ===== STATUS =====
    def status(self, mensagem, tom=None):
        self.label_status.configure(
            text=mensagem, text_color=tom or Cor.TEXTO_SECUNDARIO
        )

    def status_direita(self, mensagem):
        self.label_status_direita.configure(text=mensagem)

    def badge(self, texto, tom="neutro"):
        self.badge_topo.atualizar(texto, tom)
