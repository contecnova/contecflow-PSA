"""Registro de auditoría a prueba de manipulación (revisión 2026-11, lo que contecmind y contecintelligence tenían).

Cada fila de `audit_logs` se encadena con la anterior de SU empresa:

- `seq`: posición en la cadena de la empresa (1, 2, 3…; sin huecos);
- `prev_hash`: la huella de la fila anterior (64 ceros en la primera);
- `entry_hash`: HMAC-SHA256 de los campos de la fila más `seq` y `prev_hash`;
- `chain_key_id`: huella corta de la clave con la que se firmó.

La clave del HMAC se deriva de `SECRET_KEY` (como el cifrado de la casa) y no
está en la base: quien sólo tenga acceso a la base puede cambiar una fila, pero
no recalcular su huella, y la verificación lo encuentra. Al rotar `SECRET_KEY`,
las filas firmadas con la anterior se siguen verificando si está en
`SECRET_KEY_PREVIOUS`.

Lo que detecta: una fila cambiada (huella), una fila borrada del medio (hueco en
`seq` o `prev_hash` que no casa) y una fila inventada (no se puede firmar sin la
clave). Lo que NO detecta solo: que se borren las últimas filas. Para eso está
la exportación firmada: guarda la cabeza (`seq` y huella), y la verificación
puede comprobar que esa cabeza sigue en la cadena (`cabeza_esperada`).

`user_id` no entra en la huella: la clave ajena es `ON DELETE SET NULL` y borrar
un usuario lo cambia legítimamente. Su nombre (`user_name`) sí entra.

La exportación se firma con Ed25519 (clave también derivada de `SECRET_KEY`); la
pública está en `GET /enterprise/audit-log/chain/public-key` y dentro del propio
fichero, para que un auditor compruebe la firma sin acceder al sistema.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import text

CERO = "0" * 64
CAMPOS = ("organization_id", "user_name", "ip_address", "user_agent", "action", "resource", "resource_id",
          "resource_name", "old_values", "new_values", "metadata", "created_at")
_CACHE = "_cadena_auditoria"
# La cadena de una empresa, o la de las filas sin empresa (`:org` NULL).
_SQL_CABEZA = ("SELECT seq, entry_hash FROM audit_logs "
               "WHERE (organization_id = :org OR (organization_id IS NULL AND :org IS NULL)) "
               "AND seq IS NOT NULL ORDER BY seq DESC LIMIT 1")
_SQL_SIN_ENCADENAR = ("SELECT id, organization_id, user_name, ip_address, user_agent, action, resource, resource_id, "
                      "resource_name, old_values, new_values, metadata, created_at FROM audit_logs "
                      "WHERE (organization_id = :org OR (organization_id IS NULL AND :org IS NULL)) "
                      "AND seq IS NULL ORDER BY created_at, id")


# ── Claves ────────────────────────────────────────────────────────────────────

def _secretos() -> list[str]:
    from app.core.config import settings
    anteriores = [c.strip() for c in (settings.SECRET_KEY_PREVIOUS or "").split(",") if c.strip()]
    return [settings.SECRET_KEY] + [c for c in anteriores if c != settings.SECRET_KEY]


def _clave_hmac(secreto: str) -> bytes:
    return hmac.new(secreto.encode(), b"contecflow/audit-chain/v1", hashlib.sha256).digest()


def _id_de_clave(clave: bytes) -> str:
    return hashlib.sha256(clave).hexdigest()[:16]


def claves() -> dict[str, bytes]:
    """{id: clave} de la actual y de las anteriores; la primera es la actual."""
    salida = {}
    for s in _secretos():
        k = _clave_hmac(s)
        salida.setdefault(_id_de_clave(k), k)
    return salida


def _clave_de_firma():
    from app.core.config import settings
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    semilla = hmac.new(settings.SECRET_KEY.encode(), b"contecflow/audit-export-signing/v1", hashlib.sha256).digest()
    return Ed25519PrivateKey.from_private_bytes(semilla)


def clave_publica_pem() -> str:
    from cryptography.hazmat.primitives import serialization
    return _clave_de_firma().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


# ── Huella ────────────────────────────────────────────────────────────────────

def _instante(valor) -> Optional[str]:
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor)
    if valor.tzinfo is None:          # SQLite devuelve sin zona: se guardó en UTC
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc).isoformat(timespec="microseconds")


def huella(clave: bytes, fila: dict, seq: int, prev_hash: str) -> str:
    """HMAC-SHA256 de la fila canónica (JSON con claves ordenadas)."""
    datos = {c: fila.get(c) for c in CAMPOS}
    datos["created_at"] = _instante(datos["created_at"])
    # La columna es texto: lo que se sella puede llegar como número y la base lo devuelve como texto.
    if datos["organization_id"] is not None:
        datos["organization_id"] = str(datos["organization_id"])
    datos["seq"], datos["prev_hash"] = int(seq), prev_hash
    canon = json.dumps(datos, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hmac.new(clave, canon.encode(), hashlib.sha256).hexdigest()


def _fila_de(objeto) -> dict:
    return {c: getattr(objeto, "metadata_" if c == "metadata" else c, None) for c in CAMPOS}


# ── Escribir: se llama desde el evento `before_insert` de AuditLog ─────────────

def _cabeza(conexion, org) -> tuple[int, str]:
    """(seq, huella) de la última fila de la cadena de la empresa (0, ceros si no hay)."""
    postgres = conexion.dialect.name == "postgresql"
    previo = None
    if postgres:
        # Un candado por empresa hasta el final de la transacción: dos escrituras
        # a la vez no pueden coger la misma cabeza.
        conexion.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"audit:{org or ''}"})
        # La política RLS sólo deja ver la empresa de la sesión; la cabeza de otra
        # cadena (la global, o la de la empresa a la que escribe un superadmin) no
        # se vería. Se lee sin empresa y se restaura lo que hubiera.
        previo = conexion.execute(text("SELECT current_setting('app.tenant', true)")).scalar()
        conexion.execute(text("SELECT set_config('app.tenant', '', true)"))
    try:
        fila = conexion.execute(text(_SQL_CABEZA), {"org": org}).first()
    finally:
        if postgres:
            conexion.execute(text("SELECT set_config('app.tenant', :v, true)"), {"v": previo or ""})
    return (int(fila[0]), fila[1]) if fila else (0, CERO)


def encadenar(conexion, objeto) -> None:
    from sqlalchemy.orm import object_session
    if objeto.created_at is None:
        objeto.created_at = datetime.now(timezone.utc)
    sesion = object_session(objeto)
    cache = sesion.info.setdefault(_CACHE, {}) if sesion is not None else {}
    org = str(objeto.organization_id) if objeto.organization_id is not None else None
    seq, anterior = cache[org] if org in cache else _cabeza(conexion, org)
    clave_id, clave = next(iter(claves().items()))
    objeto.seq, objeto.prev_hash, objeto.chain_key_id = seq + 1, anterior, clave_id
    objeto.entry_hash = huella(clave, _fila_de(objeto), seq + 1, anterior)
    cache[org] = (seq + 1, objeto.entry_hash)


def olvidar_cabezas(sesion) -> None:
    """Tras cada flush la cabeza se vuelve a leer de la base (ya incluye lo insertado)."""
    sesion.info.pop(_CACHE, None)


# ── Verificar ─────────────────────────────────────────────────────────────────

def _filas(db, org) -> Iterable:
    from app.db.session import sin_filtro_de_tenant
    from app.models.enterprise import AuditLog
    with sin_filtro_de_tenant(db):
        q = db.query(AuditLog).filter(
            AuditLog.organization_id == org if org else AuditLog.organization_id.is_(None))
        yield from q.order_by(AuditLog.seq.asc().nullsfirst(), AuditLog.created_at, AuditLog.id).yield_per(1000)


def verificar(db, org, cabeza_esperada: Optional[dict] = None) -> dict:
    """Recorre TODA la cadena de la empresa y dice cuántas filas miró y dónde se rompe.

    `cabeza_esperada` ({seq, entry_hash}, de una exportación anterior) comprueba
    además que esa fila sigue ahí, que es lo que delata un borrado del final.
    """
    disponibles = claves()
    recorridas, esperado, anterior = 0, 1, CERO
    roturas: list[dict] = []
    for f in _filas(db, org):
        recorridas += 1
        if f.seq is None:
            roturas.append({"id": f.id, "seq": None, "reason": "unchained"})
            continue
        if f.seq != esperado:
            roturas.append({"id": f.id, "seq": f.seq, "reason": "seq_gap", "expected_seq": esperado})
        elif f.prev_hash != anterior:
            roturas.append({"id": f.id, "seq": f.seq, "reason": "prev_mismatch"})
        clave = disponibles.get(f.chain_key_id or "")
        if clave is None:
            roturas.append({"id": f.id, "seq": f.seq, "reason": "unknown_key"})
        elif not hmac.compare_digest(huella(clave, _fila_de(f), f.seq, f.prev_hash or ""), f.entry_hash or ""):
            roturas.append({"id": f.id, "seq": f.seq, "reason": "hash_mismatch"})
        esperado, anterior = f.seq + 1, f.entry_hash
    cabeza = {"seq": esperado - 1, "entry_hash": anterior if esperado > 1 else None}
    resultado = {"organization_id": org, "rows_checked": recorridas, "ok": not roturas,
                 "breaks": roturas[:100], "breaks_total": len(roturas), "head": cabeza,
                 "checked_at": datetime.now(timezone.utc).isoformat()}
    if cabeza_esperada:
        s, h = int(cabeza_esperada.get("seq") or 0), cabeza_esperada.get("entry_hash")
        sigue = _fila_en(db, org, s)
        resultado["expected_head"] = {"seq": s, "found": bool(sigue and sigue.entry_hash == h)}
        if not resultado["expected_head"]["found"]:
            resultado["ok"] = False
    return resultado


def _fila_en(db, org, seq):
    from app.db.session import sin_filtro_de_tenant
    from app.models.enterprise import AuditLog
    with sin_filtro_de_tenant(db):
        return db.query(AuditLog).filter(
            AuditLog.organization_id == org if org else AuditLog.organization_id.is_(None),
            AuditLog.seq == seq).first()


# ── Exportar firmado ──────────────────────────────────────────────────────────

def _canon(doc: dict) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def exportar(db, org, limite: int) -> dict:
    """La cadena entera (hasta `limite` filas, las últimas) con su verificación, firmada."""
    verificacion = verificar(db, org)
    filas = list(_filas(db, org))
    recortada = len(filas) > limite
    filas = filas[-limite:] if recortada else filas
    doc = {
        "format": "contecflow-audit-chain/v1",
        "organization_id": org,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verification": verificacion,
        "head": verificacion["head"],
        "truncated": recortada,
        "entries": [{"id": f.id, "seq": f.seq, "prev_hash": f.prev_hash, "entry_hash": f.entry_hash,
                     "chain_key_id": f.chain_key_id, "user_id": f.user_id,
                     **{c: (_instante(v) if c == "created_at" else v) for c, v in _fila_de(f).items()}}
                    for f in filas],
        "public_key_pem": clave_publica_pem(),
        "signature_alg": "Ed25519 over the canonical JSON of this document without «signature»",
    }
    doc["signature"] = base64.b64encode(_clave_de_firma().sign(_canon(doc))).decode()
    return doc


def comprobar_firma(doc: dict) -> bool:
    """Lo mismo que haría el auditor con la clave pública del documento."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    resto = {k: v for k, v in doc.items() if k != "signature"}
    try:
        load_pem_public_key(doc["public_key_pem"].encode()).verify(base64.b64decode(doc["signature"]), _canon(resto))
        return True
    except (InvalidSignature, KeyError, ValueError):
        return False


