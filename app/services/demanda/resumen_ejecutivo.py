"""Executive Summary del expediente en PDF (reportlab) y PPTX (python-pptx).

Plantilla configurable por fase (`committee.executive_summary`) o por acción
al cerrar (`on_close_actions[].params`):

    true                              → todo por defecto
    {"title": {"es": …},              → título del documento
     "fields": ["coste", …],          → campos del business case (por defecto: todos con valor)
     "opinion_phases": ["cab", …],    → fases cuyos dictámenes se incluyen (por defecto: las de
                                        revisión, aprobación y puerta ya pasadas)
     "include_history": true}         → anexo con el log de transiciones

Los dos ficheros se guardan en el repositorio del expediente con la etiqueta
`executive_summary` (internos: el cliente no los ve) y la acción queda en el log.
"""
from __future__ import annotations

import io
import json
from typing import Optional

from sqlalchemy.orm import Session

from app.services.demanda import definicion as D
from app.services.demanda.acceso import Actor
from app.services.demanda.motor import datos_de, flujo_de, registrar


def _plantilla(req, config) -> dict:
    if isinstance(config, dict):
        return config
    f = D.fase(flujo_de(req), req.current_phase_key) or {}
    c = (f.get("committee") or {}).get("executive_summary")
    return c if isinstance(c, dict) else {}


def _formato(valor) -> str:
    if valor is None or valor == "":
        return "—"
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, float):
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(valor)


def contenido(db: Session, req, idioma: str = "es", config=None) -> dict:
    """Los datos del resumen (lo mismo para el PDF y el PPTX)."""
    from app.models.demanda import DemandStepState, DemandTransition
    defn = flujo_de(req)
    plantilla = _plantilla(req, config)
    datos = datos_de(req)
    claves = plantilla.get("fields") or [c["key"] for c in D.campos(defn) if not D.vacio(datos.get(c["key"]))]
    filas = [(D.nombre((D.campo(defn, k) or {}).get("label"), idioma) or k, _formato(datos.get(k))) for k in claves]
    actual = D.indice(defn, req.current_phase_key)
    fases_dictamen = plantilla.get("opinion_phases") or [
        f["key"] for i, f in enumerate(D.fases(defn))
        if f.get("kind") in ("review", "approval", "gate") and (actual < 0 or i < actual)]
    dictamenes = []
    for clave in fases_dictamen:
        f = D.fase(defn, clave) or {}
        for st in db.query(DemandStepState).filter(DemandStepState.request_id == req.id,
                                                   DemandStepState.phase_key == clave,
                                                   DemandStepState.status != "pending") \
                .order_by(DemandStepState.round.desc()).all():
            paso = D.paso(f, st.step_key) or {}
            votos = json.loads(st.votes or "[]") if st.votes else []
            quien = ", ".join(v.get("name", "") for v in votos) or (st.decided_by or "")
            if st.decided_by:
                from app.models.user import User
                u = db.query(User).filter(User.id == st.decided_by).first()
                quien = (u.full_name if u else quien) or quien
            dictamenes.append({"fase": D.nombre(f.get("name"), idioma), "paso": D.nombre(paso.get("name"), idioma),
                               "resultado": st.status, "quien": quien, "nota": st.note or "",
                               "fecha": st.decided_at.strftime("%d/%m/%Y") if st.decided_at else ""})
            break
    historia = []
    if plantilla.get("include_history", True):
        for t in db.query(DemandTransition).filter(DemandTransition.request_id == req.id) \
                .order_by(DemandTransition.seq).all():
            historia.append((t.created_at.strftime("%d/%m/%Y %H:%M") if t.created_at else "", t.decision,
                             t.to_phase or t.from_phase or "", t.actor_name or "", t.justification or ""))
    motivos = json.loads(req.committee_reasons or "[]") if req.committee_reasons else []
    return {"titulo": D.nombre(plantilla.get("title"), idioma) or "Executive Summary",
            "codigo": req.code, "asunto": req.title, "tipo": req.type_key,
            "ambito": "Proyecto" if req.project_id else ("Iniciativa independiente" if req.standalone else req.scope_kind),
            "filas": filas, "dictamenes": dictamenes, "historia": historia, "motivos_comite": motivos,
            "fecha_comite": req.committee_date.strftime("%d/%m/%Y %H:%M") if req.committee_date else ""}


