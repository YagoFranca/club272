"""
Reconhecimento facial assíncrono, dimensionado para hardware fraco.

O gargalo é o `face_encodings` do dlib: ~400 ms por rosto nesta máquina de
desenvolvimento, e o alvo de produção é um Core 2 Duo — anterior ao AVX, então
lá deve passar de 1 s. Recompilar o dlib não resolve: a instrução não existe
nesse processador.

Duas frentes atacam o problema sem afrouxar o critério de identificação:

1. **Tirar o trabalho da thread da interface.** Uma thread captura, outra
   reconhece, e a interface só desenha. O vídeo corre solto; o resultado do
   reconhecimento chega com atraso, irrelevante para controle de presença.

2. **Só pagar pelo encoder quando é inevitável.** Uma cascata de portões
   baratos filtra o que não precisa chegar lá:

       movimento?        0,04 ms   sala parada não custa nada
       Haar detectou?    5    ms   2,6x mais rápido que o HOG
       caixa estável?    0    ms   descarta falso positivo do Haar
       já identificado?  0    ms   quem está parado não é recodificado
       -> encoder      400+ ms   só para rosto novo de verdade

A precisão da identificação não muda: mesmo encoder de 128 dimensões, mesma
tolerância. Medido: trocar a caixa do HOG pela do Haar desloca o encoding em
0,086 — contra uma tolerância de 0,45. A caixa não altera o veredito, e ainda
assim ela é refinada com HOG no recorte (4 ms) antes de codificar.
"""

import multiprocessing as mp
import queue
import threading
import time

import cv2
import face_recognition
import numpy as np

from club272 import config
from club272.core.encoding import deserialize_encoding

# O `face_recognition` guarda o detector, os preditores de pontos e o encoder
# como singletons de módulo, e objetos do dlib não são thread-safe. Duas
# threads entrando neles ao mesmo tempo corrompem estado em código nativo e o
# processo morre com segmentation fault — sem exceção, sem traceback.
#
# Toda chamada ao dlib dentro deste processo passa por esta trava. Não custa
# desempenho: o binding não solta o GIL, então já era serializado de fato;
# a trava apenas garante que a serialização aconteça na entrada, e não no meio
# de uma estrutura sendo escrita.
#
# O processo separado do encoder tem seu próprio espaço de memória e seus
# próprios singletons, então não participa desta trava.
TRAVA_DLIB = threading.RLock()


def _contiguo(imagem):
    """Garante buffer contíguo antes de entregar a imagem ao dlib.

    Um recorte como `rgb[y1:y2, x1:x2]` é uma *view*: os strides continuam os
    da imagem inteira, então cada linha "avança" mais bytes do que a largura
    recortada. O dlib recebe só o ponteiro e a forma, lê pelo stride errado e
    invade memória vizinha — violação de acesso, processo morto, sem exceção
    nem traceback.

    Fica aqui, na fronteira com o código nativo, para nenhum chamador precisar
    lembrar disso.
    """
    return np.ascontiguousarray(imagem)


def localizar_rostos(rgb, upsample=0):
    """Detecção HOG do dlib, serializada e com buffer contíguo."""
    with TRAVA_DLIB:
        return face_recognition.face_locations(
            _contiguo(rgb), number_of_times_to_upsample=upsample
        )


def extrair_encoding_de(rgb, localizacao=None, upsample=1):
    """Encoding de 128 dimensões do maior rosto encontrado, serializado.

    Devolve None se não houver rosto. Usada pela tela de cadastro, onde o
    custo de uma chamada isolada não justifica acionar o processo do encoder.
    """
    with TRAVA_DLIB:
        rgb = _contiguo(rgb)
        if localizacao is None:
            localizacoes = face_recognition.face_locations(
                rgb, number_of_times_to_upsample=upsample
            )
            if not localizacoes:
                return None
            # O maior rosto é o mais próximo da câmera.
            localizacao = max(
                localizacoes, key=lambda l: (l[2] - l[0]) * (l[1] - l[3])
            )

        encodings = face_recognition.face_encodings(rgb, [localizacao])
        return encodings[0] if encodings else None


# Um rosto já identificado e ainda dentro da janela de validade não precisa
# passar de novo pelo encoder enquanto continuar na mesma posição.
IOU_MESMO_ROSTO = 0.5
VALIDADE_RASTREIO_S = 4.0

