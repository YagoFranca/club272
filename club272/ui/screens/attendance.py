"""
Tela de Presença — protótipo do front novo.

Usa dados reais: o mesmo banco, os mesmos encodings e o mesmo motor de
reconhecimento do sistema atual. O que muda é só a camada visual.
"""

import tkinter as tk
from datetime import datetime

import customtkinter as ctk
import cv2
from PIL import Image, ImageTk

from club272 import config
from club272.core.database import DatabaseManager
from club272.core.recognition import (
    Camera,
    MotorReconhecimento,
    ReconhecedorAssincrono,
    desenhar_deteccoes,
)
from club272.ui.components import Badge, Botao, Card, EstadoVazio, ItemLista, Metrica
from club272.ui.shell import Tela
from club272.ui.theme import Cor, Espaco, Fonte, Raio

INTERVALO_MS = max(1, 1000 // config.FPS_EXIBICAO)


class TelaPresenca(Tela):
    titulo = "Presença"
    subtitulo = "Reconhecimento facial ao vivo"

    def __init__(self, master, app):
        self.db = DatabaseManager()
        self.motor = MotorReconhecimento(self.db)
        self.camera = Camera()
        self.reconhecedor = ReconhecedorAssincrono(self.camera, self.motor)
        self.evento = self.db.buscar_evento_aberto()
        self.camera_ligada = False
        self._presencas = []
        super().__init__(master, app)

    # ===== LAYOUT =====
    def construir(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        self._construir_faixa_evento()
        self._construir_coluna_video()
        self._construir_coluna_lateral()

    def _construir_faixa_evento(self):
        """Mostra o evento em curso. Abrir e encerrar é na tela de Eventos —
        gestão de evento fica junto do histórico, não no meio da captura."""
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

        self.label_evento = ctk.CTkLabel(
            esquerda, text="—", font=Fonte.SUBTITULO, text_color=Cor.TEXTO, anchor="w",
        )
        self.label_evento.pack(anchor="w")

        self.botao_ir_eventos = Botao(
            interno, "Abrir um evento", "primario", width=170,
            command=lambda: self.app.navegar("eventos"),
        )
        self.botao_ir_eventos.pack(side="right")

        self.label_dica_evento = ctk.CTkLabel(
            interno, text="", font=Fonte.PEQUENO, text_color=Cor.TEXTO_APAGADO,
        )
        self.label_dica_evento.pack(side="right", padx=Espaco.LG)

    def _construir_coluna_video(self):
        card = Card(self, titulo="Câmera")
        card.grid(row=1, column=0, sticky="nsew", padx=(0, Espaco.LG))

        moldura = ctk.CTkFrame(
            card.corpo, fg_color=Cor.FUNDO, corner_radius=Raio.MD,
        )
        moldura.pack(fill="both", expand=True)

        # Label puro do Tk: o caminho cv2 -> PIL -> ImageTk continua idêntico
        # ao do sistema atual, sem custo extra por frame.
        self.video = tk.Label(
            moldura, bg=Cor.FUNDO, text="Câmera desligada",
            fg=Cor.TEXTO_APAGADO, font=Fonte.CORPO,
        )
        self.video.pack(fill="both", expand=True, padx=Espaco.SM, pady=Espaco.SM)

        controles = ctk.CTkFrame(card.corpo, fg_color="transparent")
        controles.pack(fill="x", pady=(Espaco.LG, 0))

        self.botao_camera = Botao(
            controles, "Iniciar câmera", "sucesso", width=170,
            command=self._alternar_camera,
        )
        self.botao_camera.pack(side="left")

        self.badge_camera = Badge(controles, "Parada", "neutro")
        self.badge_camera.pack(side="left", padx=Espaco.MD)

        self.label_rostos = ctk.CTkLabel(
            controles, text=f"{len(self.motor.ids)} rostos carregados",
            font=Fonte.PEQUENO, text_color=Cor.TEXTO_APAGADO,
        )
        self.label_rostos.pack(side="right")

    def _construir_coluna_lateral(self):
        coluna = ctk.CTkFrame(self, fg_color="transparent")
        coluna.grid(row=1, column=1, sticky="nsew")
        coluna.grid_rowconfigure(1, weight=1)
        coluna.grid_columnconfigure(0, weight=1)

        # Indicadores
        metricas = ctk.CTkFrame(coluna, fg_color="transparent")
        metricas.grid(row=0, column=0, sticky="ew", pady=(0, Espaco.LG))
        metricas.grid_columnconfigure((0, 1, 2), weight=1, uniform="m")

        self.metrica_presentes = Metrica(metricas, "presentes", 0, Cor.SUCESSO)
        self.metrica_presentes.grid(row=0, column=0, sticky="ew", padx=(0, Espaco.SM))

        self.metrica_membros = Metrica(metricas, "membros", 0, Cor.ACENTO)
        self.metrica_membros.grid(row=0, column=1, sticky="ew", padx=Espaco.XS)

        self.metrica_taxa = Metrica(metricas, "presença", "0%", Cor.TEXTO)
        self.metrica_taxa.grid(row=0, column=2, sticky="ew", padx=(Espaco.SM, 0))

        # Lista ao vivo
        card = Card(coluna, titulo="Chegadas")
        card.grid(row=1, column=0, sticky="nsew")

        self.lista = ctk.CTkScrollableFrame(
            card.corpo, fg_color="transparent", scrollbar_button_color=Cor.BORDA,
        )
        self.lista.pack(fill="both", expand=True)

        self.vazio = EstadoVazio(
            self.lista, "👥", "Ninguém registrado ainda",
            "As presenças aparecem aqui assim que os rostos forem reconhecidos.",
        )
        self.vazio.pack(fill="both", expand=True)

    # ===== CICLO DE VIDA =====
    def ao_entrar(self):
        # Relê do banco: o evento pode ter sido aberto ou encerrado na tela
        # de Eventos enquanto esta ficou fora de vista.
        self.evento = self.db.buscar_evento_aberto()
        self._atualizar_evento()
        self._carregar_presencas()
        self._atualizar_metricas()

    def ao_sair(self):
        # Sai da tela, solta a webcam — coordenação que o modelo de várias
        # janelas não conseguia fazer.
        if self.camera_ligada:
            self._parar_camera()

    def _atualizar_evento(self):
        if self.evento:
            self.label_evento.configure(text=self.evento["nome"], text_color=Cor.TEXTO)
            self.botao_ir_eventos.configure(text="Ver na tela de Eventos")
            self.label_dica_evento.configure(text="")
            self.app.badge("Evento aberto", "sucesso")
        else:
            self.label_evento.configure(text="Nenhum evento aberto",
                                        text_color=Cor.TEXTO_APAGADO)
            self.botao_ir_eventos.configure(text="Abrir um evento")
            self.label_dica_evento.configure(
                text="A câmera só liga com um evento aberto."
            )
            self.app.badge("Sem evento", "neutro")

    # ===== CÂMERA =====
    def _alternar_camera(self):
        self._parar_camera() if self.camera_ligada else self._iniciar_camera()

    def _iniciar_camera(self):
        if not self.evento:
            self.app.status("Abra um evento na tela de Eventos para iniciar a câmera",
                            Cor.ALERTA)
            return

        if not self.camera.iniciar():
            self.app.status("Não foi possível acessar a webcam", Cor.PERIGO)
            self.badge_camera.atualizar("Falhou", "perigo")
            return

        self.motor.carregar()
        self.reconhecedor.iniciar()

        self.camera_ligada = True
        self.botao_camera.configure(text="Parar câmera", fg_color=Cor.PERIGO,
                                    hover_color=Cor.PERIGO_HOVER)
        self.badge_camera.atualizar("Ao vivo", "sucesso")
        self.app.status("Reconhecimento ativo", Cor.SUCESSO)
        self._proximo_frame()

    def _parar_camera(self):
        self.camera_ligada = False
        self.reconhecedor.parar()
        self.camera.parar()
        self.botao_camera.configure(text="Iniciar câmera", fg_color=Cor.SUCESSO,
                                    hover_color=Cor.SUCESSO_HOVER)
        self.badge_camera.atualizar("Parada", "neutro")
        self.video.configure(image="", text="Câmera desligada")
        self.app.status("Câmera parada", Cor.TEXTO_SECUNDARIO)

    def _proximo_frame(self):
        """Tique da interface: só desenha. Detecção e identificação acontecem
        na thread do reconhecedor, então este laço nunca bloqueia."""
        if not self.camera_ligada:
            return

        frame = self.camera.ler()
        if frame is not None:
            desenhar_deteccoes(frame, self.reconhecedor.deteccoes)
            self._mostrar(frame)

        for pessoa in self.reconhecedor.coletar_registros():
            self._registrar(pessoa)

        self.after(INTERVALO_MS, self._proximo_frame)

    def _mostrar(self, frame):
        largura = max(self.video.winfo_width(), 320)
        altura = max(self.video.winfo_height(), 240)

        # cv2.resize em vez do thumbnail LANCZOS do PIL: medido 0,05 ms contra
        # 8,4 ms, e a diferença não aparece em vídeo.
        alvo = min(largura / frame.shape[1], altura / frame.shape[0])
        if alvo < 1.0:
            frame = cv2.resize(frame, (0, 0), fx=alvo, fy=alvo,
                               interpolation=cv2.INTER_AREA)

        imagem = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        foto = ImageTk.PhotoImage(imagem)
        self.video.configure(image=foto, text="")
        self.video.image = foto  # Mantém a referência viva.

    # ===== PRESENÇAS =====
    def _registrar(self, pessoa):
        if not self.evento:
            return

        novo = self.db.registrar_presenca_evento(
            self.evento["id"], pessoa["id"], pessoa["nome"]
        )
        if not novo:
            return

        self.db.atualizar_presenca(pessoa["id"])
        self._adicionar_item(pessoa["nome"], pessoa["id"],
                             datetime.now().strftime("%H:%M:%S"),
                             pessoa.get("confianca"))
        self._atualizar_metricas()
        self.app.status(f"{pessoa['nome']} registrado", Cor.SUCESSO)

    def _carregar_presencas(self):
        for widget in self.lista.winfo_children():
            widget.destroy()

        self._presencas = (
            self.db.listar_presencas_evento(self.evento["id"]) if self.evento else []
        )

        if not self._presencas:
            self.vazio = EstadoVazio(
                self.lista, "👥", "Ninguém registrado ainda",
                "As presenças aparecem aqui assim que os rostos forem reconhecidos.",
            )
            self.vazio.pack(fill="both", expand=True)
            return

        for p in reversed(self._presencas):
            ItemLista(
                self.lista, p["nome_usuario"], f"ID {p['usuario_id']}",
                self.db.formatar_hora_presenca(p["hora_presenca"]),
            ).pack(fill="x", pady=(0, Espaco.SM))

    def _adicionar_item(self, nome, usuario_id, hora, confianca=None):
        if self.vazio and self.vazio.winfo_exists():
            self.vazio.destroy()

        subtitulo = f"ID {usuario_id}"
        if confianca is not None:
            subtitulo += f"  ·  {confianca:.0f}% de confiança"

        item = ItemLista(self.lista, nome, subtitulo, hora)
        item.pack(fill="x", pady=(0, Espaco.SM))
        self._presencas.append({"usuario_id": usuario_id})

    def _atualizar_metricas(self):
        membros = len(self.db.listar_usuarios())
        presentes = len(self._presencas)

        self.metrica_membros.definir(membros)
        self.metrica_presentes.definir(presentes)
        self.metrica_taxa.definir(f"{(100 * presentes / membros) if membros else 0:.0f}%")
        self.app.status_direita(f"{membros} membros cadastrados")
