"""Núcleo compartilhado: banco, encodings, reconhecimento e integrações."""

from club272.core.database import DatabaseManager
from club272.core.encoding import (
    deserialize_encoding,
    extrair_encoding,
    serialize_encoding,
)
from club272.core.recognition import (
    Camera,
    MotorReconhecimento,
    ReconhecedorAssincrono,
)

__all__ = [
    "DatabaseManager",
    "Camera",
    "MotorReconhecimento",
    "ReconhecedorAssincrono",
    "serialize_encoding",
    "deserialize_encoding",
    "extrair_encoding",
]
