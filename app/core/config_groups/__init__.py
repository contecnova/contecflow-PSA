"""
Configuration mixins grouped by domain.

These mixins are merged into the main `Settings` class in `app.core.config` to
keep that file focused on cross-cutting concerns (security, secrets, validators)
while domain-specific knobs live next to their logical group.

Each mixin is a plain Python class with pydantic Field annotations. They are
inherited by `Settings(BaseSettings)` — pydantic-settings 2.x merges field
definitions from mixins seamlessly as long as the mixins themselves are NOT
subclasses of BaseSettings.
"""
from app.core.config_groups.ai_config import AISettingsMixin
from app.core.config_groups.sla_config import SLASettingsMixin
from app.core.config_groups.health_config import HealthSettingsMixin
from app.core.config_groups.semantic_config import SemanticSettingsMixin
from app.core.config_groups.service_desk_config import ServiceDeskSettingsMixin
from app.core.config_groups.automations_config import AutomationsSettingsMixin
from app.core.config_groups.proceso_config import INTERRUPTORES_DE_PROCESO, ProcesoSettingsMixin
from app.core.config_groups.escalas_config import EscalasSettingsMixin
from app.core.config_groups.empresa_config import EmpresaSettingsMixin

__all__ = [
    "AISettingsMixin",
    "SLASettingsMixin",
    "HealthSettingsMixin",
    "SemanticSettingsMixin",
    "ServiceDeskSettingsMixin",
    "AutomationsSettingsMixin",
    "ProcesoSettingsMixin",
    "EscalasSettingsMixin",
    "EmpresaSettingsMixin",
    "INTERRUPTORES_DE_PROCESO",
]
