"""Informes programados de riesgo y vulnerabilidades (§11.10 del diseño).

Son los informes programados de siempre (`scheduled_reports`, worker horario,
correo con PDF por `scheduled_reports.ejecutar_informes_vencidos`) con dos
tipos nuevos:

- ``cyber_risk``: índice del ámbito con su nivel, riesgo aceptado, objetivo,
  factores, tendencia de 90 días y los primeros pasos del plan;
- ``vuln_management``: métricas (§11.6) y los hallazgos de más riesgo.

El ámbito va en `filters_json` (``scope_type``, ``scope_id``). El PDF lo pinta
`historia_pdf` dentro de `report_pdf_service.build_report_pdf`. Se gestionan
desde la pestaña Riesgo (`/cmdb/software/risk/reports`), con
`software.gestionar`; cada alta, cambio y baja, auditada (`sw_risk_report`).
"""
from __future__ import annotations

import json
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.cmdb_software.riesgo import calculo as calc

TIPOS = ("cyber_risk", "vuln_management")
FRECUENCIAS = ("daily", "weekly", "monthly")
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _filtros(r) -> dict:
    try:
        return json.loads(r.filters_json or "{}") or {}
    except ValueError:
        return {}


def serializar(r) -> dict:
    f = _filtros(r)
    try:
        destinatarios = json.loads(r.recipients or "[]")
    except ValueError:
        destinatarios = []
    return {"id": r.id, "name": r.name, "report_type": r.report_type, "scope_type": f.get("scope_type") or "org",
            "scope_id": f.get("scope_id") or None, "frequency": r.frequency, "send_hour": r.send_hour,
            "day_of_week": r.day_of_week, "day_of_month": r.day_of_month, "recipients": destinatarios,
            "is_active": bool(r.is_active), "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
            # El worker escribe `success`; la pantalla usa `ok` como el resto de ejecuciones.
            "last_status": "ok" if r.last_status == "success" else r.last_status, "last_error": r.last_error,
            "next_run_at": r.next_run_at.isoformat() if r.next_run_at else None}


def _q(db, org):
    from app.models.billing_reports import ScheduledReport
    q = db.query(ScheduledReport).filter(ScheduledReport.report_type.in_(TIPOS))
    return q.filter(ScheduledReport.organization_id == org) if org else q


def listar(db: Session, org) -> list[dict]:
    from app.models.billing_reports import ScheduledReport
    return [serializar(r) for r in _q(db, org).order_by(ScheduledReport.name)]


def informe(db, org, id_):
    from app.models.billing_reports import ScheduledReport
    r = _q(db, org).filter(ScheduledReport.id == id_).first() if id_ else None
    if r is None:
        raise error(404, "swr_informe_no_encontrado")
    return r


def _entero(campo: str, v, minimo: int, maximo: int) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise error(422, "swr_ajuste_no_valido", campo=campo)
    if not minimo <= n <= maximo:
        raise error(422, "swr_ajuste_no_valido", campo=campo)
    return n


def _aplicar(r, d: dict, nuevo: bool) -> None:
    if "name" in d or nuevo:
        nombre = (d.get("name") or "").strip()
        if len(nombre) < 2:
            raise error(422, "sw_nombre_obligatorio")
        r.name = nombre[:255]
    if "report_type" in d or nuevo:
        if d.get("report_type") not in TIPOS:
            raise error(422, "swr_informe_tipo", tipo=d.get("report_type"))
        r.report_type = d["report_type"]
    if "scope_type" in d or "scope_id" in d or nuevo:
        f = _filtros(r)
        tipo, id_ = calc.comprobar_ambito(d.get("scope_type", f.get("scope_type")), d.get("scope_id", f.get("scope_id")))
        r.filters_json = json.dumps({**f, "scope_type": tipo, "scope_id": id_ or None})
    if "frequency" in d or nuevo:
        if (d.get("frequency") or "weekly") not in FRECUENCIAS:
            raise error(422, "swr_ajuste_no_valido", campo="frequency")
        r.frequency = d.get("frequency") or "weekly"
    if "send_hour" in d:
        r.send_hour = _entero("send_hour", d["send_hour"], 0, 23) if d["send_hour"] not in (None, "") else 8
    if "day_of_week" in d:
        r.day_of_week = _entero("day_of_week", d["day_of_week"], 0, 6)
    if "day_of_month" in d:
        r.day_of_month = _entero("day_of_month", d["day_of_month"], 1, 28)
    if "recipients" in d or nuevo:
        lista = d.get("recipients") or []
        if isinstance(lista, str):
            lista = re.split(r"[\s,;]+", lista)
        lista = [x.strip() for x in lista if x and x.strip()]
        if not lista or any(not _CORREO.match(x) for x in lista):
            raise error(422, "swr_destinatarios")
        r.recipients = json.dumps(list(dict.fromkeys(lista))[:50])
    if "is_active" in d:
        r.is_active = bool(d["is_active"])


