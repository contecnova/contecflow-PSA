# Auditoría 2026-08 (hallazgo 22). Este módulo estaba en
# `app/api/v1/endpoints/v239/`, un directorio nombrado por número de versión. El
# fichero ya se llamaba por su dominio; lo que agrupaba por versión era la
# carpeta. Las rutas no han cambiado: el prefijo lo pone el registro en
# `routers/`, no la ruta del fichero.
from __future__ import annotations

import json
from typing import Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db, require_admin
from app.core.responses import APIResponse
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.services import branding_service as svc

router = APIRouter()


class BrandingUpdate(BaseModel):
    app_name: Optional[str] = None
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    background_color: Optional[str] = None
    text_color: Optional[str] = None
    custom_domain: Optional[str] = None
    support_email: Optional[str] = None
    privacy_url: Optional[str] = None
    terms_url: Optional[str] = None
    welcome_message: Optional[str] = None
    login_background_url: Optional[str] = None
    footer_text: Optional[str] = None
    help_url: Optional[str] = None
    hide_powered_by: Optional[bool] = None
    enable_portal: Optional[bool] = None
    enable_ai: Optional[bool] = None
    custom_css_vars: Optional[Dict[str, str]] = None

    @field_validator(
        "primary_color",
        "secondary_color",
        "accent_color",
        "background_color",
        "text_color",
        mode="before",
    )
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not (v.startswith("#") and len(v) in (4, 7, 9)):
            raise ValueError("Color must be a valid hex value like #RRGGBB")
        return v

    @field_validator("custom_domain", mode="before")
    @classmethod
    def validate_domain(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if "/" in v or " " in v:
                raise ValueError("custom_domain must be a bare hostname, e.g. pm.company.com")
        return v


def _branding_out(b) -> dict:
    return {
        "id": b.id,
        "organization_id": b.organization_id,
        "app_name": b.app_name,
        "tagline": b.tagline,
        "logo_url": b.logo_url,
        "favicon_url": b.favicon_url,
        "primary_color": b.primary_color,
        "secondary_color": b.secondary_color,
        "accent_color": b.accent_color,
        "background_color": b.background_color,
        "text_color": b.text_color,
        "custom_domain": b.custom_domain,
        "support_email": b.support_email,
        "privacy_url": b.privacy_url,
        "terms_url": b.terms_url,
        "welcome_message": b.welcome_message,
        "login_background_url": b.login_background_url,
        "footer_text": b.footer_text,
        "help_url": b.help_url,
        "hide_powered_by": b.hide_powered_by,
        "enable_portal": b.enable_portal,
        "enable_ai": b.enable_ai,
        "custom_css_vars": json.loads(b.custom_css_vars) if b.custom_css_vars else {},
        "updated_at": str(b.updated_at) if b.updated_at else None,
    }


# ── Los valores por defecto de la marca: una sola fuente ─────────────────────
#
# Auditoria 2026-08 (hallazgo 32). Este endpoint devolvia, para una organizacion
# sin marca configurada, un diccionario de literales escritos a mano que
# duplicaba los `default=` del modelo. Ya habia divergido en dos sentidos:
#
#   · `app_name` devolvia **"NexusPM"** —un nombre de producto anterior, que
#     todavia aparece en los docstrings de esign, jira y m365— mientras el
#     modelo declara `default="Contecflow"`. Cualquier organizacion que no
#     hubiera tocado su marca veia ese nombre EN SU INTERFAZ;
#   · faltaban `background_color` y `text_color`, o sea 2 de los 5 colores, asi
#     que quien leia la API para una organizacion sin configurar recibia un
#     payload incompleto.
#
# Ahora los defectos se leen de los `default=` declarados en el modelo, que es
# donde ya estaban. Duplicar valores por defecto no es un problema de estilo: es
# garantizar que un dia divergen, y aqui ya lo habian hecho.
#
# `app_name` es la excepcion deliberada: el nombre por defecto no es un valor de
# marca del cliente sino el de la plataforma, asi que sale de la configuracion y
# no de una constante del modelo — asi un despliegue con otro `PROJECT_NAME` no
# ensena un nombre que no es el suyo.


def _defecto_declarado(nombre_de_columna: str):
    """El `default=` que el modelo declara para esa columna.

    Se lee de los metadatos de la tabla y no del modelo instanciado a proposito:
    los `default=` de SQLAlchemy se aplican en el INSERT, no al acceder al
    atributo, asi que un `OrgBranding()` recien construido los tiene todos a
    `None` y no sirve para esto.
    """
    from app.models.white_label import OrgBranding

    columna = OrgBranding.__table__.columns.get(nombre_de_columna)
    defecto = getattr(columna, "default", None) if columna is not None else None
    return getattr(defecto, "arg", None) if defecto is not None else None


#: Los campos cuyo valor por defecto sale del modelo. `app_name` no esta aqui:
#: ver la nota de arriba.
_CAMPOS_CON_DEFECTO_DEL_MODELO = (
    "primary_color", "secondary_color", "accent_color",
    "background_color", "text_color",
    "hide_powered_by", "enable_portal", "enable_ai",
)


def _marca_por_defecto(org_id: str) -> dict:
    """La marca de una organización que nunca la ha configurado."""
    datos = {
        "organization_id": org_id,
        "app_name": settings.PROJECT_NAME,
        "custom_css_vars": {},
        "is_default": True,
    }
    for campo in _CAMPOS_CON_DEFECTO_DEL_MODELO:
        datos[campo] = _defecto_declarado(campo)
    return datos


@router.get("/orgs/{org_id}/branding", summary="Get tenant branding config")
def get_branding(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branding = svc.marca_de_la_organizacion(db, current_user, org_id)
    if not branding:
        return APIResponse.ok(data=_marca_por_defecto(org_id))
    return APIResponse.ok(data=_branding_out(branding))


@router.put("/orgs/{org_id}/branding", summary="Update tenant branding (admin)")
def update_branding(
    org_id: str,
    payload: BrandingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    branding = svc.guardar_marca(
        db, current_user, org_id, payload.dict(exclude_none=True))
    return APIResponse.ok(data=_branding_out(branding))


@router.delete("/orgs/{org_id}/branding", summary="Reset branding to defaults (admin)", status_code=204)
def reset_branding(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "org_branding", org_id, action="delete")
    svc.restablecer_marca(db, current_user, org_id)
    return None
