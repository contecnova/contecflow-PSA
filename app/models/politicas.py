"""Motor común de políticas, reglas y flujos (tarea #26, revisión 165).

Un solo motor para gastos, ausencias y los procesos que vengan (compras, partes
de horas, viajes…). El motor no conoce ningún dominio: cada dominio registra su
catálogo de campos (`app/services/politicas/catalogo.py`) y el motor evalúa
árboles de condiciones tipadas contra el contexto que el dominio le da.

Tablas:

- `politicas`: una VERSIÓN de una política. Las versiones de la misma política
  comparten `familia_id`; solo una está `publicada` a la vez. Ámbito (a quién
  aplica), prioridad, vigencia y si está activa.
- `politica_reglas`: las reglas de una versión. Cada una es un árbol de
  condiciones (grupos Y/O de condiciones tipadas) y unos resultados graduados,
  con bandas por porcentaje de exceso sobre una referencia.
- `tablas_de_referencia` y `tabla_de_referencia_filas`: valores por país,
  ciudad y categoría, con moneda y vigencia («comida ≤ el valor de la tabla
  para la ciudad del gasto» sin una regla por país).
- `politica_evaluaciones`: la explicación de cada evaluación guardada (qué
  política y regla encajó, qué valores se compararon, qué salió), para auditar
  y para enseñarle al usuario por qué.

El ámbito, las condiciones, los resultados y la explicación se guardan como
JSON, y se editan SOLO desde la pantalla «Políticas y reglas»: nadie escribe
JSON a mano. El formato está documentado en DOCS.md («Motor de políticas»).
"""
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Politica(Base):
    __tablename__ = "politicas"
    __table_args__ = (
        Index("ix_politicas_org_dominio_estado", "organization_id", "dominio", "estado"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    familia_id = Column(String(36), nullable=False, index=True)      # igual en todas las versiones
    version = Column(Integer, nullable=False, default=1)
    estado = Column(String(12), nullable=False, default="borrador")   # borrador | publicada | retirada
    dominio = Column(String(40), nullable=False)                      # gastos | ausencias | …
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    prioridad = Column(Integer, nullable=False, default=100)          # mayor = se evalúa antes y gana empates
    activa = Column(Boolean, nullable=False, default=True)
    vigente_desde = Column(Date, nullable=True)
    vigente_hasta = Column(Date, nullable=True)
    ambito = Column(Text, nullable=True)                              # JSON: departamentos, equipos, roles, ubicaciones, personas
    nota_de_version = Column(String(500), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    publicada_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    publicada_en = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    reglas = relationship("ReglaDePolitica", back_populates="politica", order_by="ReglaDePolitica.orden",
                          cascade="all, delete-orphan")


class ReglaDePolitica(Base):
    __tablename__ = "politica_reglas"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    politica_id = Column(String(36), ForeignKey("politicas.id", ondelete="CASCADE"), nullable=False, index=True)
    orden = Column(Integer, nullable=False, default=1)
    nombre = Column(String(200), nullable=False)
    activa = Column(Boolean, nullable=False, default=True)
    condicion = Column(Text, nullable=True)       # JSON: árbol de grupos y condiciones; vacío = siempre
    resultados = Column(Text, nullable=True)      # JSON: lista de resultados si la condición se cumple
    exceso = Column(Text, nullable=True)          # JSON: medida del exceso sobre una referencia y sus bandas
    detener = Column(Boolean, nullable=False, default=False)  # si encaja, no se miran las reglas siguientes de la política

    politica = relationship("Politica", back_populates="reglas")


class TablaDeReferencia(Base):
    __tablename__ = "tablas_de_referencia"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    dominio = Column(String(40), nullable=True)                 # vacío: la usa cualquier dominio
    tipo_de_valor = Column(String(10), nullable=False, default="importe")   # importe | numero
    moneda = Column(String(3), nullable=True)                   # moneda por defecto de las filas nuevas
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    filas = relationship("FilaDeTablaDeReferencia", back_populates="tabla", cascade="all, delete-orphan",
                         order_by="(FilaDeTablaDeReferencia.pais, FilaDeTablaDeReferencia.ciudad)")


class FilaDeTablaDeReferencia(Base):
    __tablename__ = "tabla_de_referencia_filas"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    tabla_id = Column(String(36), ForeignKey("tablas_de_referencia.id", ondelete="CASCADE"), nullable=False, index=True)
    pais = Column(String(2), nullable=True)          # ISO 3166-1 alfa-2; vacío = cualquier país (fila por defecto)
    ciudad = Column(String(120), nullable=True)      # vacío = cualquier ciudad del país
    categoria = Column(String(60), nullable=True)    # vacío = cualquier categoría
    valor = Column(Float, nullable=False)
    moneda = Column(String(3), nullable=True)        # con tipo_de_valor = importe
    vigente_desde = Column(Date, nullable=True)
    vigente_hasta = Column(Date, nullable=True)

    tabla = relationship("TablaDeReferencia", back_populates="filas")


class EvaluacionDePolitica(Base):
    __tablename__ = "politica_evaluaciones"
    __table_args__ = (
        Index("ix_politica_evaluaciones_entidad", "dominio", "entidad_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    dominio = Column(String(40), nullable=False)
    entidad_id = Column(String(64), nullable=False)
    momento = Column(String(30), nullable=False, default="envio")     # lo pone el dominio: envio, reenvio…
    decision = Column(String(20), nullable=False)                      # block | review | auto_approve | allow
    resultado = Column(Text, nullable=False)       # JSON: resultados combinados (ver resultados.combinar)
    explicacion = Column(Text, nullable=False)     # JSON: por política y regla, la traza de cada condición
    solicitud_id = Column(String(36), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    evaluado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