def crear(db: Session, org, d: dict, usuario) -> dict:
    from app.models.billing_reports import ScheduledReport
    from app.services.scheduled_reports import proxima_ejecucion
    r = ScheduledReport(organization_id=org, created_by=getattr(usuario, "id", None), include_pdf=True,
                        is_active=True, send_hour=8, recipients="[]", recipients_extra="[]", filters_json="{}")
    _aplicar(r, d, True)
    r.next_run_at = proxima_ejecucion(r)
    db.add(r)
    db.flush()
    audit_log(db, usuario, "CREATE", "sw_risk_report", r.id, r.name, new_values=serializar(r))
    return serializar(r)


def cambiar(db: Session, org, id_: str, d: dict, usuario) -> dict:
    from app.services.scheduled_reports import proxima_ejecucion
    r = informe(db, org, id_)
    antes = serializar(r)
    _aplicar(r, d, False)
    r.next_run_at = proxima_ejecucion(r)
    db.flush()
    audit_log(db, usuario, "UPDATE", "sw_risk_report", r.id, r.name, old_values=antes, new_values=serializar(r))
    return serializar(r)


def borrar(db: Session, org, id_: str, usuario) -> None:
    r = informe(db, org, id_)
    audit_log(db, usuario, "DELETE", "sw_risk_report", r.id, r.name, old_values=serializar(r))
    db.delete(r)
    db.flush()


def enviar_ahora(db: Session, org, id_: str, usuario) -> dict:
    from app.services.scheduled_reports import execute_report_now
    r = informe(db, org, id_)
    res = execute_report_now(r.id, db)
    audit_log(db, usuario, "SEND", "sw_risk_report", r.id, r.name, metadata={"ok": res.get("ok")})
    return res


# ── PDF ──────────────────────────────────────────────────────────────────────

