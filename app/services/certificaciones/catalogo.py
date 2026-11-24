"""Certificaciones: biblioteca de marcos y controles (§3.1).

Fuente: `app/data/certificaciones/` (formato en docs/CERTIFICACIONES_CONTENIDO.md §2):
`marcos.yaml`, `controles.yaml`, `plantillas/<clave>.yaml` y `documentos/<clave>.md`.

- `cargar()` lee y VALIDA el contenido (se cachea por fecha de los ficheros):
  claves únicas, correspondencias a marcos y niveles que existen, plantillas con
  parámetros tipados, `aplica_si` válidas, dependencias y controles que existen,
  RACI con `R`/`A` de un solo rol. Los errores dejan fuera lo que está mal (y se
  ven en `GET /certificaciones/catalogo/validacion`); los avisos no.
- `sembrar(db, org)` siembra por empresa, idempotente: crea lo que falta y pone al
  día lo sembrado que nadie ha editado (`editado = False` y huella distinta). Si un
  marco cambia de versión, guarda la anterior y marca sus correspondencias nuevas o
  retiradas como `afectado_por_version` (lo que hay que revisar).
- `sincronizar_sembrado(db)` lo mismo para cada empresa que ya sembró (al arrancar),
  igual que `bpmn_process_service.sincronizar_catalogo_sembrado`.
- GRC: los marcos ISO 27001 y SOC 2 de `app/core/marcos_de_cumplimiento.py` entran
  en la biblioteca (`migrar_grc`) y cada `compliance_evidence` queda enlazada como
  evidencia de su control (`importar_evidencias_grc`), sin copiar ni borrar nada.
- `importar_texto_oficial`: el texto con licencia de una empresa (solo en su
  espacio), y la corrección de identificadores sin perder enlaces.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.certificaciones import CertControl, CertCorrespondencia, CertEvidencia, CertMarco
from app.services.certificaciones import expresiones
from app.services.certificaciones.comun import auditar, dump, json_de, org_de

logger = logging.getLogger("contecflow.certificaciones")

RAIZ = Path(__file__).resolve().parents[2] / "data" / "certificaciones"

#: Medidas que la plataforma sabe tomar sola (`medible_por_plataforma`); ver `programas.medir`.
MEDIDAS: tuple[str, ...] = (
    "copias_seguridad", "gestion_cambios_cab", "gestion_incidentes", "gestion_vulnerabilidades",
    "inventario_activos_cmdb", "mfa_cobertura", "politica_contrasenas", "recertificacion_accesos",
    "registro_auditoria_inmutable", "retencion_datos", "revision_proveedores", "sod_conflictos",
)
TIPOS_DE_PARAMETRO = ("entero", "booleano", "opcion")
TIPOS_DE_DOCUMENTO = ("politica", "procedimiento", "registro")
ROLES_RACI = ("direccion", "responsable_seguridad", "responsable_cumplimiento", "ti", "ot", "rrhh", "finanzas",
              "auditoria_interna", "propietario_proceso", "proveedor")
_CLAVE = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")

_CACHE: dict[str, Any] = {"firma": None, "datos": None}


# ── Carga y validación ───────────────────────────────────────────────────────

def _firma(raiz: Path) -> tuple:
    return tuple(sorted((str(p), p.stat().st_mtime_ns) for p in raiz.rglob("*") if p.is_file()))


def _leer(ruta: Path):
    with ruta.open(encoding="utf8") as f:
        return yaml.safe_load(f)


def huella(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def cargar(raiz: Optional[Path] = None, *, forzar: bool = False) -> dict:
    """Contenido validado: {marcos, controles, plantillas, documentos, errores, avisos}."""
    raiz = raiz or RAIZ
    firma = _firma(raiz) if raiz.exists() else ()
    if not forzar and raiz == RAIZ and _CACHE["firma"] == firma and _CACHE["datos"] is not None:
        return _CACHE["datos"]
    datos = validar(raiz)
    if raiz == RAIZ:
        _CACHE.update(firma=firma, datos=datos)
    if datos["errores"]:
        logger.warning("Certificaciones: %s errores en el contenido (%s…)", len(datos["errores"]), datos["errores"][0])
    return datos


def validar(raiz: Path) -> dict:
    errores: list[str] = []
    avisos: list[str] = []
    marcos: dict[str, dict] = {}
    controles: dict[str, dict] = {}
    plantillas: dict[str, dict] = {}
    documentos: dict[str, str] = {}

    try:
        crudos = _leer(raiz / "marcos.yaml") or []
    except (OSError, yaml.YAMLError) as e:
        crudos = []
        errores.append(f"marcos.yaml: {e}")
    for i, m in enumerate(crudos if isinstance(crudos, list) else []):
        clave = (m or {}).get("clave")
        if not isinstance(clave, str) or not _CLAVE.match(clave) or not (m.get("nombre") or "").strip():
            errores.append(f"marcos[{i}]: falta clave o nombre")
            continue
        if clave in marcos:
            errores.append(f"marcos: clave repetida {clave}")
            continue
        niveles = m.get("niveles") or []
        if not isinstance(niveles, list) or not all(isinstance(n, str) for n in niveles):
            errores.append(f"marcos.{clave}: niveles no es una lista de textos")
            continue
        marcos[clave] = {"clave": clave, "nombre": m["nombre"], "version": str(m.get("version") or "") or None,
                         "publico": bool(m.get("publico")), "niveles": niveles,
                         "descripcion": m.get("descripcion"), "partes": m.get("partes") or []}

    try:
        crudos = _leer(raiz / "controles.yaml") or []
    except (OSError, yaml.YAMLError) as e:
        crudos = []
        errores.append(f"controles.yaml: {e}")
    for i, c in enumerate(crudos if isinstance(crudos, list) else []):
        clave = (c or {}).get("clave_comun")
        if not isinstance(clave, str) or not _CLAVE.match(clave) or not (c.get("titulo") or "").strip():
            errores.append(f"controles[{i}]: falta clave_comun o titulo")
            continue
        if clave in controles:
            errores.append(f"controles: clave repetida {clave}")
            continue
        medida = c.get("medible_por_plataforma")
        if medida and medida not in MEDIDAS:
            avisos.append(f"controles.{clave}: medida desconocida {medida} (no se medirá)")
        corr, vistos = [], set()
        for j, r in enumerate(c.get("correspondencias") or []):
            marco, idc, nivel = (r or {}).get("marco"), (r or {}).get("id_control"), (r or {}).get("nivel")
            if marco not in marcos or idc in (None, ""):
                errores.append(f"controles.{clave}.correspondencias[{j}]: marco desconocido o sin id")
                continue
            if nivel is not None and marcos[marco]["niveles"] and str(nivel) not in marcos[marco]["niveles"]:
                errores.append(f"controles.{clave}.correspondencias[{j}]: nivel {nivel} no es de {marco}")
                continue
            if (marco, str(idc)) in vistos:
                avisos.append(f"controles.{clave}: correspondencia repetida {marco} {idc}")
                continue
            vistos.add((marco, str(idc)))
            corr.append({"marco": marco, "id_control": str(idc), "nivel": str(nivel) if nivel is not None else None})
        sugerida = c.get("evidencia_sugerida") or []
        controles[clave] = {"clave_comun": clave, "titulo": c["titulo"], "descripcion": c.get("descripcion"),
                            "dominio": c.get("dominio"),
                            "evidencia_sugerida": [str(x) for x in sugerida] if isinstance(sugerida, list) else [],
                            "medible_por_plataforma": medida if medida in MEDIDAS else None,
                            "correspondencias": corr}

    for ruta in sorted((raiz / "documentos").glob("*.md")) if (raiz / "documentos").exists() else []:
        try:
            documentos[ruta.stem] = ruta.read_text(encoding="utf8")
        except OSError as e:
            avisos.append(f"documentos/{ruta.name}: {e}")

    for ruta in sorted((raiz / "plantillas").glob("*.yaml")) if (raiz / "plantillas").exists() else []:
        try:
            p = _leer(ruta) or {}
        except (OSError, yaml.YAMLError) as e:
            errores.append(f"plantillas/{ruta.name}: {e}")
            continue
        fallos = _validar_plantilla(p, marcos, controles, documentos, avisos)
        if fallos:
            errores.extend(f"plantillas/{ruta.name}: {f}" for f in fallos)
            continue
        plantillas[p["clave"]] = p

    return {"marcos": marcos, "controles": controles, "plantillas": plantillas, "documentos": documentos,
            "errores": errores, "avisos": avisos, "huella": huella([marcos, controles])}


def _validar_plantilla(p: dict, marcos: dict, controles: dict, documentos: dict, avisos: list) -> list[str]:
    fallos: list[str] = []
    clave = p.get("clave")
    if not isinstance(clave, str) or not _CLAVE.match(clave) or not (p.get("nombre") or "").strip():
        return ["falta clave o nombre"]
    for m in p.get("marcos") or []:
        if m not in marcos:
            fallos.append(f"marco desconocido {m}")
    nombres = set()
    for par in p.get("parametros") or []:
        if not isinstance(par, dict) or not par.get("clave") or par.get("tipo") not in TIPOS_DE_PARAMETRO:
            fallos.append(f"parámetro no válido {par}")
            continue
        if par["tipo"] == "opcion" and not par.get("opciones"):
            fallos.append(f"parámetro {par['clave']}: opción sin opciones")
        try:
            normalizar_parametro(par, par.get("por_defecto"))
        except ValueError:
            fallos.append(f"parámetro {par['clave']}: por_defecto no válido")
        nombres.add(par["clave"])
    tareas: dict[str, dict] = {}
    for f in p.get("fases") or []:
        if not f.get("clave") or not f.get("nombre"):
            fallos.append("fase sin clave o nombre")
            continue
        titulos = set()
        for t in f.get("tareas") or []:
            tc = t.get("clave")
            if not tc or not t.get("nombre"):
                fallos.append(f"{f['clave']}: tarea sin clave o nombre")
                continue
            if tc in tareas:
                fallos.append(f"tarea repetida {tc}")
            if t["nombre"] in titulos:
                fallos.append(f"{f['clave']}: nombre de tarea repetido «{t['nombre']}»")
            titulos.add(t["nombre"])
            tareas[tc] = t
            raci = t.get("raci") or {}
            if not isinstance(raci.get("R"), str) or not isinstance(raci.get("A"), str):
                fallos.append(f"{tc}: RACI necesita R y A de un solo rol")
            for k in ("C", "I"):
                if raci.get(k) is not None and not isinstance(raci.get(k), list):
                    fallos.append(f"{tc}: RACI {k} debe ser una lista")
            for c in t.get("controles") or []:
                if c not in controles:
                    fallos.append(f"{tc}: control desconocido {c}")
            if t.get("aplica_si"):
                motivo = expresiones.validar(t["aplica_si"], nombres)
                if motivo:
                    fallos.append(f"{tc}: aplica_si no válida ({motivo})")
            if t.get("dias") is not None and (not isinstance(t["dias"], int) or t["dias"] < 0):
                fallos.append(f"{tc}: días no válidos")
    for tc, t in tareas.items():
        for d in t.get("depende_de") or []:
            if d not in tareas:
                fallos.append(f"{tc}: depende de una tarea desconocida {d}")
    for d in p.get("documentos") or []:
        if not d.get("clave") or not d.get("nombre") or d.get("tipo") not in TIPOS_DE_DOCUMENTO:
            fallos.append(f"documento no válido {d.get('clave')}")
            continue
        if d["clave"] not in documentos:
            avisos.append(f"plantilla {clave}: documento sin plantilla documentos/{d['clave']}.md")
        for c in d.get("controles") or []:
            if c not in controles:
                fallos.append(f"documento {d['clave']}: control desconocido {c}")
    for r in p.get("riesgos") or []:
        if not r.get("titulo"):
            fallos.append("riesgo sin título")
    return fallos


def normalizar_parametro(par: dict, valor):
    """Convierte y comprueba el valor de un parámetro de plantilla (ValueError si no vale)."""
    tipo = par.get("tipo")
    if tipo == "entero":
        if isinstance(valor, bool):
            raise ValueError(par.get("clave"))
        v = int(valor)
        if v < 0:
            raise ValueError(par.get("clave"))
        return v
    if tipo == "booleano":
        if isinstance(valor, bool):
            return valor
        if str(valor).lower() in ("true", "1", "si", "sí"):
            return True
        if str(valor).lower() in ("false", "0", "no"):
            return False
        raise ValueError(par.get("clave"))
    if tipo == "opcion":
        if valor not in (par.get("opciones") or []):
            raise ValueError(par.get("clave"))
        return valor
    raise ValueError(par.get("clave"))


# ── Siembra por empresa ──────────────────────────────────────────────────────

def _campos_marco(m: dict) -> dict:
    return {"nombre": m["nombre"], "version": m["version"], "publico": m["publico"],
            "niveles": dump(m["niveles"]), "descripcion": m.get("descripcion")}


def _campos_control(c: dict) -> dict:
    return {"titulo": c["titulo"][:300], "descripcion": c.get("descripcion"), "dominio": c.get("dominio"),
            "evidencia_sugerida": dump(c.get("evidencia_sugerida") or []),
            "medible_por_plataforma": c.get("medible_por_plataforma")}


def sembrar(db: Session, org: str, *, contenido: Optional[dict] = None, usuario=None) -> dict:
    """Siembra o pone al día la biblioteca de `org`. No confirma (lo hace quien llama)."""
    datos = contenido or cargar()
    informe = {"marcos_creados": 0, "marcos_actualizados": 0, "controles_creados": 0, "controles_actualizados": 0,
               "correspondencias_creadas": 0, "correspondencias_retiradas": 0, "afectadas_por_version": 0}
    por_clave = {m.clave: m for m in db.query(CertMarco).filter(CertMarco.organization_id == org).all()}
    version_cambiada: set[str] = set()
    for clave, m in datos["marcos"].items():
        h = huella(m)
        fila = por_clave.get(clave)
        if fila is None:
            fila = CertMarco(organization_id=org, clave=clave, sembrado=True, huella_semilla=h, **_campos_marco(m))
            db.add(fila)
            por_clave[clave] = fila
            informe["marcos_creados"] += 1
        elif fila.sembrado and not fila.editado and fila.huella_semilla != h:
            if (fila.version or None) != m["version"]:
                fila.version_anterior = fila.version
                version_cambiada.add(clave)
            for k, v in _campos_marco(m).items():
                setattr(fila, k, v)
            fila.huella_semilla = h
            informe["marcos_actualizados"] += 1
    db.flush()

    controles = {c.clave_comun: c for c in db.query(CertControl).filter(CertControl.organization_id == org).all()}
    existentes = {}
    for r in db.query(CertCorrespondencia).filter(CertCorrespondencia.organization_id == org).all():
        existentes[(r.marco_id, r.id_semilla or r.id_control, r.control_id)] = r
    vistas: set = set()
    for clave, c in datos["controles"].items():
        h = huella(c)
        fila = controles.get(clave)
        if fila is None:
            fila = CertControl(organization_id=org, clave_comun=clave, sembrado=True, huella_semilla=h,
                               **_campos_control(c))
            db.add(fila)
            db.flush()
            controles[clave] = fila
            informe["controles_creados"] += 1
        elif fila.sembrado and not fila.editado and fila.huella_semilla != h:
            for k, v in _campos_control(c).items():
                setattr(fila, k, v)
            fila.huella_semilla = h
            informe["controles_actualizados"] += 1
        for r in c["correspondencias"]:
            marco = por_clave.get(r["marco"])
            if marco is None:
                continue
            k = (marco.id, r["id_control"], fila.id)
            vistas.add(k)
            hay = existentes.get(k)
            if hay is None:
                nueva = CertCorrespondencia(organization_id=org, control_id=fila.id, marco_id=marco.id,
                                            id_control=r["id_control"], id_semilla=r["id_control"],
                                            nivel=r["nivel"], version_marco=marco.version, sembrado=True,
                                            afectado_por_version=r["marco"] in version_cambiada)
                db.add(nueva)
                existentes[k] = nueva
                informe["correspondencias_creadas"] += 1
                informe["afectadas_por_version"] += int(nueva.afectado_por_version)
            elif hay.sembrado and hay.nivel != r["nivel"]:
                hay.nivel = r["nivel"]
    # Correspondencias sembradas que la semilla ya no trae: fuera si no tienen texto
    # oficial; si lo tienen (o el marco cambió de versión), se marcan para revisar.
    marcos_sembrados = {m.id for m in por_clave.values() if m.sembrado}
    for k, r in existentes.items():
        if k in vistas or not r.sembrado or r.marco_id not in marcos_sembrados:
            continue
        controles_editados = {c.id for c in controles.values() if c.editado}
        if r.control_id in controles_editados:
            continue
        if r.texto_oficial or any(m.id == r.marco_id and m.clave in version_cambiada for m in por_clave.values()):
            if not r.afectado_por_version:
                r.afectado_por_version = True
                informe["afectadas_por_version"] += 1
        else:
            db.delete(r)
            informe["correspondencias_retiradas"] += 1
    db.flush()
    informe.update(migrar_grc(db, org))
    if any(v for k, v in informe.items() if k != "grc_controles_enlazados"):
        auditar(db, usuario, "SEED", "catalogo", org, meta={"informe": informe, "huella": datos.get("huella")})
    return informe


def sembrado(db: Session, org: str) -> bool:
    return db.query(CertMarco.id).filter(CertMarco.organization_id == org, CertMarco.sembrado.is_(True)).first() \
        is not None


def asegurar_sembrado(db: Session, org: str) -> None:
    """La primera vez que una empresa abre el módulo se siembra su biblioteca.

    24-11-2026: la pantalla lanza varias peticiones a la vez al abrirse y todas
    intentaban sembrar: la segunda chocaba con el único (organización, clave) y
    respondía 500. Si otra petición ya sembró, se deshace lo propio y se sigue.
    """
    if sembrado(db, org):
        return
    from sqlalchemy.exc import IntegrityError
    try:
        sembrar(db, org)
        db.commit()
    except IntegrityError:
        db.rollback()
        if not sembrado(db, org):
            raise


def sincronizar_sembrado(db: Session) -> int:
    """Al arrancar: pone al día la biblioteca sembrada de cada empresa que ya la tiene."""
    from app.db.contexto_de_tenant import con_empresa
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        orgs = [r[0] for r in db.query(CertMarco.organization_id).filter(CertMarco.sembrado.is_(True)).distinct()]
    total = 0
    for org in orgs:
        with con_empresa(db, org):
            inf = sembrar(db, org)
            db.commit()
            total += inf["marcos_actualizados"] + inf["controles_actualizados"] + inf["correspondencias_creadas"]
    return total


# ── GRC: ISO 27001 y SOC 2 de «Marcos y evidencias» ──────────────────────────

#: SOC 2 no está en el contenido común: entra desde el GRC. Cada criterio se cuelga
#: del control común que cubre el mismo requisito de ISO 27001 (Anexo A).
SOC2_A_ISO = {"SOC2-CC6.1": "A.8.5", "SOC2-CC6.2": "A.5.18", "SOC2-CC6.3": "A.5.15", "SOC2-CC7.2": "A.8.16"}
_MARCOS_GRC = {"ISO27001": "iso27001", "SOC2": "soc2"}


def _id_grc(legado: str) -> str:
    """«ISO27001-A.5.17» → «A.5.17»; «SOC2-CC6.1» → «CC6.1»."""
    return legado.split("-", 1)[1] if "-" in legado else legado


def _control_por_iso(db: Session, org: str, iso: Optional[CertMarco], id_iso: str) -> Optional[CertControl]:
    if iso is None:
        return None
    return (db.query(CertControl).join(CertCorrespondencia, CertCorrespondencia.control_id == CertControl.id)
            .filter(CertCorrespondencia.organization_id == org, CertCorrespondencia.marco_id == iso.id,
                    CertCorrespondencia.id_control == id_iso)
            .order_by(CertControl.clave_comun).first())


def control_de_grc(db: Session, org: str, framework: str, control_id: str) -> Optional[CertControl]:
    """El control común de un identificador del GRC (aplica los alias de `marcos_de_cumplimiento`)."""
    from app.core import marcos_de_cumplimiento as marcos
    legado = marcos.canonico(control_id)
    clave_marco = _MARCOS_GRC.get((framework or "").upper())
    if not clave_marco:
        return None
    marco = db.query(CertMarco).filter(CertMarco.organization_id == org, CertMarco.clave == clave_marco).first()
    if marco is None:
        return None
    r = db.query(CertCorrespondencia).filter(CertCorrespondencia.organization_id == org,
                                             CertCorrespondencia.marco_id == marco.id,
                                             CertCorrespondencia.id_control == _id_grc(legado)).first()
    return db.get(CertControl, r.control_id) if r else None


def migrar_grc(db: Session, org: str) -> dict:
    """Los marcos ISO 27001 y SOC 2 del GRC en la biblioteca (idempotente) y sus evidencias enlazadas."""
    from app.core import marcos_de_cumplimiento as marcos
    enlazados = 0
    filas = {m.clave: m for m in db.query(CertMarco).filter(CertMarco.organization_id == org,
                                                           CertMarco.clave.in_(_MARCOS_GRC.values())).all()}
    if "soc2" not in filas:
        filas["soc2"] = CertMarco(organization_id=org, clave="soc2", nombre="SOC 2 (Trust Services Criteria 2017)",
                                  version="2017", publico=False, niveles=dump([]), sembrado=True,
                                  descripcion="Migrado del GRC («Marcos y evidencias»).")
        db.add(filas["soc2"])
    if "iso27001" not in filas:
        filas["iso27001"] = CertMarco(organization_id=org, clave="iso27001", nombre="ISO/IEC 27001:2022",
                                      version="2022", publico=False, niveles=dump(["clausulas", "anexo_a"]),
                                      sembrado=True, descripcion="Migrado del GRC («Marcos y evidencias»).")
        db.add(filas["iso27001"])
    db.flush()
    iso = filas["iso27001"]
    for fw, ids in marcos.CONTROLES.items():
        marco = filas[_MARCOS_GRC[fw]]
        for legado in ids:
            idc = _id_grc(legado)
            hay = db.query(CertCorrespondencia.id).filter(CertCorrespondencia.organization_id == org,
                                                          CertCorrespondencia.marco_id == marco.id,
                                                          CertCorrespondencia.id_control == idc).first()
            if hay is not None:
                continue
            control = _control_por_iso(db, org, iso, SOC2_A_ISO.get(legado, idc)) if fw == "SOC2" else None
            if control is None:
                clave = "grc-" + re.sub(r"[^a-z0-9]+", "-", legado.lower()).strip("-")
                control = db.query(CertControl).filter(CertControl.organization_id == org,
                                                       CertControl.clave_comun == clave).first()
                if control is None:
                    control = CertControl(organization_id=org, clave_comun=clave, titulo=legado.replace("-", " ", 1),
                                          descripcion="Control migrado del GRC («Marcos y evidencias»).",
                                          dominio="cumplimiento", sembrado=True)
                    db.add(control)
                    db.flush()
            db.add(CertCorrespondencia(organization_id=org, control_id=control.id, marco_id=marco.id,
                                       id_control=idc, id_semilla=idc, version_marco=marco.version, sembrado=True))
            enlazados += 1
    db.flush()
    return {"grc_controles_enlazados": enlazados, "grc_evidencias_enlazadas": importar_evidencias_grc(db, org)}


_TIPO_DE_GRC = {"policy": "documento", "report": "informe_sistema", "audit_log": "registro", "ticket": "registro",
                "screenshot": "registro", "other": "registro"}


def importar_evidencias_grc(db: Session, org: str) -> int:
    """Cada `compliance_evidence` de la empresa, enlazada (una vez) como evidencia de su control común."""
    from app.models.governance import ComplianceEvidence
    ya = {r[0] for r in db.query(CertEvidencia.compliance_evidence_id).filter(
        CertEvidencia.organization_id == org, CertEvidencia.compliance_evidence_id.isnot(None)).all()}
    n = 0
    for ev in db.query(ComplianceEvidence).filter(ComplianceEvidence.organization_id == org).all():
        if ev.id in ya:
            continue
        control = control_de_grc(db, org, ev.framework, ev.control_id)
        if control is None:
            continue
        sha = ev.artifact_hash if ev.artifact_hash and len(ev.artifact_hash) == 64 else None
        db.add(CertEvidencia(organization_id=org, control_id=control.id, titulo=(ev.title or ev.control_id)[:300],
                             tipo=_TIPO_DE_GRC.get(ev.evidence_type, "registro"), origen="grc",
                             compliance_evidence_id=ev.id, uri=ev.artifact_uri, sha256=sha,
                             valida_desde=ev.created_at.date() if ev.created_at else None,
                             creado_por=ev.created_by))
        n += 1
    if n:
        db.flush()
    return n


# ── Consultas ────────────────────────────────────────────────────────────────

def serializar_marco(m: CertMarco) -> dict:
    return {"id": m.id, "clave": m.clave, "nombre": m.nombre, "version": m.version,
            "version_anterior": m.version_anterior, "publico": m.publico, "niveles": json_de(m.niveles, []),
            "descripcion": m.descripcion, "sembrado": m.sembrado, "editado": m.editado, "activo": m.activo}


def marcos(db: Session, usuario) -> list[dict]:
    org = org_de(usuario)
    asegurar_sembrado(db, org)
    filas = db.query(CertMarco).filter(CertMarco.organization_id == org).order_by(CertMarco.clave).all()
    from sqlalchemy import func
    cuentas = dict(db.query(CertCorrespondencia.marco_id, func.count(CertCorrespondencia.id))
                   .filter(CertCorrespondencia.organization_id == org).group_by(CertCorrespondencia.marco_id).all())
    return [{**serializar_marco(m), "controles": cuentas.get(m.id, 0)} for m in filas]


def serializar_control(c: CertControl, corr: list[CertCorrespondencia], marcos_por_id: dict) -> dict:
    return {"id": c.id, "clave_comun": c.clave_comun, "titulo": c.titulo, "descripcion": c.descripcion,
            "dominio": c.dominio, "evidencia_sugerida": json_de(c.evidencia_sugerida, []),
            "medible_por_plataforma": c.medible_por_plataforma, "sembrado": c.sembrado, "editado": c.editado,
            "activo": c.activo,
            "correspondencias": [{"id": r.id, "marco": marcos_por_id[r.marco_id].clave if r.marco_id in marcos_por_id
                                  else None, "id_control": r.id_control, "id_semilla": r.id_semilla,
                                  "nivel": r.nivel, "texto_oficial": r.texto_oficial,
                                  "afectado_por_version": r.afectado_por_version} for r in corr]}


def controles(db: Session, usuario, *, marco: Optional[str] = None, dominio: Optional[str] = None,
              q: Optional[str] = None, afectados: bool = False) -> list[dict]:
    org = org_de(usuario)
    asegurar_sembrado(db, org)
    marcos_por_id = {m.id: m for m in db.query(CertMarco).filter(CertMarco.organization_id == org).all()}
    corr: dict[str, list] = {}
    for r in db.query(CertCorrespondencia).filter(CertCorrespondencia.organization_id == org).all():
        corr.setdefault(r.control_id, []).append(r)
    query = db.query(CertControl).filter(CertControl.organization_id == org)
    if dominio:
        query = query.filter(CertControl.dominio == dominio)
    if q:
        query = query.filter(CertControl.titulo.ilike(f"%{q}%") | CertControl.clave_comun.ilike(f"%{q}%"))
    salida = []
    for c in query.order_by(CertControl.clave_comun).all():
        propias = corr.get(c.id, [])
        if marco and not any(marcos_por_id.get(r.marco_id) and marcos_por_id[r.marco_id].clave == marco
                             for r in propias):
            continue
        if afectados and not any(r.afectado_por_version for r in propias):
            continue
        salida.append(serializar_control(c, propias, marcos_por_id))
    return salida


def editar_control(db: Session, usuario, control_id: str, datos: dict) -> dict:
    """Editar un control sembrado lo marca `editado`: la siembra ya no lo pisa."""
    from app.services.certificaciones.comun import propio
    c = propio(db, CertControl, control_id, usuario, "control")
    antes = {k: getattr(c, k) for k in ("titulo", "descripcion", "dominio", "activo")}
    for k in ("titulo", "descripcion", "dominio", "activo"):
        if k in datos and datos[k] is not None:
            setattr(c, k, datos[k])
    if "evidencia_sugerida" in datos and datos["evidencia_sugerida"] is not None:
        c.evidencia_sugerida = dump([str(x) for x in datos["evidencia_sugerida"]])
    c.editado = True
    auditar(db, usuario, "UPDATE", "control", c.id, c.clave_comun, antes=antes,
            despues={k: getattr(c, k) for k in antes})
    db.commit()
    marcos_por_id = {m.id: m for m in db.query(CertMarco).filter(CertMarco.organization_id == c.organization_id)}
    corr = db.query(CertCorrespondencia).filter(CertCorrespondencia.control_id == c.id).all()
    return serializar_control(c, corr, marcos_por_id)


def revisar_version(db: Session, usuario, correspondencia_id: str) -> dict:
    """Quita la marca «afectada por cambio de versión» tras revisarla."""
    from app.services.certificaciones.comun import propio
    r = propio(db, CertCorrespondencia, correspondencia_id, usuario, "correspondencia")
    r.afectado_por_version = False
    m = db.get(CertMarco, r.marco_id)
    r.version_marco = m.version if m else r.version_marco
    auditar(db, usuario, "REVIEW", "correspondencia", r.id, r.id_control)
    db.commit()
    return {"ok": True}


def importar_texto_oficial(db: Session, usuario, filas: list[dict], licencia: Optional[dict] = None) -> dict:
    """Texto oficial con licencia de la empresa: [{marco, id_control, texto_oficial?, id_control_nuevo?}].

    Cruza por (marco, id_control) —o por el id de la semilla— y, con
    `id_control_nuevo`, corrige el identificador sin perder el enlace al control
    (la semilla lo sigue reconociendo por `id_semilla`). Los que no casan se informan.
    """
    org = org_de(usuario)
    asegurar_sembrado(db, org)
    por_clave = {m.clave: m for m in db.query(CertMarco).filter(CertMarco.organization_id == org).all()}
    actualizados, renombrados, sin_casar = 0, 0, []
    for i, f in enumerate(filas or []):
        marco = por_clave.get(str(f.get("marco") or ""))
        idc = str(f.get("id_control") or "").strip()
        if marco is None or not idc:
            sin_casar.append({"fila": i, "marco": f.get("marco"), "id_control": idc})
            continue
        rs = db.query(CertCorrespondencia).filter(
            CertCorrespondencia.organization_id == org, CertCorrespondencia.marco_id == marco.id,
            (CertCorrespondencia.id_control == idc) | (CertCorrespondencia.id_semilla == idc)).all()
        if not rs:
            sin_casar.append({"fila": i, "marco": marco.clave, "id_control": idc})
            continue
        for r in rs:
            if f.get("texto_oficial") is not None:
                r.texto_oficial = str(f["texto_oficial"])
                actualizados += 1
            nuevo = str(f.get("id_control_nuevo") or "").strip()
            if nuevo and nuevo != r.id_control:
                if r.id_semilla is None:
                    r.id_semilla = r.id_control
                r.id_control = nuevo[:60]
                renombrados += 1
    auditar(db, usuario, "IMPORT", "texto_oficial", org,
            meta={"actualizados": actualizados, "renombrados": renombrados, "sin_casar": len(sin_casar),
                  "licencia": licencia or {}})
    db.commit()
    return {"actualizados": actualizados, "renombrados": renombrados, "sin_casar": sin_casar}


def resumen_de_validacion() -> dict:
    d = cargar()
    return {"marcos": len(d["marcos"]), "controles": len(d["controles"]), "plantillas": len(d["plantillas"]),
            "documentos": len(d["documentos"]), "errores": d["errores"], "avisos": d["avisos"],
            "huella": d["huella"]}


def plantillas() -> list[dict]:
    d = cargar()
    salida = []
    for clave, p in sorted(d["plantillas"].items()):
        tareas = [t for f in p.get("fases") or [] for t in f.get("tareas") or []]
        salida.append({"clave": clave, "nombre": p["nombre"], "marcos": p.get("marcos") or [],
                       "parametros": p.get("parametros") or [], "fases": len(p.get("fases") or []),
                       "tareas": len(tareas), "condicionales": sum(1 for t in tareas if t.get("aplica_si")),
                       "riesgos": len(p.get("riesgos") or []), "documentos": len(p.get("documentos") or [])})
    return salida


def plantilla(clave: str) -> dict:
    p = cargar()["plantillas"].get(clave)
    if p is None:
        raise error(404, "no_encontrado", que="cert_plantilla")
    return p