def pdf(c: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm,
                            bottomMargin=2 * cm, title=f"{c['titulo']} {c['codigo']}")
    st = getSampleStyleSheet()
    p = lambda t, s="BodyText": Paragraph(escape(str(t)).replace("\n", "<br/>"), st[s])  # noqa: E731
    estilo = TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8ccd4")),
                         ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f4f7")),
                         ("VALIGN", (0, 0), (-1, -1), "TOP")])
    partes = [p(c["titulo"], "Title"), p(f"{c['codigo']} · {c['asunto']}", "Heading2"),
              p(f"{c['tipo']} · {c['ambito']}" + (f" · Comité: {c['fecha_comite']}" if c["fecha_comite"] else "")),
              Spacer(1, 12), p("Business case", "Heading3")]
    if c["filas"]:
        t = Table([[p(k), p(v)] for k, v in c["filas"]], colWidths=[5.5 * cm, 11.5 * cm])
        t.setStyle(estilo)
        partes.append(t)
    if c["motivos_comite"]:
        partes += [Spacer(1, 8), p("Motivos para el comité: " + "; ".join(c["motivos_comite"]))]
    partes += [Spacer(1, 12), p("Dictámenes", "Heading3")]
    for d in c["dictamenes"]:
        partes.append(p(f"{d['fase']} — {d['paso']}: {d['resultado']} ({d['quien']}, {d['fecha']})", "Heading5"))
        if d["nota"]:
            partes.append(p(d["nota"]))
    if not c["dictamenes"]:
        partes.append(p("—"))
    if c["historia"]:
        partes += [Spacer(1, 12), p("Trazabilidad", "Heading3")]
        t = Table([[p(x) for x in fila] for fila in c["historia"]],
                  colWidths=[2.8 * cm, 2.6 * cm, 2.6 * cm, 3.5 * cm, 5.5 * cm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c8ccd4")),
                               ("FONTSIZE", (0, 0), (-1, -1), 7)]))
        partes.append(t)
    doc.build(partes)
    return buf.getvalue()


def pptx(c: dict) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

    def diapositiva(titulo: str, lineas: list[str]):
        s = prs.slides.add_slide(prs.slide_layouts[5])
        s.shapes.title.text = titulo
        caja = s.shapes.add_textbox(Inches(0.6), Inches(1.5), Inches(12.1), Inches(5.6)).text_frame
        caja.word_wrap = True
        for i, linea in enumerate(lineas or ["—"]):
            par = caja.paragraphs[0] if i == 0 else caja.add_paragraph()
            par.text = linea[:900]
            par.font.size = Pt(14)

    portada = prs.slides.add_slide(prs.slide_layouts[0])
    portada.shapes.title.text = c["titulo"]
    portada.placeholders[1].text = f"{c['codigo']} · {c['asunto']}\n{c['tipo']} · {c['ambito']}" + (
        f"\nComité: {c['fecha_comite']}" if c["fecha_comite"] else "")
    filas = [f"{k}: {v}" for k, v in c["filas"]]
    for i in range(0, max(len(filas), 1), 8):
        diapositiva("Business case", filas[i:i + 8])
    diapositiva("Dictámenes", [f"{d['fase']} — {d['paso']}: {d['resultado']} ({d['quien']}, {d['fecha']})"
                               + (f". {d['nota']}" if d["nota"] else "") for d in c["dictamenes"]]
                + ([f"Motivos para el comité: {'; '.join(c['motivos_comite'])}"] if c["motivos_comite"] else []))
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def generar(db: Session, req, actor: Actor, idioma: str = "es", config=None) -> list:
    """Genera PDF y PPTX, los guarda en el expediente y lo registra. No commitea."""
    from app.services.demanda.documentos import guardar_generado
    c = contenido(db, req, idioma, config)
    base = f"executive-summary-{req.code}"
    docs = [guardar_generado(db, req, actor, f"{base}.pdf", "application/pdf", pdf(c), "executive_summary"),
            guardar_generado(db, req, actor, f"{base}.pptx",
                             "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                             pptx(c), "executive_summary")]
    registrar(db, req, actor, "executive_summary", desde=req.current_phase_key, hacia=req.current_phase_key,
              estado_previo=req.status, datos={"documents": [d.id for d in docs]})
    return docs


def generar_y_confirmar(db: Session, req, actor: Actor, idioma: str = "es", config=None) -> list:
    """`generar` y confirma la transacción."""
    resultado = generar(db, req, actor, idioma, config)
    db.commit()
    return resultado


def agendar_comite(db: Session, req, actor: Actor, fecha, idioma: str = "es") -> list:
    """Agenda el comité de la fase actual y, si la fase lo pide, genera el resumen. Commitea."""
    from app.core.codigos_de_error import error
    f = D.fase(flujo_de(req), req.current_phase_key) or {}
    if f.get("kind") != "committee" or req.status not in ("in_progress", "on_hold"):
        raise error(409, "dem_comite_no_aplica")
    req.committee_date = fecha
    registrar(db, req, actor, "committee_scheduled", desde=req.current_phase_key, hacia=req.current_phase_key,
              estado_previo=req.status, datos={"date": fecha.isoformat() if fecha else None})
    docs: list = []
    if (f.get("committee") or {}).get("executive_summary"):
        docs = generar(db, req, actor, idioma)
    db.commit()
    return docs


def leer_config(valor: Optional[str]) -> Optional[dict]:
    try:
        return json.loads(valor) if valor else None
    except ValueError:
        return None
