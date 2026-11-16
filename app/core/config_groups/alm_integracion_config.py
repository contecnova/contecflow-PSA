"""Licencias y hardware — fase 4: integración (16-11-2026). Se leen en vivo por
empresa (grupo `licencias_integracion` del catálogo de ajustes); estos son los
valores por defecto."""
from pydantic import Field


class ALMIntegracionSettingsMixin:
    ALM_OFFBOARDING_LICENSE_RELEASE_DAYS: int = Field(
        default=0, ge=0, env="ALM_OFFBOARDING_LICENSE_RELEASE_DAYS",
        description="Offboarding — days after the leaving date to release the person's licences (0: at once)")
    ALM_OFFBOARDING_PENDING_ASSETS: str = Field(
        default="avisar", env="ALM_OFFBOARDING_PENDING_ASSETS",
        description="Offboarding — equipment not yet returned: avisar (warn), confirmar (a manual "
                    "deactivation must confirm it) or bloquear (a manual deactivation is refused; "
                    "SCIM and contract end are never blocked)")
    ALM_RETURN_DUE_DAYS: int = Field(
        default=7, ge=0, env="ALM_RETURN_DUE_DAYS",
        description="Returns — days the person has to return each piece of equipment (0: no deadline)")
    ALM_RETURN_GROUP_ID: str = Field(
        default="", env="ALM_RETURN_GROUP_ID",
        description="Returns — service desk queue (group id) for return tickets; empty: routing rules")
    ALM_PURCHASE_GROUP_ID: str = Field(
        default="", env="ALM_PURCHASE_GROUP_ID",
        description="Purchases — queue (group id) for purchase requests when no seat or unit is free; "
                    "empty: routing rules")
    ALM_BREAKDOWN_GROUP_ID: str = Field(
        default="", env="ALM_BREAKDOWN_GROUP_ID",
        description="Breakdowns — queue (group id) for faults reported from «My equipment»; empty: routing rules")
    ALM_KIT_ON_HIRE: bool = Field(
        default=True, env="ALM_KIT_ON_HIRE",
        description="Onboarding — propose the matching kit when a person is created (manually or by SCIM)")
    ALM_KIT_FALLBACK_ROLES: str = Field(
        default="admin,hr", env="ALM_KIT_FALLBACK_ROLES",
        description="Onboarding — roles that confirm a kit when the new person has no manager (CSV)")
    ALM_CONTRACT_END_OFFBOARDING: bool = Field(
        default=True, env="ALM_CONTRACT_END_OFFBOARDING",
        description="Offboarding — when a subcontractor's contract ends (available until), open the "
                    "offboarding automatically")
