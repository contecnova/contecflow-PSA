"""contecintelligence como analítica conversacional de contecflow (revisión 2026-11).

contecflow ya pregunta a SUS datos («Pregunta a los datos», sobre su almacén
analítico). contecintelligence pregunta a TODAS las fuentes de la empresa
(ERP, CRM, contecflow…), con métricas certificadas, la explicación de un
cambio, anomalías y un recibo firmado por respuesta. Aquí se llama con la
identidad de quien usa contecflow: contecintelligence aplica sus permisos y su
filtro de filas a esa persona.

Medido en su OpenAPI el 05-11-2026 (alcances en su `security/scopes.py`):

- `GET /sources` (`sources:read`), `POST /ask` y `POST /ask/stream` (SSE)
  (`chat:ask`);
- `GET /catalog/metrics`, `POST /metrics/query`, `POST /metrics/explain`,
  `POST /metrics/anomalies` (`metrics:read`);
- `GET /receipts/{id}` y `GET /receipts/{id}/verify` (`receipts:read`).

El rol: `analyst` para los roles de `CONTECINTELLIGENCE_ANALYST_ROLES`,
`viewer` para el resto. En contecintelligence un `viewer` sólo puede
preguntar y ver fuentes; las métricas le devuelven 403 y la pantalla lo dice.
"""
from __future__ import annotations

from typing import Iterator, Optional

from sqlalchemy.orm import Session

from app.services.conectores.anfitrion import (
    CONTECINTELLIGENCE, ErrorDeConector, _ajuste, abrir_flujo, cerrar_flujo, configuracion, llamar, token_delegado,
)

PREGUNTAR = ("chat:ask", "sources:read")
METRICAS = ("metrics:read", "sources:read")
RECIBOS = ("receipts:read",)
COMPONENTES = ("chat:ask", "sources:read", "metrics:read", "receipts:read")


def _plazo_pregunta(db: Session, org_id) -> float:
    return float(_ajuste(db, "CONTECINTELLIGENCE_ASK_TIMEOUT_SECONDS", org_id, "float"))


def fuente_por_defecto(db: Session, usuario) -> Optional[str]:
    return configuracion(db, CONTECINTELLIGENCE, usuario.organization_id).get("source_id") or None


def _fuente(db: Session, usuario, source_id: Optional[str]) -> str:
    fuente = source_id or fuente_por_defecto(db, usuario)
    if not fuente:
        raise ErrorDeConector("no_configurado", "Elige una fuente (o configura la fuente por defecto en "
                                                "Ajustes → Integraciones → contecintelligence)")
    return fuente


def fuentes(db: Session, usuario) -> list[dict]:
    r = llamar(db, CONTECINTELLIGENCE, usuario, "fuentes", "GET", "/sources", alcances=PREGUNTAR,
               params={"limit": 200})
    datos = r.json()
    items = datos if isinstance(datos, list) else (datos.get("items") or [])
    return [{"id": s.get("id"), "name": s.get("name"), "source_type": s.get("source_type"),
             "status": s.get("status"), "puedes_preguntar": s.get("puedes_preguntar", True),
             "supports_time_windows": s.get("supports_time_windows")} for s in items if isinstance(s, dict)]


def preguntar(db: Session, usuario, pregunta: str, source_id: Optional[str] = None,
              conversation_id: Optional[str] = None) -> dict:
    fuente = _fuente(db, usuario, source_id)
    r = llamar(db, CONTECINTELLIGENCE, usuario, "preguntar", "POST", "/ask", alcances=PREGUNTAR,
               json={"source_id": fuente, "question": pregunta, "conversation_id": conversation_id},
               plazo=_plazo_pregunta(db, usuario.organization_id))
    d = r.json()
    return {"text": d.get("text") or "", "payload": d.get("payload"), "receipt_id": d.get("receipt_id"),
            "receipt_signed": d.get("receipt_signed"), "conversation_id": d.get("conversation_id"),
            "source_id": fuente}


