"""Altas, cambios, versiones y validación de políticas y tablas de referencia.

Ciclo de vida de una política (todas sus versiones comparten `familia_id`):

    borrador ──publicar──▶ publicada ──(se publica otra versión)──▶ retirada
       ▲                       │
       └─── nueva versión ─────┘   (copia la publicada como borrador v+1)

Solo los borradores se editan. Publicar retira la versión publicada anterior
de la familia. «Borrar» un borrador lo elimina; «borrar» una publicada la
retira (queda en el historial). `activa` apaga una versión publicada sin
crear otra.

Todas las funciones confirman (`commit`) lo que escriben e invalidan la caché
del motor de su empresa y dominio.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.politicas import (EvaluacionDePolitica, FilaDeTablaDeReferencia, Politica, ReglaDePolitica,
                                  TablaDeReferencia)
from app.services.politicas import catalogo, motor, resultados as res
from app.services.politicas.condiciones import validar_arbol

AMBITO_CLAVES = ("departamentos", "equipos", "roles", "ubicaciones", "personas",
                 # Rev. 180: grupos y excepciones (personas o grupos que quedan fuera).
                 "grupos", "excepto_personas", "excepto_grupos")
MAX_REGLAS = 200
MAX_FILAS = 5000


def _org(usuario) -> Optional[str]:
    return getattr(usuario, "organization_id", None)


def _fecha(v) -> Optional[date]:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ErrorDeDominio(422, f"Fecha no válida: {v}")


def _dump(v) -> Optional[str]:
    return None if v in (None, "", [], {}) else json.dumps(v, ensure_ascii=False)


def _load(v, defecto):
    return motor._json(v, defecto)


def guardar_tipos_de_documento(db: Session, usuario, tipos: list[str]) -> list[str]:
    """Rev. 166 (#27): la lista de `POLICY_DOCUMENT_TYPES` de la empresa, editada en pantalla.

    Cada tipo es una clave corta (letras, números, `_`/`-`); la pantalla la
    traduce (`pol.doc_<clave>`) o la enseña tal cual. No se puede quitar uno
    que use una política vigente o un justificante.
    """
    import re
    from app.models.expenses import ExpenseAttachment
    from app.services import settings_service as s
    limpios = list(dict.fromkeys(str(t).strip().lower() for t in tipos or [] if str(t).strip()))
    malos = [t for t in limpios if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", t)]
    if malos:
        raise ErrorDeDominio(422, f"Tipo de documento no válido (letras, números, _ o -): {malos}")
    if not limpios:
        raise ErrorDeDominio(422, "Hace falta al menos un tipo de documento")
    quitados = set(tipos_de_documento(db, _org(usuario))) - set(limpios)
    en_uso = set()
    for p in db.query(Politica).filter(Politica.estado != "retirada").all():
        texto = json.dumps([regla_dict(r) for r in p.reglas])
        en_uso |= {t for t in quitados if f'"{t}"' in texto}
    en_uso |= {t for (t,) in db.query(ExpenseAttachment.document_type)
               .filter(ExpenseAttachment.document_type.in_(quitados or [""])).distinct()}
    if en_uso:
        raise ErrorDeDominio(409, f"Están en uso (políticas o justificantes): {sorted(en_uso)}")
    s.set_runtime_value(db, "politicas", "POLICY_DOCUMENT_TYPES", ",".join(limpios), _org(usuario),
                        actor_id=usuario.id)
    db.commit()
    return limpios


def tipos_de_documento(db: Session, org) -> list[str]:
    from app.services import settings_service as s
    crudo = s.get_runtime_str(db, "POLICY_DOCUMENT_TYPES", org) or ""
    return [x.strip() for x in crudo.split(",") if x.strip()]


def tipos_de_documento_de(db: Session, dominio, org) -> list[str]:
    """Los del dominio si los declara (ausencias: su catálogo), si no los de `POLICY_DOCUMENT_TYPES`."""
    if dominio.tipos_de_documento is not None:
        return [o.valor for o in dominio.tipos_de_documento(db)]
    return tipos_de_documento(db, org)


# ── Serialización ────────────────────────────────────────────────────────────

def regla_dict(r: ReglaDePolitica) -> dict:
    return {"id": r.id, "orden": r.orden, "nombre": r.nombre, "activa": bool(r.activa), "detener": bool(r.detener),
            "condicion": _load(r.condicion, None), "resultados": _load(r.resultados, []),
            "exceso": _load(r.exceso, None)}


def politica_dict(p: Politica, con_reglas: bool = True) -> dict:
    d = {"id": p.id, "familia_id": p.familia_id, "version": p.version, "estado": p.estado, "dominio": p.dominio,
         "nombre": p.nombre, "descripcion": p.descripcion, "prioridad": p.prioridad, "activa": bool(p.activa),
         "vigente_desde": p.vigente_desde.isoformat() if p.vigente_desde else None,
         "vigente_hasta": p.vigente_hasta.isoformat() if p.vigente_hasta else None,
         "ambito": {k: (_load(p.ambito, {}) or {}).get(k) or [] for k in AMBITO_CLAVES},
         "nota_de_version": p.nota_de_version, "created_by": p.created_by,
         "publicada_por": p.publicada_por, "publicada_en": p.publicada_en.isoformat() if p.publicada_en else None,
         "created_at": p.created_at.isoformat() if p.created_at else None,
         "updated_at": p.updated_at.isoformat() if p.updated_at else None,
         "n_reglas": len(p.reglas or [])}
    if con_reglas:
        d["reglas"] = [regla_dict(r) for r in sorted(p.reglas or [], key=lambda r: r.orden)]
    return d


# ── Validación ───────────────────────────────────────────────────────────────

def validar(db: Session, usuario, doc: dict) -> list[dict]:
    """Errores del documento de una política, cada uno con su `ruta` (la pantalla los señala)."""
    errores: list[dict] = []
    try:
        dominio = catalogo.dominio(doc.get("dominio") or "")
    except ErrorDeDominio:
        return [{"ruta": "dominio", "mensaje": "elige un dominio"}]
    if not (doc.get("nombre") or "").strip():
        errores.append({"ruta": "nombre", "mensaje": "la política necesita nombre"})
    desde, hasta = _fecha(doc.get("vigente_desde")), _fecha(doc.get("vigente_hasta"))
    if desde and hasta and hasta < desde:
        errores.append({"ruta": "vigente_hasta", "mensaje": "la vigencia termina antes de empezar"})
    for u in (doc.get("ambito") or {}).get("ubicaciones") or []:
        if len(str(u).split("/", 1)[0]) != 2:
            errores.append({"ruta": "ambito.ubicaciones", "mensaje": f"ubicación no válida: {u}"})
    reglas = doc.get("reglas") or []
    if len(reglas) > MAX_REGLAS:
        errores.append({"ruta": "reglas", "mensaje": f"máximo {MAX_REGLAS} reglas"})
    tipos_doc = tipos_de_documento_de(db, dominio, _org(usuario))
    tablas = {t.id for t in db.query(TablaDeReferencia.id).all()}
    for i, r in enumerate(reglas):
        ruta = f"reglas[{i}]"
        if not (r.get("nombre") or "").strip():
            errores.append({"ruta": f"{ruta}.nombre", "mensaje": "la regla necesita nombre"})
        validar_arbol(dominio, r.get("condicion"), f"{ruta}.condicion", errores)
        res.validar(dominio, r.get("resultados") or [], f"{ruta}.resultados", errores, tipos_doc)
        exc = r.get("exceso")
        if exc and exc.get("campo"):
            campo = dominio.campo(exc["campo"])
            if campo is None or campo.tipo not in ("importe", "numero"):
                errores.append({"ruta": f"{ruta}.exceso.campo", "mensaje": "el exceso se mide sobre un importe o un número"})
            ref = exc.get("referencia") or {}
            if ref.get("tipo") not in ("valor", "campo", "tabla"):
                errores.append({"ruta": f"{ruta}.exceso.referencia", "mensaje": "elige la referencia del exceso"})
            if ref.get("tipo") == "tabla" and ref.get("tabla_id") not in tablas:
                errores.append({"ruta": f"{ruta}.exceso.referencia", "mensaje": "esa tabla de referencia no existe"})
            previo = None
            bandas = sorted(exc.get("bandas") or [], key=lambda b: float(b.get("desde") or 0))
            if not bandas:
                errores.append({"ruta": f"{ruta}.exceso.bandas", "mensaje": "añade al menos una banda"})
            for j, b in enumerate(bandas):
                d0 = float(b.get("desde") or 0)
                h0 = b.get("hasta")
                if d0 < 0 or (h0 not in (None, "") and float(h0) <= d0):
                    errores.append({"ruta": f"{ruta}.exceso.bandas[{j}]", "mensaje": "la banda debe ir de menos a más"})
                if previo is not None and (previo in (None, "") or d0 < float(previo)):
                    errores.append({"ruta": f"{ruta}.exceso.bandas[{j}]", "mensaje": "las bandas se solapan"})
                previo = h0
                res.validar(dominio, b.get("resultados") or [], f"{ruta}.exceso.bandas[{j}].resultados", errores, tipos_doc)
        _tablas_de_arbol(r.get("condicion"), tablas, f"{ruta}.condicion", errores)
    return errores


def _tablas_de_arbol(nodo, existentes: set, ruta: str, errores: list) -> None:
    if not isinstance(nodo, dict):
        return
    ref = nodo.get("referencia") or {}
    if ref.get("tipo") == "tabla" and ref.get("tabla_id") not in existentes:
        errores.append({"ruta": ruta, "mensaje": "esa tabla de referencia no existe"})
    for i, h in enumerate(nodo.get("hijos") or []):
        _tablas_de_arbol(h, existentes, f"{ruta}.hijos[{i}]", errores)


def _exigir_valida(db, usuario, doc) -> None:
    errores = validar(db, usuario, doc)
    if errores:
        raise ErrorDeDominio(422, {"message": "La política tiene errores", "errors": errores})


# ── Políticas ────────────────────────────────────────────────────────────────

def _politica(db: Session, politica_id: str) -> Politica:
    p = db.query(Politica).filter(Politica.id == politica_id).first()
    if p is None:
        raise ErrorDeDominio(404, "Política no encontrada")
    return p


def listar(db: Session, dominio: Optional[str] = None) -> list[dict]:
    """La última versión de cada política, con la publicada al lado si es otra."""
    q = db.query(Politica)
    if dominio:
        q = q.filter(Politica.dominio == dominio)
    por_familia: dict = {}
    for p in q.order_by(Politica.version).all():
        por_familia.setdefault(p.familia_id, []).append(p)
    salida = []
    for versiones in por_familia.values():
        ultima = versiones[-1]
        pub = next((v for v in versiones if v.estado == "publicada"), None)
        d = politica_dict(ultima, con_reglas=False)
        d["version_publicada"] = pub.version if pub else None
        d["id_publicada"] = pub.id if pub else None
        d["n_versiones"] = len(versiones)
        salida.append(d)
    return sorted(salida, key=lambda d: (d["dominio"], -d["prioridad"], d["nombre"].lower()))


def detalle(db: Session, politica_id: str) -> dict:
    return politica_dict(_politica(db, politica_id))


def _aplicar_doc(p: Politica, doc: dict) -> None:
    p.nombre = doc["nombre"].strip()[:200]
    p.descripcion = doc.get("descripcion")
    p.prioridad = int(doc.get("prioridad") if doc.get("prioridad") is not None else 100)
    p.activa = bool(doc.get("activa", True))
    p.vigente_desde = _fecha(doc.get("vigente_desde"))
    p.vigente_hasta = _fecha(doc.get("vigente_hasta"))
    ambito = {k: list(dict.fromkeys((doc.get("ambito") or {}).get(k) or [])) for k in AMBITO_CLAVES}
    p.ambito = _dump({k: v for k, v in ambito.items() if v})
    p.nota_de_version = (doc.get("nota_de_version") or None)
    p.updated_at = datetime.now(timezone.utc)


def _reglas_desde_doc(p: Politica, doc: dict) -> None:
    p.reglas.clear()
    for i, r in enumerate(doc.get("reglas") or []):
        p.reglas.append(ReglaDePolitica(
            id=str(uuid.uuid4()), organization_id=p.organization_id, orden=i + 1,
            nombre=(r.get("nombre") or "").strip()[:200], activa=bool(r.get("activa", True)),
            detener=bool(r.get("detener")), condicion=_dump(r.get("condicion")),
            resultados=_dump(r.get("resultados") or []), exceso=_dump(r.get("exceso"))))


def crear(db: Session, usuario, doc: dict) -> dict:
    _exigir_valida(db, usuario, doc)
    pid = str(uuid.uuid4())
    p = Politica(id=pid, familia_id=pid, version=1, estado="borrador", dominio=doc["dominio"],
                 organization_id=_org(usuario), created_by=usuario.id, nombre="")
    _aplicar_doc(p, doc)
    db.add(p)
    _reglas_desde_doc(p, doc)
    db.commit()
    motor.invalidar(p.organization_id, p.dominio)
    return detalle(db, p.id)


def guardar(db: Session, usuario, politica_id: str, doc: dict) -> dict:
    """Guarda un BORRADOR completo (cabecera y reglas)."""
    p = _politica(db, politica_id)
    if p.estado != "borrador":
        raise ErrorDeDominio(409, "Solo se edita un borrador: crea una versión nueva")
    doc = {**doc, "dominio": p.dominio}
    _exigir_valida(db, usuario, doc)
    _aplicar_doc(p, doc)
    _reglas_desde_doc(p, doc)
    db.commit()
    motor.invalidar(p.organization_id, p.dominio)
    return detalle(db, p.id)


def publicar(db: Session, usuario, politica_id: str) -> dict:
    p = _politica(db, politica_id)
    if p.estado != "borrador":
        raise ErrorDeDominio(409, "Solo se publica un borrador")
    _exigir_valida(db, usuario, {**politica_dict(p), "dominio": p.dominio})
    ahora = datetime.now(timezone.utc)
    for v in db.query(Politica).filter(Politica.familia_id == p.familia_id, Politica.estado == "publicada").all():
        v.estado = "retirada"
        v.updated_at = ahora
    p.estado, p.publicada_por, p.publicada_en, p.updated_at = "publicada", usuario.id, ahora, ahora
    db.commit()
    motor.invalidar(p.organization_id, p.dominio)
    dominio = catalogo.dominio(p.dominio)
    if dominio.al_publicar is not None:
        dominio.al_publicar(db, politica_dict(p))
    return detalle(db, p.id)


def nueva_version(db: Session, usuario, politica_id: str) -> dict:
    base = _politica(db, politica_id)
    if db.query(Politica.id).filter(Politica.familia_id == base.familia_id, Politica.estado == "borrador").first():
        raise ErrorDeDominio(409, "Ya hay un borrador de esta política: edítalo")
    ultima = max(v for (v,) in db.query(Politica.version).filter(Politica.familia_id == base.familia_id).all())
    nueva = Politica(id=str(uuid.uuid4()), familia_id=base.familia_id, version=ultima + 1, estado="borrador",
                     dominio=base.dominio, organization_id=base.organization_id, created_by=usuario.id, nombre="")
    doc = politica_dict(base)
    doc["nota_de_version"] = None
    _aplicar_doc(nueva, doc)
    db.add(nueva)
    _reglas_desde_doc(nueva, doc)
    db.commit()
    return detalle(db, nueva.id)


def activar(db: Session, usuario, politica_id: str, activa: bool) -> dict:
    p = _politica(db, politica_id)
    p.activa = bool(activa)
    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    motor.invalidar(p.organization_id, p.dominio)
    return detalle(db, p.id)


def borrar(db: Session, usuario, politica_id: str) -> dict:
    """Un borrador se elimina; una versión publicada se retira (queda en el historial)."""
    p = _politica(db, politica_id)
    org, dom = p.organization_id, p.dominio
    if p.estado == "borrador":
        db.delete(p)
        resultado = {"eliminada": True}
    else:
        p.estado = "retirada"
        p.updated_at = datetime.now(timezone.utc)
        resultado = {"retirada": True}
    db.commit()
    motor.invalidar(org, dom)
    return resultado


def historial(db: Session, politica_id: str) -> list[dict]:
    p = _politica(db, politica_id)
    from app.models.user import User
    versiones = db.query(Politica).filter(Politica.familia_id == p.familia_id).order_by(Politica.version.desc()).all()
    ids = {x for v in versiones for x in (v.created_by, v.publicada_por) if x}
    nombres = dict(db.query(User.id, User.full_name).filter(User.id.in_(ids)).all()) if ids else {}
    salida = []
    for v in versiones:
        d = politica_dict(v)
        d["creada_por_nombre"] = nombres.get(v.created_by)
        d["publicada_por_nombre"] = nombres.get(v.publicada_por)
        salida.append(d)
    return salida


# ── Reglas sueltas (la pantalla guarda el borrador entero; esto es para la API) ──

def _borrador_de(db, politica_id) -> Politica:
    p = _politica(db, politica_id)
    if p.estado != "borrador":
        raise ErrorDeDominio(409, "Solo se editan las reglas de un borrador")
    return p


def crear_regla(db: Session, usuario, politica_id: str, regla: dict) -> dict:
    p = _borrador_de(db, politica_id)
    doc = politica_dict(p)
    doc["reglas"].append(regla)
    return guardar(db, usuario, politica_id, doc)


def editar_regla(db: Session, usuario, politica_id: str, regla_id: str, cambios: dict) -> dict:
    p = _borrador_de(db, politica_id)
    doc = politica_dict(p)
    actual = next((r for r in doc["reglas"] if r["id"] == regla_id), None)
    if actual is None:
        raise ErrorDeDominio(404, "Regla no encontrada")
    actual.update({k: v for k, v in cambios.items() if k != "id"})
    return guardar(db, usuario, politica_id, doc)


def borrar_regla(db: Session, usuario, politica_id: str, regla_id: str) -> dict:
    p = _borrador_de(db, politica_id)
    doc = politica_dict(p)
    antes = len(doc["reglas"])
    doc["reglas"] = [r for r in doc["reglas"] if r["id"] != regla_id]
    if len(doc["reglas"]) == antes:
        raise ErrorDeDominio(404, "Regla no encontrada")
    return guardar(db, usuario, politica_id, doc)


# ── Tablas de referencia ─────────────────────────────────────────────────────

def tabla_dict(t: TablaDeReferencia, con_filas: bool = True) -> dict:
    d = {"id": t.id, "nombre": t.nombre, "descripcion": t.descripcion, "dominio": t.dominio,
         "tipo_de_valor": t.tipo_de_valor, "moneda": t.moneda, "uso": t.uso, "n_filas": len(t.filas or []),
         "updated_at": t.updated_at.isoformat() if t.updated_at else None}
    if con_filas:
        d["filas"] = [{"id": f.id, "pais": f.pais, "ciudad": f.ciudad, "categoria": f.categoria, "valor": f.valor,
                       "moneda": f.moneda,
                       "vigente_desde": f.vigente_desde.isoformat() if f.vigente_desde else None,
                       "vigente_hasta": f.vigente_hasta.isoformat() if f.vigente_hasta else None}
                      for f in t.filas or []]
    return d


def _tabla(db, tabla_id) -> TablaDeReferencia:
    t = db.query(TablaDeReferencia).filter(TablaDeReferencia.id == tabla_id).first()
    if t is None:
        raise ErrorDeDominio(404, "Tabla de referencia no encontrada")
    return t


def tablas(db: Session) -> list[dict]:
    return [tabla_dict(t, con_filas=False) for t in db.query(TablaDeReferencia).order_by(TablaDeReferencia.nombre).all()]


def tabla(db: Session, tabla_id: str) -> dict:
    return tabla_dict(_tabla(db, tabla_id))


def _cabecera_de_tabla(t: TablaDeReferencia, datos: dict) -> None:
    if not (datos.get("nombre") or "").strip():
        raise ErrorDeDominio(422, "La tabla necesita nombre")
    if datos.get("tipo_de_valor", t.tipo_de_valor or "importe") not in ("importe", "numero"):
        raise ErrorDeDominio(422, "Tipo de valor: importe o número")
    if datos.get("dominio"):
        catalogo.dominio(datos["dominio"])
    t.nombre = datos["nombre"].strip()[:200]
    t.descripcion = datos.get("descripcion")
    t.dominio = datos.get("dominio") or None
    t.tipo_de_valor = datos.get("tipo_de_valor") or t.tipo_de_valor or "importe"
    t.moneda = (datos.get("moneda") or "").upper()[:3] or None
    # Rev. 166 (#27): un uso del dominio además de las reglas (gastos: kilometraje).
    uso = datos.get("uso") or None
    if uso:
        usos = {o.valor for o in catalogo.dominio(t.dominio).usos_de_tabla} if t.dominio else set()
        if uso not in usos:
            raise ErrorDeDominio(422, "Ese uso no existe en el dominio de la tabla")
    t.uso = uso
    t.updated_at = datetime.now(timezone.utc)


def crear_tabla(db: Session, usuario, datos: dict) -> dict:
    t = TablaDeReferencia(id=str(uuid.uuid4()), organization_id=_org(usuario), created_by=usuario.id)
    _cabecera_de_tabla(t, datos)
    db.add(t)
    db.commit()
    return tabla(db, t.id)


def editar_tabla(db: Session, usuario, tabla_id: str, datos: dict) -> dict:
    t = _tabla(db, tabla_id)
    _cabecera_de_tabla(t, {**tabla_dict(t, False), **datos})
    db.commit()
    motor.invalidar(t.organization_id)
    return tabla(db, t.id)


def borrar_tabla(db: Session, usuario, tabla_id: str) -> None:
    t = _tabla(db, tabla_id)
    en_uso = [p.nombre for p in db.query(Politica).filter(Politica.estado != "retirada").all()
              if tabla_id in json.dumps([regla_dict(r) for r in p.reglas])]
    if en_uso:
        raise ErrorDeDominio(409, "La usan estas políticas: " + ", ".join(sorted(set(en_uso))))
    org = t.organization_id
    db.delete(t)
    db.commit()
    motor.invalidar(org)


def validar_filas(t: TablaDeReferencia, filas: list[dict]) -> tuple[list[dict], list[dict]]:
    """(filas normalizadas, errores con su fila). Sin duplicados de (país, ciudad, categoría, desde)."""
    limpias, errores, vistas = [], [], set()
    if len(filas) > MAX_FILAS:
        return [], [{"fila": None, "mensaje": f"máximo {MAX_FILAS} filas"}]
    for i, f in enumerate(filas):
        pais = (f.get("pais") or "").strip().upper() or None
        ciudad = (f.get("ciudad") or "").strip() or None
        categoria = (f.get("categoria") or "").strip() or None
        moneda = (f.get("moneda") or t.moneda or "").strip().upper() or None
        try:
            valor = float(f.get("valor"))
        except (TypeError, ValueError):
            errores.append({"fila": i, "mensaje": "el valor debe ser un número"})
            continue
        if pais and len(pais) != 2:
            errores.append({"fila": i, "mensaje": "el país es un código de dos letras (ES, FR…)"})
        if ciudad and not pais:
            errores.append({"fila": i, "mensaje": "una ciudad necesita su país"})
        if t.tipo_de_valor == "importe" and not moneda:
            errores.append({"fila": i, "mensaje": "falta la moneda"})
        try:
            desde, hasta = _fecha(f.get("vigente_desde")), _fecha(f.get("vigente_hasta"))
        except ErrorDeDominio:
            errores.append({"fila": i, "mensaje": "fecha no válida"})
            continue
        if desde and hasta and hasta < desde:
            errores.append({"fila": i, "mensaje": "la vigencia termina antes de empezar"})
        clave = (pais, (ciudad or "").lower(), categoria, desde)
        if clave in vistas:
            errores.append({"fila": i, "mensaje": "fila repetida (mismo país, ciudad, categoría y desde)"})
        vistas.add(clave)
        limpias.append({"pais": pais, "ciudad": ciudad, "categoria": categoria, "valor": valor,
                        "moneda": moneda if t.tipo_de_valor == "importe" else None,
                        "vigente_desde": desde, "vigente_hasta": hasta})
    return limpias, errores


def guardar_filas(db: Session, usuario, tabla_id: str, filas: list[dict]) -> dict:
    t = _tabla(db, tabla_id)
    limpias, errores = validar_filas(t, filas)
    if errores:
        raise ErrorDeDominio(422, {"message": "La tabla tiene errores", "errors": errores})
    t.filas.clear()
    for f in limpias:
        t.filas.append(FilaDeTablaDeReferencia(id=str(uuid.uuid4()), organization_id=t.organization_id, **f))
    t.updated_at = datetime.now(timezone.utc)
    db.commit()
    motor.invalidar(t.organization_id)
    return tabla(db, t.id)


_COLUMNAS = {"pais": ("pais", "país", "country"), "ciudad": ("ciudad", "city"),
             "categoria": ("categoria", "categoría", "category"), "valor": ("valor", "value", "importe", "amount"),
             "moneda": ("moneda", "currency"), "vigente_desde": ("vigente_desde", "desde", "from", "valid_from"),
             "vigente_hasta": ("vigente_hasta", "hasta", "to", "valid_to")}


def importar(db: Session, usuario, tabla_id: str, contenido: bytes, nombre: str) -> dict:
    """Lee un CSV o XLSX y devuelve las filas para revisarlas en la rejilla. NO guarda nada."""
    t = _tabla(db, tabla_id)
    nombre = (nombre or "").lower()
    if nombre.endswith(".xlsx"):
        from openpyxl import load_workbook
        hoja = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True).active
        filas = [["" if c is None else (c.isoformat() if isinstance(c, (date, datetime)) else str(c)) for c in fila]
                 for fila in hoja.iter_rows(values_only=True)]
    else:
        texto = contenido.decode("utf-8-sig", errors="replace")
        dialecto = csv.Sniffer().sniff(texto[:2048], delimiters=",;\t") if texto.strip() else csv.excel
        filas = list(csv.reader(io.StringIO(texto), dialecto))
    if not filas:
        raise ErrorDeDominio(422, "El fichero está vacío")
    cab = [c.strip().lower() for c in filas[0]]
    indice = {k: next((cab.index(a) for a in alias if a in cab), None) for k, alias in _COLUMNAS.items()}
    if indice["valor"] is None:
        raise ErrorDeDominio(422, "Falta la columna «valor»")
    leidas = [{k: (fila[i].strip() if i is not None and i < len(fila) else "") for k, i in indice.items()}
              for fila in filas[1:] if any((c or "").strip() for c in fila)]
    limpias, errores = validar_filas(t, leidas)
    return {"filas": [{**f, "vigente_desde": f["vigente_desde"].isoformat() if f["vigente_desde"] else None,
                       "vigente_hasta": f["vigente_hasta"].isoformat() if f["vigente_hasta"] else None}
                      for f in limpias], "errores": errores}


# ── Explicación por entidad ──────────────────────────────────────────────────

def explicaciones(db: Session, usuario, dominio_clave: str, entidad_id: str) -> dict:
    """Por qué: las evaluaciones guardadas de una entidad, la más reciente primero.

    Las ve un administrador, el dueño de la entidad o quien la tenga que aprobar.
    """
    dominio = catalogo.dominio(dominio_clave)
    entidad = dominio.cargar(db, entidad_id)
    if entidad is None:
        raise ErrorDeDominio(404, "No encontrado")
    rol = getattr(usuario.role, "value", usuario.role)
    if not (usuario.is_superadmin or rol == "admin" or dominio.propietario(entidad) == usuario.id
            or _es_aprobador(db, usuario, dominio, entidad_id)):
        raise ErrorDeDominio(403, "No puedes ver por qué se decidió esto")
    filas = db.query(EvaluacionDePolitica).filter(EvaluacionDePolitica.dominio == dominio.clave,
                                                  EvaluacionDePolitica.entidad_id == str(entidad_id)) \
        .order_by(EvaluacionDePolitica.created_at.desc()).limit(20).all()
    return {"dominio": dominio.clave, "entidad_id": entidad_id, "resumen": dominio.resumen(entidad),
            "evaluaciones": [{"id": f.id, "momento": f.momento, "decision": f.decision,
                              "resultado": _load(f.resultado, {}), "explicacion": _load(f.explicacion, {}),
                              "solicitud_id": f.solicitud_id,
                              "created_at": f.created_at.isoformat() if f.created_at else None} for f in filas]}


def _es_aprobador(db: Session, usuario, dominio, entidad_id) -> bool:
    if not dominio.tipo_de_aprobacion:
        return False
    from app.models.billing_reports import ApprovalRequest
    from app.services.approval_engine._base import _is_authorized
    from app.services.approval_engine.pasos import pasos_de
    for req in db.query(ApprovalRequest).filter(ApprovalRequest.entity_type == dominio.tipo_de_aprobacion,
                                                ApprovalRequest.entity_id == str(entidad_id)).all():
        if any(d.approver_id == usuario.id for d in req.decisions or []):
            return True
        if any(not getattr(s, "kind", "approve") == "inform" and _is_authorized(s, usuario, req.requested_by, db, req=req)
               for s in pasos_de(db, req)):
            return True
    return False


# ── Opciones para los selectores de la pantalla ──────────────────────────────

def opciones(db: Session, usuario) -> dict:
    from app.core.config import settings
    from app.models.billing_reports import ApprovalGroup
    from app.models.bookings import ExchangeRate
    from app.models.user import User, UserRole
    activos = db.query(User).filter(User.is_active.is_(True))
    departamentos = sorted({d for (d,) in activos.with_entities(User.department).distinct() if d})
    equipos = sorted({d for (d,) in activos.with_entities(User.team).distinct() if d})
    roles = sorted({r.value for r in UserRole} | {str(getattr(r, "value", r)) for (r,) in
                                                   activos.with_entities(User.role).distinct() if r})
    from app.services.settings_service.por_empresa import moneda_de_empresa
    moneda_por_defecto = moneda_de_empresa(db)  # 18-11-2026: la de la empresa
    monedas = {moneda_por_defecto}
    for a, b in db.query(ExchangeRate.from_currency, ExchangeRate.to_currency).distinct().all():
        monedas |= {a, b}
    ciudades = sorted({c for (c,) in db.query(FilaDeTablaDeReferencia.ciudad).distinct() if c})
    return {"departamentos": departamentos, "equipos": equipos, "roles": roles,
            "monedas": sorted(m for m in monedas if m), "moneda_por_defecto": moneda_por_defecto,
            "grupos": [{"id": g.id, "nombre": g.name} for g in db.query(ApprovalGroup).order_by(ApprovalGroup.name)],
            "tipos_de_documento": tipos_de_documento(db, _org(usuario)), "ciudades": ciudades,
            "tablas": tablas(db), **_opciones_de_dominios(db)}


def _opciones_de_dominios(db: Session) -> dict:
    """Lo que depende de la empresa en cada dominio: opciones de campos `enum`
    (tipos de ausencia, turnos…) y tipos de documento propios (tarea #25)."""
    campos: dict = {}
    documentos: dict = {}
    for d in catalogo.dominios():
        if d.opciones_dinamicas is not None:
            campos[d.clave] = {k: [{"valor": o.valor, "etiqueta": o.etiqueta} for o in v]
                               for k, v in d.opciones_dinamicas(db).items()}
        if d.tipos_de_documento is not None:
            documentos[d.clave] = [{"valor": o.valor, "etiqueta": o.etiqueta} for o in d.tipos_de_documento(db)]
    return {"opciones_de_campos": campos, "tipos_de_documento_por_dominio": documentos}


# ── Ejemplos («Cargar ejemplos»: borradores, nunca se aplican solos) ─────────

def _con_tablas(nodo, ids: dict):
    """Cambia las referencias `{"tipo": "tabla", "tabla": clave}` de un ejemplo por el id de la tabla."""
    if isinstance(nodo, dict):
        if nodo.get("tipo") == "tabla" and "tabla" in nodo:
            return {"tipo": "tabla", "tabla_id": ids[nodo["tabla"]]}
        return {k: _con_tablas(v, ids) for k, v in nodo.items()}
    if isinstance(nodo, list):
        return [_con_tablas(x, ids) for x in nodo]
    return nodo


def _solo_tipos_configurados(nodo, tipos: set):
    if isinstance(nodo, dict):
        if nodo.get("tipo") == "require_attachment":
            return {**nodo, "tipos_de_documento": [t for t in nodo.get("tipos_de_documento") or [] if t in tipos]}
        return {k: _solo_tipos_configurados(v, tipos) for k, v in nodo.items()}
    if isinstance(nodo, list):
        return [_solo_tipos_configurados(x, tipos) for x in nodo]
    return nodo


def cargar_ejemplos(db: Session, usuario, dominio_clave: str) -> dict:
    """Crea las tablas y políticas de ejemplo del dominio como BORRADOR.

    Idempotente por nombre: una tabla o política que ya existe con ese nombre
    no se duplica (la tabla existente se reutiliza). Un tipo de documento que
    la empresa no tiene configurado se quita del ejemplo («cualquier documento»).
    """
    dominio = catalogo.dominio(dominio_clave)
    if dominio.ejemplos is None:
        raise ErrorDeDominio(404, "Este dominio no tiene ejemplos")
    datos = dominio.ejemplos(db, usuario)
    ids: dict = {}
    creadas_t, creadas_p, existentes = [], [], []
    for t in datos.get("tablas") or []:
        previa = db.query(TablaDeReferencia).filter(TablaDeReferencia.nombre == t["nombre"]).first()
        if previa is not None:
            ids[t["clave"]] = previa.id
            existentes.append(t["nombre"])
            continue
        nueva = crear_tabla(db, usuario, {**{k: t.get(k) for k in ("nombre", "descripcion", "tipo_de_valor",
                                                                     "moneda", "uso")}, "dominio": dominio.clave})
        guardar_filas(db, usuario, nueva["id"], t.get("filas") or [])
        ids[t["clave"]] = nueva["id"]
        creadas_t.append(t["nombre"])
    tipos = set(tipos_de_documento_de(db, dominio, _org(usuario)))
    nombres = {n for (n,) in db.query(Politica.nombre).filter(Politica.dominio == dominio.clave).all()}
    for p in datos.get("politicas") or []:
        if p["nombre"] in nombres:
            existentes.append(p["nombre"])
            continue
        doc = _solo_tipos_configurados(_con_tablas({
            "dominio": dominio.clave, "nombre": p["nombre"], "descripcion": p.get("descripcion"),
            "prioridad": p.get("prioridad", 100), "activa": True, "ambito": p.get("ambito") or {},
            "nota_de_version": "Ejemplo cargado", "reglas": p["reglas"]}, ids), tipos)
        creadas_p.append(crear(db, usuario, doc)["id"])
    return {"tablas_creadas": creadas_t, "politicas_creadas": len(creadas_p), "ya_existian": existentes}


def catalogo_publico() -> dict:
    from app.services.politicas.catalogo import ENTIDADES, OPERADORES_POR_TIPO
    return {"dominios": [d.a_dict() for d in catalogo.dominios()],
            "operadores_por_tipo": {k: list(v) for k, v in OPERADORES_POR_TIPO.items()},
            "resultados": list(res.TIPOS), "tipos_de_aprobador": list(res.TIPOS_DE_APROBADOR),
            "destinatarios": list(res.DESTINATARIOS), "canales": list(res.CANALES), "entidades": list(ENTIDADES),
            "max_niveles": res.MAX_NIVELES}
