"""
Tela de Membros — lista, busca, edição e remoção do cadastro.

Substitui a janela de "gerenciar usuários" que ficava escondida atrás de um
botão na tela de eventos. Aqui a lista e o detalhe convivem: clicar numa linha
abre os dados à direita.
"""

import customtkinter as ctk

from club272.core.database import DatabaseManager
from club272.core.encoding import deserialize_encoding
from club272.core.fotos import caminho_da_foto
from club272.ui.assets import foto_de_membro
from club272.ui.components import (
    Badge,
    Botao,
    Campo,
    Card,
    EstadoVazio,
    Metrica,
    Tabela,
)
from club272.ui.shell import Tela
from club272.ui.theme import Cor, Espaco, Fonte, Raio


class TelaMembros(Tela):
    titulo = "Membros"
    subtitulo = "Cadastro, edição e situação dos rostos"

    def __init__(self, master, app):
        self.db = DatabaseManager()
        self.membros = []
        self.selecionado = None
        self._confirmando_remocao = False
        super().__init__(master, app)

    # ===== LAYOUT =====
    def construir(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        self._construir_indicadores()
        self._construir_lista()
        self._construir_detalhe()

    def _construir_indicadores(self):
        faixa = ctk.CTkFrame(self, fg_color="transparent")
        faixa.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, Espaco.LG))
        faixa.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="m")

        self.m_total = Metrica(faixa, "cadastrados", 0, Cor.ACENTO)
        self.m_total.grid(row=0, column=0, sticky="ew", padx=(0, Espaco.SM))

        self.m_rostos = Metrica(faixa, "com rosto", 0, Cor.SUCESSO)
        self.m_rostos.grid(row=0, column=1, sticky="ew", padx=Espaco.XS)

        self.m_sem_rosto = Metrica(faixa, "sem rosto", 0, Cor.ALERTA)
        self.m_sem_rosto.grid(row=0, column=2, sticky="ew", padx=Espaco.XS)

        self.m_pendentes = Metrica(faixa, "a sincronizar", 0, Cor.TEXTO_SECUNDARIO)
        self.m_pendentes.grid(row=0, column=3, sticky="ew", padx=(Espaco.SM, 0))

    def _construir_lista(self):
        def busca(cabecalho):
            self.busca = ctk.CTkEntry(
                cabecalho, placeholder_text="Buscar por nome ou ID...",
                width=260, height=34, corner_radius=Raio.MD,
                fg_color=Cor.SUPERFICIE_ALTA, border_color=Cor.BORDA,
                font=Fonte.CORPO,
            )
            self.busca.pack(side="right")
            self.busca.bind("<KeyRelease>", lambda _: self._filtrar())

        card = Card(self, titulo="Todos os membros", acao=busca)
        card.grid(row=1, column=0, sticky="nsew", padx=(0, Espaco.LG))

        self.area_lista = ctk.CTkFrame(card.corpo, fg_color="transparent")
        self.area_lista.pack(fill="both", expand=True)
        self.tabela = None

    def _construir_detalhe(self):
        card = Card(self, titulo="Detalhes")
        card.grid(row=1, column=1, sticky="nsew")
        self.area_detalhe = card.corpo
        self.form = None
        self._mostrar_sem_selecao()

    # ===== CICLO DE VIDA =====
    def ao_entrar(self):
        self.membros = self.db.listar_usuarios()

        com_rosto = sum(
            1 for m in self.membros if deserialize_encoding(m["encoding"]) is not None
        )
        pendentes = sum(1 for m in self.membros if m["sync_status"] == "pending")

        self.m_total.definir(len(self.membros))
        self.m_rostos.definir(com_rosto)
        self.m_sem_rosto.definir(len(self.membros) - com_rosto)
        self.m_pendentes.definir(pendentes)

        self.app.badge(f"{len(self.membros)} membros", "acento")
        self.app.status_direita("")
        self._filtrar()

    # ===== LISTA =====
    def _filtrar(self):
        termo = getattr(self, "busca", None)
        termo = termo.get().strip().lower() if termo else ""

        visiveis = [
            m for m in self.membros
            if not termo
            or termo in (m["name"] or "").lower()
            or termo in str(m["id"]).lower()
        ]

        for widget in self.area_lista.winfo_children():
            widget.destroy()

        if not visiveis:
            EstadoVazio(
                self.area_lista, "busca", "Nenhum membro encontrado",
                f"Nada corresponde a “{termo}”." if termo
                else "Cadastre alguém pela tela de Cadastro.",
            ).pack(fill="both", expand=True)
            self.tabela = None
            self.app.status(f"0 de {len(self.membros)} membros")
            return

        self.tabela = Tabela(
            self.area_lista, ["ID", "Nome", "Grupo", "Rosto"], [2, 4, 2, 2],
            ao_selecionar=self._selecionar,
        )
        self.tabela.pack(fill="both", expand=True)

        for m in visiveis:
            tem_rosto = deserialize_encoding(m["encoding"]) is not None
            self.tabela.adicionar(
                [m["id"], m["name"], m["group_name"] or "—",
                 "ok" if tem_rosto else "faltando"],
                dado=m,
                tons={3: Cor.SUCESSO if tem_rosto else Cor.ALERTA},
            )

        self.app.status(f"{len(visiveis)} de {len(self.membros)} membros")

    # ===== DETALHE =====
    def _limpar_detalhe(self):
        for widget in self.area_detalhe.winfo_children():
            widget.destroy()
        self.form = None
        self._confirmando_remocao = False

    def _mostrar_sem_selecao(self):
        self._limpar_detalhe()
        EstadoVazio(
            self.area_detalhe, "contato", "Nenhum membro selecionado",
            "Clique numa linha da lista para ver e editar os dados.",
        ).pack(fill="both", expand=True)

    def _selecionar(self, membro):
        self.selecionado = membro
        self._limpar_detalhe()

        tem_rosto = deserialize_encoding(membro["encoding"]) is not None

        # O formulário rola: com foto, três campos, resumo e dois botões, ele
        # não cabe em janela pequena — e sem rolagem o Tk esmaga o que sobra.
        # Já aconteceu de os botões de salvar e remover ficarem com 1 pixel.
        self.form = ctk.CTkScrollableFrame(
            self.area_detalhe, fg_color="transparent",
            scrollbar_button_color=Cor.BORDA,
        )
        self.form.pack(fill="both", expand=True)

        # Cabeçalho na horizontal: a foto empilhada sobre ID e etiqueta
        # ocupava 188 px de altura, quase metade do painel.
        cabecalho = ctk.CTkFrame(self.form, fg_color="transparent")
        cabecalho.pack(fill="x", pady=(0, Espaco.LG))

        # A foto é localizada pelo ID, não pelo caminho gravado no banco: esse
        # caminho é da máquina onde o cadastro foi feito e não existe em
        # nenhuma outra.
        foto = foto_de_membro(caminho_da_foto(membro), tamanho=88)
        if foto is not None:
            rotulo_foto = ctk.CTkLabel(cabecalho, image=foto, text="")
            rotulo_foto.image = foto  # mantém a referência viva
            rotulo_foto.pack(side="left")
        else:
            ctk.CTkLabel(
                cabecalho, text=(membro["name"] or "?")[:1].upper(),
                font=(Fonte.FAMILIA, 32, "bold"), text_color=Cor.ACENTO,
                fg_color=Cor.ACENTO_FUNDO, corner_radius=Raio.PILULA,
                width=88, height=88,
            ).pack(side="left")

        ao_lado = ctk.CTkFrame(cabecalho, fg_color="transparent")
        ao_lado.pack(side="left", fill="both", expand=True, padx=(Espaco.MD, 0))

        ctk.CTkLabel(
            ao_lado, text=membro["id"], font=Fonte.CODIGO,
            text_color=Cor.ACENTO, anchor="w",
        ).pack(anchor="w", pady=(Espaco.LG, 0))

        Badge(ao_lado, "rosto cadastrado" if tem_rosto else "sem rosto",
              "sucesso" if tem_rosto else "alerta").pack(anchor="w",
                                                         pady=(Espaco.XS, 0))

        self.campo_nome = Campo(self.form, "Nome")
        self.campo_nome.pack(fill="x", pady=(0, Espaco.SM))
        self.campo_nome.definir(membro["name"])

        self.campo_grupo = Campo(self.form, "Grupo")
        self.campo_grupo.pack(fill="x", pady=(0, Espaco.SM))
        self.campo_grupo.definir(membro["group_name"] or "")

        self.campo_telefone = Campo(self.form, "Telefone")
        self.campo_telefone.pack(fill="x", pady=(0, Espaco.MD))
        self.campo_telefone.definir(membro["phone"] or "")

        resumo = ctk.CTkFrame(self.form, fg_color=Cor.SUPERFICIE_ALTA,
                              corner_radius=Raio.MD)
        resumo.pack(fill="x", pady=(0, Espaco.LG))

        for rotulo, valor in (
            ("Presenças", membro["total_attendance"] or 0),
            ("Última", self.db.formatar_hora_presenca(
                membro["last_attendance_time"]) or "nunca"),
            ("Sincronização", membro["sync_status"] or "—"),
        ):
            linha = ctk.CTkFrame(resumo, fg_color="transparent")
            linha.pack(fill="x", padx=Espaco.MD, pady=Espaco.XS)
            ctk.CTkLabel(linha, text=rotulo, font=Fonte.MICRO,
                         text_color=Cor.TEXTO_APAGADO).pack(side="left")
            ctk.CTkLabel(linha, text=str(valor), font=Fonte.PEQUENO,
                         text_color=Cor.TEXTO_SECUNDARIO).pack(side="right")

        acoes = ctk.CTkFrame(self.form, fg_color="transparent")
        acoes.pack(fill="x", pady=(Espaco.SM, 0))

        Botao(acoes, "Salvar alterações", "primario",
              command=self._salvar).pack(fill="x", pady=(0, Espaco.SM))

        self.botao_remover = Botao(
            acoes, "Remover membro", "fantasma", command=self._remover
        )
        self.botao_remover.pack(fill="x")

    def _salvar(self):
        nome = self.campo_nome.valor()
        self.campo_nome.erro("" if nome else "Informe o nome")
        if not nome:
            return

        self.db.atualizar_usuario(
            self.selecionado["id"],
            nome=nome,
            grupo=self.campo_grupo.valor(),
            telefone=self.campo_telefone.valor(),
        )
        self.app.status(f"{nome} atualizado", Cor.SUCESSO)
        self.ao_entrar()

    def _remover(self):
        """Dois cliques: o primeiro pede confirmação no próprio botão.

        Evita uma caixa de diálogo do sistema, que destoa do resto da
        interface, sem deixar a remoção acontecer por engano.
        """
        if not self._confirmando_remocao:
            self._confirmando_remocao = True
            self.botao_remover.configure(
                text="Confirmar remoção?", fg_color=Cor.PERIGO,
                hover_color=Cor.PERIGO_HOVER, text_color=Cor.TEXTO_SOBRE_ACENTO,
                border_width=0,
            )
            self.app.status(
                "Clique de novo para remover — as presenças também serão apagadas",
                Cor.ALERTA,
            )
            return

        nome = self.selecionado["name"]
        self.db.remover_usuario(self.selecionado["id"])
        self.selecionado = None
        self.app.status(f"{nome} removido", Cor.TEXTO_SECUNDARIO)
        self._mostrar_sem_selecao()
        self.ao_entrar()