def preguntar_en_directo(db: Session, usuario, pregunta: str, source_id: Optional[str] = None,
                         conversation_id: Optional[str] = None) -> Iterator[bytes]:
    """Los eventos SSE de contecintelligence, tal cual, para reenviarlos a la pantalla.

    El primer `abrir_flujo` va FUERA del generador: si falla (sin alta, sin
    fuente), el endpoint responde con el error en vez de abrir un flujo vacío.
    """
    fuente = _fuente(db, usuario, source_id)
    cliente, r = abrir_flujo(db, CONTECINTELLIGENCE, usuario, "preguntar_directo", "POST", "/ask/stream",
                             alcances=PREGUNTAR, json={"source_id": fuente, "question": pregunta,
                                                       "conversation_id": conversation_id},
                             plazo=_plazo_pregunta(db, usuario.organization_id))

    def eventos() -> Iterator[bytes]:
        try:
            yield from r.iter_bytes()
        finally:
            cerrar_flujo(cliente, r)
    return eventos()


def metricas(db: Session, usuario, source_id: Optional[str] = None) -> list[dict]:
    params = {"limit": 500}
    if source_id:
        params["source_id"] = source_id
    r = llamar(db, CONTECINTELLIGENCE, usuario, "metricas", "GET", "/catalog/metrics", alcances=METRICAS,
               params=params)
    datos = r.json()
    items = datos if isinstance(datos, list) else (datos.get("items") or [])
    return [{"id": m.get("id"), "name": m.get("name"), "label": m.get("label") or m.get("name"),
             "description": m.get("description") or "", "source_id": m.get("source_id"),
             "dimensions": m.get("dimensions") or [], "grain": m.get("grain")}
            for m in items if isinstance(m, dict)]


def consultar_metrica(db: Session, usuario, source_id: str, consulta: dict) -> dict:
    r = llamar(db, CONTECINTELLIGENCE, usuario, "metrica", "POST", "/metrics/query", alcances=METRICAS,
               json={"source_id": source_id, "query": consulta}, plazo=_plazo_pregunta(db, usuario.organization_id))
    return r.json()


def explicar_cambio(db: Session, usuario, source_id: str, metrica: str, actual: dict, anterior: dict,
                    dimensiones: Optional[list[str]] = None) -> dict:
    r = llamar(db, CONTECINTELLIGENCE, usuario, "explicar", "POST", "/metrics/explain", alcances=METRICAS,
               json={"source_id": source_id, "metric": metrica, "actual": actual, "anterior": anterior,
                     "dimensions": dimensiones}, plazo=_plazo_pregunta(db, usuario.organization_id))
    return r.json()


def anomalias(db: Session, usuario, source_id: str, metrica: str, columna_tiempo: str, inicio: str, fin: str,
              granularidad: str = "day") -> dict:
    r = llamar(db, CONTECINTELLIGENCE, usuario, "anomalias", "POST", "/metrics/anomalies", alcances=METRICAS,
               json={"source_id": source_id, "metric": metrica, "time_column": columna_tiempo, "start": inicio,
                     "end": fin, "granularity": granularidad}, plazo=_plazo_pregunta(db, usuario.organization_id))
    return r.json()


def recibo(db: Session, usuario, receipt_id: str) -> dict:
    r = llamar(db, CONTECINTELLIGENCE, usuario, "recibo", "GET", f"/receipts/{receipt_id}", alcances=RECIBOS)
    return r.json()


def verificar_recibo(db: Session, usuario, receipt_id: str) -> dict:
    r = llamar(db, CONTECINTELLIGENCE, usuario, "verificar_recibo", "GET", f"/receipts/{receipt_id}/verify",
               alcances=RECIBOS)
    return r.json()


def token_para_componentes(db: Session, usuario, source_id: Optional[str] = None) -> dict:
    """Token acotado para `<ci-chat>` / `<ci-metric>` en el navegador. La credencial no sale de aquí."""
    extra = {"source_id": source_id} if source_id else None
    token, ttl, base = token_delegado(db, CONTECINTELLIGENCE, usuario, COMPONENTES, extra=extra)
    return {"access_token": token, "expires_in": ttl, "base_url": base}