# Um rosto que já foi codificado e deu "desconhecido" também não precisa voltar
# ao encoder a cada ciclo enquanto continuar parado. Sem isso, um estranho
# diante da câmera geraria codificações sem fim — o pior caso para a CPU.
VALIDADE_DESCONHECIDO_S = 3.0

# O Haar erra para mais. Exigir a caixa em duas passadas seguidas evita gastar
# o encoder num falso positivo.
DETECCOES_ANTES_DE_CODIFICAR = 2


def iou(a, b):
    """Interseção sobre união de duas caixas (esq, topo, dir, baixo)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    intersecao = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return intersecao / float(area_a + area_b - intersecao)


class MotorReconhecimento:
    """Compara um encoding contra os rostos conhecidos.

    Os encodings ficam numa matriz numpy montada uma vez, em vez de uma lista
    reconvertida a cada comparação.
    """

    def __init__(self, database, tolerancia=None):
        self.database = database
        self.tolerancia = tolerancia if tolerancia is not None else config.FACE_TOLERANCE
        self.matriz = np.empty((0, 128))
        self.ids = []
        self.nomes = {}
        self.carregar()

    def carregar(self):
        """(Re)carrega os encodings do banco. Devolve quantos foram lidos."""
        encodings, ids, nomes = [], [], {}

        for usuario in self.database.listar_usuarios():
            encoding = deserialize_encoding(usuario.get("encoding"))
            if encoding is None:
                continue
            encodings.append(encoding)
            ids.append(usuario["id"])
            nomes[usuario["id"]] = usuario["name"]

        self.matriz = np.array(encodings) if encodings else np.empty((0, 128))
        self.ids = ids
        self.nomes = nomes
        return len(ids)

    def identificar(self, encoding):
        """Devolve (usuario_id, distancia), ou (None, distancia) se ninguém
        ficou dentro da tolerância."""
        if not len(self.matriz):
            return None, 1.0

        # Uma passada de distância euclidiana. O código antigo chamava
        # compare_faces e face_distance, calculando a mesma coisa duas vezes.
        distancias = np.linalg.norm(self.matriz - encoding, axis=1)
        indice = int(np.argmin(distancias))
        distancia = float(distancias[indice])

        if distancia <= self.tolerancia:
            return self.ids[indice], distancia
        return None, distancia


class Detector:
    """Localiza rostos: Haar para achar, HOG no recorte para precisar a caixa.

    O Haar sozinho já serve para identificar, mas o refino custa poucos
    milissegundos e devolve a caixa que o dlib usaria.
    """

    def __init__(self, usar_haar=True, refinar=True, tamanho_minimo=40):
        self.usar_haar = usar_haar
        self.refinar = refinar
        self.tamanho_minimo = tamanho_minimo
        self._cascata = (
            cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            if usar_haar else None
        )

    def detectar(self, rgb):
        """Devolve caixas no formato do face_recognition: (topo, dir, baixo, esq).

        A trava cobre o método inteiro: além do dlib, o `CascadeClassifier` do
        OpenCV também não aceita uso simultâneo da mesma instância.
        """
        if not self.usar_haar:
            return localizar_rostos(rgb, upsample=0)

        with TRAVA_DLIB:
            cinza = cv2.cvtColor(_contiguo(rgb), cv2.COLOR_RGB2GRAY)
            achados = self._cascata.detectMultiScale(
                cinza, scaleFactor=1.2, minNeighbors=5,
                minSize=(self.tamanho_minimo, self.tamanho_minimo),
            )

        caixas = []
        altura, largura = rgb.shape[:2]
        for (x, y, w, h) in achados:
            caixa = (y, x + w, y + h, x)
            if self.refinar:
                caixa = self._refinar(rgb, caixa, largura, altura) or caixa
            caixas.append(caixa)
        return caixas

    def _refinar(self, rgb, caixa, largura, altura):
        """Roda o HOG só na vizinhança da caixa — barato e preciso."""
        topo, direita, baixo, esquerda = caixa
        margem = int(0.3 * (direita - esquerda))

        y1, y2 = max(0, topo - margem), min(altura, baixo + margem)
        x1, x2 = max(0, esquerda - margem), min(largura, direita + margem)

        encontrados = localizar_rostos(rgb[y1:y2, x1:x2], upsample=0)
        if not encontrados:
            return None

        t, d, b, e = encontrados[0]
        return (t + y1, d + x1, b + y1, e + x1)


def _laco_encoder(entrada, saida):
    """Corpo do processo dedicado ao encoder.

    Roda em processo separado, e não em thread, porque o binding do dlib não
    solta o GIL: medido, uma chamada em thread congela a interface por ~440 ms.
    Num processo à parte o trabalho cai no outro núcleo e a janela nem sente.

    Recebe recortes de rosto já cortados — trafegar 150x150 pela fila é barato,
    o frame inteiro não seria.
    """
    import face_recognition as fr  # importado aqui: o filho tem seu próprio espaço

    pai = mp.parent_process()

    while True:
        try:
            tarefa = entrada.get(timeout=5.0)
        except queue.Empty:
            # Se o pai morreu de forma abrupta (um segfault, por exemplo), o
            # `daemon=True` não adianta: ninguém executa o encerramento. Sem
            # esta checagem o filho fica órfão, segurando ~200 MB para sempre.
            if pai is not None and not pai.is_alive():
                break
            continue

        if tarefa is None:
            break

        marca, recorte = tarefa
        try:
            altura, largura = recorte.shape[:2]
            encodings = fr.face_encodings(recorte, [(0, largura, altura, 0)])
            saida.put((marca, encodings[0] if encodings else None))
        except Exception:
            saida.put((marca, None))


class EncoderRemoto:
    """Fachada do processo do encoder.

    Mantém no máximo uma tarefa em voo: numa máquina fraca, enfileirar
    codificações só acumularia atraso.
    """

    def __init__(self):
        self._processo = None
        self._entrada = None
        self._saida = None
        self._marca = 0
        self._em_voo = None

    def iniciar(self):
        if self._processo is not None:
            return True
        try:
            contexto = mp.get_context("spawn")
            self._entrada = contexto.Queue()
            self._saida = contexto.Queue()
            self._processo = contexto.Process(
                target=_laco_encoder, args=(self._entrada, self._saida), daemon=True
            )
            self._processo.start()
            return True
        except Exception as e:
            print(f"Encoder em processo indisponível ({e}); usando o processo atual.")
            self._processo = None
            return False

    @property
    def ativo(self):
        return self._processo is not None and self._processo.is_alive()

    @property
    def ocupado(self):
        return self._em_voo is not None

    def enviar(self, recorte):
        """Despacha um recorte. False se já houver tarefa em andamento."""
        if not self.ativo or self._em_voo is not None:
            return False
        self._marca += 1
        self._em_voo = self._marca
        self._entrada.put((self._marca, recorte))
        return True

    def receber(self, espera=0.5):
        """Aguarda o encoding da tarefa em voo. None se falhar ou expirar."""
        if self._em_voo is None:
            return None
        try:
            marca, encoding = self._saida.get(timeout=espera)
        except queue.Empty:
            return None
        if marca != self._em_voo:
            return None
        self._em_voo = None
        return encoding

    def parar(self):
        if self._processo is None:
            return
        try:
            self._entrada.put(None)
            self._processo.join(timeout=3.0)
            if self._processo.is_alive():
                self._processo.terminate()
                self._processo.join(timeout=1.0)
        except Exception:
            pass

        # Fechar as filas encerra a QueueFeederThread que o multiprocessing
        # cria por baixo; sem isso ela fica viva até o fim do processo.
        for fila in (self._entrada, self._saida):
            try:
                fila.close()
                fila.join_thread()
            except Exception:
                pass

        self._processo = None
        self._entrada = None
        self._saida = None
        self._em_voo = None


class Camera:
    """Captura em thread própria, mantendo apenas o frame mais recente.

    Ler a webcam no laço da interface acumula latência de buffer e trava o
    desenho. Aqui a leitura corre solta e quem consome sempre pega o quadro
    mais novo — quadros atrasados são descartados, que é o certo para vídeo ao
    vivo.
    """

    def __init__(self, indice=0, largura=None, altura=None):
        self.indice = indice
        self.largura = largura or config.CAMERA_LARGURA
        self.altura = altura or config.CAMERA_ALTURA
        self._frame = None
        self._lock = threading.Lock()
        self._rodando = False
        self._thread = None
        self._pronta = threading.Event()
        self._falhou = threading.Event()

    def iniciar(self, espera=8.0):
        """Abre o dispositivo e começa a capturar. False se não conseguir."""
        if self._rodando:
            return True

        self._pronta.clear()
        self._falhou.clear()
        self._rodando = True
        self._thread = threading.Thread(target=self._laco, daemon=True)
        self._thread.start()

        # A thread é quem abre o dispositivo; aqui só esperamos o veredito.
        limite = time.time() + espera
        while time.time() < limite:
            if self._pronta.is_set():
                return True
            if self._falhou.is_set():
                self._rodando = False
                return False
            time.sleep(0.02)

        self.parar()
        return False

    def _abrir(self):
        """Tenta abrir a webcam. DSHOW primeiro: no Windows abre bem mais
        rápido que o backend padrão."""
        for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
            cap = cv2.VideoCapture(self.indice, backend)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.largura)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.altura)
                # Buffer curto: evita exibir imagem velha da fila do driver.
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return cap
            cap.release()
        return None

    def _laco(self):
        """Único dono do VideoCapture: abre, lê e libera.

        Nada fora desta thread toca o objeto. A versão anterior liberava a
        captura de fora depois de um `join` com timeout — quando o `read()`
        demorava mais que o timeout, o release acontecia com o OpenCV ainda
        dentro da leitura, e o processo morria com segmentation fault.
        """
        cap = self._abrir()
        if cap is None:
            self._falhou.set()
            self._rodando = False
            return

        try:
            while self._rodando:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.01)
                    continue
                frame = cv2.flip(frame, 1)  # Espelha: natural para quem se vê.
                with self._lock:
                    self._frame = frame
                self._pronta.set()
        finally:
            cap.release()
            with self._lock:
                self._frame = None

    def ler(self):
        """Cópia do frame mais recente, ou None."""
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    @property
    def ativa(self):
        return self._rodando and self._pronta.is_set()

    def parar(self, espera=5.0):
        """Sinaliza e espera a thread encerrar. Não libera nada por fora."""
        self._rodando = False
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=espera)
        self._pronta.clear()
        self._falhou.clear()


class ReconhecedorAssincrono:
    """Detecta e identifica numa thread, sobre o frame mais recente da câmera.

    A interface lê `deteccoes` para desenhar e `coletar_registros()` para saber
    quem foi confirmado desde a última consulta.
    """

    def __init__(self, camera, motor, detector=None, confirmacoes=3, espera_s=3.0):
        self.camera = camera
        self.motor = motor
        self.detector = detector or Detector(
            usar_haar=config.DETECTOR_RAPIDO, refinar=config.REFINAR_CAIXA
        )
        self.confirmacoes_necessarias = confirmacoes
        self.espera_s = espera_s
        self.encoder = EncoderRemoto()

        self.deteccoes = []
        self.estatisticas = {
            "ciclos": 0, "codificacoes": 0,
            "pulos_movimento": 0, "pulos_rastreio": 0,
            "ms_ultimo_ciclo": 0.0,
        }

        self._contagem = {}
        self._ultimo_registro = {}
        self._pendentes = []
        self._rastreio = []
        self._candidatos = []       # caixas vistas, aguardando estabilidade
        self._referencia_movimento = None

        self._lock = threading.Lock()
        self._rodando = False
        self._thread = None

    # ===== CICLO DE VIDA =====
    def iniciar(self):
        if self._rodando:
            return
        self.encoder.iniciar()
        self._rodando = True
        self._thread = threading.Thread(target=self._laco, daemon=True)
        self._thread.start()

    def parar(self):
        self._rodando = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self.encoder.parar()
        with self._lock:
            self.deteccoes = []
            self._rastreio = []
            self._candidatos = []
            self._contagem.clear()
            self._referencia_movimento = None

    def coletar_registros(self):
        """Devolve e limpa a fila de confirmados."""
        with self._lock:
            registros, self._pendentes = self._pendentes, []
            return registros

    # ===== LAÇO =====
    def _laco(self):
        while self._rodando:
            frame = self.camera.ler()
            if frame is None:
                time.sleep(0.02)
                continue

            inicio = time.perf_counter()
            try:
                deteccoes = self._processar(frame)
            except Exception as e:  # uma falha de frame não derruba a thread
                print(f"Erro no reconhecimento: {e}")
                deteccoes = []

            decorrido = (time.perf_counter() - inicio) * 1000
            with self._lock:
                self.deteccoes = deteccoes
                self._rastreio = deteccoes
                self.estatisticas["ciclos"] += 1
                self.estatisticas["ms_ultimo_ciclo"] = decorrido

            # Um respiro para a interface, que divide os mesmos 2 núcleos.
            time.sleep(0.01)

    def _processar(self, frame):
        pequeno = cv2.resize(
            frame, (0, 0),
            fx=config.ESCALA_DETECCAO, fy=config.ESCALA_DETECCAO,
        )

        # --- Portão 1: a cena mudou? ---
        # Só vale pular quando não há trabalho pendente. Se a passada anterior
        # viu um rosto ainda não identificado, precisamos continuar — senão
        # quem entra e fica parado trava o portão e nunca é reconhecido.
        if not self._ha_pendencia() and not self._houve_movimento(pequeno):
            with self._lock:
                self.estatisticas["pulos_movimento"] += 1
                return list(self._rastreio)  # mantém as caixas anteriores

        # --- Portão 2: há rosto? ---
        rgb = cv2.cvtColor(pequeno, cv2.COLOR_BGR2RGB)
        localizacoes = self.detector.detectar(rgb)
        if not localizacoes:
            with self._lock:
                self._contagem.clear()
                self._candidatos = []
            return []

        fator = 1.0 / config.ESCALA_DETECCAO
        agora = time.time()

        with self._lock:
            rastreio = list(self._rastreio)

        deteccoes = []
        a_codificar = []

        for i, (topo, direita, baixo, esquerda) in enumerate(localizacoes):
            caixa = (
                int(esquerda * fator), int(topo * fator),
                int(direita * fator), int(baixo * fator),
            )

            # --- Portão 3: já identificado e parado no mesmo lugar? ---
            reaproveitado = self._reaproveitar(caixa, rastreio, agora)
            if reaproveitado:
                deteccoes.append(reaproveitado)
                with self._lock:
                    self.estatisticas["pulos_rastreio"] += 1
                continue

            deteccoes.append({"caixa": caixa, "usuario_id": None,
                              "nome": None, "confianca": 0.0})
            # --- Portão 4: a caixa se repetiu o bastante? ---
            if self._estavel(caixa):
                a_codificar.append(i)

        self._atualizar_candidatos([d["caixa"] for d in deteccoes])

        # --- Encoder: no máximo um rosto por ciclo ---
        # Numa máquina fraca, codificar três rostos de uma vez seria vários
        # segundos parado. O maior rosto é o mais próximo da câmera, que é
        # quem está se apresentando.
        if a_codificar:
            i = max(a_codificar, key=lambda k: _area(deteccoes[k]["caixa"]))
            encoding = self._codificar(rgb, localizacoes[i])
            with self._lock:
                self.estatisticas["codificacoes"] += 1
            if encoding is not None:
                self._identificar_em(deteccoes[i], encoding, agora)
            # Marca como avaliado mesmo quando não bateu com ninguém: é o que
            # impede o estranho parado de voltar ao encoder a cada ciclo.
            deteccoes[i]["verificado_em"] = agora

        return deteccoes

    def _codificar(self, rgb, localizacao):
        """Extrai o encoding do rosto, de preferência no processo dedicado.

        Envia só o recorte com margem, não o frame inteiro: menos dados na
        fila e nenhuma diferença no resultado, já que o dlib só olha o rosto.
        """
        topo, direita, baixo, esquerda = localizacao
        altura, largura = rgb.shape[:2]
        margem = int(0.25 * (direita - esquerda))

        y1, y2 = max(0, topo - margem), min(altura, baixo + margem)
        x1, x2 = max(0, esquerda - margem), min(largura, direita + margem)
        recorte = np.ascontiguousarray(rgb[y1:y2, x1:x2])

        if self.encoder.enviar(recorte):
            encoding = self.encoder.receber(espera=8.0)
            if encoding is not None:
                return encoding

        # Sem processo disponível (ou falha nele): codifica aqui mesmo. A
        # interface engasga, mas o sistema não deixa de funcionar.
        return extrair_encoding_de(rgb, localizacao)

    # ===== PORTÕES =====
    def _ha_pendencia(self):
        """True quando ainda há trabalho a fazer sobre os rostos em cena.

        São dois casos: rosto que nunca passou pelo encoder, e rosto já
        identificado que ainda não juntou as confirmações para ser registrado.
        Em ambos, parar por falta de movimento deixaria a pessoa sem registro —
        exatamente o que acontece com quem chega e fica parado.
        """
        with self._lock:
            for d in self._rastreio:
                if not d.get("verificado_em"):
                    return True
                usuario_id = d.get("usuario_id")
                if usuario_id and usuario_id not in self._ultimo_registro:
                    return True
            return False

    def _houve_movimento(self, pequeno):
        """Compara com o último frame analisado. Custa ~0,04 ms."""
        if not config.FILTRO_MOVIMENTO:
            return True

        miniatura = cv2.cvtColor(
            cv2.resize(pequeno, (160, 120)), cv2.COLOR_BGR2GRAY
        )
        anterior, self._referencia_movimento = self._referencia_movimento, miniatura

        if anterior is None:
            return True
        return cv2.absdiff(anterior, miniatura).mean() >= config.LIMIAR_MOVIMENTO

    def _estavel(self, caixa):
        """True quando a caixa já apareceu em passadas anteriores."""
        vistas = sum(
            1 for c in self._candidatos if iou(caixa, c) >= IOU_MESMO_ROSTO
        )
        return vistas + 1 >= DETECCOES_ANTES_DE_CODIFICAR

    def _atualizar_candidatos(self, caixas):
        self._candidatos = caixas

    def _reaproveitar(self, caixa, rastreio, agora):
        """Mantém o resultado de um rosto que continua no mesmo lugar, em vez
        de gastar outra passada no encoder.

        Vale para quem já foi registrado neste evento e para quem já deu
        desconhecido — em ambos os casos recodificar não traria informação
        nova. Quem foi identificado mas ainda não atingiu as confirmações
        necessárias continua indo ao encoder: as confirmações só valem como
        garantia se vierem de codificações independentes.

        Os prazos são curtos para que uma troca de pessoa na mesma posição
        seja reavaliada.
        """
        for anterior in rastreio:
            if iou(caixa, anterior["caixa"]) < IOU_MESMO_ROSTO:
                continue
            if not anterior.get("verificado_em"):
                continue

            usuario_id = anterior.get("usuario_id")
            if usuario_id:
                with self._lock:
                    ja_registrado = usuario_id in self._ultimo_registro
                if not ja_registrado:
                    continue  # Ainda coletando confirmações.
                limite = VALIDADE_RASTREIO_S
            else:
                limite = VALIDADE_DESCONHECIDO_S

            if agora - anterior["verificado_em"] > limite:
                continue  # Passou do prazo: reavalia.

            copia = dict(anterior)
            copia["caixa"] = caixa
            return copia
        return None

    def _identificar_em(self, deteccao, encoding, agora):
        usuario_id, distancia = self.motor.identificar(encoding)
        if usuario_id is None:
            with self._lock:
                self._contagem.clear()
            return

        deteccao["usuario_id"] = usuario_id
        deteccao["nome"] = self.motor.nomes.get(usuario_id, usuario_id)
        deteccao["confianca"] = (1.0 - distancia) * 100.0

        with self._lock:
            ultimo = self._ultimo_registro.get(usuario_id)
            if ultimo and agora - ultimo < self.espera_s:
                return  # Registrado há pouco.

            self._contagem[usuario_id] = self._contagem.get(usuario_id, 0) + 1
            for outro in list(self._contagem):
                if outro != usuario_id:
                    self._contagem[outro] = 0

            if self._contagem[usuario_id] >= self.confirmacoes_necessarias:
                self._contagem[usuario_id] = 0
                self._ultimo_registro[usuario_id] = agora
                self._pendentes.append({
                    "id": usuario_id,
                    "nome": deteccao["nome"],
                    "confianca": deteccao["confianca"],
                })


def _area(caixa):
    esquerda, topo, direita, baixo = caixa
    return (direita - esquerda) * (baixo - topo)


def desenhar_deteccoes(frame, deteccoes):
    """Desenha as caixas sobre o frame. Barato: roda na thread da interface."""
    for d in deteccoes:
        esquerda, topo, direita, baixo = d["caixa"]
        conhecido = d.get("usuario_id") is not None

        cor = (92, 168, 150) if conhecido else (71, 90, 224)  # BGR
        cv2.rectangle(frame, (esquerda, topo), (direita, baixo), cor, 2)

        rotulo = f"{d['nome']} {d['confianca']:.0f}%" if conhecido else "Desconhecido"
        cv2.rectangle(frame, (esquerda, baixo - 22), (direita, baixo), cor, cv2.FILLED)
        cv2.putText(
            frame, rotulo, (esquerda + 6, baixo - 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 16, 14), 1, cv2.LINE_AA,
        )
    return frame
