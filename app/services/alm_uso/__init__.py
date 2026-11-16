"""Licencias y hardware — fase 2: uso real (16-11-2026).

Quién usa (o dejó de usar) cada licencia y cada equipo, según fuentes externas
(Microsoft 365 / Entra ID, Intune, Google Workspace, Okta, Jamf) e internas
(accesos y SSO de contecflow, agente de inventario de la CMDB), y lo que se
hace con ello: recuperación con el motor de políticas, ajuste de nivel,
cumplimiento real y software no controlado.

Módulos:
- `proveedores/`: interfaz común `ProveedorDeUso` y los conectores (registro).
- `conexiones`: fuentes de una empresa y sus credenciales cifradas.
- `sincronizacion`: lecturas programadas y manuales, con su registro.
- `conciliacion`: titulares → personas/activos, productos → licencias, instalaciones.
- `estado`: estado de uso por asignación y por licencia (en_uso / infrautilizada / sin_uso / sin_datos).
- `recuperacion`: harvesting escalonado (dominio de políticas `licencias`).
- `ajuste`: propuestas de bajar de nivel con ahorro.
- `cumplimiento`: posición efectiva por licencia y exportación para auditoría.
- `no_controlado`: candidatos fuera de ALM (gastos, SSO, inventario).
- `inventario`: lo que envía el agente de la CMDB en su check-in.

API de LECTURA para otros módulos (renovaciones de la fase 3, informes):

    from app.services import alm_uso
    alm_uso.uso_de_licencia(db, license_id) -> dict
        Claves (contrato con `alm_renovaciones.uso_de_licencia`):
          asignados, total, en_uso, infrautilizadas, sin_uso, sin_datos,
          pico_concurrente, fuente (texto con las fuentes), medido_en (ISO de la
          lectura más reciente);
        y además: license_id, nombre, metric, estado (global), uso_sin_asignacion
          (titulares que la usan o la tienen en la fuente sin asignación en ALM),
          ultimo_uso, fuentes (lista), pico_medido_en y `asignaciones` (el
          detalle de `uso_de_asignacion` de cada una).
        `sin_datos` = asignaciones de las que ninguna fuente dice nada: una
        renovación no debe leer «sin datos» como «sin uso».

    alm_uso.uso_de_asignacion(db, assignment_id) -> dict
        estado, motivo, ultimo_uso, dias_sin_uso, dias_sin_uso_efectivos
        (descontando ausencias aprobadas), dias_ausencia, en_ausencia, frecuencia,
        periodo_dias, fuente, fiabilidad, leido_at, datos_desactualizados,
        cuenta_desactivada, fuentes ([{fuente, ultimo_uso, fiabilidad, leido_at, …}]),
        servicios ({servicio: fecha ISO del último uso}).

    alm_uso.uso_de_licencias(db, organization_id, license_ids=None) -> [dict]
        El mismo resumen para muchas licencias en una sola carga.

Todas acotan a la empresa (la de la sesión si no se dice).
"""
from __future__ import annotations

from app.services.alm_uso.estado import (  # noqa: F401
    uso_de_asignacion, uso_de_equipos, uso_de_licencia, uso_de_licencias,
)


def panel(db, organization_id: str) -> dict:
    """KPIs de la pantalla de uso: estado de las asignaciones, gasto en licencias ociosas y fuentes."""
    from app.services.alm_uso import ajuste, conexiones, recuperacion
    from app.services.alm_uso._comun import exigir_org, moneda_de_empresa
    org = exigir_org(organization_id)
    licencias = uso_de_licencias(db, org, con_asignaciones=True)
    cuenta = {k: sum(l[k] for l in licencias) for k in ("asignados", "en_uso", "infrautilizadas", "sin_uso", "sin_datos")}
    from app.models.alm import ALMLicense
    from app.services.alm_uso._comun import coste_unitario_anual
    costes = {l.id: coste_unitario_anual(l) for l in db.query(ALMLicense).filter(ALMLicense.organization_id == org)}
    ocioso = sum((costes.get(l["license_id"]) or 0) * l["sin_uso"] for l in licencias)
    fuentes = conexiones.listar(db, org)
    activas = [f for f in fuentes if f["activa"]]
    return {
        **cuenta,
        "licencias": len(licencias),
        "licencias_sin_datos": sum(1 for l in licencias if l["estado"] == "sin_datos"),
        "coste_anual_sin_uso": round(ocioso, 2), "moneda": moneda_de_empresa(db, org),
        "fuentes_activas": len(activas),
        "fuentes_con_error": sum(1 for f in activas if f["ultimo_estado"] == "error"),
        "ultima_lectura": max((f["ultima_sincronizacion_at"] for f in activas if f["ultima_sincronizacion_at"]),
                              default=None),
        "recuperaciones": recuperacion.listar(db, org, "abiertas")["kpis"],
        "ahorro_por_ajuste": ajuste.ahorro_logrado(db, org),
    }


def pasada_diaria(db, organization_id: str) -> dict:
    """La pasada diaria del worker en una empresa: software no controlado en gastos y recuperación.

    La sincronización de fuentes va aparte, cada hora (`sincronizacion.sincronizar_pendientes`),
    y lee cada fuente cuando vence su intervalo `ALM_USAGE_SYNC_INTERVAL_HOURS`.
    """
    from app.services.alm_uso import no_controlado, recuperacion
    candidatos = no_controlado.detectar_gastos(db, organization_id)
    db.commit()
    return {"candidatos_de_gastos": candidatos, "recuperacion": recuperacion.pasada(db, organization_id)}
