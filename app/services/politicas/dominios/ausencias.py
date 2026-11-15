"""Dominio `ausencias` del motor de políticas (tarea #25).

Mapea `Absence` al catálogo del motor. El ciclo de vida (pedir, cupos, lista
de espera, decidir, documentos) vive en `app/services/ausencias/`; aquí solo lo
que el motor necesita:

- los CAMPOS tipados (tipo, días, periodo, turno, equipo, departamento,
  ubicación, rol, persona, sustituto, saldo que queda, antelación, días
  seguidos, compañeros ausentes, cobertura que queda…), con las opciones que
  dependen de la empresa (tipos, turnos, oficinas: `opciones_dinamicas`);
- el resultado propio `cupo` (como mucho N personas ausentes por día × turno ×
  grupo, en el momento de pedir o de aprobar, y qué pasa si está lleno: lista
  de espera, bloqueo, aviso…), que resuelve `reglas.resolver_cupo`;
- la lista de espera (`waitlist`) y los tipos de documento del dominio.

Reglas típicas que se escriben en la pantalla, sin código:
  · cierre de vacaciones: «Periodo solapa con 20/12–06/01» → bloquear;
  · antelación mínima: «Antelación < 15 días» → avisar o bloquear;
  · máximo de días seguidos: «Días seguidos > 15» → +1 nivel de aprobación;
  · cobertura mínima: «Cobertura que queda < 0» → bloquear o avisar;
  · sustituto obligatorio: «Sustituto está vacío» → bloquear;
  · saldo: «Saldo que queda < 0» → bloquear.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.services.politicas.catalogo import Campo, Dominio, Opcion, Parametro, ResultadoPropio, registrar

_NUMERO_ENTERO = ("gt", "gte", "lt", "lte", "eq", "ne", "between")

CAMPOS = [
    Campo("tipo", "Tipo de ausencia", "enum", categoria_de_tabla=True),
    Campo("unidad", "Unidad", "enum", opciones=(Opcion("dias", "Días"), Opcion("medios_dias", "Medios días"),
                                                Opcion("horas", "Horas"))),
    Campo("cantidad", "Cantidad (en la unidad del tipo)", "numero", operadores=_NUMERO_ENTERO),
    Campo("dias_laborables", "Días laborables", "numero", operadores=_NUMERO_ENTERO,
          ayuda="Los días con turno (cuadrante) o, sin cuadrante, de lunes a viernes salvo festivos"),
    Campo("dias_consecutivos", "Días seguidos (naturales)", "numero", operadores=_NUMERO_ENTERO),
    Campo("fecha_inicio", "Primer día", "fecha"),
    Campo("fecha_fin", "Último día", "fecha"),
    Campo("periodo", "Periodo de la ausencia", "periodo",
          ayuda="Para cierres: «solapa con» un periodo bloqueado"),
    Campo("turno", "Turno", "enum"),
    Campo("ubicacion", "Oficina del turno", "enum"),
    Campo("equipo", "Equipo", "entidad", entidad="equipo"),
    Campo("departamento", "Departamento", "entidad", entidad="departamento"),
    Campo("rol", "Rol", "entidad", entidad="rol"),
    Campo("persona", "Persona", "entidad", entidad="usuario"),
    Campo("sustituto", "Sustituto", "entidad", entidad="usuario"),
    Campo("saldo_restante", "Saldo que queda (tras la petición)", "numero", operadores=_NUMERO_ENTERO,
          ayuda="Vacío si el tipo no descuenta saldo"),
    Campo("antelacion_dias", "Antelación (días)", "numero", operadores=_NUMERO_ENTERO,
          ayuda="Días entre la petición y el primer día"),
    Campo("companeros_ausentes", "Compañeros de equipo ausentes (máx. en un día)", "numero", operadores=_NUMERO_ENTERO),
    Campo("cobertura_restante", "Cobertura que queda en el peor turno", "numero", operadores=_NUMERO_ENTERO,
          ayuda="Personas disponibles menos las requeridas, contando esta ausencia; negativo = falta gente"),
    Campo("datos_especiales", "Datos de categoría especial (salud)", "booleano"),
    Campo("motivo", "Motivo", "texto"),
    Campo("documentos", "Documentos adjuntos", "numero", operadores=_NUMERO_ENTERO),
]

CUPO = ResultadoPropio(
    clave="cupo", etiqueta="Cupo de personas ausentes",
    ayuda="Como mucho N personas ausentes a la vez por día (y turno) dentro de un grupo",
    parametros=(
        Parametro("clave", "Identificador", "clave"),
        Parametro("maximo", "Máximo de personas ausentes", "numero", defecto=2, minimo=0),
        Parametro("agrupar_por", "Por cada", "enum", defecto="equipo", opciones=(
            Opcion("empresa", "Toda la empresa"), Opcion("equipo", "Equipo"), Opcion("departamento", "Departamento"),
            Opcion("ubicacion", "Oficina"), Opcion("rol", "Rol"), Opcion("turno", "Turno"),
            Opcion("grupo", "Grupo personalizado"))),
        Parametro("grupo_id", "Grupo", "entidad", entidad="grupo", visible_si=("agrupar_por", ("grupo",))),
        Parametro("por_turno", "Contar cada turno por separado", "booleano", defecto=True, obligatorio=False),
        Parametro("momento", "La plaza se asigna", "enum", defecto="solicitud", opciones=(
            Opcion("solicitud", "Al pedirla (por orden de llegada)"), Opcion("aprobacion", "Al aprobarla"))),
        Parametro("si_lleno", "Si está lleno", "resultados", defecto=[{"tipo": "waitlist", "mensaje": ""}],
                  obligatorio=False),
        Parametro("avisar_al_promover", "Al dar la plaza a quien espera, avisar a", "destinatarios",
                  defecto=[{"tipo": "solicitante"}], obligatorio=False),
        Parametro("canales", "Por", "canales", defecto=["app"], obligatorio=False),
    ),
)


def contexto(db, a) -> dict:
    from app.services.ausencias import reglas
    return reglas.contexto(db, a)


def cargar(db, entidad_id: str):
    from app.models.resources import Absence
    return db.query(Absence).filter(Absence.id == entidad_id).first()


def historicos(db, desde: Optional[date], hasta: Optional[date], limite: int) -> list:
    """Ausencias pedidas alguna vez (no canceladas), las más recientes primero."""
    from app.models.resources import Absence, AbsenceStatus
    q = db.query(Absence).filter(Absence.status != AbsenceStatus.cancelled)
    if desde:
        q = q.filter(Absence.start_date >= desde)
    if hasta:
        q = q.filter(Absence.start_date <= hasta)
    return q.order_by(Absence.start_date.desc(), Absence.created_at.desc()).limit(limite).all()


def resumen(a) -> str:
    return f"{a.type} · {a.start_date} → {a.end_date} · {a.working_days or 0:g} d"


def cumple_requisito(db, a, requisito: dict) -> bool:
    if requisito.get("tipo") == "require_justification":
        return bool((a.reason or "").strip())
    if requisito.get("tipo") == "require_attachment":
        if not a.id:
            return False
        from app.models.ausencias import DocumentoDeAusencia, TipoDeDocumentoDeAusencia
        q = db.query(DocumentoDeAusencia.id).filter(DocumentoDeAusencia.absence_id == a.id,
                                                   DocumentoDeAusencia.estado == "vigente")
        tipos = requisito.get("tipos_de_documento") or []
        if tipos:
            q = q.join(TipoDeDocumentoDeAusencia, TipoDeDocumentoDeAusencia.id == DocumentoDeAusencia.tipo_id) \
                .filter(TipoDeDocumentoDeAusencia.clave.in_(tipos))
        return q.first() is not None
    return True


def resolver_propio(db, ctx: dict, resultado: dict) -> tuple:
    from app.services.ausencias import reglas
    if resultado.get("tipo") == "cupo":
        return reglas.resolver_cupo(db, ctx, resultado)
    return [], {}


def tipos_de_documento(db) -> list:
    from app.services.ausencias import catalogo
    return [Opcion(d.clave, d.nombre) for d in catalogo.documentos(db)]


def opciones_dinamicas(db) -> dict:
    from app.models.advanced_config import Office
    from app.services.ausencias import catalogo, turnos
    return {"tipo": [Opcion(t.clave, t.nombre) for t in catalogo.tipos(db, incluir_inactivos=True)],
            "turno": [Opcion(t.id, t.nombre) for t in turnos.turnos(db, incluir_inactivos=True)],
            "ubicacion": [Opcion(o.id, o.name) for o in db.query(Office).order_by(Office.name).all()]}


def ejemplos(db, usuario) -> dict:
    from app.services.ausencias import ejemplos as ej
    return {"tablas": [], "politicas": [ej.politica_de_ejemplo()]}


registrar(Dominio(
    clave="ausencias", etiqueta="Ausencias", campos=CAMPOS, contexto=contexto, cargar=cargar,
    historicos=historicos, propietario=lambda a: a.user_id, resumen=resumen,
    tipo_de_aprobacion="leave", cumple_requisito=cumple_requisito, ejemplos=ejemplos,
    resultados_propios=(CUPO,), resolver_propio=resolver_propio, admite_lista_de_espera=True,
    tipos_de_documento=tipos_de_documento, opciones_dinamicas=opciones_dinamicas,
))
