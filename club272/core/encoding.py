"""
Utilitários de encoding facial.

Antes duplicados em `register.py`, `batch_register.py` e
`sistema_integrado_completo.py`.
"""

import pickle

import numpy as np


def serialize_encoding(encoding):
    """Serializa um encoding facial (numpy array) para gravar no banco."""
    if encoding is None:
        return None
    return pickle.dumps(encoding)


def deserialize_encoding(encoding_bytes):
    """Desserializa um encoding facial vindo do banco."""
    if encoding_bytes is None:
        return None
    try:
        return pickle.loads(encoding_bytes)
    except Exception as e:
        print(f"Erro ao desserializar encoding: {e}")
        return None


def extrair_encoding(imagem_path):
    """Extrai o encoding do primeiro rosto encontrado numa imagem.

    Retorna None quando o arquivo não abre ou nenhum rosto é detectado.
    """
    import cv2
    import face_recognition

    try:
        imagem = cv2.imread(str(imagem_path))
        if imagem is None:
            return None

        rgb = cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)
        localizacoes = face_recognition.face_locations(rgb)
        if not localizacoes:
            return None

        encodings = face_recognition.face_encodings(rgb, [localizacoes[0]])
        return encodings[0] if encodings else None
    except Exception as e:
        print(f"Erro ao extrair encoding de {imagem_path}: {e}")
        return None


def encoding_para_lista(encoding):
    """Converte um encoding para lista de floats (útil para JSON/Supabase)."""
    if encoding is None:
        return None
    return np.asarray(encoding).tolist()
