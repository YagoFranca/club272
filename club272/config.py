"""
Configuração central do 272 Club.

Reúne num único lugar tudo o que antes estava espalhado e duplicado pelos
módulos: caminhos de pastas, caminho do banco e credenciais do Supabase.

As credenciais são lidas do arquivo `.env` na raiz do projeto (veja
`.env.example`). Nada de segredo deve voltar para dentro do código-fonte.
"""

import os
from pathlib import Path

# ===== CAMINHOS DO PROJETO =====
# club272/config.py -> club272/ -> raiz do projeto
BASE_DIR = Path(__file__).resolve().parent.parent

ASSETS_DIR = BASE_DIR / "club272" / "assets"
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
PHOTOS_DIR = DATA_DIR / "photos"
BACKUPS_DIR = DATA_DIR / "backups"
TEMPLATES_DIR = BASE_DIR / "templates"

# `CLUB272_DB` aponta para outro arquivo — usado pelos testes de ponta a
# ponta, e útil para experimentar sem tocar no banco de produção.
DB_PATH = os.environ.get("CLUB272_DB") or str(DATA_DIR / "sistema_integrado.db")

LOGO_PATH = str(ASSETS_DIR / "272club.png")
ICON_PATH = str(ASSETS_DIR / "272club.ico")


def ensure_directories():
    """Cria as pastas de dados caso ainda não existam."""
    for folder in (DATA_DIR, IMAGES_DIR, PHOTOS_DIR, BACKUPS_DIR):
        folder.mkdir(parents=True, exist_ok=True)


# ===== .env =====
def _load_dotenv():
    """Carrega o `.env` da raiz. Usa python-dotenv se disponível, senão faz o
    parse manual (mantém o projeto rodando mesmo sem a dependência)."""
    env_file = BASE_DIR / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file)
        return
    except ImportError:
        pass

    if not env_file.exists():
        return
    for linha in env_file.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        os.environ.setdefault(chave.strip(), valor.strip().strip("'\""))


_load_dotenv()


# ===== SUPABASE =====
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
# Chave service_role: só é necessária para operações de Storage.
STORAGE_KEY = os.environ.get("SUPABASE_STORAGE_KEY", "")

SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "FaceAttendenceRealTime")

# Timeout padrão (segundos) das chamadas HTTP ao Supabase.
REQUEST_TIMEOUT = int(os.environ.get("SUPABASE_TIMEOUT", "10"))


def supabase_headers(key=None):
    """Cabeçalhos padrão para a API REST do Supabase."""
    key = key or SUPABASE_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def supabase_configurado():
    """True quando URL e chave anon estão presentes."""
    return bool(SUPABASE_URL and SUPABASE_KEY)


# ===== RECONHECIMENTO FACIAL =====
# Distância máxima aceita ao comparar rostos (menor = mais rigoroso).
FACE_TOLERANCE = float(os.environ.get("FACE_TOLERANCE", "0.45"))

# Prefixo e faixa dos IDs gerados automaticamente.
TSU_PREFIX = "TSU_"
TSU_START = 10000


# ===== DESEMPENHO =====
# PERFIL_LEVE liga os ajustes pensados para máquina antiga (o alvo é um Core 2
# Duo com vídeo integrado). Nenhum deles mexe na tolerância de identificação —
# só evitam trabalho que não muda o resultado.
PERFIL_LEVE = os.environ.get("CLUB272_PERFIL", "leve").lower() == "leve"

# Resolução de captura. Mais pixels não melhoram o reconhecimento e custam
# banda de barramento e CPU na conversão.
# Índice do dispositivo. "auto" procura o primeiro que entregue imagem de
# verdade — câmeras virtuais (NVIDIA Broadcast, OBS) costumam ocupar o índice
# 0 e devolver quadros pretos, o que antes aparecia como uma prévia preta sem
# explicação nenhuma.
CAMERA_INDICE = os.environ.get("CAMERA_INDICE", "auto")

# Quantos dispositivos sondar na busca automática.
CAMERA_MAX_INDICE = int(os.environ.get("CAMERA_MAX_INDICE", "4"))

# Desvio padrão mínimo do quadro para considerá-lo imagem, e não tela preta.
CAMERA_DESVIO_MINIMO = float(os.environ.get("CAMERA_DESVIO_MINIMO", "1.0"))

CAMERA_LARGURA = int(os.environ.get("CAMERA_LARGURA", "480" if PERFIL_LEVE else "640"))
CAMERA_ALTURA = int(os.environ.get("CAMERA_ALTURA", "360" if PERFIL_LEVE else "480"))

# Quadros por segundo desenhados na tela. 15 é fluido para o olho e custa
# metade de 30 numa máquina sem folga.
FPS_EXIBICAO = int(os.environ.get("FPS_EXIBICAO", "15" if PERFIL_LEVE else "30"))

# Fração do frame usada na detecção. Em 0.5 com upsample=0 o custo é o mesmo
# que 0.25 com upsample=1, e enxerga rostos com metade do tamanho.
ESCALA_DETECCAO = float(os.environ.get("ESCALA_DETECCAO", "0.5"))

# Haar (OpenCV) acha rostos ~2,6x mais rápido que o HOG do dlib. A caixa sai
# menos justa, mas medimos que isso desloca o encoding em 0,086 — contra uma
# tolerância de 0,45, não muda o veredito.
DETECTOR_RAPIDO = os.environ.get("DETECTOR", "haar").lower() == "haar"

# Refina a caixa do Haar com HOG no recorte (~4 ms). Barato e devolve a mesma
# caixa que o dlib usaria.
REFINAR_CAIXA = os.environ.get("REFINAR_CAIXA", "1") == "1"

# ===== CAPTURA AUTOMÁTICA (tela de cadastro) =====
# Segundos que o rosto precisa ficar firme antes da foto sair sozinha.
TEMPO_ESTAVEL = float(os.environ.get("TEMPO_ESTAVEL", "1.2"))

# Fração mínima da largura do quadro que o rosto deve ocupar. Rosto pequeno é
# rosto longe, e encoding de rosto longe fica ruim para sempre.
LARGURA_MINIMA_ROSTO = float(os.environ.get("LARGURA_MINIMA_ROSTO", "0.16"))


# Pula o pipeline inteiro enquanto a cena não muda. Custa 0,04 ms e zera o
# consumo com a sala vazia.
FILTRO_MOVIMENTO = os.environ.get("FILTRO_MOVIMENTO", "1") == "1"
LIMIAR_MOVIMENTO = float(os.environ.get("LIMIAR_MOVIMENTO", "1.5"))

# Mesmo sem movimento, o pipeline roda pelo menos uma vez neste intervalo.
# É a rede de segurança do portão: sem ela, quem entra devagar ou com pouco
# contraste nunca abre o portão e jamais é detectado.
INTERVALO_BATIMENTO = float(os.environ.get("INTERVALO_BATIMENTO", "1.5"))
