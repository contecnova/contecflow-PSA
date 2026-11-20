"""Interfaz de un proveedor de bots de reunión (el bot entra como participante).

Un proveedor externo es **encargado de tratamiento**: solo se usa si la
empresa lo activó con la referencia de su contrato (`config.guardar`).
Estados normalizados que devuelve `interpretar_evento`:
`programada`, `bot_unido`, `grabando`, `terminada`, `error`.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional


class ErrorDeBot(Exception):
    def __init__(self, codigo: str, detalle: str = ""):
        super().__init__(f"{codigo}: {detalle}")
        self.codigo, self.detalle = codigo, detalle


@dataclass
class EventoDeBot:
    bot_id: str
    estado: Optional[str]           # normalizado (ver arriba) o None si no cambia nada
    estado_crudo: str = ""
    datos: dict = field(default_factory=dict)


class ProveedorDeBots(abc.ABC):
    nombre: str = "abstracto"

    @abc.abstractmethod
    def crear_bot(self, url_reunion: str, *, nombre_bot: str, mensaje_al_entrar: str,
                  unirse_en: Optional[str] = None, metadatos: Optional[dict] = None) -> dict:
        """Crea el bot. Devuelve `{"id": ..., "estado": ...}`."""

    @abc.abstractmethod
    def estado(self, bot_id: str) -> str:
        """Estado normalizado del bot."""

    @abc.abstractmethod
    def salir(self, bot_id: str) -> None:
        """Saca el bot de la llamada."""

    @abc.abstractmethod
    def transcripcion(self, bot_id: str) -> list[dict]:
        """Segmentos `{speaker, start_ms, end_ms, text}` cuando la reunión terminó."""

    @abc.abstractmethod
    def borrar_medios(self, bot_id: str) -> None:
        """Pide al proveedor borrar audio, vídeo y transcripción (RGPD, retención)."""

    @abc.abstractmethod
    def verificar_firma(self, cabeceras: dict, cuerpo: bytes, secreto: str) -> bool:
        """¿El aviso viene firmado con el secreto de la empresa?"""

    @abc.abstractmethod
    def interpretar_evento(self, carga: dict) -> Optional[EventoDeBot]:
        """El aviso del proveedor normalizado (o None si no es de un bot)."""
