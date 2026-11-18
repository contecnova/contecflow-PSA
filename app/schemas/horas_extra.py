"""Entradas del API de horas extra (`/overtime`, 18-11-2026). Las salidas son diccionarios del servicio."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PeticionDeHorasExtraIn(BaseModel):
    user_id: Optional[str] = Field(None, description="Para quién (vacío: quien pide); su responsable puede pedir por él")
    fecha: date
    tipo: Literal["laborable", "fuera_de_franja", "festivo", "no_laborable", "guardia"] = "laborable"
    hora_inicio: Optional[str] = Field(None, description="HH:MM")
    hora_fin: Optional[str] = Field(None, description="HH:MM (si es menor que el inicio, cruza la medianoche)")
    horas: Optional[float] = Field(None, gt=0, le=24)
    motivo: Optional[str] = Field(None, max_length=4000)
    project_id: Optional[str] = None
    ticket_id: Optional[str] = Field(None, max_length=36)
    sustituto_id: Optional[str] = None
    compensacion: Optional[Literal["pago", "bolsa", "ninguna"]] = None


class VistaPreviaIn(PeticionDeHorasExtraIn):
    id: Optional[str] = Field(None, description="La petición que se está editando")


class RevisarIn(BaseModel):
    aprobado: bool
    nota: Optional[str] = Field(None, max_length=2000)
    horas_autorizadas: Optional[float] = Field(None, ge=0, le=24)


class NotaIn(BaseModel):
    nota: Optional[str] = Field(None, max_length=2000)


class LiquidarIn(BaseModel):
    referencia: str = Field(..., min_length=1, max_length=120)


class ConfigIn(BaseModel):
    activo: bool
    control_imputacion: Literal["ninguno", "avisar", "regularizar", "bloquear"]
    tolerancia_minutos: int = Field(15, ge=0, le=240)
    compensaciones: list[Literal["pago", "bolsa", "ninguna"]]
    compensacion_por_defecto: Literal["pago", "bolsa", "ninguna"]
    workflow_id: Optional[str] = None
    tipo_bolsa_id: Optional[str] = None
    pedir_en_nombre: bool = True
    exigir_motivo: bool = True


class PresupuestoIn(BaseModel):
    ambito: Literal["empresa", "departamento", "equipo", "proyecto"]
    valor: Optional[str] = Field(None, max_length=160)
    periodo: Literal["mes", "anio"] = "anio"
    anio: Optional[int] = Field(None, ge=2000, le=2100)
    horas: float = Field(..., ge=0)
    nota: Optional[str] = Field(None, max_length=255)
    activo: bool = True


class RegularizarIn(BaseModel):
    desde: date
    hasta: date