# ── Rellenar las filas que ya existían (migración 137) ─────────────────────────

def encadenar_existentes(conexion) -> int:
    """Encadena, por empresa y en orden de creación, las filas sin `seq`. Devuelve cuántas."""
    clave_id, clave = next(iter(claves().items()))
    orgs = [o for (o,) in conexion.execute(text(
        "SELECT DISTINCT organization_id FROM audit_logs WHERE seq IS NULL"))]
    total = 0
    for org in orgs:
        seq, anterior = 0, CERO
        ultima = conexion.execute(text(_SQL_CABEZA), {"org": org}).first()
        if ultima:
            seq, anterior = int(ultima[0]), ultima[1]
        filas = conexion.execute(text(_SQL_SIN_ENCADENAR), {"org": org}).mappings().all()
        for f in filas:
            seq += 1
            creado = f["created_at"] or datetime.now(timezone.utc)
            h = huella(clave, {**dict(f), "created_at": creado}, seq, anterior)
            conexion.execute(text(
                "UPDATE audit_logs SET seq = :s, prev_hash = :p, entry_hash = :h, chain_key_id = :k, "
                "created_at = :c WHERE id = :id"),
                {"s": seq, "p": anterior, "h": h, "k": clave_id, "c": creado, "id": f["id"]})
            anterior = h
            total += 1
    return total
