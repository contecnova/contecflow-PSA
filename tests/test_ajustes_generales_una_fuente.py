"""Ajustes generales con una sola fuente (18-11-2026, reorganización de Configuración).

Configuración → General guardaba moneda, zona, idioma y jornada en filas
`app_settings` propias que no leía nadie; lo que usa la aplicación son las
claves de ejecución `DEFAULT_*` (`/settings/org-defaults`). Ahora el alias de
General lee y escribe esa clave (`ALIAS_DE_EJECUCION`).
"""
from app.models.settings import AppSetting
from app.services.politica_de_visibilidad import Audiencia
from app.services.settings_service import ajustes_generales_para, defaults_de_organizacion, update_setting
from app.services.settings_service.generales import ALIAS_DE_EJECUCION


def _general(db, org):
    return {f["key"]: f["value"] for f in ajustes_generales_para(db, Audiencia.ADMIN, False, org)}


def test_cambiar_la_moneda_en_general_cambia_la_de_la_empresa(db):
    update_setting("currency", "USD", "1", db)
    assert defaults_de_organizacion(db, "1", Audiencia.ADMIN)["currency"] == "USD"
    fila = db.query(AppSetting).filter(AppSetting.key == "DEFAULT_CURRENCY", AppSetting.organization_id == "1").one()
    assert fila.value == "USD"
    # Ya no hay fila suelta con el alias.
    assert db.query(AppSetting).filter(AppSetting.key == "currency").count() == 0
    assert _general(db, "1")["currency"] == "USD"


def test_general_ensena_el_valor_efectivo_y_una_vez_por_clave(db):
    # Una fila vieja del alias (anterior a la revisión 185) no manda ni se duplica.
    db.add(AppSetting(key="timezone", value="Asia/Tokyo", organization_id="1"))
    db.commit()
    update_setting("timezone", "Europe/Lisbon", "1", db)
    filas = [f for f in ajustes_generales_para(db, Audiencia.ADMIN, False, "1") if f["key"] == "timezone"]
    assert [f["value"] for f in filas] == ["Europe/Lisbon"]
    assert defaults_de_organizacion(db, "1", Audiencia.ADMIN)["timezone"] == "Europe/Lisbon"


def test_la_jornada_se_valida_como_numero(db):
    import pytest
    with pytest.raises(ValueError):
        update_setting("work_hours_per_day", "ocho", "1", db)
    update_setting("work_hours_per_day", "7.5", "1", db)
    assert defaults_de_organizacion(db, "1", Audiencia.ADMIN)["working_hours_per_day"] == 7.5


def test_los_cuatro_alias_salen_en_general(db):
    assert set(ALIAS_DE_EJECUCION) <= set(_general(db, "1"))


def test_otro_ajuste_general_sigue_en_su_fila(db):
    update_setting("idle_timeout_minutes", "15", "1", db)
    assert _general(db, "1")["idle_timeout_minutes"] == "15"
