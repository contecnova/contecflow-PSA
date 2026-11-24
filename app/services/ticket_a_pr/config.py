"""Configuración de «Del ticket al PR» por empresa (docs/integraciones/TICKET_A_PR.md §Configuración).

Tres sitios, cada uno con lo suyo:

- **Encendido**: el módulo `ticket_pr` de la gobernanza de IA (sin fila,
  APAGADO: `governance_service.APAGADOS_SIN_CONFIGURAR`).
- **Ajustes** de la empresa: `app_settings`, clave `ticket_pr.config` (JSON),
  sobre los valores de la plataforma (`TICKET_PR_*` en `Settings`/`.env`):
  motor, imagen y versión fijada, proveedor y modelo de IA, ficheros
  protegidos, límites, tests, salida extra (registros de paquetes), órdenes de
  shell permitidas y plantillas de instrucción. Cada cambio, en `audit_log`.
- **Credenciales** (cifradas): almacén de integraciones, proveedor `ticket_pr`
  (GitHub App: id, instalación y clave privada; GitLab: URL y token de
  proyecto). Nunca salen en claro ni llegan al contenedor del agente.

Los repositorios permitidos por proyecto están en `ticket_pr_repos` (`servicio`).
"""
from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)

MODULO = "ticket_pr"
CLAVE = "ticket_pr.config"
PROVEEDOR_DE_CREDENCIALES = "ticket_pr"
MOTORES = ("opencode",)
PROVEEDORES_GIT = ("github", "gitlab")
TIPOS_DE_CAMBIO = ("normal", "standard_if_fits")

#: Ficheros que el agente nunca puede tocar (además de los que añada la empresa).
#: Sintaxis de glob: `*` dentro de un directorio, `**` cualquier profundidad; sin
#: `/`, casa con el nombre del fichero en cualquier carpeta.
PROTEGIDOS_DE_FABRICA: tuple[str, ...] = (
    ".github/workflows/**", ".github/actions/**", ".github/CODEOWNERS", "CODEOWNERS",
    ".gitlab-ci.yml", ".gitlab/**", ".circleci/**", "Jenkinsfile", "azure-pipelines.yml",
    "bitbucket-pipelines.yml", ".travis.yml", ".drone.yml", ".buildkite/**",
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "id_rsa*", "id_ed25519*",
    "**/secrets/**", "*.tfvars", ".npmrc", ".pypirc", ".netrc", ".git/**", ".gitmodules",
)

#: Ficheros que ni siquiera se copian al contenedor (el agente no los puede leer).
NO_SE_COPIAN: tuple[str, ...] = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "id_rsa*", "id_ed25519*",
    ".npmrc", ".pypirc", ".netrc", "*.tfvars", "**/secrets/**",
)

PLANTILLA_PLAN = (
    "Eres un agente de código trabajando en el repositorio {repo} (rama {rama}).\n"
    "Origen: {tipo} {codigo} — {titulo}\n\n"
    "Descripción (los datos personales están ocultos):\n{descripcion}\n\n"
    "FASE PLAN (solo lectura): NO modifiques ningún fichero ni ejecutes órdenes que cambien nada. "
    "Analiza el código y propón un plan breve: causa probable, ficheros que cambiarías y por qué, "
    "riesgos y cómo se prueba. Termina con una lista «FICHEROS:» con una ruta por línea."
)
PLANTILLA_BUILD = (
    "Eres un agente de código trabajando en el repositorio {repo} (rama {rama}).\n\n"
    "Encargo revisado por una persona (los datos personales están ocultos):\n{instruccion}\n\n"
    "Plan aprobado por una persona:\n{plan}\n\n"
    "FASE BUILD: aplica SOLO los cambios del plan aprobado, mínimos y revisables. No toques la "
    "integración continua, los secretos ni ficheros de configuración de despliegue. No añadas "
    "credenciales. Al terminar, resume en pocas líneas qué has cambiado y por qué."
)


def _settings():
    from app.core.config import settings
    return settings


def por_defecto() -> dict[str, Any]:
    """Los valores de la plataforma (`TICKET_PR_*`)."""
    s = _settings()
    return {
        "engine": "opencode",
        "engine_image": s.TICKET_PR_ENGINE_IMAGE,
        "engine_version": s.TICKET_PR_ENGINE_VERSION,
        "proxy_image": s.TICKET_PR_EGRESS_PROXY_IMAGE,
        "ai_provider_id": None,
        "model": None,
        "protected_paths": [],
        "run_tests": False,
        "block_on_test_failure": True,
        "extra_egress_hosts": [],
        "bash_allow": [],
        "plan_requires_other_person": False,
        "change_type": "normal",
        "standard_model_id": None,
        "templates": {"plan": PLANTILLA_PLAN, "build": PLANTILLA_BUILD},
        "limits": {
            "max_runs_per_day": s.TICKET_PR_MAX_RUNS_PER_DAY,
            "max_cost_per_day_usd": s.TICKET_PR_MAX_COST_PER_DAY_USD,
            "max_concurrent": s.TICKET_PR_MAX_CONCURRENT,
            "plan_timeout_min": s.TICKET_PR_PLAN_TIMEOUT_MIN,
            "build_timeout_min": s.TICKET_PR_BUILD_TIMEOUT_MIN,
            "cpus": s.TICKET_PR_CPUS,
            "memory_mb": s.TICKET_PR_MEMORY_MB,
            "max_changed_files": s.TICKET_PR_MAX_CHANGED_FILES,
            "max_diff_kb": s.TICKET_PR_MAX_DIFF_KB,
            "max_repo_mb": s.TICKET_PR_MAX_REPO_MB,
        },
    }