def _tabla(filas: list[list], anchos, styles):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    t = Table(filas, colWidths=anchos, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), styles["_cabecera_fondo"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), styles["_cabecera_texto"]),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ROWPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def historia_pdf(report, db, org_id, styles) -> list:
    """Bloques del PDF de un informe de riesgo (`report_pdf_service`)."""
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Spacer
    from app.services.textos_de_salida import texto
    idioma = styles.get("_idioma")

    def t(clave, **p):
        return texto(f"riesgo.{clave}", idioma, **p)
    f = _filtros(report)
    tipo, id_ = calc.comprobar_ambito(f.get("scope_type"), f.get("scope_id"))
    ctx = calc.contexto(db, org_id)
    idx = calc.indice_de_ambito(db, org_id, tipo, id_, ctx)
    story = [Paragraph(t("ambito", ambito=idx.get("scope_name") or tipo), styles["body"]), Spacer(1, 6)]
    if report.report_type == "cyber_risk":
        filas = [[t("indicador"), t("valor")],
                 [t("indice"), f"{idx['score']:.1f} ({idx.get('level') or '-'})"],
                 [t("aceptado"), f"{idx['accepted_score']:.1f}"],
                 [t("objetivo"), f"{idx['target']:.0f}"],
                 [t("hallazgos_vivos"), str(idx["counts"]["findings_live"])],
                 [t("explotados"), str(idx["counts"]["exploited"])],
                 [t("expuestos"), str(idx["counts"]["internet_assets"])]]
        story += [Paragraph(t("resumen"), styles["section"]), _tabla(filas, [9 * cm, 6 * cm], styles)]
        filas = [[t("factor"), t("puntuacion"), t("peso"), t("contribucion")]]
        filas += [[t(f"factor_{x['key']}"), f"{x['score']:.1f}", f"{x['weight']:.2f}", f"{x['contribution']:.1f}"]
                  for x in idx["factors"]]
        story += [Paragraph(t("factores"), styles["section"]), _tabla(filas, [6 * cm, 3 * cm, 3 * cm, 3 * cm], styles)]
        hist = calc.historico(db, org_id, tipo, id_, 90)
        if hist:
            muestras = hist[:: max(1, len(hist) // 12)]
            filas = [[t("dia"), t("indice"), t("aceptado")]] + [[h["day"], f"{h['score']:.1f}",
                                                                   f"{h['accepted_score']:.1f}"] for h in muestras]
            story += [Paragraph(t("tendencia"), styles["section"]), _tabla(filas, [5 * cm, 4 * cm, 4 * cm], styles)]
        pl = calc.plan(db, org_id, tipo, id_, None, maximo=15)
        if pl["steps"]:
            filas = [[t("aviso"), t("software"), t("impacto"), t("tras")]]
            for p in pl["steps"]:
                h = p["finding"]
                filas.append([h.get("vuln_id") or "-", f"{h.get('product_name') or '-'} {h.get('affected_version') or ''}",
                              f"-{p['impact']:.1f}", f"{p['score_after']:.1f}"])
            story += [Paragraph(t("plan", desde=f"{pl['current']:.0f}", hasta=f"{pl['target']:.0f}"), styles["section"]),
                      _tabla(filas, [4 * cm, 6 * cm, 2.5 * cm, 2.5 * cm], styles)]
    else:
        from app.services.cmdb_software.riesgo.metricas import hallazgos, metricas
        m = metricas(db, org_id, tipo, id_, 90)

        def v(x, suf=""):
            return "-" if x is None else f"{x}{suf}"
        filas = [[t("indicador"), t("valor")],
                 [t("pct_activos"), v(m["pct_assets_with_vulns"], " %")],
                 [t("pct_internos"), v(m["pct_internal_with_vulns"], " %")],
                 [t("pct_maquinas"), v(m["pct_machines_with_vulns"], " %")],
                 [t("densidad_activo"), v(m["density_per_asset"])],
                 [t("densidad_maquina"), v(m["density_per_machine"])],
                 [t("mttp"), v(m["mttp_days"])],
                 [t("antiguedad"), v(m["avg_age_unpatched_days"])],
                 [t("so_sin_soporte"), v(m["os_unsupported"])],
                 [t("impacto_alto"), v(m["by_impact"]["high"])], [t("impacto_medio"), v(m["by_impact"]["medium"])],
                 [t("impacto_bajo"), v(m["by_impact"]["low"])],
                 [t("estado_nuevo"), v(m["by_state"]["new"])], [t("estado_en_curso"), v(m["by_state"]["in_progress"])],
                 [t("estado_resuelto"), v(m["by_state"]["resolved"])], [t("estado_aceptado"), v(m["by_state"]["accepted"])]]
        story += [Paragraph(t("metricas"), styles["section"]), _tabla(filas, [9 * cm, 6 * cm], styles)]
        top = hallazgos(db, org_id, por_pagina=20)["items"]
        if top:
            filas = [[t("aviso"), t("severidad"), t("software"), t("maquina"), t("riesgo")]]
            filas += [[h.get("vuln_id") or "-", h.get("severity") or "-",
                       f"{h.get('product_name') or '-'} {h.get('affected_version') or ''}"[:40],
                       (h.get("ci_name") or "-")[:25], f"{h.get('risk_points') or 0:.0f}"] for h in top]
            story += [Paragraph(t("top_hallazgos"), styles["section"]),
                      _tabla(filas, [3.5 * cm, 2 * cm, 5 * cm, 3.5 * cm, 1.5 * cm], styles)]
    return story
