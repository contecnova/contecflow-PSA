"""Dominio `licencias` del motor de políticas: recuperación (harvesting) de licencias sin uso.

Licencias y hardware — fase 2: uso real (16-11-2026). La entidad es una
ASIGNACIÓN de licencia vigente (`ALMAsignacion`, titular persona o equipo). El
contexto sale del uso real (`app/services/alm_uso/estado.py`): días sin uso
(también descontando ausencias aprobadas), estado de uso, frecuencia, fuente y
su fiabilidad, si los datos están desactualizados, si la cuenta está
desactivada en la fuente; y de la licencia y el titular: producto, licencia,
proveedor, métrica, tipo, coste anual del puesto, días desde la asignación,
rol, departamento, equipo, proyecto, si está ausente hoy.

Resultado propio `recuperar` (avisos escalonados): avisar a la persona →
pasados N días, avisar a su responsable / jefe de proyecto / responsable del
contrato → pasados M días, liberar la licencia y devolverla a la bolsa, con
aprobación opcional. Lo ejecuta `alm_uso.recuperacion` (pasada diaria del
worker); el motor solo dice a quién y con qué pasos.

Protecciones que NO dependen de la política (se aplican siempre en
`alm_uso.recuperacion`): nunca a quien está ausente hoy (vacaciones, baja), ni
a una asignación más joven que `ALM_RECLAIM_GRACE_DAYS`, ni con datos
desactualizados o sin datos, ni a quien dijo que la sigue necesitando (durante
`ALM_RECLAIM_KEEP_DAYS`).

Reglas típicas:
  · «Días sin uso (descontando ausencias) > 60» y «Fiabilidad en alta, media» → recuperar;
  · «Cuenta desactivada en la fuente = sí» → recuperar sin esperas;
  · «Coste anual del puesto > 500» → recuperar con aprobación.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from app.services.politicas.registro import Campo, Dominio, Opcion, Parametro, ResultadoPropio, registrar

_NUM = ("gt", "gte", "lt", "lte", "eq", "ne", "between")
_ESTADOS = (("en_uso", "En uso"), ("infrautilizada", "Infrautilizada"), ("sin_uso", "Sin uso"),
            ("sin_datos", "Sin datos"))
_FIABILIDAD = (("alta", "Alta"), ("media", "Media"), ("baja", "Baja"))
_METRICAS = (("named_user", "Usuario nominal"), ("device", "Dispositivo"), ("concurrent", "Concurrente"),
             ("volume", "Volumen"), ("site", "Sitio"))

CAMPOS = [
    Campo("dias_sin_uso", "Días sin uso", "numero", operadores=_NUM,
          ayuda="Desde el último uso según la fuente (o desde la asignación si nunca se usó)"),
    Campo("dias_sin_uso_efectivos", "Días sin uso (descontando ausencias)", "numero", operadores=_NUM,
          ayuda="Sin contar los días de ausencias aprobadas de la persona"),
    Campo("estado_de_uso", "Estado de uso", "enum", opciones=tuple(Opcion(v, e) for v, e in _ESTADOS)),
    Campo("frecuencia", "Días con uso en el periodo de la fuente", "numero", operadores=_NUM),
    Campo("fiabilidad", "Fiabilidad de la fuente", "enum", opciones=tuple(Opcion(v, e) for v, e in _FIABILIDAD)),
    Campo("fuente", "Fuente del dato", "enum"),
    Campo("cuenta_desactivada", "Cuenta desactivada en la fuente", "booleano"),
    Campo("datos_desactualizados", "Datos desactualizados", "booleano"),
    Campo("licencia", "Licencia", "enum", categoria_de_tabla=True),
    Campo("producto", "Producto", "texto"),
    Campo("proveedor", "Proveedor", "enum"),
    Campo("metrica", "Métrica de la licencia", "enum", opciones=tuple(Opcion(v, e) for v, e in _METRICAS)),
    Campo("tipo_de_licencia", "Tipo de licencia", "enum", opciones=tuple(Opcion(v, v) for v in (
        "perpetual", "subscription", "concurrent", "named", "device", "trial", "free", "oem", "volume"))),
    Campo("coste_anual", "Coste anual del puesto", "importe",
          ayuda="Coste anual de la licencia ÷ puestos, en la moneda del contrato o de la empresa"),
    Campo("dias_desde_asignacion", "Días desde la asignación", "numero", operadores=_NUM),
    Campo("en_ausencia", "Está ausente hoy", "booleano"),
    Campo("titular", "Titular", "enum", opciones=(Opcion("persona", "Persona"), Opcion("dispositivo", "Equipo"))),
    Campo("persona", "Persona", "entidad", entidad="usuario"),
    Campo("rol", "Rol", "entidad", entidad="rol"),
    Campo("departamento", "Departamento", "entidad", entidad="departamento"),
    Campo("equipo", "Equipo", "entidad", entidad="equipo"),
    Campo("proyecto", "Proyecto al que se carga", "entidad", entidad="proyecto"),
]

RECUPERAR = ResultadoPropio(
    clave="recuperar", etiqueta="Recuperar la licencia",
    ayuda="Avisa a la persona, luego a su responsable, y al final libera la licencia (con aprobación si se pide)",
    parametros=(
        Parametro("clave", "Identificador", "clave"),
        Parametro("dias_hasta_responsable", "Días desde el aviso a la persona hasta avisar al responsable", "numero",
                  defecto=7, minimo=0),
        Parametro("escalar_a", "Responsable al que se avisa", "enum", defecto="responsable", opciones=(
            Opcion("responsable", "Su responsable directo"), Opcion("jefe_de_proyecto", "Jefe del proyecto"),
            Opcion("propietario", "Responsable del contrato"), Opcion("ninguno", "Nadie (pasar a liberar)"))),
        Parametro("dias_hasta_liberar", "Días desde el aviso al responsable hasta liberar", "numero", defecto=7,
                  minimo=0),
        Parametro("requiere_aprobacion", "Liberar solo con aprobación", "booleano", defecto=True, obligatorio=False),
        Parametro("canales", "Por", "canales", defecto=["app", "email"], obligatorio=False),
        Parametro("mensaje", "Mensaje para la persona", "texto", obligatorio=False),
    ),
)


def contexto(db, a) -> dict:
    """Contexto de una asignación. Solo lee (lo usan el simulador y la previsualización)."""
    from app.services.alm_uso.recuperacion import contexto_de_asignacion
    return contexto_de_asignacion(db, a)


def cargar(db, entidad_id: str):
    from app.models.alm import ALMLicenseAssignment as Asignacion
    return db.query(Asignacion).filter(Asignacion.id == entidad_id, Asignacion.resource_type == "license").first()


def historicos(db, desde: Optional[date], hasta: Optional[date], limite: int) -> list:
    """Las asignaciones de licencia vigentes (de persona o equipo): lo que la política tocaría hoy."""
    from app.models.alm import ALMLicenseAssignment as Asignacion
    q = db.query(Asignacion).filter(Asignacion.resource_type == "license", Asignacion.status == "active",
                                    Asignacion.holder_type.in_(("user", "asset")))
    if desde:
        q = q.filter(Asignacion.valid_from >= desde)
    if hasta:
        q = q.filter(Asignacion.valid_from <= hasta)
    return q.order_by(Asignacion.valid_from.desc()).limit(limite).all()


def resumen(a) -> str:
    lic = getattr(a, "license", None)
    quien = getattr(getattr(a, "holder_user", None), "full_name", None) or \
        getattr(getattr(a, "holder_asset", None), "name", None) or a.holder_type
    return f"{getattr(lic, 'name', a.license_id)} · {quien}"


def resolver_propio(db, ctx: dict, resultado: dict) -> tuple:
    """`recuperar` no se traduce a resultados del motor: lo ejecuta la recuperación."""
    return [], {"dias_sin_uso_efectivos": ctx.get("dias_sin_uso_efectivos"), "estado_de_uso": ctx.get("estado_de_uso")}


def opciones_dinamicas(db) -> dict:
    from app.models.alm import ALMLicense, ALMVendor
    from app.services.alm_uso.proveedores import proveedores
    return {"licencia": [Opcion(l.id, l.name) for l in db.query(ALMLicense).filter(ALMLicense.is_active.is_(True))
                         .order_by(ALMLicense.name).all()],
            "proveedor": [Opcion(v.id, v.name) for v in db.query(ALMVendor).filter(ALMVendor.is_active.is_(True))
                          .order_by(ALMVendor.name).all()],
            "fuente": [Opcion(p.clave, p.etiqueta) for p in proveedores()]}


def ejemplos(db, usuario) -> dict:
    return {"tablas": [], "politicas": [{
        "dominio": "licencias", "nombre": "Recuperar licencias sin uso", "prioridad": 10,
        "descripcion": "Ejemplo: más de 60 días sin uso (sin contar ausencias) con una fuente fiable → avisar, "
                       "escalar y liberar con aprobación",
        "activa": True,
        "ambito": {"departamentos": [], "equipos": [], "roles": [], "ubicaciones": [], "personas": []},
        "reglas": [{
            "nombre": "Sin uso en 60 días", "activa": True, "detener": True,
            "exceso": None,
            "condicion": {"tipo": "grupo", "op": "and", "hijos": [
                {"tipo": "condicion", "campo": "dias_sin_uso_efectivos", "operador": "gt", "valor": 60},
                {"tipo": "condicion", "campo": "fiabilidad", "operador": "in",
                 "valor": ["alta", "media"]},
            ]},
            "resultados": [{"tipo": "recuperar", "clave": str(uuid.uuid4()), "dias_hasta_responsable": 7,
                            "escalar_a": "responsable", "dias_hasta_liberar": 7, "requiere_aprobacion": True,
                            "canales": ["app", "email"], "mensaje": ""}],
        }],
    }]}


registrar(Dominio(
    clave="licencias", etiqueta="Licencias (recuperación)", campos=CAMPOS, contexto=contexto, cargar=cargar,
    historicos=historicos, propietario=lambda a: a.holder_user_id, resumen=resumen,
    tipo_de_aprobacion="license_reclaim", ejemplos=ejemplos, resultados_propios=(RECUPERAR,),
    resolver_propio=resolver_propio, opciones_dinamicas=opciones_dinamicas,
))
