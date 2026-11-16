"""Interfaz común de los proveedores de uso (conectores) y lo que devuelven.

Un proveedor es una clase registrable (`proveedores.registrar`) que sabe LEER
una fuente y traducirla a cuatro cosas neutras:

- `Evidencia`: el uso de un producto por un titular (persona o dispositivo),
  con último uso, frecuencia, servicios usados y si la fuente dice que lo
  tiene asignado;
- `Dispositivo`: un equipo inventariado (nº de serie, último contacto, usuario
  principal y software detectado);
- `Derecho`: lo comprado de un SKU según el fabricante;
- `Aplicacion`: una aplicación vista (accesos SSO, tokens), para detectar
  software no controlado.

El proveedor NO escribe en la base: `sincronizacion` concilia lo leído con ALM
(titulares, licencias, activos) y lo guarda. Así cada conector se prueba con un
doble de HTTP y la conciliación se prueba una vez para todos.

Las llamadas salen por `ContextoDeLectura.http` (con tiempo de espera y la
protección de URLs salientes) y con las credenciales de ESA empresa
(`ContextoDeLectura.credenciales`): nunca con las de otra ni con las globales.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


class ErrorDeConector(Exception):
    """Un fallo de la fuente con un código estable (la pantalla lo traduce)."""

    def __init__(self, codigo: str, mensaje: str, *, estado_http: Optional[int] = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.estado_http = estado_http


@dataclass
class Evidencia:
    titular_tipo: str                      # persona | dispositivo
    titular: str                           # UPN/correo, o nº de serie / nombre del equipo
    producto: str                          # clave del producto en la fuente
    nombre_producto: Optional[str] = None
    sku: Optional[str] = None
    ultimo_uso: Optional[datetime] = None
    frecuencia: Optional[int] = None       # días con uso en `periodo_dias`
    periodo_dias: Optional[int] = None
    servicios: dict = field(default_factory=dict)   # {servicio: datetime | None}
    asignada: Optional[bool] = None
    detalle: dict = field(default_factory=dict)


@dataclass
class AppInstalada:
    nombre: str
    version: Optional[str] = None
    editor: Optional[str] = None
    ultimo_uso: Optional[datetime] = None


@dataclass
class Dispositivo:
    externo_id: str
    nombre: Optional[str] = None
    serie: Optional[str] = None
    sistema: Optional[str] = None
    version_sistema: Optional[str] = None
    fabricante: Optional[str] = None
    modelo: Optional[str] = None
    usuario: Optional[str] = None          # correo/UPN del usuario principal
    ultimo_contacto: Optional[datetime] = None
    ip: Optional[str] = None
    apps: list[AppInstalada] = field(default_factory=list)
    apps_leidas: bool = False              # False: la fuente no dio software (no se retira nada)
    detalle: dict = field(default_factory=dict)


@dataclass
class Derecho:
    sku: str
    nombre: Optional[str] = None
    comprados: Optional[int] = None
    consumidos: Optional[int] = None
    suspendidos: Optional[int] = None
    detalle: dict = field(default_factory=dict)


@dataclass
class Aplicacion:
    nombre: str
    usuarios: int = 0
    ultimo_uso: Optional[datetime] = None
    origen: str = "sso"


@dataclass
class ResultadoDeLectura:
    evidencias: list[Evidencia] = field(default_factory=list)
    dispositivos: list[Dispositivo] = field(default_factory=list)
    derechos: list[Derecho] = field(default_factory=list)
    aplicaciones: list[Aplicacion] = field(default_factory=list)
    #: Lo que no se pudo leer sin impedir el resto (p. ej. un informe sin permiso).
    avisos: list[dict] = field(default_factory=list)

    def avisar(self, codigo: str, mensaje: str) -> None:
        self.avisos.append({"codigo": codigo, "mensaje": mensaje})


@dataclass
class ContextoDeLectura:
    db: Any
    organization_id: str
    credenciales: dict
    configuracion: dict
    http: Any                              # proveedores.http.ClienteHttp o un doble
    max_paginas: int = 200
    periodo_dias: int = 30
    max_apps: int = 500
    ahora: Optional[datetime] = None


class ProveedorDeUso:
    """Base de un conector. Las subclases fijan los atributos y `leer`."""

    clave: str = ""
    etiqueta: str = ""
    #: Proveedor de `integration_credentials` cuyas claves usa (None: no necesita).
    credencial: Optional[str] = None
    #: Claves de la credencial sin las que no se puede leer.
    obligatorias: tuple[str, ...] = ()
    fiabilidad: str = "media"
    #: interno: lee la propia base; externo: llama a una API; agente: recibe envíos.
    tipo: str = "externo"
    #: Permisos de API que necesita (para la pantalla y DOCS.md).
    permisos: tuple[str, ...] = ()
    #: Qué aporta: evidencias, dispositivos, derechos, aplicaciones.
    aporta: tuple[str, ...] = ()
    #: Opciones no secretas que admite `configuracion` (clave, descripción).
    opciones: tuple[tuple[str, str], ...] = ()

    def leer(self, ctx: ContextoDeLectura) -> ResultadoDeLectura:  # pragma: no cover - interfaz
        raise NotImplementedError

    def probar(self, ctx: ContextoDeLectura) -> dict:
        """Comprueba credenciales y permisos con la llamada más barata. Por defecto, una lectura."""
        r = self.leer(ctx)
        return {"ok": True, "evidencias": len(r.evidencias), "dispositivos": len(r.dispositivos),
                "avisos": r.avisos}

    def describir(self) -> dict:
        return {"clave": self.clave, "etiqueta": self.etiqueta, "credencial": self.credencial,
                "obligatorias": list(self.obligatorias), "fiabilidad": self.fiabilidad, "tipo": self.tipo,
                "permisos": list(self.permisos), "aporta": list(self.aporta),
                "opciones": [{"clave": k, "descripcion": d} for k, d in self.opciones]}
