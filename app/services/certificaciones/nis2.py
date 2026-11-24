"""Certificaciones: obligaciones regulatorias NIS2 (§3.8).

Incidente notificable (Directiva (UE) 2022/2555, art. 23) enlazado a un ticket
del Service Desk, con tres relojes desde que se tuvo conocimiento
(`detectado_en`), configurables por empresa:

- alerta temprana: 24 h;
- notificación del incidente: 72 h;
- informe final: 1 mes desde la notificación (o desde el plazo de la
  notificación si aún no se ha enviado).

Cada reloj: `cumplido` (enviado a tiempo), `tarde` (enviado fuera de plazo),
`pendiente` o `vencido`. Registrar una comunicación (`comunicar`) con su tipo
para el reloj y avanza el estado. Plantillas de notificación a la autoridad
(CSIRT o autoridad competente) en es/en/zh (`textos_de_salida_certificaciones`).
Avisos del reloj (6 h antes y al vencer, una vez cada uno): `trabajos.relojes_nis2`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.certificaciones import CertComunicacion, CertIncidente, CertPrograma
from app.services.certificaciones.comun import (
    ahora, auditar, aware, config, elegir, fecha_hora, iso, json_de, nombre_de, org_de, propio, siguiente_codigo,
    usuario_de_la_empresa,
)

ESTADOS = ("abierto", "alerta_enviada", "notificado", "informe_final", "cerrado", "descartado")
TIPOS_COMUNICACION = ("alerta_temprana", "notificacion", "informe_intermedio", "informe_final", "otra")
RELOJES = ("alerta", "notificacion", "informe_final")
_CAMPO = {"alerta_temprana": "alerta_enviada_en", "notificacion": "notificacion_enviada_en",
          "informe_final": "informe_final_enviado_en"}
_ESTADO_TRAS = {"alerta_temprana": "alerta_enviada", "notificacion": "notificado", "informe_final": "informe_final"}


def plazos(inc: CertIncidente, cfg) -> dict[str, datetime]:
    base = aware(inc.detectado_en)
    alerta = base + timedelta(hours=int(cfg.nis2_alerta_horas or 24))
    notificacion = base + timedelta(hours=int(cfg.nis2_notificacion_horas or 72))
    informe = (aware(inc.notificacion_enviada_en) or notificacion) + timedelta(days=int(cfg.nis2_informe_final_dias
                                                                                       or 30))
    return {"alerta": alerta, "notificacion": notificacion, "informe_final": informe}


def relojes(inc: CertIncidente, cfg, momento: Optional[datetime] = None) -> dict[str, dict]:
    """Estado de cada reloj: plazo, enviado, estado y segundos que quedan (negativo si vencido)."""
    momento = momento or ahora()
    enviados = {"alerta": aware(inc.alerta_enviada_en), "notificacion": aware(inc.notificacion_enviada_en),
                "informe_final": aware(inc.informe_final_enviado_en)}
    salida = {}
    for clave, plazo in plazos(inc, cfg).items():
        enviado = enviados[clave]
        if not inc.significativo or inc.estado == "descartado":
            estado = "no_aplica"
        elif enviado is not None:
            estado = "cumplido" if enviado <= plazo else "tarde"
        else:
            estado = "vencido" if momento > plazo else "pendiente"
        salida[clave] = {"plazo": iso(plazo), "enviado": iso(enviado), "estado": estado,
                         "segundos_restantes": int((plazo - momento).total_seconds()) if enviado is None else None}
    return salida


def serializar(db: Session, inc: CertIncidente, detalle: bool = False) -> dict:
    cfg = config(db, inc.organization_id)
    ticket = None
    if inc.ticket_id:
        from app.models.service_desk.tickets import Ticket
        t = db.get(Ticket, inc.ticket_id)
        if t is not None:
            ticket = {"id": t.id, "number": t.number, "title": t.title}
    d = {"id": inc.id, "codigo": inc.codigo, "titulo": inc.titulo, "descripcion": inc.descripcion,
         "programa_id": inc.programa_id, "ticket": ticket, "detectado_en": iso(inc.detectado_en),
         "significativo": inc.significativo, "transfronterizo": inc.transfronterizo, "impacto": inc.impacto,
         "estado": inc.estado, "autoridad": inc.autoridad or cfg.autoridad_nis2,
         "responsable_id": inc.responsable_id, "responsable": nombre_de(db, inc.responsable_id),
         "relojes": relojes(inc, cfg), "cerrado_en": iso(inc.cerrado_en)}
    if detalle:
        d["comunicaciones"] = [{"id": c.id, "tipo": c.tipo, "destinatario": c.destinatario, "asunto": c.asunto,
                                "contenido": c.contenido, "referencia": c.referencia, "enviado_en": iso(c.enviado_en),
                                "enviado_por": nombre_de(db, c.enviado_por)}
                               for c in db.query(CertComunicacion).filter(CertComunicacion.incidente_id == inc.id)
                               .order_by(CertComunicacion.enviado_en).all()]
    return d


def listar(db: Session, usuario, solo_abiertos: bool = False) -> list[dict]:
    org = org_de(usuario)
    q = db.query(CertIncidente).filter(CertIncidente.organization_id == org)
    if solo_abiertos:
        q = q.filter(CertIncidente.estado.notin_(("cerrado", "descartado")))
    return [serializar(db, i) for i in q.order_by(CertIncidente.detectado_en.desc()).all()]


def _ticket(db: Session, org: str, ref: Optional[str]):
    if not ref:
        return None
    from app.models.service_desk.tickets import Ticket
    t = db.query(Ticket).filter(Ticket.organization_id == org, (Ticket.id == ref) | (Ticket.number == ref)).first()
    if t is None:
        raise error(422, "cert_campo_no_valido", campo="ticket")
    return t


def crear(db: Session, usuario, datos: dict) -> dict:
    org = org_de(usuario)
    t = _ticket(db, org, datos.get("ticket"))
    titulo = (datos.get("titulo") or (t.title if t else "") or "").strip()
    if not titulo:
        raise error(422, "cert_campo_no_valido", campo="titulo")
    detectado = fecha_hora(datos.get("detectado_en"), "detectado_en") or (aware(t.created_at) if t else None) \
        or ahora()
    if detectado > ahora() + timedelta(minutes=5):
        raise error(422, "cert_campo_no_valido", campo="detectado_en")
    programa_id = propio(db, CertPrograma, datos["programa_id"], usuario, "programa_de_certificacion").id \
        if datos.get("programa_id") else None
    inc = CertIncidente(organization_id=org, programa_id=programa_id, ticket_id=t.id if t else None,
                        codigo=siguiente_codigo(db, CertIncidente, org, "NIS2"), titulo=titulo[:300],
                        descripcion=datos.get("descripcion"), detectado_en=detectado,
                        significativo=bool(datos.get("significativo", True)),
                        transfronterizo=bool(datos.get("transfronterizo", False)), impacto=datos.get("impacto"),
                        estado="abierto", autoridad=datos.get("autoridad") or config(db, org).autoridad_nis2,
                        responsable_id=usuario_de_la_empresa(db, org, datos.get("responsable_id"), "responsable_id")
                        or usuario.id, creado_por=usuario.id)
    db.add(inc)
    db.flush()
    auditar(db, usuario, "CREATE", "incidente_nis2", inc.id, inc.codigo,
            despues={"ticket_id": inc.ticket_id, "detectado_en": iso(detectado), "significativo": inc.significativo})
    db.commit()
    return serializar(db, inc, True)


def editar(db: Session, usuario, incidente_id: str, datos: dict) -> dict:
    inc = propio(db, CertIncidente, incidente_id, usuario, "incidente_nis2")
    antes = {"estado": inc.estado, "significativo": inc.significativo, "detectado_en": iso(inc.detectado_en)}
    for k in ("titulo", "descripcion", "impacto", "autoridad"):
        if k in datos and datos[k] is not None:
            setattr(inc, k, datos[k])
    for k in ("significativo", "transfronterizo"):
        if k in datos and datos[k] is not None:
            setattr(inc, k, bool(datos[k]))
    if "detectado_en" in datos and datos["detectado_en"]:
        inc.detectado_en = fecha_hora(datos["detectado_en"], "detectado_en")
    if "responsable_id" in datos:
        inc.responsable_id = usuario_de_la_empresa(db, inc.organization_id, datos["responsable_id"], "responsable_id")
    if "estado" in datos and datos["estado"]:
        inc.estado = elegir(datos["estado"], ESTADOS, "estado")
        inc.cerrado_en = ahora() if inc.estado in ("cerrado", "descartado") else None
    auditar(db, usuario, "UPDATE", "incidente_nis2", inc.id, inc.codigo, antes=antes,
            despues={"estado": inc.estado, "significativo": inc.significativo, "detectado_en": iso(inc.detectado_en)})
    db.commit()
    return serializar(db, inc, True)


def comunicar(db: Session, usuario, incidente_id: str, datos: dict) -> dict:
    """Registra lo enviado a la autoridad (o a los destinatarios) y para su reloj."""
    inc = propio(db, CertIncidente, incidente_id, usuario, "incidente_nis2")
    tipo = elegir(datos.get("tipo"), TIPOS_COMUNICACION, "tipo")
    if tipo == "notificacion" and inc.alerta_enviada_en is None and inc.significativo:
        # La notificación de 72 h incluye la alerta si no se envió antes (art. 23.4.b actualiza la alerta).
        inc.alerta_enviada_en = fecha_hora(datos.get("enviado_en"), "enviado_en") or ahora()
    if tipo == "informe_final" and inc.notificacion_enviada_en is None:
        raise error(409, "cert_nis2_informe_sin_notificacion")
    enviado = fecha_hora(datos.get("enviado_en"), "enviado_en") or ahora()
    c = CertComunicacion(organization_id=inc.organization_id, incidente_id=inc.id, tipo=tipo,
                         destinatario=datos.get("destinatario") or inc.autoridad, asunto=datos.get("asunto"),
                         contenido=datos.get("contenido"), referencia=datos.get("referencia"), enviado_en=enviado,
                         enviado_por=usuario.id)
    db.add(c)
    campo = _CAMPO.get(tipo)
    if campo and getattr(inc, campo) is None:
        setattr(inc, campo, enviado)
    if tipo in _ESTADO_TRAS and ESTADOS.index(_ESTADO_TRAS[tipo]) > ESTADOS.index(inc.estado):
        inc.estado = _ESTADO_TRAS[tipo]
    db.flush()
    auditar(db, usuario, "NOTIFY", "incidente_nis2", inc.id, inc.codigo,
            despues={"tipo": tipo, "enviado_en": iso(enviado), "destinatario": c.destinatario,
                     "referencia": c.referencia})
    db.commit()
    return serializar(db, inc, True)


def plantilla(db: Session, usuario, incidente_id: str, tipo: str, idioma: Optional[str] = None) -> dict:
    """Texto propuesto para la comunicación `tipo` a la autoridad, con los datos del incidente."""
    from app.services.textos_de_salida import texto
    inc = propio(db, CertIncidente, incidente_id, usuario, "incidente_nis2")
    elegir(tipo, TIPOS_COMUNICACION, "tipo")
    if tipo == "otra":
        tipo = "informe_intermedio"
    rel = relojes(inc, config(db, inc.organization_id))
    params = {"codigo": inc.codigo, "titulo": inc.titulo, "detectado": iso(inc.detectado_en),
              "autoridad": inc.autoridad or config(db, inc.organization_id).autoridad_nis2 or "—",
              "impacto": inc.impacto or "—", "transfronterizo": "sí" if inc.transfronterizo else "no",
              "descripcion": inc.descripcion or "—", "plazo": rel.get(
                  {"alerta_temprana": "alerta", "notificacion": "notificacion"}.get(tipo, "informe_final"), {}
              ).get("plazo") or "—"}
    return {"tipo": tipo, "asunto": texto(f"cert.nis2.{tipo}.asunto", idioma, **params),
            "contenido": texto(f"cert.nis2.{tipo}.contenido", idioma, **params)}


def avisos_enviados(inc: CertIncidente) -> dict:
    return json_de(inc.avisos, {})
