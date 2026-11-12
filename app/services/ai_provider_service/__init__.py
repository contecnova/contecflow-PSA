"""
ai_provider_service.py — Motor unificado de llamadas IA y gestión de proveedores.

Funciones exportadas (públicas):
  PROVIDER_CATALOG          — dict con todos los proveedores y modelos
  get_default_provider(db)  — obtener el proveedor por defecto
  call_ai(db, messages, ...) -> str  — despacho principal

Auditoria 2026-11 (#24): eran 1542 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `catalogo`: Catalogo de proveedores y modelos (de `app/core/ai_models.json`), modelos retirados y normalizacion de URLs base.
- `clientes`: Clientes HTTP de cada proveedor: llamada, adjuntos, listado y sincronizacion de modelos, despacho `call_provider` y diagnostico.
- `resolucion`: Resolucion del proveedor por defecto: base de datos (empresa, global), `.env` y credencial; pausa tras error.
- `gestion`: Alta, edicion, borrado y estadisticas de proveedores; probar sin guardar e importar el del `.env`.
- `rutas`: Proveedor y modelo por funcion (`MODULOS_DE_IA` y sus rutas por empresa).
- `gobernanza`: Guardarrailes de gobernanza de entrada y salida (de `call_ai` y del agente).
- `gasto`: Registro de uso, tope diario de gasto por empresa, coste estimado y turnos gobernados del agente.
- `despacho`: Despacho de una llamada (`call_ai`): eleccion de proveedor, llamada con respaldo y contabilidad del proveedor.

Sustituir un nombre en el paquete (`monkeypatch.setattr(svc, "call_provider", ...)`)
lo sustituye tambien en cada submodulo que lo tiene, de modo que `call_ai` y
el resto ven el parche igual que cuando era un solo fichero (ver `_Paquete`).
"""

import sys as _sys
import types as _types

import httpx  # noqa: F401

from app.services.ai_provider_service.catalogo import (  # noqa: F401
    _normalize_openai_base,
    _normalize_ollama_base,
    _MODELOS_POR_DEFECTO,
    _cargar_modelos,
    _MODELOS,
    _modelos,
    PROVIDER_CATALOG,
    _DEPRECATED_MODELS,
    _validate_model,
)

from app.services.ai_provider_service.clientes import (  # noqa: F401
    _con_adjuntos,
    _call_anthropic,
    _call_openai_compat,
    _call_gemini,
    espera_de_ia,
    _call_ollama,
    _list_openai_compatible_models,
    _list_anthropic_models,
    _list_gemini_models,
    _list_ollama_models,
    _list_azure_models,
    list_models_for_provider,
    sync_provider_models,
    call_provider,
    diagnose_provider,
)

from app.services.ai_provider_service.resolucion import (  # noqa: F401
    ProveedorDeEntorno,
    _SIN_CLAVE,
    proveedor_desde_entorno,
    proveedor_de_credencial,
    _disponible,
    get_default_provider,
)

from app.services.ai_provider_service.gestion import (  # noqa: F401
    list_providers,
    _clear_default,
    create_provider,
    get_provider,
    CAMPOS_EDITABLES_DEL_PROVEEDOR,
    update_provider,
    delete_provider,
    set_default_provider,
    update_provider_test_result,
    get_stats,
    proveedor_sin_guardar,
    importar_proveedor_de_entorno,
)

from app.services.ai_provider_service.rutas import (  # noqa: F401
    MODULOS_DE_IA,
    _CLAVE_RUTAS,
    rutas_por_modulo,
    guardar_rutas,
)

from app.services.ai_provider_service.gobernanza import (  # noqa: F401
    _resolver_usuario_de_gobernanza,
    _aplicar_guardrail_de_entrada,
    _aplicar_guardrail_de_salida,
    guardrail_de_instruccion,
    guardrail_de_respuesta,
)

from app.services.ai_provider_service.gasto import (  # noqa: F401
    _registrar_uso,
    PresupuestoDeIAAgotado,
    _inicio_de_hoy,
    gasto_de_hoy,
    presupuesto_diario,
    _exigir_presupuesto,
    coste_estimado,
    turno_de_agente,
    _org_de_la_llamada,
    _avisar_si_el_coste_diario_se_pasa,
)

from app.services.ai_provider_service.despacho import (  # noqa: F401
    _try_fallback_providers,
    _seleccionar_proveedor,
    _apuntar_uso_en_el_proveedor,
    _marcar_proveedor_en_error,
    SIN_PROVEEDOR,
    AVISO_SIN_PROVEEDOR,
    es_aviso_de_ia,
    _llamar_con_respaldo,
    call_ai,
)

from app.services.ai_provider_service.clientes import _logger  # noqa: F401
from app.services.ai_provider_service import catalogo, clientes, resolucion, gestion, rutas, gobernanza, gasto, despacho  # noqa: E402

_SUBMODULOS = (catalogo, clientes, resolucion, gestion, rutas, gobernanza, gasto, despacho)


class _Paquete(_types.ModuleType):
    """Propaga a los submodulos lo que se asigna en el paquete.

    Era un solo modulo: un parche en `app.services.ai_provider_service.X` lo veia
    todo el codigo. Partido, cada submodulo tiene su propia referencia a `X`;
    asi se sigue cambiando en todos a la vez (y deshacer el parche tambien).
    """

    def __setattr__(self, nombre, valor):
        # Los `__dunder__` (los fija `importlib.reload`) son de cada modulo.
        if not (nombre.startswith("__") and nombre.endswith("__")):
            for sub in _SUBMODULOS:
                if nombre in vars(sub):
                    setattr(sub, nombre, valor)
        super().__setattr__(nombre, valor)


_sys.modules[__name__].__class__ = _Paquete
