"""Importacion de datos por CSV: plantillas, validacion y ejecucion.

Parte de `app.services.billing_reports_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import csv
import io
import json
import secrets
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.user import User
from app.models.project import Project
from app.models.imputation import Imputation
from app.models.billing_reports import ImportJob, ImportStatus
from app.services.audit import audit_log
from app.core.security import get_password_hash

from app.services.billing_reports_service._comun import _logger


# ═══════════════════════════════════════════════════════════════════════════════
# BULK IMPORT
# ═══════════════════════════════════════════════════════════════════════════════

IMPORT_TEMPLATES = {
    "projects": {
        "columns": ["code", "name", "client_name", "project_type", "status", "start_date",
                    "end_date_planned", "budget_amount", "billing_type", "pm_email"],
        "example": [["PRJ-001", "Proyecto Ejemplo", "Cliente SA", "consulting", "active",
                     "2025-01-01", "2025-06-30", "50000", "time_material", "pm@empresa.com"]],
    },
    "tasks": {
        "columns": ["project_code", "title", "description", "status", "priority",
                    "assignee_email", "due_date", "estimated_hours", "story_points"],
        "example": [["PRJ-001", "Tarea ejemplo", "Descripción...", "todo", "medium",
                     "dev@empresa.com", "2025-03-31", "8", "5"]],
    },
    "users": {
        "columns": ["username", "email", "full_name", "first_name", "last_name", "role",
                    "department", "job_title", "weekly_capacity_hours", "hourly_rate"],
        "example": [["jdoe", "jdoe@empresa.com", "John Doe", "John", "Doe", "employee",
                     "Engineering", "Developer", "40", "65"]],
    },
    "imputations": {
        "columns": ["user_email", "project_code", "date", "hours", "description",
                    "is_billable", "work_type"],
        "example": [["dev@empresa.com", "PRJ-001", "2025-01-15", "4",
                     "Desarrollo módulo login", "true", "development"]],
    },
    "expenses": {
        "columns": ["user_email", "project_code", "category", "description",
                    "amount", "currency", "expense_date", "is_billable"],
        "example": [["dev@empresa.com", "PRJ-001", "travel", "Vuelo Madrid-Barcelona",
                     "187.50", "EUR", "2025-01-20", "true"]],
    },
}


# ── Importación por CSV ──────────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `validate_import_csv` era complejidad 18: la
# comprobacion de campos obligatorios era una cadena de `elif` por tipo de
# entidad. Ahora es una tabla, y anadir un tipo importable es anadir una fila.
#
# `MAX_IMPORT_BYTES` estaba definido DOS VECES con el mismo valor, una en cada
# funcion. Dos constantes con el mismo nombre y sitios distintos acaban
# divergiendo: se sube a nivel de modulo.

# Tope del fichero que se acepta importar. 5 MB son del orden de 50.000 filas de
# proyecto; por encima de eso la importacion deberia ir por otro camino.
MAX_IMPORT_BYTES = 5 * 1024 * 1024

# Campos que no pueden venir vacios, por tipo de entidad, con el mensaje que se
# muestra. El orden de la tupla es el orden en que aparecen los errores.
_CAMPOS_OBLIGATORIOS = {
    "projects": (
        ("name", "Nombre obligatorio"),
        ("project_type", "Tipo obligatorio"),
    ),
    "users": (
        ("email", "Email obligatorio"),
        ("full_name", "Nombre completo obligatorio"),
    ),
    "imputations": (
        ("hours", "Horas obligatorio"),
    ),
}

# Campos que ademas tienen que ser un numero.
_CAMPOS_NUMERICOS = {
    "imputations": ("hours",),
}

# Cuantas filas se revisan al validar. Es una PREVISUALIZACION, no la validacion
# completa: `execute_import_csv` recorre todas las filas y reporta los fallos de
# cada una, asi que un error en la fila 500 no se pierde — se ve al importar, no
# al validar.
_FILAS_QUE_SE_VALIDAN = 10


def _errores_de_fila(entity_type: str, fila: dict, n: int) -> list[dict]:
    """Los errores de una fila: campos vacios y numeros que no lo son."""
    errores = []
    for campo, mensaje in _CAMPOS_OBLIGATORIOS.get(entity_type, ()):
        if not fila.get(campo):
            errores.append({"row": n, "field": campo, "error": mensaje})

    for campo in _CAMPOS_NUMERICOS.get(entity_type, ()):
        valor = fila.get(campo)
        if not valor:
            # Que falte ya lo ha dicho la comprobacion de obligatorios; decirlo
            # dos veces solo duplicaria el error en la pantalla.
            continue
        try:
            float(valor)
        except ValueError:
            errores.append({
                "row": n, "field": campo, "error": f"Valor inválido: {valor}",
            })
    return errores


def _leer_csv(content: bytes, que_hace: str, filename: str = "") -> tuple:
    """Decodifica y parsea el CSV. Devuelve (lector, filas).

    UTF-8 con BOM porque es lo que exporta Excel en Windows, que es de donde
    viene la mayoria de estos ficheros.
    """
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError("too_large")
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        _logger.warning(
            "CSV import %s rejected non-UTF8 payload%s",
            que_hace, f" (filename={filename})" if filename else "",
            exc_info=True,
        )
        raise ValueError("not_utf8")

    reader = csv.DictReader(io.StringIO(text))
    return reader, list(reader)


def validate_import_csv(entity_type: str, content: bytes) -> dict:
    """Comprueba un CSV antes de importarlo y devuelve una previsualizacion."""
    reader, rows = _leer_csv(content, "validation")
    if not rows:
        raise ValueError("empty")
    if entity_type not in IMPORT_TEMPLATES:
        raise ValueError("invalid_type")

    expected_cols = set(IMPORT_TEMPLATES[entity_type]["columns"])
    actual_cols = set(reader.fieldnames or [])
    missing = expected_cols - actual_cols
    extra = actual_cols - expected_cols

    warnings = []
    # Las columnas que faltan son un AVISO y no un error: la importacion usa
    # valores por defecto. Las que sobran tambien, y se ignoran.
    if missing:
        warnings.append(
            f"Columnas no encontradas: {missing}. Se usarán valores por defecto."
        )
    if extra:
        warnings.append(f"Columnas adicionales ignoradas: {extra}")

    errors = []
    for i, row in enumerate(rows[:_FILAS_QUE_SE_VALIDAN], 1):
        errors.extend(_errores_de_fila(entity_type, row, i))

    return {
        "valid": len(errors) == 0,
        "total_rows": len(rows),
        "errors": errors,
        "warnings": warnings,
        "preview": rows[:5],
    }


class _FilaRechazada(Exception):
    """Una fila que no se puede importar por una razon de negocio conocida.

    Se distingue de un error inesperado: un correo repetido es un caso previsto
    y se registra a nivel de depuracion, mientras que un fallo al construir la
    entidad se registra como aviso porque indica un dato con una forma que nadie
    habia previsto.
    """


def _defectos_de_proyecto(db: Session) -> dict:
    """Los valores por defecto de un proyecto, leidos UNA vez por importacion.

    Van aparte del constructor a proposito: leerlos por fila serian dos
    consultas de ajustes por cada linea del CSV, y un fichero de 50.000 filas
    haria 100.000. El original tambien los leia una sola vez.
    """
    from app.services.settings_service import get_runtime_str

    return {
        "project_type": get_runtime_str(db, "DEFAULT_PROJECT_TYPE", db.info.get("organization_id")) or settings.DEFAULT_PROJECT_TYPE,
        "billing_type": get_runtime_str(db, "DEFAULT_BILLING_TYPE", db.info.get("organization_id")) or settings.DEFAULT_BILLING_TYPE,
    }


def _crear_proyecto(db: Session, row: dict, i: int, current_user: User, ctx: dict):
    _proj_type = ctx["project_type"]
    _bill_type = ctx["billing_type"]
    return Project(
        # Sin codigo se genera uno por posicion: el codigo es obligatorio en el
        # modelo y una importacion no puede quedarse a medias por eso.
        code=row.get("code") or f"IMP-{i:04d}",
        name=row["name"],
        client_name=row.get("client_name"),
        project_type=row.get("project_type", _proj_type),
        status=row.get("status", "planning"),
        start_date=row.get("start_date") or None,
        end_date_planned=row.get("end_date_planned") or None,
        budget_amount=float(row["budget_amount"]) if row.get("budget_amount") else None,
        billing_type=row.get("billing_type", _bill_type),
        created_by=current_user.id,
    )


def _crear_usuario(db: Session, row: dict, i: int, current_user: User, ctx: dict):
    existing = db.query(User).filter(User.email == row["email"]).first()
    if existing:
        raise _FilaRechazada(f"Email ya existe: {row['email']}")
    return User(
        username=row.get("username") or row["email"].split("@")[0],
        email=row["email"],
        full_name=row["full_name"],
        first_name=row.get("first_name"),
        last_name=row.get("last_name"),
        role=row.get("role", "employee"),
        department=row.get("department"),
        job_title=row.get("job_title"),
        weekly_capacity_hours=(
            float(row["weekly_capacity_hours"]) if row.get("weekly_capacity_hours")
            else settings.DEFAULT_WEEKLY_CAPACITY_HOURS
        ),
        hourly_rate=float(row["hourly_rate"]) if row.get("hourly_rate") else None,
        # Seguridad: cada usuario importado recibe una contraseña ALEATORIA y única
        # (no la DEFAULT_USER_PASSWORD compartida y conocida). El usuario debe
        # establecerla vía "olvidé mi contraseña"; así una importación masiva no
        # crea cuentas accesibles con una credencial por defecto compartida.
        hashed_password=get_password_hash(secrets.token_urlsafe(24)),
    )


def _crear_imputacion(db: Session, row: dict, i: int, current_user: User, ctx: dict):
    user = db.query(User).filter(User.email == row.get("user_email")).first()
    project = db.query(Project).filter(Project.code == row.get("project_code")).first()
    if not user:
        raise ValueError(f"Usuario no encontrado: {row.get('user_email')}")
    if not project:
        raise ValueError(f"Proyecto no encontrado: {row.get('project_code')}")
    return Imputation(
        user_id=user.id,
        project_id=project.id,
        date=row["date"],
        hours=float(row["hours"]),
        description=row.get("description", ""),
        is_billable=row.get("is_billable", "true").lower() == "true",
        # Auditoria 2026-08/09. Aqui habia
        # `work_type=row.get("work_type", "development")` y **`Imputation` no
        # tenia esa columna**, asi que la importacion de imputaciones desde CSV
        # **fallaba fila por fila** con `TypeError`.
        #
        # La columna existe desde la revision 096. Y no se repone el respaldo a
        # «development»: si el CSV no trae el campo, la fila se queda sin tipo
        # de trabajo. El respaldo vive donde de verdad hace falta —en el
        # informe que lo lee— y ponerlo aqui seria inventar un dato que nadie
        # ha dicho.
        work_type=row.get("work_type") or None,
    )


# Que se construye por cada tipo importable. Los tres bloques del original eran
# el mismo bucle con un constructor distinto dentro; ahora el bucle es uno.
_CONSTRUCTORES = {
    "projects": _crear_proyecto,
    "users": _crear_usuario,
    "imputations": _crear_imputacion,
}

# Lo que hay que preparar una vez antes de recorrer las filas, por tipo. Los
# tipos que no necesitan nada no aparecen.
_PREPARACION = {
    "projects": _defectos_de_proyecto,
}


def _importar_filas(db: Session, entity_type: str, rows: list,
                    current_user: User) -> tuple[int, int, list]:
    """Importa fila a fila. Devuelve (correctas, fallidas, errores).

    Una fila mala NO aborta la importacion: se cuenta y se sigue. Es lo que
    permite que un fichero de mil filas con tres malas importe 997 en vez de
    ninguna, y que el trabajo acabe en estado «parcial» con el detalle de las
    tres.
    """
    construir = _CONSTRUCTORES.get(entity_type)
    if construir is None:
        return 0, 0, []

    preparar = _PREPARACION.get(entity_type)
    ctx = preparar(db) if preparar else {}

    correctas = 0
    fallidas = 0
    errores: list[dict] = []
    for i, row in enumerate(rows, 1):
        try:
            db.add(construir(db, row, i, current_user, ctx))
            correctas += 1
        except _FilaRechazada as rechazo:
            _logger.debug("CSV import row %s rejected for %s: %s", i, entity_type, rechazo)
            fallidas += 1
            errores.append({"row": i, "error": str(rechazo)[:100]})
        except Exception as e:
            _logger.warning(
                "CSV import row %s failed for %s: %s", i, entity_type, e, exc_info=True
            )
            fallidas += 1
            errores.append({"row": i, "error": str(e)[:100]})
    return correctas, fallidas, errores


def _estado_del_trabajo(correctas: int, fallidas: int):
    """Completado, parcial o fallido.

    «Parcial» existe para que una importacion con algunas filas malas no se
    presente como un exito ni como un fracaso: hay datos dentro y hay que
    revisar el detalle.
    """
    if fallidas == 0:
        return ImportStatus.completed
    return ImportStatus.partial if correctas > 0 else ImportStatus.failed


def execute_import_csv(entity_type: str, content: bytes, filename: str, current_user: User, db: Session) -> dict:
    """Importa un CSV de verdad, creando el registro de trabajo."""
    _reader, rows = _leer_csv(content, "execution", filename)

    job = ImportJob(
        entity_type=entity_type,
        filename=filename,
        status=ImportStatus.processing,
        total_rows=len(rows),
        created_by=current_user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    succeeded, failed_rows, errors = _importar_filas(
        db, entity_type, rows, current_user
    )

    job.status = _estado_del_trabajo(succeeded, failed_rows)
    job.processed = len(rows)
    job.succeeded = succeeded
    job.failed_rows = failed_rows
    # Se guardan como maximo 50 errores: el campo es texto y un fichero entero
    # mal formado generaria un JSON de megabytes.
    job.errors = json.dumps(errors[:50])
    job.completed_at = datetime.now(timezone.utc)
    try:
        db.commit()
        audit_log(db, current_user, "IMPORT", entity_type, job.id, filename,
                  new_values={"succeeded": succeeded, "failed": failed_rows})
        db.commit()
    except Exception:
        _logger.exception("Fallo finalizando import CSV (entity=%s, job=%s)", entity_type, job.id)
        db.rollback()
        raise RuntimeError("finalize_failed")

    return {
        "job_id": job.id,
        "status": job.status,
        "total": len(rows), "succeeded": succeeded, "failed": failed_rows,
        "errors": errors[:10],
    }
