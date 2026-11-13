"""
Empresas y costes de personal: valores por defecto (barrido «nada en duro» 2026-11).

Antes, numeros escritos en el endpoint de empresas (`max_users=25`,
`max_projects=100`) y en `app.core.constantes` (horas productivas y sobrecoste
de empresa). Ahora son ajustes con el mismo valor por defecto; los de coste
tambien se pueden cambiar por empresa (grupo `locale` del registro en vivo) y
los de alta de empresa son de plataforma (grupo `tenants`).

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from pydantic import Field


class EmpresaSettingsMixin:
    # ── Alta de una empresa (plataforma) ─────────────────────────────────────
    ORG_DEFAULT_MAX_USERS: int = Field(default=25, ge=1, env="ORG_DEFAULT_MAX_USERS")
    ORG_DEFAULT_MAX_PROJECTS: int = Field(default=100, ge=1, env="ORG_DEFAULT_MAX_PROJECTS")

    # ── Coste de personal (cuando ni la ficha ni el preset del pais dicen otra cosa)
    # Horas productivas al año: base de `coste/hora = coste anual / horas`.
    DEFAULT_PRODUCTIVE_HOURS_YEAR: float = Field(default=1700.0, gt=0, env="DEFAULT_PRODUCTIVE_HOURS_YEAR")
    # Sobrecoste de empresa sobre el bruto (0.32 = 32 %).
    DEFAULT_EMPLOYER_COST_PCT: float = Field(default=0.32, ge=0, env="DEFAULT_EMPLOYER_COST_PCT")
