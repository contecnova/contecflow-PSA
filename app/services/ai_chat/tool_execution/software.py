"""Herramienta de la CMDB de software para Nexus (19-11-2026).

`search_software_inventory` contesta, con los mismos servicios y la misma
guarda que `GET /cmdb/software/*` (dirección y PM):

- ``where_used``: «¿dónde está nginx?», «¿qué usa php < 8.2?»;
- ``findings``: vulnerabilidades abiertas (por software, máquina, severidad o KEV);
- ``eol``: software sin soporte o en fin de vida;
- ``machine``: qué corre en una máquina (por nombre, hostname o IP);
- ``impact``: qué software, máquinas, servicios y clientes afecta un CVE;
- ``summary``: cuadro de mando.

Solo lectura; los resultados se recortan para el contexto del modelo.
"""
from __future__ import annotations

from app.services.ai_chat.tool_execution.textos import mensaje as _msg


def _search_software_inventory(tool_input, db, user, now, is_financial_role):
    from app.services.cmdb_software import analisis, gestion
    from app.services.cmdb_software.importacion import buscar_ci
    org = getattr(user, "organization_id", None)
    modo = (tool_input.get("mode") or "where_used").strip()
    consulta = (tool_input.get("query") or "").strip()
    limite = min(int(tool_input.get("limit") or 25), 100)
    if modo == "summary":
        return {"summary": analisis.cuadro_de_mando(db, org)}
    if modo == "where_used":
        if not consulta:
            return {"error": _msg(db, user, "software_indica")}
        r = analisis.donde_se_usa(db, org, consulta)
        return {"products": r["products"][:10], "summary": r["summary"], "versions": r["versions"],
                "instances": [{k: i.get(k) for k in ("product_name", "version", "ci_name", "ci_hostname", "ci_ip",
                                                      "environment", "install_path", "config_path", "ports",
                                                      "config_summary", "lifecycle", "open_findings")}
                              for i in r["instances"][:limite]],
                "software": [{"product": s["product_name"], "version": s["version"],
                              "components": [f"{c['name']} {c['version'] or ''}".strip() for c in s["components"][:5]],
                              "machines": [m.get("name") for m in s["machines"][:10]]} for s in r["software"][:limite]]}
    if modo == "findings":
        ci_id = None
        if tool_input.get("machine"):
            ci = buscar_ci(db, org, tool_input["machine"])
            if ci is None:
                return {"error": _msg(db, user, "maquina_no_encontrada", nombre=tool_input['machine'])}
            ci_id = ci.id
        r = gestion.listar(db, org, "live", tool_input.get("severity"), None, ci_id, tool_input.get("kev"),
                           tool_input.get("out_of_sla"), consulta or None, None, 1, limite)
        return {"total": r["total"], "findings": [{k: f.get(k) for k in (
            "vuln_id", "title", "severity", "priority_score", "kev", "product_name", "affected_version",
            "fixed_version", "parent_product_name", "parent_version", "ci_name", "environment", "status",
            "sla_due_at", "sla_breached")} for f in r["items"]]}
    if modo == "eol":
        r = analisis.fin_de_vida(db, org, tool_input.get("days"), bool(tool_input.get("prod_only")))
        return {"summary": r["summary"],
                "instances": [{k: i.get(k) for k in ("product_name", "version", "ci_name", "environment", "lifecycle",
                                                      "eol_date", "support_end")} for i in r["instances"][:limite]],
                "components": r["components"][:limite]}
    if modo == "machine":
        ci = buscar_ci(db, org, consulta or tool_input.get("machine"))
        if ci is None:
            return {"error": _msg(db, user, "maquina_no_encontrada", nombre=consulta)}
        r = analisis.maquina(db, org, ci.id)
        return {"ci": r["ci"], "findings_by_severity": r["findings_by_severity"], "assets": r["assets"],
                "licenses": r["licenses"], "open_tickets": r["open_tickets"],
                "software": [{k: i.get(k) for k in ("product_name", "version", "environment", "status", "ports",
                                                     "config", "lifecycle", "open_findings", "baseline_violations",
                                                     "drift_detected_at")} for i in r["instances"][:limite]]}
    if modo == "impact":
        from app.models.cmdb_software import Vulnerability
        from sqlalchemy import or_
        v = db.query(Vulnerability).filter(Vulnerability.organization_id == org, or_(
            Vulnerability.vuln_id == consulta, Vulnerability.aliases.ilike(f'%"{consulta}"%'))).first()
        if v is None:
            return {"error": _msg(db, user, "aviso_no_registrado", nombre=consulta)}
        r = analisis.impacto(db, org, vulnerability_id=v.id)
        return {"vulnerability": {"id": v.vuln_id, "severity": v.severity, "cvss": v.cvss_score, "kev": v.kev,
                                  "title": v.title}, "summary": r["summary"],
                "software": r["software"][:limite], "machines": r["machines"][:limite],
                "services": r["services"][:limite], "clients": r["clients"][:limite], "owners": r["owners"]}
    return {"error": _msg(db, user, "modo_desconocido", modo=modo)}


HANDLERS = {"search_software_inventory": _search_software_inventory}
