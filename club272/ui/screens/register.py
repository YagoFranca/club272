"""
Tela de Cadastro — registra uma pessoa capturando o rosto pela webcam.

A captura é automática: quando um rosto aparece bem posicionado e fica firme
pelo tempo de estabilização, o sistema fotografa sozinho. Quem se cadastra
fica com as duas mãos livres, sem precisar alcançar o mouse — que era o
problema do botão de capturar.

A detecção usa o mesmo `Detector` do reconhecimento (Haar + refino com HOG) e
roda fora da thread da interface, então a prévia não trava.
"""

import threading
import time
import tkinter as tk

import customtkinter as ctk
import cv2
from PIL import Image, ImageTk

from club272 import config
from club272.core.database import DatabaseManager
from club272.core.encoding import serialize_encoding
from club272.core.recognition import (
    Camera,
    Detector,
    extrair_encoding_de,
    iou,
)
from club272.ui.components import Badge, Botao, Campo, Card
from club272.ui.shell import Tela
from club272.ui.theme import Cor, Espaco, Fonte, Raio

INTERVALO_MS = max(1, 1000 // config.FPS_EXIBICAO)

# Curto demais fotografa quem só passou na frente; longo demais irrita.
TEMPO_ESTAVEL_S = config.TEMPO_ESTAVEL
LARGURA_MINIMA = config.LARGURA_MINIMA_ROSTO

# Quanto a caixa pode se deslocar entre leituras e ainda contar como "parada".
IOU_ESTAVEL = 0.6


class TelaCadastro(Tela):
    titulo = "Cadastro"
    subtitulo = "Registro individual pela webcam"

    def __init__(self, master, app):
        self.db = DatabaseManager()
        self.camera = Camera()
        self.detector = Detector(
            usar_haar=config.DETECTOR_RAPIDO, refinar=config.REFINAR_CAIXA
        )

        self.camera_ligada = False
        self.encoding_capturado = None
        self.frame_capturado = None

        self._detectando = False
        self._extraindo = False
        self._caixa = None
        self._estavel_desde = None
        # Depois de salvar, espera o quadro esvaziar antes de armar de novo:
        # sem isso a pessoa recém-cadastrada, ainda parada na frente da
        # câmera, é fotografada outra vez como se fosse a próxima.
        self._aguardando_saida = False
        # Só uma detecção de verdade que não achou ninguém libera a espera.
        # Confiar em `_caixa is None` não serve: o próprio fluxo de salvar
        # limpa esse campo, e a trava se liberaria sozinha na hora.
        self._quadro_livre = False
        # Guardadas para poder esperá-las antes de encerrar: thread daemon
        # morta dentro do dlib derruba o processo na finalização.
        self._threads = []
        super().__init__(master, app)

    # ===== LAYOUT =====
    def construir(self):
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        self._construir_formulario()
        self._construir_camera()

    def _construir_formulario(self):
        card = Card(self, titulo="Dados do membro")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, Espaco.LG))

        # O ID é gerado pelo sistema: mostrado, nunca digitado.
        faixa_id = ctk.CTkFrame(card.corpo, fg_color="transparent")
        faixa_id.pack(fill="x", pady=(0, Espaco.LG))

        ctk.CTkLabel(
            faixa_id, text="ID QUE SERÁ GERADO", font=Fonte.MICRO,
            text_color=Cor.TEXTO_APAGADO, anchor="w",
        ).pack(anchor="w")

        self.label_id = ctk.CTkLabel(
            faixa_id, text="—", font=Fonte.SUBTITULO,
            text_color=Cor.ACENTO, anchor="w",
        )
        self.label_id.pack(anchor="w")

        self.campo_nome = Campo(card.corpo, "Nome completo", "Ex.: Maria Santos")
        self.campo_nome.pack(fill="x", pady=(0, Espaco.MD))

        self.campo_grupo = Campo(card.corpo, "Grupo", "Ex.: Oficial 0")
        self.campo_grupo.pack(fill="x", pady=(0, Espaco.MD))

        self.campo_telefone = Campo(card.corpo, "Telefone", "Ex.: 11999999999")
        self.campo_telefone.pack(fill="x", pady=(0, Espaco.LG))

        acoes = ctk.CTkFrame(card.corpo, fg_color="transparent")
        acoes.pack(fill="x", side="bottom")

        # Só habilita depois que o rosto for capturado: sem encoding o
        # cadastro não serve para reconhecer ninguém.
        self.botao_salvar = Botao(
            acoes, "Aguardando o rosto", "primario",
            command=self._salvar, state="disabled",
        )
        self.botao_salvar.pack(fill="x", pady=(0, Espaco.SM))

        Botao(acoes, "Limpar", "fantasma", command=self._limpar).pack(fill="x")

    def _construir_camera(self):
        card = Card(self, titulo="Captura do rosto")
        card.grid(row=0, column=1, sticky="nsew")

        moldura = ctk.CTkFrame(card.corpo, fg_color=Cor.FUNDO, corner_radius=Raio.MD)
        moldura.pack(fill="both", expand=True)

        self.video = tk.Label(
            moldura, bg=Cor.FUNDO, text="Câmera desligada",
            fg=Cor.TEXTO_APAGADO, font=Fonte.CORPO,
        )
        self.video.pack(fill="both", expand=True, padx=Espaco.SM, pady=Espaco.SM)

        # Mostra o quanto falta para a foto sair sozinha.
        self.barra_estabilidade = ctk.CTkProgressBar(
            card.corpo, height=6, corner_radius=Raio.SM,
            fg_color=Cor.SUPERFICIE_ALTA, progress_color=Cor.ACENTO,
        )
        self.barra_estabilidade.pack(fill="x", pady=(Espaco.MD, 0))
        self.barra_estabilidade.set(0)

        self.label_orientacao = ctk.CTkLabel(
            card.corpo, text="", font=Fonte.PEQUENO,
            text_color=Cor.TEXTO_SECUNDARIO, anchor="w",
        )
        self.label_orientacao.pack(fill="x", pady=(Espaco.SM, 0))

        controles = ctk.CTkFrame(card.corpo, fg_color="transparent")
        controles.pack(fill="x", pady=(Espaco.MD, 0))

        self.botao_camera = Botao(
            controles, "Ligar câmera", "sucesso", width=150,
            command=self._alternar_camera,
        )
        self.botao_camera.pack(side="left")

        self.botao_refazer = Botao(
            controles, "Refazer captura", "fantasma", width=160,
            command=self._refazer, state="disabled",
        )
        self.botao_refazer.pack(side="left", padx=Espaco.MD)

        self.badge_rosto = Badge(controles, "Câmera desligada", "neutro")
        self.badge_rosto.pack(side="right")

    # ===== CICLO DE VIDA =====
    def ao_entrar(self):
        self.label_id.configure(text=self.db.get_next_tsu_id())
        self.app.badge("Pronto para cadastrar", "acento")
        self.app.status_direita(f"{len(self.db.listar_usuarios())} membros cadastrados")

    def ao_sair(self):
        if self.camera_ligada:
            self._parar_camera()
        self._aguardar_threads()

    def _lancar(self, alvo):
        """Dispara uma thread de trabalho e guarda a referência."""
        self._threads = [t for t in self._threads if t.is_alive()]
        thread = threading.Thread(target=alvo, daemon=True)
        self._threads.append(thread)
        thread.start()

    def _aguardar_threads(self, espera=5.0):
        """Espera o trabalho em voo terminar antes de deixar a tela morrer."""
        limite = time.time() + espera
        for thread in self._threads:
            restante = max(0.1, limite - time.time())
            thread.join(timeout=restante)
        self._threads = []

    # ===== CÂMERA =====
    def _alternar_camera(self):
        self._parar_camera() if self.camera_ligada else self._iniciar_camera()

    def _iniciar_camera(self):
        if not self.camera.iniciar():
            self.app.status("Não foi possível acessar a webcam", Cor.PERIGO)
            self.badge_rosto.atualizar("Sem webcam", "perigo")
            return

        self.camera_ligada = True
        self._reiniciar_estabilidade()
        self.botao_camera.configure(text="Desligar câmera", fg_color=Cor.PERIGO,
                                    hover_color=Cor.PERIGO_HOVER)
        self.app.status("Olhe para a câmera — a foto sai sozinha",
                        Cor.TEXTO_SECUNDARIO)
        self._proximo_frame()

    def _parar_camera(self):
        self.camera_ligada = False
        self.camera.parar()
        self.botao_camera.configure(text="Ligar câmera", fg_color=Cor.SUCESSO,
                                    hover_color=Cor.SUCESSO_HOVER)
        self.badge_rosto.atualizar("Câmera desligada", "neutro")
        self.barra_estabilidade.set(0)
        self.label_orientacao.configure(text="")
        if self.frame_capturado is None:
            self.video.configure(image="", text="Câmera desligada")

    def _proximo_frame(self):
        """Tique da interface: desenha, mede estabilidade e dispara a captura."""
        if not self.camera_ligada:
            return

        # Com a foto já tirada, a prévia congela no que foi capturado.
        if self.frame_capturado is None:
            frame = self.camera.ler()
            if frame is not None:
                self._agendar_deteccao(frame)
                self._avaliar_estabilidade(frame)
                self._mostrar(self._com_marcacao(frame))

        self.after(INTERVALO_MS, self._proximo_frame)

    # ===== DETECÇÃO =====
    def _agendar_deteccao(self, frame):
        """Procura rosto numa thread, no máximo uma busca por vez."""
        if self._detectando:
            return
        self._detectando = True

        def trabalho():
            caixa = None
            try:
                pequeno = cv2.resize(
                    frame, (0, 0),
                    fx=config.ESCALA_DETECCAO, fy=config.ESCALA_DETECCAO,
                )
                rgb = cv2.cvtColor(pequeno, cv2.COLOR_BGR2RGB)
                achados = self.detector.detectar(rgb)
                if achados:
                    fator = 1.0 / config.ESCALA_DETECCAO
                    # O maior rosto é o mais próximo — quem está se cadastrando.
                    topo, direita, baixo, esquerda = max(
                        achados, key=lambda l: (l[2] - l[0]) * (l[1] - l[3])
                    )
                    caixa = (int(esquerda * fator), int(topo * fator),
                             int(direita * fator), int(baixo * fator))
            except Exception:
                caixa = None
            finally:
                self._detectando = False
            self.entregar(self._registrar_caixa, caixa)

        self._lancar(trabalho)

    def _registrar_caixa(self, caixa):
        """Recebe a caixa da thread e mantém o cronômetro de estabilidade."""
        if not self.camera_ligada or self.frame_capturado is not None:
            return

        if caixa is None:
            self._reiniciar_estabilidade()
            self._caixa = None
            self._quadro_livre = True
            return

        self._quadro_livre = False

        # Rosto mudou de lugar? O cronômetro recomeça.
        if self._caixa is None or iou(caixa, self._caixa) < IOU_ESTAVEL:
            self._estavel_desde = time.time()

        self._caixa = caixa

    def _reiniciar_estabilidade(self):
        self._estavel_desde = None
        self.barra_estabilidade.set(0)

    # ===== ESTABILIDADE E CAPTURA AUTOMÁTICA =====
    def _avaliar_estabilidade(self, frame):
        """Decide se já dá para fotografar, e orienta a pessoa enquanto não dá."""
        if self._aguardando_saida:
            self._avaliar_saida()
            return

        if self._caixa is None:
            self.badge_rosto.atualizar("Procurando rosto", "neutro")
            self.label_orientacao.configure(text="Posicione-se em frente à câmera.")
            self.barra_estabilidade.set(0)
            return

        esquerda, _, direita, _ = self._caixa
        proporcao = (direita - esquerda) / frame.shape[1]

        if proporcao < LARGURA_MINIMA:
            self.badge_rosto.atualizar("Aproxime-se", "alerta")
            self.label_orientacao.configure(
                text="Você está longe demais para uma boa captura."
            )
            self._reiniciar_estabilidade()
            return

        if self._estavel_desde is None:
            self._estavel_desde = time.time()

        decorrido = time.time() - self._estavel_desde
        self.barra_estabilidade.set(min(decorrido / TEMPO_ESTAVEL_S, 1.0))

        if decorrido >= TEMPO_ESTAVEL_S:
            self._capturar(frame)
        else:
            self.badge_rosto.atualizar("Segure firme", "acento")
            self.label_orientacao.configure(text="Não se mexa — capturando...")

    def _avaliar_saida(self):
        """Segura a captura até o quadro ficar livre depois de um cadastro."""
        self.barra_estabilidade.set(0)

        if not self._quadro_livre:
            self.badge_rosto.atualizar("Cadastro concluído", "sucesso")
            self.label_orientacao.configure(
                text="Afaste-se da câmera para liberar o próximo cadastro."
            )
            return

        # Liberado: o fluxo normal assume no próximo quadro e volta a
        # mostrar "Procurando rosto".
        self._aguardando_saida = False

    def _capturar(self, frame):
        if self._extraindo:
            return
        self._extraindo = True

        self.badge_rosto.atualizar("Capturando", "acento")
        self.label_orientacao.configure(text="Extraindo características do rosto...")

        def trabalho():
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # upsample=1 vale o custo: é uma vez só, e um encoding ruim
            # prejudica todo reconhecimento futuro dessa pessoa. A função do
            # núcleo serializa o acesso ao dlib — esta thread e a de detecção
            # rodam ao mesmo tempo, e os singletons do dlib são compartilhados.
            encoding = extrair_encoding_de(rgb, upsample=1)
            self.entregar(self._capturado, encoding, frame)

        self._lancar(trabalho)

    def _capturado(self, encoding, frame):
        self._extraindo = False

        if encoding is None:
            # Falhou: recomeça o cronômetro em vez de travar esperando ação.
            self.badge_rosto.atualizar("Não deu — tentando de novo", "alerta")
            self.label_orientacao.configure(
                text="Rosto não ficou nítido. Ajuste a iluminação e continue parado."
            )
            self._reiniciar_estabilidade()
            return

        self.encoding_capturado = encoding
        self.frame_capturado = frame
        self.badge_rosto.atualizar("Rosto capturado", "sucesso")
        self.label_orientacao.configure(text="Preencha os dados e salve.")
        self.barra_estabilidade.set(1.0)
        self.botao_refazer.configure(state="normal")
        self.botao_salvar.configure(state="normal", text="Salvar cadastro")
        self.app.status("Rosto capturado", Cor.SUCESSO)
        self._mostrar(frame)

    def _refazer(self):
        """Descarta a captura e volta a procurar rosto.

        É uma ação deliberada sobre a mesma pessoa (a foto saiu ruim), então
        não passa pela espera de saída do quadro.
        """
        self._aguardando_saida = False
        self._quadro_livre = False
        self.encoding_capturado = None
        self.frame_capturado = None
        self._caixa = None
        self._reiniciar_estabilidade()
        self.botao_refazer.configure(state="disabled")
        self.botao_salvar.configure(state="disabled", text="Aguardando o rosto")
        self.badge_rosto.atualizar(
            "Procurando rosto" if self.camera_ligada else "Câmera desligada", "neutro"
        )
        self.app.status("Captura descartada", Cor.TEXTO_SECUNDARIO)

        if not self.camera_ligada:
            self.video.configure(image="", text="Câmera desligada")

    # ===== EXIBIÇÃO =====
    def _com_marcacao(self, frame):
        """Desenha a caixa do rosto, colorida pelo estado da captura."""
        if self._caixa is None:
            return frame

        esquerda, topo, direita, baixo = self._caixa
        proporcao = (direita - esquerda) / frame.shape[1]
        # Verde quando já serve; azul enquanto a pessoa está longe demais.
        cor = (92, 168, 150) if proporcao >= LARGURA_MINIMA else (224, 148, 98)

        marcado = frame.copy()
        cv2.rectangle(marcado, (esquerda, topo), (direita, baixo), cor, 2)
        return marcado

    def _mostrar(self, frame):
        largura = max(self.video.winfo_width(), 320)
        altura = max(self.video.winfo_height(), 240)

        escala = min(largura / frame.shape[1], altura / frame.shape[0])
        if escala < 1.0:
            frame = cv2.resize(frame, (0, 0), fx=escala, fy=escala,
                               interpolation=cv2.INTER_AREA)

        foto = ImageTk.PhotoImage(
            Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        )
        self.video.configure(image=foto, text="")
        self.video.image = foto  # Mantém a referência viva.

    # ===== SALVAR =====
    def _salvar(self):
        nome = self.campo_nome.valor()
        self.campo_nome.erro("" if nome else "Informe o nome")
        if not nome:
            return

        # Rede de segurança: o botão já fica desabilitado sem captura.
        if self.encoding_capturado is None:
            self.app.status("Capture o rosto antes de salvar", Cor.ALERTA)
            return

        usuario_id = self.db.get_next_tsu_id()
        caminho_foto = self._gravar_foto(usuario_id)

        self.db.adicionar_usuario(
            usuario_id=usuario_id,
            nome=nome,
            grupo=self.campo_grupo.valor(),
            telefone=self.campo_telefone.valor(),
            encoding=serialize_encoding(self.encoding_capturado),
            imagem_path=caminho_foto,
        )

        self.app.status(f"{nome} cadastrado como {usuario_id}", Cor.SUCESSO)
        self.app.status_direita(f"{len(self.db.listar_usuarios())} membros cadastrados")
        self._limpar()
        self._aguardando_saida = True
        self._quadro_livre = False

    def _gravar_foto(self, usuario_id):
        """Salva o quadro da captura em `data/images/<id>.jpg`."""
        if self.frame_capturado is None:
            return None
        config.ensure_directories()
        destino = config.IMAGES_DIR / f"{usuario_id}.jpg"
        cv2.imwrite(str(destino), self.frame_capturado)
        return str(destino)

    def _limpar(self):
        """Zera o formulário e reabre a captura para a próxima pessoa."""
        for campo in (self.campo_nome, self.campo_grupo, self.campo_telefone):
            campo.limpar()
        self._refazer()
        self.label_id.configure(text=self.db.get_next_tsu_id())
