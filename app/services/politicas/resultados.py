"""Resultados graduados y su combinación determinista.

Tipos (`{"tipo": …}` más sus datos):

- `allow`: no hace nada (útil con «detener»).
- `auto_approve`: se aprueba sin revisión humana… si nada más lo impide.
- `warn` {mensaje}: se envía marcado.
- `require_justification` {mensaje}: hay que explicar el porqué.
- `require_attachment` {tipos_de_documento: [...], mensaje}: hay que adjuntar.
- `add_approval_levels` {niveles: n} o {pasos: [paso, …]}: más aprobación.
  Un nivel es el siguiente responsable en la cadena de quien pide.
  Un paso: {nombre, approver_type (role|user|manager|manager_level|
  any_in_department|group), approver_role, approver_user_id,
  approver_department, approver_group_id, approver_level, required_approvals}.
- `notify` {destinatarios: [{tipo: persona|rol|responsable|grupo|departamento|
  solicitante, valor}], canales: [app|email|canal], mensaje}.
- `block` {mensaje}: no se puede enviar. SOLO si se configura explícitamente.
- `set_field` {campo, valor}: fija un campo asignable del dominio.
- `tag` {etiqueta}.

Combinación (la misma entrada da siempre la misma salida):

1. `block` manda: decisión `block`; los demás resultados se conservan en la
   explicación pero no se aplican.
2. Niveles de aprobación: el MÁXIMO de `niveles` de todas las reglas (no la
   suma: dos reglas que piden «+1» piden lo mismo); los `pasos` concretos se
   unen sin repetir aprobador, en orden de prioridad de la política y de la
   regla.
3. Requisitos (`require_*`), avisos y etiquetas: la unión.
4. `notify`: la unión de destinatarios y de canales, por mensaje.
5. `set_field` sobre el mismo campo: gana la política de mayor prioridad y,
   dentro de ella, la regla de menor orden.
6. `auto_approve` solo si no hay bloqueo, ni niveles añadidos, ni avisos, ni
   requisitos. Decisión final: block > review > auto_approve > allow
   (`review` = hay que pasar por el flujo de aprobación).
"""
from __future__ import annotations

TIPOS = ("allow", "auto_approve", "warn", "require_justification", "require_attachment",
         "add_approval_levels", "notify", "block", "set_field", "tag")
TIPOS_DE_APROBADOR = ("role", "user", "manager", "manager_level", "any_in_department", "group")
DESTINATARIOS = ("persona", "rol", "responsable", "grupo", "departamento", "solicitante")
CANALES = ("app", "email", "canal")
MAX_NIVELES = 10


def validar(dominio, resultados: list, ruta: str, errores: list, tipos_de_documento: list[str]) -> None:
    for i, r in enumerate(resultados or []):
        donde = f"{ruta}[{i}]"
        t = (r or {}).get("tipo")
        if t not in TIPOS:
            errores.append({"ruta": donde, "mensaje": f"resultado desconocido: {t}"})
            continue
        if t == "add_approval_levels":
            n, pasos = r.get("niveles"), r.get("pasos") or []
            if not n and not pasos:
                errores.append({"ruta": donde, "mensaje": "indica cuántos niveles o qué pasos se añaden"})
            if n and not (1 <= int(n) <= MAX_NIVELES):
                errores.append({"ruta": donde, "mensaje": f"entre 1 y {MAX_NIVELES} niveles"})
            for j, p in enumerate(pasos):
                if p.get("approver_type") not in TIPOS_DE_APROBADOR:
                    errores.append({"ruta": f"{donde}.pasos[{j}]", "mensaje": "elige quién aprueba"})
                faltan = {"role": "approver_role", "user": "approver_user_id", "group": "approver_group_id",
                          "any_in_department": "approver_department", "manager_level": "approver_level"}
                clave = faltan.get(p.get("approver_type"))
                if clave and not p.get(clave):
                    errores.append({"ruta": f"{donde}.pasos[{j}]", "mensaje": "falta el aprobador"})
        elif t == "notify":
            if not r.get("destinatarios"):
                errores.append({"ruta": donde, "mensaje": "elige a quién se avisa"})
            if any(d.get("tipo") not in DESTINATARIOS for d in r.get("destinatarios") or []):
                errores.append({"ruta": donde, "mensaje": "destinatario desconocido"})
            if not r.get("canales") or any(c not in CANALES for c in r.get("canales")):
                errores.append({"ruta": donde, "mensaje": "elige al menos un canal válido"})
        elif t == "require_attachment":
            malos = [x for x in r.get("tipos_de_documento") or [] if x not in tipos_de_documento]
            if malos:
                errores.append({"ruta": donde, "mensaje": f"tipo de documento no configurado: {malos}"})
        elif t == "set_field":
            campo = dominio.campo(r.get("campo") or "")
            if campo is None or not campo.asignable:
                errores.append({"ruta": donde, "mensaje": "ese campo no se puede fijar desde una política"})
        elif t == "tag" and not (r.get("etiqueta") or "").strip():
            errores.append({"ruta": donde, "mensaje": "escribe la etiqueta"})
        elif t == "block" and not (r.get("mensaje") or "").strip():
            errores.append({"ruta": donde, "mensaje": "un bloqueo necesita el mensaje que verá el usuario"})


