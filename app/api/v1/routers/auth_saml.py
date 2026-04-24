"""
Auth SAML Router — SAML 2.0 service provider endpoints.
"""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings
from app.core.deps import require_admin
from app.models.user import User

import app.services.auth_service as _svc

router = APIRouter()


@router.get("/saml/metadata", summary="Metadata SAML del Service Provider")
def saml_metadata():
    """Devuelve la metadata SAML 2.0 del service provider."""
    entity_id = f"{settings.BASE_URL}/api/v1/auth/saml/metadata"
    acs_url = f"{settings.BASE_URL}/api/v1/auth/saml/callback"
    slo_url = f"{settings.BASE_URL}/api/v1/auth/saml/logout"
    metadata_xml = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<EntityDescriptor xmlns=\"urn:oasis:names:tc:SAML:2.0:metadata\" entityID=\"{entity_id}\">
  <SPSSODescriptor AuthnRequestsSigned=\"false\" WantAssertionsSigned=\"true\" protocolSupportEnumeration=\"urn:oasis:names:tc:SAML:2.0:protocol\">
    <NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</NameIDFormat>
    <AssertionConsumerService Binding=\"urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST\" Location=\"{acs_url}\" index=\"1\" isDefault=\"true\"/>
    <SingleLogoutService Binding=\"urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect\" Location=\"{slo_url}\"/>
  </SPSSODescriptor>
</EntityDescriptor>
"""
    return Response(content=metadata_xml, media_type="application/samlmetadata+xml")


@router.get("/saml/health", summary="Health de configuración SAML")
def saml_health(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Health check para configuraciones SAML activas."""
    saml_configs = _svc.get_saml_health(db)
    return {
        "metadata_url": f"{settings.BASE_URL}/api/v1/auth/saml/metadata",
        "configs": saml_configs,
    }
