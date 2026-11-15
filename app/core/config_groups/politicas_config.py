"""Motor de politicas, reglas y flujos (tarea #26). Se leen en vivo por empresa
(grupo `politicas` del catalogo de ajustes); estos son los valores por defecto."""
from pydantic import Field


class PoliticasSettingsMixin:
    POLICY_SIMULATION_DEFAULT_LAST_N: int = Field(
        default=100, env="POLICY_SIMULATION_DEFAULT_LAST_N",
        description="Policies — the simulator replays the last N entities of the domain unless a date range is given")
    POLICY_SIMULATION_MAX_ENTITIES: int = Field(
        default=1000, env="POLICY_SIMULATION_MAX_ENTITIES",
        description="Policies — maximum entities one simulation replays")
    POLICY_DOCUMENT_TYPES: str = Field(
        default="receipt,invoice,ticket,attendees,other", env="POLICY_DOCUMENT_TYPES",
        description="Policies — document types an outcome «require attachment» can ask for (CSV)")