#: Límites: (mínimo, máximo) de cada uno; fuera, 422.
RANGOS = {
    "max_runs_per_day": (0, 1000), "max_cost_per_day_usd": (0.0, 10000.0), "max_concurrent": (1, 20),
    "plan_timeout_min": (1, 120), "build_timeout_min": (1, 240), "cpus": (0.25, 16.0),
    "memory_mb": (256, 65536), "max_changed_files": (1, 1000), "max_diff_kb": (1, 20480),
    "max_repo_mb": (1, 4096),
}


# ── Encendido ────────────────────────────────────────────────────────────────

def encendido(db: Session, org: Optional[str]) -> bool:
    from app.services.governance_service import config_de_modulo
    fila = config_de_modulo(db, org, MODULO)
    return bool(fila and fila.is_enabled)


def encender(db: Session, org: Optional[str], usuario, valor: bool) -> None:
    """Enciende o apaga el módulo para la empresa (confirma: `upsert_ai_module_config`)."""
    from app.services import governance_service as _gsvc
    _gsvc.upsert_ai_module_config(db, org, MODULO, bool(valor), usuario.id)


# ── Ajustes ──────────────────────────────────────────────────────────────────

def _fila(db: Session, org: Optional[str]):
    from app.models.settings import AppSetting
    q = db.query(AppSetting).filter(AppSetting.key == CLAVE)
    q = q.filter(AppSetting.organization_id == org) if org else q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def leer(db: Session, org: Optional[str]) -> dict:
    """La configuración de la empresa sobre los valores de la plataforma."""
    cfg = copy.deepcopy(por_defecto())
    fila = _fila(db, org)
    if fila is not None and fila.value:
        try:
            guardado = json.loads(fila.value) or {}
        except ValueError:
            logger.warning("ticket_pr.config ilegible en la empresa %s", org)
            guardado = {}
        for k, v in guardado.items():
            if k in cfg and isinstance(cfg[k], dict) and isinstance(v, dict):
                cfg[k].update(v)
            elif k in cfg:
                cfg[k] = v
    return cfg


def _no_valida(campo: str):
    return error(422, "ticket_pr_config_no_valida", campo=campo)


def _lista_de_textos(valor, campo: str, maximo: int = 100, largo: int = 200) -> list[str]:
    if not isinstance(valor, list) or len(valor) > maximo:
        raise _no_valida(campo)
    salida = []
    for x in valor:
        texto = str(x or "").strip()
        if not texto:
            continue
        if len(texto) > largo or "\n" in texto or "\x00" in texto:
            raise _no_valida(campo)
        salida.append(texto)
    return list(dict.fromkeys(salida))


_HOST = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")
_IMAGEN = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,250}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$|^sha256:[a-f0-9]{64}$")


def _hosts(valor) -> list[str]:
    """Hosts extra de salida (registros de paquetes). Solo nombres; pasan el guardia SSRF."""
    from app.core.outbound_url import validar_host_saliente
    hosts = [h.lower() for h in _lista_de_textos(valor, "extra_egress_hosts", 30, 253)]
    for h in hosts:
        if not _HOST.match(h):
            raise _no_valida("extra_egress_hosts")
        validar_host_saliente(h, field="extra_egress_hosts")
    return hosts


