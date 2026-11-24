"""Flujo de «Del ticket al PR» (docs/integraciones/TICKET_A_PR.md).

    lanzar ──► PLAN (contenedor, solo lectura) ──► una persona aprueba / rechaza
           ──► BUILD (contenedor) ──► diff comprobado ──► [tests] ──► rama + PR
           ──► cambio ITSM (normal, o estándar si encaja) ──► CAB
           ──► estado `contecflow/cab` del PR: pending → success / failure
           ──► una PERSONA fusiona en GitHub/GitLab (contecflow nunca fusiona)

Reglas:

- módulo `ticket_pr` encendido en la empresa (apagado sin fila);
- capacidades literales: `ticket_pr.ver`, `ticket_pr.lanzar`,
  `ticket_pr.aprobar_plan`, `ticket_pr.config` (en el endpoint);
- el origen (ticket o tarea) tiene que ser VISIBLE para quien lanza o mira
  (`scope_ticket_query`, proyectos visibles); el repositorio, uno permitido de
  su proyecto; todo acotado por empresa;
- límites por empresa y día (ejecuciones y coste), concurrencia, y el tope
  diario de IA de la empresa;
- sin Docker no se ejecuta nada (y se dice);
- auditoría (`audit_log`, recurso `ticket_pr_run`): lanzamiento, aprobación o
  rechazo del plan, bloqueo, apertura del PR, vínculo con el cambio,
  sincronización con el CAB y cancelación;
- coste de IA en `ai_usage_logs` (módulo `ticket_pr`, tope diario de la empresa)
  e imputado al proyecto en la propia ejecución (`cost_usd`, `project_id`);
- segregación: el cambio lo pide quien lanzó (`requester_id`) y el CAB no le
  deja votar el suyo (`cab_workflow_service`, `exigir_que_no_sea_suyo`).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.codigos_de_error import ErrorConCodigo, error
from app.core.errores import ErrorDeDominio
from app.models.ticket_a_pr import ACTIVOS, FINALES, TicketPrRepo, TicketPrRun
from app.services.ticket_a_pr import config as _config
from app.services.ticket_a_pr import diff as _diff
from app.services.ticket_a_pr import git_clientes, instruccion as _instr, motor as _motor, sandbox

logger = logging.getLogger(__name__)

RECURSO = "ticket_pr_run"
ORIGENES = ("ticket", "task")
MAX_LOG = 256 * 1024
_RAMA = re.compile(r"^(?!/)(?!.*\.\.)(?!.*//)(?!.*@\{)[A-Za-z0-9._/-]{1,200}(?<!/)(?<!\.lock)$")
_REPO = {"github": re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$"),
         "gitlab": re.compile(r"^[A-Za-z0-9_.-]{1,100}(/[A-Za-z0-9_.-]{1,100}){1,9}$")}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _inicio_de_hoy() -> datetime:
    return _ahora().replace(hour=0, minute=0, second=0, microsecond=0)


def _org(usuario) -> Optional[str]:
    return getattr(usuario, "organization_id", None)


def _json(valor) -> Optional[str]:
    return json.dumps(valor, ensure_ascii=False, default=str) if valor is not None else None


def _de_json(texto: Optional[str], defecto=None):
    if not texto:
        return defecto
    try:
        return json.loads(texto)
    except ValueError:
        return defecto


def _auditar(db: Session, usuario, accion: str, run: TicketPrRun, extra: Optional[dict] = None,
             ip: Optional[str] = None, ua: Optional[str] = None) -> None:
    from app.services.audit import audit_log
    audit_log(db, usuario, accion, RECURSO, run.id, run.source_ref,
              metadata={"canal": "ticket_pr", "empresa": run.organization_id, "origen": run.source_type,
                        "ticket_id": run.ticket_id, "task_id": run.task_id, "project_id": run.project_id,
                        "repo": run.repo_full_name, "estado": run.status, **(extra or {})},
              ip_address=ip, user_agent=ua)


def _fijar_estado(run: TicketPrRun, estado: str, codigo: Optional[str] = None, params: Optional[dict] = None) -> None:
    run.status = estado
    run.status_code = codigo
    run.status_params = _json(params) if params else None
    if estado in FINALES and run.finished_at is None:
        run.finished_at = _ahora()


def _anadir_log(db: Session, run: TicketPrRun, texto: str, usuario=None) -> None:
    """Log del contenedor con los datos personales ocultos y recortado (lo último)."""
    if not texto:
        return
    oculto = _instr.ocultar(texto, None, None)
    # La clave del modelo nunca queda en el log aunque el agente la imprima.
    for secreto in getattr(run, "_secretos", ()) or ():
        if secreto and len(secreto) >= 8:
            oculto = oculto.replace(secreto, "[OCULTO]")
    run.log_redacted = ((run.log_redacted or "") + "\n" + oculto)[-MAX_LOG:]


# ── Origen, visibilidad y repositorios ───────────────────────────────────────

def obtener_origen(db: Session, usuario, tipo: str, origen_id: str):
    """El ticket o la tarea si `usuario` lo ve; 404 si no (también de otra empresa)."""
    if tipo == "ticket":
        from app.models.service_desk import Ticket
        from app.services.service_desk.scoping import scope_ticket_query
        origen = scope_ticket_query(db.query(Ticket), db, usuario).filter(Ticket.id == origen_id).first()
    elif tipo == "task":
        from app.models.task import Task
        from app.services.politica_de_visibilidad import acotar_a_proyectos_visibles
        q = db.query(Task).filter(Task.id == origen_id)
        origen = acotar_a_proyectos_visibles(q, Task.project_id, db, usuario).first()
    else:
        raise error(422, "ticket_pr_origen_no_valido", tipo=str(tipo)[:20])
    if origen is None or (_org(usuario) and getattr(origen, "organization_id", None) not in (None, _org(usuario))):
        raise ErrorDeDominio(404)
    return origen


def _referencia(tipo: str, origen) -> str:
    return (origen.number if tipo == "ticket" else origen.code) or origen.id[:8]


def repos_del_proyecto(db: Session, org: Optional[str], project_id: Optional[str]) -> list[TicketPrRepo]:
    if not project_id:
        return []
    return db.query(TicketPrRepo).filter(TicketPrRepo.project_id == project_id, TicketPrRepo.is_active == True,  # noqa: E712
                                         TicketPrRepo.organization_id == org).order_by(TicketPrRepo.repo_full_name).all()


def serializar_repo(r: TicketPrRepo) -> dict:
    return {"id": r.id, "project_id": r.project_id, "provider": r.provider, "repo_full_name": r.repo_full_name,
            "default_branch": r.default_branch, "test_command": r.test_command, "is_active": bool(r.is_active),
            "created_at": r.created_at.isoformat() if r.created_at else None}


def validar_rama(rama: str) -> str:
    rama = (rama or "").strip()
    if not _RAMA.match(rama) or rama.startswith("-"):
        raise error(422, "ticket_pr_rama_no_valida", rama=rama[:60])
    return rama


def _validar_repo(datos: dict, parcial: bool = False) -> dict:
    limpio: dict = {}
    proveedor = datos.get("provider")
    if proveedor is not None or not parcial:
        if proveedor not in _config.PROVEEDORES_GIT:
            raise error(422, "ticket_pr_proveedor_git_no_valido", proveedor=str(proveedor)[:20])
        limpio["provider"] = proveedor
    if "repo_full_name" in datos or not parcial:
        nombre = str(datos.get("repo_full_name") or "").strip().strip("/")
        patron = _REPO.get(limpio.get("provider") or datos.get("_provider_actual") or "gitlab")
        if not patron.match(nombre) or ".." in nombre:
            raise error(422, "ticket_pr_repo_no_valido", repo=nombre[:80])
        limpio["repo_full_name"] = nombre
    if "default_branch" in datos or not parcial:
        limpio["default_branch"] = validar_rama(datos.get("default_branch") or "main")
    if "test_command" in datos:
        orden = str(datos.get("test_command") or "").strip()
        if len(orden) > 500 or "\x00" in orden or "\n" in orden:
            raise error(422, "ticket_pr_config_no_valida", campo="test_command")
        limpio["test_command"] = orden or None
    if "is_active" in datos:
        limpio["is_active"] = bool(datos["is_active"])
    return limpio


def listar_repos(db: Session, usuario, project_id: Optional[str] = None) -> list[dict]:
    q = db.query(TicketPrRepo).filter(TicketPrRepo.organization_id == _org(usuario))
    if project_id:
        q = q.filter(TicketPrRepo.project_id == project_id)
    return [serializar_repo(r) for r in q.order_by(TicketPrRepo.repo_full_name).all()]


def _proyecto_de_la_empresa(db: Session, usuario, project_id: str):
    from app.models.project import Project
    p = db.query(Project).filter(Project.id == project_id).first()
    if p is None or (p.organization_id and p.organization_id != _org(usuario)):
        raise ErrorDeDominio(404)
    return p


def crear_repo(db: Session, usuario, datos: dict) -> TicketPrRepo:
    from app.services.audit import audit_log
    _proyecto_de_la_empresa(db, usuario, str(datos.get("project_id") or ""))
    limpio = _validar_repo(datos)
    existe = db.query(TicketPrRepo).filter(TicketPrRepo.organization_id == _org(usuario),
                                           TicketPrRepo.project_id == datos["project_id"],
                                           TicketPrRepo.provider == limpio["provider"],
                                           TicketPrRepo.repo_full_name == limpio["repo_full_name"]).first()
    if existe is not None:
        raise error(409, "ticket_pr_repo_duplicado", repo=limpio["repo_full_name"])
    repo = TicketPrRepo(organization_id=_org(usuario), project_id=datos["project_id"], created_by=usuario.id,
                        is_active=True, **{k: v for k, v in limpio.items() if k != "is_active"})
    db.add(repo)
    db.flush()
    audit_log(db, usuario, "CREATE", "ticket_pr_repo", repo.id, repo.repo_full_name, new_values=serializar_repo(repo),
              metadata={"canal": "settings"})
    return repo


def _repo_de_la_empresa(db: Session, usuario, repo_id: str) -> TicketPrRepo:
    repo = db.query(TicketPrRepo).filter(TicketPrRepo.id == repo_id,
                                         TicketPrRepo.organization_id == _org(usuario)).first()
    if repo is None:
        raise ErrorDeDominio(404)
    return repo


def editar_repo(db: Session, usuario, repo_id: str, datos: dict) -> TicketPrRepo:
    from app.services.audit import audit_log
    repo = _repo_de_la_empresa(db, usuario, repo_id)
    antes = serializar_repo(repo)
    limpio = _validar_repo({**datos, "_provider_actual": repo.provider}, parcial=True)
    for k, v in limpio.items():
        setattr(repo, k, v)
    audit_log(db, usuario, "UPDATE", "ticket_pr_repo", repo.id, repo.repo_full_name, old_values=antes,
              new_values=serializar_repo(repo), metadata={"canal": "settings"})
    return repo


def borrar_repo(db: Session, usuario, repo_id: str) -> None:
    """Se desactiva (las ejecuciones lo siguen referenciando)."""
    from app.services.audit import audit_log
    repo = _repo_de_la_empresa(db, usuario, repo_id)
    repo.is_active = False
    audit_log(db, usuario, "DELETE", "ticket_pr_repo", repo.id, repo.repo_full_name, metadata={"canal": "settings"})


# ── Modelo, límites y motor ──────────────────────────────────────────────────

def _proveedor_de_ia(db: Session, org: Optional[str], cfg: dict):
    from app.services.ai_provider_service.despacho import _seleccionar_proveedor
    return _seleccionar_proveedor(db, cfg.get("ai_provider_id"), False, org)


def modelo_de_la_empresa(db: Session, org: Optional[str], cfg: dict) -> _motor.Modelo:
    """El proveedor de IA de la empresa (o el elegido en la configuración) y su modelo."""
    from app.core.encryption import decrypt_value
    p = _proveedor_de_ia(db, org, cfg)
    if p is None:
        raise ErrorConCodigo("ticket_pr_sin_modelo")
    tipo = getattr(p.provider, "value", p.provider)
    modelo = cfg.get("model") or p.default_model
    if not modelo:
        raise ErrorConCodigo("ticket_pr_sin_modelo")
    clave = decrypt_value(p.api_key) if p.api_key else ""
    return _motor.Modelo(proveedor=str(tipo), modelo=str(modelo), api_key=clave or "",
                         base_url=p.api_base_url or "", provider_id=p.id)


def _limites(cfg: dict, fase: str) -> sandbox.Limites:
    from app.core.config import settings
    minutos = _config.limite(cfg, "plan_timeout_min" if fase == "plan" else "build_timeout_min")
    return sandbox.Limites(cpus=float(_config.limite(cfg, "cpus")), memoria_mb=int(_config.limite(cfg, "memory_mb")),
                           procesos=int(settings.TICKET_PR_PIDS_LIMIT), segundos=int(minutos) * 60)


def _hosts_extra(cfg: dict) -> list[tuple[str, int]]:
    return [(h, 443) for h in cfg.get("extra_egress_hosts") or []]


def uso_de_hoy(db: Session, org: Optional[str]) -> dict:
    hoy = _inicio_de_hoy()
    base = db.query(TicketPrRun).filter(TicketPrRun.organization_id == org, TicketPrRun.created_at >= hoy)
    return {
        "runs": base.count(),
        "cost_usd": float(db.query(func.coalesce(func.sum(TicketPrRun.cost_usd), 0)).filter(
            TicketPrRun.organization_id == org, TicketPrRun.created_at >= hoy).scalar() or 0),
        "active": db.query(TicketPrRun).filter(TicketPrRun.organization_id == org,
                                               TicketPrRun.status.in_(tuple(ACTIVOS))).count(),
    }


def exigir_limites(db: Session, org: Optional[str], cfg: dict, nueva: bool = True) -> None:
    """Ejecuciones y coste por empresa y día, concurrencia y tope diario de IA de la empresa."""
    uso = uso_de_hoy(db, org)
    max_runs = int(_config.limite(cfg, "max_runs_per_day"))
    if nueva and uso["runs"] >= max_runs:
        raise error(429, "ticket_pr_limite_diario", max=max_runs)
    max_coste = float(_config.limite(cfg, "max_cost_per_day_usd"))
    if max_coste > 0 and uso["cost_usd"] >= max_coste:
        raise error(429, "ticket_pr_limite_de_coste", max=f"{max_coste:.2f}")
    max_activas = int(_config.limite(cfg, "max_concurrent"))
    if uso["active"] >= max_activas:
        raise error(409, "ticket_pr_limite_de_concurrencia", max=max_activas)
    from app.services.ai_provider_service.gasto import PresupuestoDeIAAgotado, _exigir_presupuesto
    try:
        _exigir_presupuesto(db, org)
    except PresupuestoDeIAAgotado as exc:
        raise error(429, exc.codigo, **exc.params) from exc


def exigir_docker() -> None:
    """Sin Docker no se ejecuta NADA (salvo el motor simulado de los tests)."""
    if _motor.motor_forzado():
        return
    ok, _ = sandbox.disponible()
    if not ok:
        raise error(409, "ticket_pr_docker_no_disponible")


def _apuntar_uso(db: Session, run: TicketPrRun, res: _motor.ResultadoMotor, modelo: Optional[_motor.Modelo]) -> None:
    """Tokens, coste y horas en la ejecución (imputados al proyecto) y en `ai_usage_logs`."""
    run.tokens_in = (run.tokens_in or 0) + int(res.tokens_in or 0)
    run.tokens_out = (run.tokens_out or 0) + int(res.tokens_out or 0)
    run.cost_usd = float(run.cost_usd or 0) + float(res.coste_usd or 0)
    run.agent_seconds = (run.agent_seconds or 0) + int(res.segundos or 0)
    if modelo is None or not (res.tokens_in or res.tokens_out or res.coste_usd):
        return
    from app.models.ai_providers import AIUsageLog
    db.add(AIUsageLog(organization_id=run.organization_id, provider_id=modelo.provider_id, user_id=run.launched_by,
                      module=_config.MODULO, model=modelo.modelo, tokens_in=int(res.tokens_in or 0),
                      tokens_out=int(res.tokens_out or 0), cost_usd=float(res.coste_usd or 0),
                      latency_ms=int(res.segundos or 0) * 1000, success=bool(res.ok),
                      error_msg=None if res.ok else (res.codigo or "")[:200]))


# ── Disponibilidad y lanzamiento ─────────────────────────────────────────────

def estado_de_la_empresa(db: Session, usuario) -> dict:
    from app.core import capacidades as _capacidades
    org = _org(usuario)
    ok, version = (True, "simulado") if _motor.motor_forzado() else sandbox.disponible()
    return {
        "enabled": _config.encendido(db, org),
        "docker": {"available": ok, "version": version},
        "can_launch": _capacidades.tiene(db, usuario, "ticket_pr.lanzar"),
        "can_approve": _capacidades.tiene(db, usuario, "ticket_pr.aprobar_plan"),
        "can_config": _capacidades.tiene(db, usuario, "ticket_pr.config"),
    }


def disponibilidad(db: Session, usuario, tipo: str, origen_id: str) -> dict:
    """Lo que necesita el botón «Proponer arreglo con IA» y el panel de ejecuciones del ticket o tarea."""
    from app.core import capacidades as _capacidades
    origen = obtener_origen(db, usuario, tipo, origen_id)
    org = _org(usuario)
    activo = _config.encendido(db, org)
    repos = repos_del_proyecto(db, org, origen.project_id) if activo else []
    puede = _capacidades.tiene(db, usuario, "ticket_pr.lanzar")
    motivo = None
    if not activo:
        motivo = "ticket_pr_apagado"
    elif not origen.project_id:
        motivo = "ticket_pr_sin_proyecto"
    elif not repos:
        motivo = "ticket_pr_sin_repositorio"
    elif not puede:
        motivo = "ticket_pr_sin_capacidad"
    return {
        "enabled": activo,
        "can_launch": bool(activo and repos and puede),
        "can_approve": _capacidades.tiene(db, usuario, "ticket_pr.aprobar_plan"),
        "reason": motivo,
        "repos": [serializar_repo(r) for r in repos],
        # El historial se ve aunque el módulo se haya apagado después (trazabilidad).
        "runs": [serializar(db, usuario, r) for r in _ejecuciones_del_origen(db, tipo, origen.id)],
    }


def _ejecuciones_del_origen(db: Session, tipo: str, origen_id: str) -> list[TicketPrRun]:
    col = TicketPrRun.ticket_id if tipo == "ticket" else TicketPrRun.task_id
    return db.query(TicketPrRun).filter(col == origen_id).order_by(TicketPrRun.created_at.desc()).limit(50).all()


def _repo_para(db: Session, usuario, origen, repo_id: str) -> TicketPrRepo:
    repo = db.query(TicketPrRepo).filter(TicketPrRepo.id == repo_id, TicketPrRepo.organization_id == _org(usuario),
                                         TicketPrRepo.is_active == True).first()  # noqa: E712
    if repo is None or not origen.project_id or repo.project_id != origen.project_id:
        raise error(422, "ticket_pr_repo_no_permitido")
    return repo


def proponer_instruccion(db: Session, usuario, tipo: str, origen_id: str, repo_id: str, rama: Optional[str]) -> dict:
    org = _org(usuario)
    if not _config.encendido(db, org):
        raise error(409, "ticket_pr_apagado")
    origen = obtener_origen(db, usuario, tipo, origen_id)
    repo = _repo_para(db, usuario, origen, repo_id)
    rama = validar_rama(rama or repo.default_branch)
    cfg = _config.leer(db, org)
    return {"instruction": _instr.instruccion_de_plan(db, usuario, origen, repo.repo_full_name, rama, cfg),
            "base_branch": rama, "repo_id": repo.id}


def lanzar(db: Session, usuario, tipo: str, origen_id: str, repo_id: str, rama: Optional[str],
           instruccion: Optional[str], ip: Optional[str] = None, ua: Optional[str] = None) -> TicketPrRun:
    """Crea la ejecución (auditada) y encola la fase PLAN."""
    org = _org(usuario)
    if not _config.encendido(db, org):
        raise error(409, "ticket_pr_apagado")
    origen = obtener_origen(db, usuario, tipo, origen_id)
    repo = _repo_para(db, usuario, origen, repo_id)
    rama = validar_rama(rama or repo.default_branch)
    cfg = _config.leer(db, org)
    imagen = _config.imagen_del_motor(cfg)
    try:
        modelo = modelo_de_la_empresa(db, org, cfg)
    except ErrorConCodigo as exc:
        raise error(409, exc.codigo, **exc.params) from exc
    exigir_docker()
    exigir_limites(db, org, cfg)
    texto = (instruccion or "").strip() or _instr.instruccion_de_plan(db, usuario, origen, repo.repo_full_name, rama, cfg)
    texto = _instr.ocultar(texto, db, usuario)[:_instr.MAX_INSTRUCCION]   # lo escrito a mano también se oculta
    if not texto.strip():
        raise error(422, "ticket_pr_instruccion_vacia")
    run = TicketPrRun(
        organization_id=org, source_type=tipo, ticket_id=origen.id if tipo == "ticket" else None,
        task_id=origen.id if tipo == "task" else None, source_ref=_referencia(tipo, origen)[:40],
        project_id=origen.project_id, repo_id=repo.id, provider=repo.provider, repo_full_name=repo.repo_full_name,
        base_branch=rama, engine=cfg.get("engine") or "opencode", engine_image=imagen,
        ai_provider_id=modelo.provider_id, model=modelo.modelo, instruction=texto, status="queued_plan",
        launched_by=usuario.id)
    db.add(run)
    db.flush()
    _auditar(db, usuario, "TICKET_PR_LAUNCH", run, {"imagen": imagen, "modelo": modelo.modelo, "rama": rama},
             ip=ip, ua=ua)
    db.commit()
    _encolar(ejecutar_plan, run, db)
    db.refresh(run)
    return run


def _encolar(funcion, run: TicketPrRun, db: Session) -> None:
    from app.core.segundo_plano import encolar
    encolar(funcion, run.id, _organizacion=run.organization_id, _sesion=db)


# ── Fases (en el worker) ─────────────────────────────────────────────────────

def _usuario(db: Session, user_id: Optional[str]):
    from app.models.user import User
    return db.get(User, user_id) if user_id else None


def _cargar(db: Session, run_id: str) -> Optional[TicketPrRun]:
    return db.query(TicketPrRun).filter(TicketPrRun.id == run_id).first()


def _arbol_base(cliente: git_clientes.ClienteGit, run: TicketPrRun, cfg: dict) -> _diff.Arbol:
    if not run.base_sha:
        run.base_sha = cliente.sha_de_rama(run.repo_full_name, run.base_branch)
    datos = cliente.descargar(run.repo_full_name, run.base_sha)
    return _diff.leer_tar(datos, quitar_prefijo=True, max_bytes=int(_config.limite(cfg, "max_repo_mb")) * 1024 * 1024,
                          excluir=_config.NO_SE_COPIAN)


def _contexto(run: TicketPrRun, instruccion: str, arbol: _diff.Arbol, modelo: _motor.Modelo, cfg: dict,
              fase: str) -> _motor.Contexto:
    return _motor.Contexto(run_id=run.id, instruccion=instruccion, arbol=arbol, modelo=modelo,
                           imagen=run.engine_image or _config.imagen_del_motor(cfg), limites=_limites(cfg, fase),
                           hosts_extra=_hosts_extra(cfg), bash_permitido=list(cfg.get("bash_allow") or []),
                           max_bytes=int(_config.limite(cfg, "max_repo_mb")) * 1024 * 1024)


def _fallo(db: Session, run: TicketPrRun, usuario, codigo: str, params: Optional[dict] = None) -> None:
    _fijar_estado(run, "failed", codigo, params)
    _auditar(db, usuario, "TICKET_PR_FAILED", run, {"codigo": codigo})
    db.commit()


def _codigo_de(exc: Exception) -> tuple[str, dict]:
    if isinstance(exc, git_clientes.ErrorGit):
        return exc.codigo, exc.params
    if isinstance(exc, sandbox.DockerNoDisponible):
        return exc.codigo, {}
    if isinstance(exc, ErrorConCodigo):
        return exc.codigo, exc.params or {}
    if isinstance(exc, ErrorDeDominio) and exc.code:
        return exc.code, exc.params or {}
    if isinstance(exc, ValueError) and str(exc).startswith("ticket_pr_"):
        return str(exc), {}
    return "ticket_pr_error_interno", {}


def _ficheros_del_plan(plan: str) -> list[str]:
    salida, dentro = [], False
    for linea in (plan or "").splitlines():
        limpia = linea.strip().strip("-*` ").strip()
        if limpia.upper().startswith("FICHEROS:") or limpia.upper().startswith("FILES:"):
            dentro = True
            resto = limpia.split(":", 1)[1].strip()
            if resto:
                salida.append(resto)
            continue
        if dentro and limpia:
            ruta = _diff.ruta_segura(limpia)
            if ruta:
                salida.append(ruta)
    return list(dict.fromkeys(salida))[:200]


def ejecutar_plan(db: Session, run_id: str) -> Optional[str]:
    """Fase PLAN (agente de solo lectura). Deja la ejecución esperando aprobación."""
    run = _cargar(db, run_id)
    if run is None or run.status != "queued_plan":
        return None
    usuario = _usuario(db, run.launched_by)
    cfg = _config.leer(db, run.organization_id)
    if not _config.encendido(db, run.organization_id):
        _fallo(db, run, usuario, "ticket_pr_apagado")
        return run.status
    _fijar_estado(run, "planning")
    run.started_at = run.started_at or _ahora()
    db.commit()
    modelo = None
    try:
        modelo = modelo_de_la_empresa(db, run.organization_id, cfg)
        run._secretos = (modelo.api_key,)
        cliente = git_clientes.cliente_para(run.provider, _config.credenciales_git(db, run.organization_id))
        arbol = _arbol_base(cliente, run, cfg)
        db.commit()
        motor = _motor.obtener_motor(run.engine)
        res = motor.planificar(_contexto(run, run.instruction, arbol, modelo, cfg, "plan"))
    except Exception as exc:   # noqa: BLE001 — todo fallo queda con su código en la ejecución
        logger.warning("ticket_pr: fallo en PLAN de %s", run_id, exc_info=True)
        db.rollback()
        run = _cargar(db, run_id)
        codigo, params = _codigo_de(exc)
        _fallo(db, run, usuario, codigo, params)
        return run.status
    db.refresh(run)
    run._secretos = (modelo.api_key,) if modelo else ()
    _apuntar_uso(db, run, res, modelo)
    _anadir_log(db, run, res.log)
    if run.status == "cancelled":           # cancelada mientras pensaba: se guarda el coste y nada más
        db.commit()
        return run.status
    if not res.ok:
        _fallo(db, run, usuario, res.codigo or "ticket_pr_motor_fallo", res.params)
        return run.status
    run.plan_text = _instr.ocultar(res.texto, db, usuario)[:50000]
    run.plan_files = _json(_ficheros_del_plan(res.texto))
    _fijar_estado(run, "awaiting_approval")
    db.commit()
    _avisar(db, run, "ticket_pr.plan_listo")
    return run.status


def decidir_plan(db: Session, usuario, run_id: str, aprobar: bool, nota: Optional[str] = None,
                 ip: Optional[str] = None, ua: Optional[str] = None) -> TicketPrRun:
    """Una persona aprueba (→ BUILD) o rechaza (fin) el plan. Auditado."""
    run = obtener_ejecucion(db, usuario, run_id)
    if run.status != "awaiting_approval":
        raise error(409, "ticket_pr_estado_no_valido", estado=run.status)
    cfg = _config.leer(db, run.organization_id)
    if cfg.get("plan_requires_other_person") and usuario.id == run.launched_by:
        raise error(403, "ticket_pr_plan_propio")
    if aprobar:
        if not _config.encendido(db, run.organization_id):
            raise error(409, "ticket_pr_apagado")
        exigir_docker()
        exigir_limites(db, run.organization_id, cfg, nueva=False)
    run.plan_decided_by = usuario.id
    run.plan_decided_at = _ahora()
    run.plan_decision_note = (_instr.ocultar(nota, db, usuario) or None) if nota else None
    _fijar_estado(run, "queued_build" if aprobar else "rejected")
    _auditar(db, usuario, "TICKET_PR_PLAN_APPROVE" if aprobar else "TICKET_PR_PLAN_REJECT", run, ip=ip, ua=ua)
    db.commit()
    if aprobar:
        _encolar(ejecutar_build, run, db)
        db.refresh(run)
    return run


def _rama(run: TicketPrRun) -> str:
    ref = re.sub(r"[^A-Za-z0-9._-]+", "-", run.source_ref or "item").strip("-.").lower()[:40] or "item"
    return f"contecflow/{ref}-{run.id[:8]}"


def ejecutar_build(db: Session, run_id: str) -> Optional[str]:
    """Fase BUILD: cambios en el contenedor, diff comprobado, tests, rama + PR, cambio y CAB."""
    run = _cargar(db, run_id)
    if run is None or run.status != "queued_build":
        return None
    usuario = _usuario(db, run.launched_by)
    cfg = _config.leer(db, run.organization_id)
    if not _config.encendido(db, run.organization_id):
        _fallo(db, run, usuario, "ticket_pr_apagado")
        return run.status
    _fijar_estado(run, "building")
    db.commit()
    modelo = None
    try:
        modelo = modelo_de_la_empresa(db, run.organization_id, cfg)
        run._secretos = (modelo.api_key,)
        cliente = git_clientes.cliente_para(run.provider, _config.credenciales_git(db, run.organization_id))
        antes = _arbol_base(cliente, run, cfg)
        texto = _instr.instruccion_de_build(db, usuario, run.instruction, run.repo_full_name, run.base_branch,
                                            run.plan_text or "", cfg)
        motor = _motor.obtener_motor(run.engine)
        res = motor.construir(_contexto(run, texto, antes, modelo, cfg, "build"))
    except Exception as exc:   # noqa: BLE001
        logger.warning("ticket_pr: fallo en BUILD de %s", run_id, exc_info=True)
        db.rollback()
        run = _cargar(db, run_id)
        codigo, params = _codigo_de(exc)
        _fallo(db, run, usuario, codigo, params)
        return run.status
    db.refresh(run)
    run._secretos = (modelo.api_key,)
    _apuntar_uso(db, run, res, modelo)
    _anadir_log(db, run, res.log)
    if run.status == "cancelled":
        db.commit()
        return run.status
    if not res.ok or res.arbol is None:
        _fallo(db, run, usuario, res.codigo or "ticket_pr_motor_fallo", res.params)
        return run.status
    run.reasoning_summary = _instr.ocultar(res.texto, db, usuario)[:20000]
    despues = _diff.quitar_ignorados(antes, res.arbol)
    cambios = _diff.comparar(antes, despues)
    run.diff_summary = _json(_diff.resumen(antes, cambios))
    bloqueo = _diff.comprobar(antes, despues, cambios, protegidos=_config.protegidos(cfg),
                              max_ficheros=int(_config.limite(cfg, "max_changed_files")),
                              max_diff_kb=int(_config.limite(cfg, "max_diff_kb")), literales=(modelo.api_key,))
    if bloqueo is not None:
        _fijar_estado(run, "blocked", bloqueo.codigo, bloqueo.params)
        _auditar(db, usuario, "TICKET_PR_BLOCKED", run, {"codigo": bloqueo.codigo, **bloqueo.params})
        db.commit()
        return run.status
    repo = db.get(TicketPrRepo, run.repo_id) if run.repo_id else None
    if cfg.get("run_tests") and repo is not None and repo.test_command:
        try:
            tres = _motor.obtener_motor(run.engine).ejecutar_tests(
                _contexto(run, "", despues, modelo, cfg, "build"), repo.test_command)
        except Exception as exc:   # noqa: BLE001
            logger.warning("ticket_pr: fallo al ejecutar los tests de %s", run_id, exc_info=True)
            codigo, params = _codigo_de(exc)
            _fallo(db, run, usuario, codigo, params)
            return run.status
        run.tests_ran = True
        run.tests_passed = bool(tres.ok)
        run.agent_seconds = (run.agent_seconds or 0) + int(tres.segundos or 0)
        _anadir_log(db, run, tres.log)
        if not tres.ok and cfg.get("block_on_test_failure", True):
            _fijar_estado(run, "blocked", "ticket_pr_bloqueo_tests", {"codigo": (tres.params or {}).get("codigo", 1)})
            _auditar(db, usuario, "TICKET_PR_BLOCKED", run, {"codigo": "ticket_pr_bloqueo_tests"})
            db.commit()
            return run.status
    db.commit()
    db.refresh(run)
    if run.status == "cancelled":
        return run.status
    try:
        _abrir_pr(db, run, cliente, cambios)
    except Exception as exc:   # noqa: BLE001
        logger.warning("ticket_pr: fallo al abrir el PR de %s", run_id, exc_info=True)
        db.rollback()
        run = _cargar(db, run_id)
        codigo, params = _codigo_de(exc)
        _fallo(db, run, usuario, codigo, params)
        return run.status
    vincular_cambio(db, run, usuario)
    sincronizar(db, run, cliente)
    _avisar(db, run, "ticket_pr.pr_abierto")
    return run.status


# ── PR, cambio y CAB ─────────────────────────────────────────────────────────

def _enlace_del_origen(run: TicketPrRun) -> str:
    from app.core.config import settings
    base = str(settings.FRONTEND_URL or "").rstrip("/")
    if run.source_type == "ticket":
        return f"{base}/service-desk?ticket={run.ticket_id}"
    return f"{base}/tasks?project_id={run.project_id}&search={run.source_ref or ''}"


def cuerpo_del_pr(run: TicketPrRun, cambio_numero: Optional[str] = None) -> str:
    """Descripción del PR. Sin nombres de personas ni datos personales (sale de la plataforma)."""
    resumen = _de_json(run.diff_summary, {}) or {}
    filas = "\n".join(f"| `{f['path']}` | {f['action']} | +{f['added']} | -{f['removed']} |"
                      for f in (resumen.get("files") or [])[:100])
    tests = ("no se han ejecutado" if not run.tests_ran else ("pasan" if run.tests_passed else "FALLAN"))
    cambio = (f"Cambio ITSM **{cambio_numero}** en revisión del CAB." if cambio_numero
              else "El cambio ITSM se vincula a continuación.")
    return (
        "Propuesta generada por el agente de código de contecflow («Del ticket al PR»).\n\n"
        f"- Origen: [{run.source_ref}]({_enlace_del_origen(run)})\n"
        f"- Ejecución: `{run.id}` · motor `{run.engine}` (`{run.engine_image}`) · modelo `{run.model}`\n"
        f"- Plan aprobado por una persona el {run.plan_decided_at.isoformat() if run.plan_decided_at else '-'}\n"
        f"- {cambio} El merge queda bloqueado por el estado `{git_clientes.CONTEXTO_DE_ESTADO}` hasta que el "
        "CAB lo apruebe. **contecflow nunca fusiona**: lo hace una persona.\n"
        f"- Tests del repositorio: {tests}\n\n"
        "## Resumen del razonamiento\n\n"
        f"{(run.reasoning_summary or '-')[:8000]}\n\n"
        "## Plan aprobado\n\n"
        f"{(run.plan_text or '-')[:8000]}\n\n"
        "## Ficheros\n\n| Fichero | Acción | Añadidas | Quitadas |\n|---|---|---|---|\n"
        f"{filas}\n"
    )


def _abrir_pr(db: Session, run: TicketPrRun, cliente: git_clientes.ClienteGit, cambios: list) -> None:
    run.branch_name = _rama(run)
    titulo = f"[contecflow] {run.source_ref}: " + (_titulo_oculto(db, run) or "arreglo propuesto")
    mensaje = f"{titulo}\n\nEjecución {run.id} de «Del ticket al PR». Plan aprobado por una persona."
    run.head_sha = cliente.publicar(run.repo_full_name, run.base_sha, run.branch_name, cambios, mensaje)
    run.pr_number, run.pr_url = cliente.abrir_pr(run.repo_full_name, run.branch_name, run.base_branch, titulo,
                                                 cuerpo_del_pr(run))
    cliente.poner_estado(run.repo_full_name, run.head_sha, "pending", "Pendiente de aprobación del CAB",
                         _enlace_del_origen(run))
    run.pr_status_state = "pending"
    _fijar_estado(run, "awaiting_cab")
    _auditar(db, _usuario(db, run.launched_by), "TICKET_PR_PR_OPENED", run,
             {"pr": run.pr_number, "pr_url": run.pr_url, "rama": run.branch_name, "sha": run.head_sha})
    db.commit()


def _titulo_oculto(db: Session, run: TicketPrRun) -> str:
    origen = None
    if run.ticket_id:
        from app.models.service_desk import Ticket
        origen = db.get(Ticket, run.ticket_id)
    elif run.task_id:
        from app.models.task import Task
        origen = db.get(Task, run.task_id)
    return _instr.ocultar(getattr(origen, "title", "") or "", None, None)[:180]


def vincular_cambio(db: Session, run: TicketPrRun, usuario=None) -> Optional[str]:
    """Crea el cambio ITSM vinculado al PR y lo manda al CAB. Devuelve el id o None (con el motivo en la ejecución).

    El cambio lo pide quien lanzó: el CAB no le deja votarlo (segregación).
    `standard_if_fits` con un modelo del catálogo: estándar si encaja (si no, normal).
    """
    if run.change_id or not run.pr_url:
        return run.change_id
    from app.services.service_desk import change_service
    usuario = usuario or _usuario(db, run.launched_by)
    if usuario is None:
        _fijar_estado(run, run.status, "ticket_pr_sin_solicitante")
        db.commit()
        return None
    cfg = _config.leer(db, run.organization_id)
    resumen = _de_json(run.diff_summary, {}) or {}
    datos = {
        "title": f"[Agente] {run.source_ref}: {_titulo_oculto(db, run) or 'arreglo propuesto'}"[:250],
        "description": (f"PR {run.pr_url} propuesto por el agente de código («Del ticket al PR», ejecución {run.id}).\n"
                        f"Ficheros: {len(resumen.get('files') or [])}, +{resumen.get('added', 0)} "
                        f"-{resumen.get('removed', 0)}.\n\n{(run.reasoning_summary or '')[:4000]}"),
        "implementation_plan": f"Revisar y fusionar el PR {run.pr_url} (lo fusiona una persona tras la aprobación "
                               "del CAB; contecflow no fusiona).",
        "rollback_plan": f"Revertir el commit del PR {run.pr_url} (git revert) o cerrar el PR sin fusionar.",
        "test_plan": ("Tests del repositorio ejecutados en el contenedor: "
                      + ("pasan." if run.tests_passed else "fallan.")) if run.tests_ran
                     else "Revisión del PR y tests del pipeline del repositorio.",
        "risk": "medium", "priority": "p3_medium",
        "related_ticket_id": run.ticket_id,
    }
    if cfg.get("change_type") == "standard_if_fits" and cfg.get("standard_model_id"):
        datos.update({"change_type": "standard", "standard_model_id": cfg["standard_model_id"]})
    try:
        try:
            cambio = change_service.create_change_record(db, usuario, datos)
        except ErrorDeDominio as exc:
            if datos.get("change_type") != "standard":
                raise
            logger.info("ticket_pr: el cambio no encaja como estándar (%s); va como normal", exc.code)
            db.rollback()
            datos.pop("standard_model_id", None)
            datos["change_type"] = "normal"
            cambio = change_service.create_change_record(db, usuario, datos)
        run.change_id = cambio.id
        db.flush()
        estado = getattr(cambio.status, "value", cambio.status)
        if estado != "approved":
            try:
                change_service.update_change_record(db, usuario, cambio.id, {"status": "submitted"})
            except ErrorDeDominio as exc:
                # Sin CAB configurado el cambio queda en borrador: el PR sigue bloqueado (pending).
                logger.warning("ticket_pr: el cambio %s no pudo ir al CAB (%s)", cambio.id, exc.code)
                run.status_code, run.status_params = exc.code or "ticket_pr_cab_no_disponible", _json(exc.params or {})
        _auditar(db, usuario, "TICKET_PR_CHANGE_LINKED", run,
                 {"change_id": cambio.id, "change_number": cambio.number,
                  "change_type": getattr(cambio.change_type, "value", cambio.change_type)})
        db.commit()
    except Exception as exc:   # noqa: BLE001 — el PR ya existe y sigue bloqueado; se puede reintentar
        logger.warning("ticket_pr: no se pudo vincular el cambio de %s", run.id, exc_info=True)
        db.rollback()
        run = _cargar(db, run.id)
        codigo, params = _codigo_de(exc)
        run.status_code, run.status_params = codigo, _json(params)
        db.commit()
        return None
    try:
        cliente = git_clientes.cliente_para(run.provider, _config.credenciales_git(db, run.organization_id))
        cliente.actualizar_pr(run.repo_full_name, run.pr_number, cuerpo=cuerpo_del_pr(run, cambio.number))
    except Exception:   # noqa: BLE001 — la descripción es informativa; el bloqueo lo pone el estado
        logger.info("ticket_pr: no se pudo actualizar la descripción del PR de %s", run.id, exc_info=True)
    return run.change_id


#: Estado del cambio → estado del PR (`contecflow/cab`).
_APROBADOS = frozenset({"approved", "scheduled", "in_progress", "implemented", "post_review", "closed_success"})
_DENEGADOS = frozenset({"cancelled", "closed_failed"})


def estado_para_el_pr(estado_del_cambio: Optional[str]) -> str:
    if estado_del_cambio in _APROBADOS:
        return "success"
    if estado_del_cambio in _DENEGADOS:
        return "failure"
    return "pending"


def sincronizar(db: Session, run: TicketPrRun, cliente: Optional[git_clientes.ClienteGit] = None) -> TicketPrRun:
    """Lleva el estado del cambio al PR (y el del PR a la ejecución). Nunca fusiona."""
    if run.status not in ("awaiting_cab", "cab_approved") or not run.pr_number:
        return run
    from app.models.service_desk import ITSMChangeRequest
    cambio = db.get(ITSMChangeRequest, run.change_id) if run.change_id else None
    estado_cambio = getattr(getattr(cambio, "status", None), "value", getattr(cambio, "status", None))
    deseado = estado_para_el_pr(estado_cambio) if cambio is not None else "pending"
    cliente = cliente or git_clientes.cliente_para(run.provider, _config.credenciales_git(db, run.organization_id))
    antes = run.status
    if deseado != run.pr_status_state and run.head_sha:
        texto = {"success": f"Cambio {cambio.number} aprobado por el CAB" if cambio else "Aprobado",
                 "failure": f"Cambio {cambio.number} rechazado o cancelado" if cambio else "Rechazado",
                 "pending": "Pendiente de aprobación del CAB"}[deseado]
        cliente.poner_estado(run.repo_full_name, run.head_sha, deseado, texto, _enlace_del_origen(run))
        if deseado == "success":
            cliente.actualizar_pr(run.repo_full_name, run.pr_number, listo=True)
        run.pr_status_state = deseado
    if deseado == "success":
        run.status = "cab_approved"
    elif deseado == "failure":
        _fijar_estado(run, "cab_rejected")
    if run.status not in FINALES:
        pr = cliente.estado_pr(run.repo_full_name, run.pr_number)
        if pr == "merged":
            _fijar_estado(run, "merged")
        elif pr == "closed":
            _fijar_estado(run, "closed")
    if run.status != antes:
        _auditar(db, None, "TICKET_PR_CAB_SYNC", run, {"antes": antes, "pr_estado": run.pr_status_state,
                                                        "cambio_estado": estado_cambio})
    db.commit()
    return run


def sincronizar_empresa(db: Session, org_id: Optional[str] = None) -> dict:
    """Trabajo periódico por empresa: PR ↔ CAB, y ejecuciones colgadas (worker caído) a fallo.

    Sigue aunque el módulo se haya apagado: los PR abiertos tienen que seguir
    bloqueados (o desbloquearse) según su cambio.
    """
    n = colgadas = errores = 0
    de_la_empresa = [TicketPrRun.organization_id == org_id] if org_id else []
    for run in db.query(TicketPrRun).filter(TicketPrRun.status.in_(("awaiting_cab", "cab_approved")),
                                            *de_la_empresa).limit(500).all():
        try:
            if not run.change_id:
                vincular_cambio(db, run)
            sincronizar(db, run)
            n += 1
        except Exception:   # noqa: BLE001 — una ejecución no para a las demás
            errores += 1
            db.rollback()
            logger.warning("ticket_pr: sincronización de %s fallida", run.id, exc_info=True)
    limite = _ahora() - timedelta(minutes=300)
    for run in db.query(TicketPrRun).filter(TicketPrRun.status.in_(("planning", "building")),
                                            TicketPrRun.updated_at < limite, *de_la_empresa).all():
        _fijar_estado(run, "failed", "ticket_pr_tiempo_agotado", {"minutos": 300})
        colgadas += 1
    db.commit()
    return {"sincronizadas": n, "colgadas": colgadas, "errores": errores}


def cancelar(db: Session, usuario, run_id: str, ip: Optional[str] = None, ua: Optional[str] = None) -> TicketPrRun:
    """Cancela (auditado). Con el PR abierto: cancela el cambio y el PR queda en fallo (no se fusiona)."""
    from app.core import capacidades as _capacidades
    run = obtener_ejecucion(db, usuario, run_id)
    if run.status in FINALES:
        raise error(409, "ticket_pr_estado_no_valido", estado=run.status)
    if usuario.id != run.launched_by and not _capacidades.tiene(db, usuario, "ticket_pr.aprobar_plan"):
        raise error(403, "ticket_pr_sin_permiso")
    antes = run.status
    if run.status in ("awaiting_cab", "cab_approved") and run.change_id:
        from app.services.service_desk import change_service
        try:
            change_service.cancelar_cambio(db, usuario, run.change_id)
        except ErrorDeDominio:
            logger.info("ticket_pr: el cambio de %s no se pudo cancelar", run.id, exc_info=True)
    if run.pr_number and run.head_sha:
        try:
            cliente = git_clientes.cliente_para(run.provider, _config.credenciales_git(db, run.organization_id))
            cliente.poner_estado(run.repo_full_name, run.head_sha, "failure", "Cancelado en contecflow",
                                 _enlace_del_origen(run))
            run.pr_status_state = "failure"
        except Exception:   # noqa: BLE001
            logger.warning("ticket_pr: no se pudo marcar el PR de %s como cancelado", run.id, exc_info=True)
    run.cancelled_by = usuario.id
    _fijar_estado(run, "cancelled")
    _auditar(db, usuario, "TICKET_PR_CANCEL", run, {"antes": antes}, ip=ip, ua=ua)
    db.commit()
    return run


# ── Lectura ──────────────────────────────────────────────────────────────────

def obtener_ejecucion(db: Session, usuario, run_id: str) -> TicketPrRun:
    """La ejecución si su origen es visible para `usuario` (o, sin origen, si configura el módulo)."""
    from app.core import capacidades as _capacidades
    run = db.query(TicketPrRun).filter(TicketPrRun.id == run_id).first()
    if run is None or (_org(usuario) and run.organization_id != _org(usuario)):
        raise ErrorDeDominio(404)
    origen_id = run.ticket_id or run.task_id
    if origen_id:
        obtener_origen(db, usuario, run.source_type, origen_id)
    elif not _capacidades.tiene(db, usuario, "ticket_pr.config"):
        raise ErrorDeDominio(404)
    return run


def _nombre(db: Session, user_id: Optional[str]) -> Optional[str]:
    u = _usuario(db, user_id)
    return getattr(u, "full_name", None) if u else None


def serializar(db: Session, usuario, run: TicketPrRun) -> dict:
    from app.core import capacidades as _capacidades
    cambio = None
    if run.change_id:
        from app.models.service_desk import ITSMChangeRequest
        c = db.get(ITSMChangeRequest, run.change_id)
        if c is not None:
            cambio = {"id": c.id, "number": c.number, "status": getattr(c.status, "value", c.status),
                      "change_type": getattr(c.change_type, "value", c.change_type)}
    puede_aprobar = _capacidades.tiene(db, usuario, "ticket_pr.aprobar_plan")
    return {
        "id": run.id, "status": run.status, "status_code": run.status_code,
        "status_params": _de_json(run.status_params, {}),
        "source_type": run.source_type, "ticket_id": run.ticket_id, "task_id": run.task_id,
        "source_ref": run.source_ref, "project_id": run.project_id, "provider": run.provider,
        "repo_full_name": run.repo_full_name, "base_branch": run.base_branch, "base_sha": run.base_sha,
        "branch_name": run.branch_name, "engine": run.engine, "engine_image": run.engine_image, "model": run.model,
        "instruction": run.instruction, "plan_text": run.plan_text, "plan_files": _de_json(run.plan_files, []),
        "launched_by": run.launched_by, "launched_by_name": _nombre(db, run.launched_by),
        "plan_decided_by": run.plan_decided_by, "plan_decided_by_name": _nombre(db, run.plan_decided_by),
        "plan_decided_at": run.plan_decided_at.isoformat() if run.plan_decided_at else None,
        "plan_decision_note": run.plan_decision_note,
        "diff_summary": _de_json(run.diff_summary, None), "tests_ran": bool(run.tests_ran),
        "tests_passed": run.tests_passed, "reasoning_summary": run.reasoning_summary,
        "pr_number": run.pr_number, "pr_url": run.pr_url, "pr_status_state": run.pr_status_state,
        "change": cambio, "tokens_in": run.tokens_in or 0, "tokens_out": run.tokens_out or 0,
        "cost_usd": round(float(run.cost_usd or 0), 6), "agent_hours": round((run.agent_seconds or 0) / 3600, 3),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "can_decide": run.status == "awaiting_approval" and puede_aprobar,
        "can_cancel": run.status not in FINALES and (usuario.id == run.launched_by or puede_aprobar),
    }


def coste_por_proyecto(db: Session, usuario, dias: int = 30) -> list[dict]:
    """Coste de IA, tokens y horas del agente por proyecto (imputación)."""
    from app.models.project import Project
    desde = _ahora() - timedelta(days=max(1, min(dias, 3660)))
    filas = (db.query(TicketPrRun.project_id, func.count(TicketPrRun.id), func.sum(TicketPrRun.cost_usd),
                      func.sum(TicketPrRun.tokens_in), func.sum(TicketPrRun.tokens_out),
                      func.sum(TicketPrRun.agent_seconds))
             .filter(TicketPrRun.organization_id == _org(usuario), TicketPrRun.created_at >= desde)
             .group_by(TicketPrRun.project_id).all())
    nombres = {p.id: p.name for p in db.query(Project).filter(Project.id.in_([f[0] for f in filas if f[0]])).all()}
    return [{"project_id": pid, "project_name": nombres.get(pid), "runs": int(n or 0),
             "cost_usd": round(float(c or 0), 6), "tokens_in": int(ti or 0), "tokens_out": int(to or 0),
             "agent_hours": round(float(s or 0) / 3600, 3)} for pid, n, c, ti, to, s in filas]


def _avisar(db: Session, run: TicketPrRun, clave: str) -> None:
    """Aviso en la aplicación a quien lanzó (plan listo, PR abierto). Un fallo no para el flujo."""
    if not run.launched_by:
        return
    try:
        from app.services.notifications import notify_user
        notify_user(db, run.launched_by, "info", clave, None, RECURSO, run.id, None,
                    aviso={"titulo": clave, "cuerpo": None, "params": {"ref": run.source_ref or "",
                                                                       "repo": run.repo_full_name}})
        db.commit()
    except Exception:   # noqa: BLE001
        db.rollback()
        logger.info("ticket_pr: aviso %s no enviado", clave, exc_info=True)
