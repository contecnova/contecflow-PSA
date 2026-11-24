"""Prueba de conexión REAL de «Del ticket al PR» (docs/integraciones/pruebas_de_conexion.md).

Comprueba, con lo configurado en la empresa y sin lanzar ningún agente:

- `docker`: el demonio responde (`docker version`);
- `imagen_motor`, `imagen_proxy`, `imagen_ayudante`: las imágenes fijadas se
  descargan (`docker pull`); el motor sin versión fijada no se prueba;
- `git`: la credencial de cada proveedor configurado es válida y, si hay un
  repositorio permitido de ese proveedor, da acceso a él (GitHub: token de
  instalación limitado a ese repositorio; GitLab: lectura del proyecto);
- `modelo`: el proveedor de IA de la empresa responde con su clave (lista de modelos).

Cada comprobación es `true`, `false` o `null` (no aplica o no se pudo probar).
`verificado`: `credencial_y_uso` si todo lo aplicable pasa y hay al menos un
repositorio probado; `credencial` si Git y modelo pasan pero falta Docker o un
repositorio; `nada` si no. Nunca devuelve cuerpos remotos ni secretos.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.ticket_a_pr import TicketPrRepo
from app.services.ticket_a_pr import config as _config
from app.services.ticket_a_pr import git_clientes, sandbox

logger = logging.getLogger(__name__)


def _git(db: Session, org: Optional[str]) -> tuple[Optional[bool], dict, bool]:
    creds = _config.credenciales_git(db, org)
    detalles: dict = {}
    resultados: list[bool] = []
    con_repo = False
    configurados = []
    if creds.get("github_app_id") and creds.get("github_installation_id") and creds.get("github_private_key"):
        configurados.append("github")
    if creds.get("gitlab_token"):
        configurados.append("gitlab")
    for proveedor in configurados:
        repo = db.query(TicketPrRepo).filter(TicketPrRepo.organization_id == org, TicketPrRepo.provider == proveedor,
                                             TicketPrRepo.is_active == True).first()  # noqa: E712
        try:
            r = git_clientes.cliente_para(proveedor, creds).probar(repo.repo_full_name if repo else None)
        except Exception as exc:   # noqa: BLE001 — la prueba nunca da 500
            logger.info("ticket_pr: prueba de %s fallida", proveedor, exc_info=True)
            r = {"ok": False, "detail": type(exc).__name__}
        detalles[proveedor] = {"ok": bool(r.get("ok")), "detail": str(r.get("detail") or "")[:200],
                               "repo": repo.repo_full_name if repo else None}
        resultados.append(bool(r.get("ok")))
        con_repo = con_repo or bool(repo and r.get("ok"))
    if not resultados:
        return None, detalles, False
    return all(resultados), detalles, con_repo


def _modelo(db: Session, org: Optional[str], cfg: dict) -> tuple[Optional[bool], str]:
    from app.services.ai_provider_service.clientes import diagnose_provider
    from app.services.ticket_a_pr.servicio import _proveedor_de_ia
    p = _proveedor_de_ia(db, org, cfg)
    if p is None:
        return None, "sin proveedor de IA"
    try:
        d = diagnose_provider(p)
    except Exception as exc:   # noqa: BLE001
        logger.info("ticket_pr: prueba del modelo fallida", exc_info=True)
        return False, type(exc).__name__
    return d.get("status") in ("ok", "warning"), f"{d.get('provider_type')}/{cfg.get('model') or d.get('model')}"


def probar(db: Session, org: Optional[str], descargar_imagenes: bool = True) -> dict:
    from app.core.config import settings
    cfg = _config.leer(db, org)
    c: dict = {"docker": None, "imagen_motor": None, "imagen_proxy": None, "imagen_ayudante": None,
               "git": None, "modelo": None}
    detalle: dict = {}
    ok_docker, version = sandbox.disponible()
    c["docker"] = ok_docker
    detalle["docker"] = version or "no disponible"
    try:
        imagen = _config.imagen_del_motor(cfg)
    except Exception:   # noqa: BLE001 — versión sin fijar
        logger.debug("probar: excepcion ignorada", exc_info=True)
        imagen = None
        detalle["imagen_motor"] = "versión sin fijar"
    if ok_docker and descargar_imagenes:
        if imagen:
            c["imagen_motor"] = sandbox.descargar_imagen(imagen)
            detalle["imagen_motor"] = imagen
        c["imagen_proxy"] = sandbox.descargar_imagen(settings.TICKET_PR_EGRESS_PROXY_IMAGE)
        c["imagen_ayudante"] = sandbox.descargar_imagen(settings.TICKET_PR_HELPER_IMAGE)
    elif imagen is None:
        c["imagen_motor"] = False
    c["git"], detalle["git"], con_repo = _git(db, org)
    c["modelo"], detalle["modelo"] = _modelo(db, org, cfg)
    aplicables = [v for v in c.values() if v is not None]
    todo = bool(aplicables) and all(aplicables)
    if todo and c["docker"] and c["git"] and c["modelo"] and con_repo and c["imagen_motor"]:
        verificado = "credencial_y_uso"
    elif c["git"] and c["modelo"]:
        verificado = "credencial"
    else:
        verificado = "nada"
    return {"ok": todo and verificado != "nada", "verificado": verificado, "comprobaciones": c, "detalle": detalle,
            "detail": ", ".join(f"{k}: {'ok' if v else ('—' if v is None else 'fallo')}" for k, v in c.items())}