def validar(datos: dict) -> dict:
    """Solo las claves conocidas, con su tipo y sus límites."""
    if not isinstance(datos, dict):
        raise _no_valida("*")
    limpio: dict = {}
    if "engine" in datos:
        if datos["engine"] not in MOTORES:
            raise _no_valida("engine")
        limpio["engine"] = datos["engine"]
    for campo, patron in (("engine_image", _IMAGEN), ("proxy_image", re.compile(r"^[a-z0-9][a-z0-9._/:-]{0,250}$"))):
        if campo in datos:
            valor = str(datos[campo] or "").strip()
            if not patron.match(valor):
                raise _no_valida(campo)
            limpio[campo] = valor
    if "engine_version" in datos:
        version = str(datos["engine_version"] or "").strip()
        # Fijada: ni vacía ni «latest» (una imagen que cambia sola no es auditable).
        if version and (version.lower() == "latest" or not _VERSION.match(version)):
            raise error(422, "ticket_pr_version_sin_fijar")
        limpio["engine_version"] = version
    if "ai_provider_id" in datos:
        limpio["ai_provider_id"] = (str(datos["ai_provider_id"]).strip()[:36] or None) if datos["ai_provider_id"] else None
    if "model" in datos:
        modelo = str(datos["model"] or "").strip()
        if len(modelo) > 120 or (modelo and not re.match(r"^[A-Za-z0-9._:/@-]+$", modelo)):
            raise _no_valida("model")
        limpio["model"] = modelo or None
    if "protected_paths" in datos:
        limpio["protected_paths"] = _lista_de_textos(datos["protected_paths"], "protected_paths")
    if "extra_egress_hosts" in datos:
        limpio["extra_egress_hosts"] = _hosts(datos["extra_egress_hosts"])
    if "bash_allow" in datos:
        limpio["bash_allow"] = _lista_de_textos(datos["bash_allow"], "bash_allow", 50, 200)
    for campo in ("run_tests", "block_on_test_failure", "plan_requires_other_person"):
        if campo in datos:
            limpio[campo] = bool(datos[campo])
    if "change_type" in datos:
        if datos["change_type"] not in TIPOS_DE_CAMBIO:
            raise _no_valida("change_type")
        limpio["change_type"] = datos["change_type"]
    if "standard_model_id" in datos:
        limpio["standard_model_id"] = (str(datos["standard_model_id"]).strip()[:36] or None) \
            if datos["standard_model_id"] else None
    if "templates" in datos:
        t = datos["templates"] if isinstance(datos["templates"], dict) else None
        if t is None:
            raise _no_valida("templates")
        plantillas = {}
        for fase in ("plan", "build"):
            if fase in t:
                texto = str(t[fase] or "").strip()
                if not texto or len(texto) > 8000:
                    raise _no_valida(f"templates.{fase}")
                plantillas[fase] = texto
        limpio["templates"] = plantillas
    if "limits" in datos:
        lim = datos["limits"] if isinstance(datos["limits"], dict) else None
        if lim is None:
            raise _no_valida("limits")
        salida = {}
        for clave, (minimo, maximo) in RANGOS.items():
            if clave not in lim:
                continue
            try:
                valor = float(lim[clave]) if isinstance(minimo, float) else int(lim[clave])
            except (TypeError, ValueError):
                raise _no_valida(f"limits.{clave}") from None
            if not minimo <= valor <= maximo:
                raise _no_valida(f"limits.{clave}")
            salida[clave] = valor
        limpio["limits"] = salida
    return limpio


def guardar(db: Session, org: Optional[str], usuario, datos: dict) -> dict:
    """Guarda (auditado, antes y después). No confirma."""
    from app.models.settings import AppSetting
    from app.services.audit import audit_log
    antes = leer(db, org)
    limpio = validar(datos)
    nuevo = copy.deepcopy(antes)
    for k, v in limpio.items():
        if isinstance(nuevo.get(k), dict) and isinstance(v, dict):
            nuevo[k].update(v)
        else:
            nuevo[k] = v
    fila = _fila(db, org)
    if fila is None:
        fila = AppSetting(key=CLAVE, organization_id=org, description="Del ticket al PR (docs/integraciones/TICKET_A_PR.md)")
        db.add(fila)
    fila.value = json.dumps(nuevo, ensure_ascii=False)
    audit_log(db, usuario, "UPDATE", "ticket_pr_config", org, CLAVE,
              old_values={k: antes.get(k) for k in limpio}, new_values=limpio, metadata={"canal": "settings"})
    return nuevo


# ── Lo que se deriva ─────────────────────────────────────────────────────────

def imagen_del_motor(cfg: dict) -> str:
    """`imagen:versión` fijada. Sin versión o con `latest`, 409: no se ejecuta nada."""
    imagen = str(cfg.get("engine_image") or "").strip()
    version = str(cfg.get("engine_version") or "").strip()
    if not imagen or not version or version.lower() == "latest":
        raise error(409, "ticket_pr_version_sin_fijar")
    return f"{imagen}@{version}" if version.startswith("sha256:") else f"{imagen}:{version}"


def protegidos(cfg: dict) -> tuple[str, ...]:
    return tuple(dict.fromkeys(PROTEGIDOS_DE_FABRICA + tuple(cfg.get("protected_paths") or ())))


def limite(cfg: dict, clave: str):
    lim = cfg.get("limits") or {}
    return lim.get(clave, por_defecto()["limits"][clave])


def credenciales_git(db: Session, org: Optional[str]) -> dict:
    """Las credenciales Git de la empresa (descifradas, solo en memoria del servidor)."""
    from app.services.integration_credentials_service import get_provider_config
    return get_provider_config(db, PROVEEDOR_DE_CREDENCIALES, org)


def resumen_de_credenciales(db: Session, org: Optional[str]) -> dict:
    """Qué está configurado (nunca los valores secretos)."""
    from app.services.integration_credentials_service import describe_provider
    return describe_provider(db, PROVEEDOR_DE_CREDENCIALES, org)
