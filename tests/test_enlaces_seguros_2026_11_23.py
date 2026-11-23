"""Auditoría 2026-11-22 (04 A6 y 04b A3): enlaces guardados solo http(s)."""
import pytest
from pydantic import BaseModel, ValidationError

from app.schemas._enlaces import EnlaceSeguro


class _Modelo(BaseModel):
    url: EnlaceSeguro = None


@pytest.mark.parametrize("valor", ["https://ejemplo.com/a", "http://intranet/x", "/api/v1/uploads/1", "staging", None, ""])
def test_admite_http_rutas_propias_y_texto(valor):
    _Modelo(url=valor)


@pytest.mark.parametrize("valor", ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "java\tscript:alert(1)",
                                   "data:text/html,x", "vbscript:x", "file:///etc/passwd"])
def test_rechaza_otros_esquemas(valor):
    with pytest.raises(ValidationError):
        _Modelo(url=valor)