def _clave_de_paso(p: dict) -> tuple:
    return (p.get("approver_type"), p.get("approver_role"), p.get("approver_user_id"),
            p.get("approver_department"), p.get("approver_group_id"), p.get("approver_level"))


def combinar(aplicados: list[tuple[dict, dict]]) -> dict:
    """`aplicados`: [(origen, resultado)], ya en orden de prioridad (política
    de mayor prioridad primero, reglas por orden). `origen` = {politica_id,
    politica, regla_id, regla}. Devuelve el resultado combinado."""
    salida = {"decision": "allow", "bloqueos": [], "avisos": [], "requisitos": [], "niveles": 0,
              "pasos": [], "avisar": [], "campos": {}, "etiquetas": [], "auto_aprobar": False, "origenes": {}}
    vistos_pasos: set = set()
    vistas_req: set = set()
    auto = False
    for origen, r in aplicados:
        t = r.get("tipo")
        o = {k: origen.get(k) for k in ("politica_id", "politica", "regla_id", "regla")}
        if t == "block":
            salida["bloqueos"].append({"mensaje": r.get("mensaje"), **o})
        elif t == "warn":
            salida["avisos"].append({"mensaje": r.get("mensaje"), **o})
        elif t in ("require_justification", "require_attachment"):
            clave = (t, tuple(sorted(r.get("tipos_de_documento") or [])))
            if clave not in vistas_req:
                vistas_req.add(clave)
                salida["requisitos"].append({"tipo": t, "tipos_de_documento": list(clave[1]),
                                             "mensaje": r.get("mensaje"), **o})
        elif t == "add_approval_levels":
            if r.get("niveles"):
                if int(r["niveles"]) > salida["niveles"]:
                    salida["niveles"] = int(r["niveles"])
                    salida["origenes"]["niveles"] = o
            for p in r.get("pasos") or []:
                if _clave_de_paso(p) not in vistos_pasos:
                    vistos_pasos.add(_clave_de_paso(p))
                    salida["pasos"].append({**p, "origen": o})
        elif t == "notify":
            salida["avisar"].append({"destinatarios": r.get("destinatarios") or [],
                                     "canales": sorted(set(r.get("canales") or ["app"])),
                                     "mensaje": r.get("mensaje"), **o})
        elif t == "set_field":
            # El primero que llega es el de mayor prioridad: gana.
            salida["campos"].setdefault(r.get("campo"), {"valor": r.get("valor"), **o})
        elif t == "tag":
            e = (r.get("etiqueta") or "").strip()
            if e and e not in salida["etiquetas"]:
                salida["etiquetas"].append(e)
        elif t == "auto_approve":
            auto = True
    if salida["bloqueos"]:
        salida["decision"] = "block"
    elif salida["niveles"] or salida["pasos"] or salida["avisos"] or salida["requisitos"]:
        salida["decision"] = "review"
    elif auto:
        salida["decision"] = "auto_approve"
        salida["auto_aprobar"] = True
    return salida
