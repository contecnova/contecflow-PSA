"""Registro de proveedores de uso (conectores).

Añadir una fuente: una subclase de `base.ProveedorDeUso` con `clave`,
credencial (si la necesita, un proveedor `alm_*` en
`integration_credentials_service.PROVIDER_REGISTRY`), permisos y `leer(ctx)`;
y `registrar(MiProveedor())` aquí abajo. La conciliación, el registro de
sincronizaciones, la pantalla de conexiones y el worker la recogen solos.
"""
from __future__ import annotations

from app.core.errores import ErrorDeDominio
from app.services.alm_uso.proveedores.base import ProveedorDeUso
from app.core.codigos_de_error import ErrorConCodigo

_REGISTRO: dict[str, ProveedorDeUso] = {}


def registrar(p: ProveedorDeUso) -> ProveedorDeUso:
    if not p.clave:
        raise ErrorConCodigo("alm_proveedor_uso_sin_clave", detail="un proveedor de uso necesita clave")
    _REGISTRO[p.clave] = p
    return p


def proveedor(clave: str) -> ProveedorDeUso:
    p = _REGISTRO.get(clave)
    if p is None:
        raise ErrorDeDominio(404, {"code": "ALM_USAGE_UNKNOWN_PROVIDER", "message": f"Fuente desconocida: {clave}"})
    return p


def proveedores() -> list[ProveedorDeUso]:
    return list(_REGISTRO.values())


def _incluidos() -> None:
    from app.services.alm_uso.proveedores.google import GoogleWorkspace
    from app.services.alm_uso.proveedores.internos import AccesoContecflow, AgenteInventario, SsoContecflow
    from app.services.alm_uso.proveedores.jamf import Jamf
    from app.services.alm_uso.proveedores.microsoft import Intune, Microsoft365
    from app.services.alm_uso.proveedores.okta import Okta
    for p in (Microsoft365(), Intune(), GoogleWorkspace(), Okta(), Jamf(), AccesoContecflow(), SsoContecflow(),
              AgenteInventario()):
        registrar(p)


_incluidos()
