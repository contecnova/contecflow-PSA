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

Rev. 180 (turnos y ausencias por horas) — más campos y resultados, para que
cualquier regla de un convenio se escriba sin código:

  · unidad y modo (días / horas), horas de la petición, máximo de horas en un
    día, hora de inicio y de fin (tipo «hora»), si es día completo, horas de la
    franja fuera de su horario;
  · mínimos y máximos por petición, día, mes y año: horas/días/peticiones del
    mismo tipo en el mes y el año contando esta;
  · antelación en días y preaviso en horas;
  · solapes con compañeros de equipo, turno, rol, sede y departamento;
  · antigüedad (meses desde el alta), tipo de contrato, sede, grupos;
  · saldo: el disponible, el que queda en su unidad y en horas; retribuido;
  · dependencias entre tipos: tipos que solapan, que van pegados (día
    laborable anterior o siguiente) y los usados en el año;
  · resultados propios: `saldo_negativo` (permite quedar en negativo hasta N)
    y `redondeo` (redondea las horas a múltiplos de 15/30/60 minutos); el
    `cupo` puede contar por franja horaria (`franja_minutos`).

Ejemplos: «Modo es horas Y Horas < 1» → bloquear («mínimo una hora»); «Horas
en el mes > 16» → +1 nivel; «Tipos que solapan está en [baja]» → bloquear;
«Antigüedad < 12 Y Tipo es asuntos_propios» → bloquear; «Días seguidos > 10»
→ exigir justificante; «Preaviso (horas) < 48» → avisar.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.services.politicas.registro import Campo, Dominio, Opcion, Parametro, ResultadoPropio, registrar

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
    # ── Rev. 180: horas, acumulados, solapes, persona, saldo, dependencias ──
    Campo("modo", "Se pide por", "enum", opciones=(Opcion("dias", "Días"), Opcion("horas", "Horas"))),
    Campo("horas", "Horas de la petición (de su horario)", "numero", operadores=_NUMERO_ENTERO,
          ayuda="Las horas de su turno o jornada que cubre; un día entero cuenta las de ese día"),
    Campo("horas_max_dia", "Máximo de horas en un mismo día", "numero", operadores=_NUMERO_ENTERO),
    Campo("hora_inicio", "Hora de inicio (por horas)", "hora"),
    Campo("hora_fin", "Hora de fin (por horas)", "hora"),
    Campo("dia_completo", "Todos los días completos", "booleano"),
    Campo("horas_fuera_de_horario", "Horas de la franja fuera de su horario", "numero", operadores=_NUMERO_ENTERO),
    Campo("horas_en_mes", "Horas del mismo tipo en el mes (con esta)", "numero", operadores=_NUMERO_ENTERO),
    Campo("dias_en_mes", "Días del mismo tipo en el mes (con esta)", "numero", operadores=_NUMERO_ENTERO),
    Campo("horas_en_anio", "Horas del mismo tipo en el año (con esta)", "numero", operadores=_NUMERO_ENTERO),
    Campo("dias_en_anio", "Días del mismo tipo en el año (con esta)", "numero", operadores=_NUMERO_ENTERO),
    Campo("peticiones_en_mes", "Peticiones del mismo tipo en el mes (con esta)", "numero", operadores=_NUMERO_ENTERO),
    Campo("peticiones_en_anio", "Peticiones del mismo tipo en el año (con esta)", "numero", operadores=_NUMERO_ENTERO),
    Campo("antelacion_horas", "Preaviso (horas)", "numero", operadores=_NUMERO_ENTERO,
          ayuda="Horas entre la petición y el comienzo de la ausencia en su horario"),
    Campo("ausentes_mismo_turno", "Ausentes de su mismo turno (máx. en un día)", "numero", operadores=_NUMERO_ENTERO),
    Campo("ausentes_mismo_rol", "Ausentes de su mismo rol (máx. en un día)", "numero", operadores=_NUMERO_ENTERO),
    Campo("ausentes_misma_sede", "Ausentes de su misma sede (máx. en un día)", "numero", operadores=_NUMERO_ENTERO),
    Campo("ausentes_mismo_departamento", "Ausentes de su departamento (máx. en un día)", "numero",
          operadores=_NUMERO_ENTERO),
    Campo("sede", "Sede de la persona", "enum"),
    Campo("grupos", "Grupos de la persona", "entidad", entidad="grupo",
          operadores=("eq", "ne", "in", "not_in", "empty", "not_empty")),
    Campo("tipo_de_contrato", "Tipo de contrato", "enum"),
    Campo("antiguedad_meses", "Antigüedad (meses)", "numero", operadores=_NUMERO_ENTERO,
          ayuda="Desde la fecha de alta hasta el primer día; vacío si no hay fecha de alta"),
    Campo("saldo_disponible", "Saldo antes de la petición", "numero", operadores=_NUMERO_ENTERO),
    Campo("saldo_restante_horas", "Saldo que queda, en horas", "numero", operadores=_NUMERO_ENTERO),
    Campo("retribuido", "Permiso retribuido", "booleano"),
    Campo("tipos_solapados", "Tipos de sus otras ausencias que solapan", "enum",
          operadores=("in", "not_in", "empty", "not_empty"), ayuda="Para dependencias: no pedir X si hay Y"),
    Campo("tipos_contiguos", "Tipos de sus ausencias pegadas (día laborable antes o después)", "enum",
          operadores=("in", "not_in", "empty", "not_empty")),
    Campo("tipos_en_el_anio", "Tipos que ya ha usado en el año", "enum",
          operadores=("in", "not_in", "empty", "not_empty")),
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
        Parametro("franja_minutos", "Contar por franja horaria de (minutos)", "numero", defecto=0, minimo=0,
                  obligatorio=False, ayuda="0 = el día entero; 60 = por horas: un permiso por horas solo ocupa sus franjas"),
        Parametro("momento", "La plaza se asigna", "enum", defecto="solicitud", opciones=(
            Opcion("solicitud", "Al pedirla (por orden de llegada)"), Opcion("aprobacion", "Al aprobarla"))),
        Parametro("si_lleno", "Si está lleno", "resultados", defecto=[{"tipo": "waitlist", "mensaje": ""}],
                  obligatorio=False),
        Parametro("avisar_al_promover", "Al dar la plaza a quien espera, avisar a", "destinatarios",
                  defecto=[{"tipo": "solicitante"}], obligatorio=False),
        Parametro("canales", "Por", "canales", defecto=["app"], obligatorio=False),
    ),
)


SALDO_NEGATIVO = ResultadoPropio(
    clave="saldo_negativo", etiqueta="Permitir saldo negativo",
    ayuda="La petición puede dejar el saldo en negativo hasta este límite (en la unidad del saldo)",
    parametros=(Parametro("hasta", "Hasta (en negativo)", "numero", defecto=0, minimo=0),),
)

REDONDEO = ResultadoPropio(
    clave="redondeo", etiqueta="Redondear las horas",
    ayuda="Las horas que descuenta la petición se redondean a múltiplos de estos minutos",
    parametros=(
        Parametro("minutos", "Múltiplos de (minutos)", "enum", defecto="30", opciones=(
            Opcion("15", "15"), Opcion("30", "30"), Opcion("60", "60"), Opcion("240", "240"))),
        Parametro("modo", "Redondeo", "enum", defecto="arriba", opciones=(
            Opcion("arriba", "Hacia arriba"), Opcion("abajo", "Hacia abajo"), Opcion("cercano", "Al más cercano"))),
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
    if resultado.get("tipo") == "saldo_negativo":
        return [], reglas.resolver_saldo_negativo(ctx, resultado)
    if resultado.get("tipo") == "redondeo":
        h = float(ctx.get("horas") or 0)
        return [], {"horas": h, "redondeadas": reglas.redondear(h, int(resultado.get("minutos") or 0),
                                                               resultado.get("modo") or "arriba")}
    return [], {}


def tipos_de_documento(db) -> list:
    from app.services.ausencias import catalogo
    return [Opcion(d.clave, d.nombre) for d in catalogo.documentos(db)]


def opciones_dinamicas(db) -> dict:
    from app.models.advanced_config import Office
    from app.models.user import User
    from app.services.ausencias import catalogo, turnos
    tipos = [Opcion(t.clave, t.nombre) for t in catalogo.tipos(db, incluir_inactivos=True)]
    sedes = [Opcion(o.id, o.name) for o in db.query(Office).order_by(Office.name).all()]
    contratos = sorted({c for (c,) in db.query(User.employment_type).filter(User.employment_type.isnot(None)).distinct()
                        if c})
    return {"tipo": tipos, "tipos_solapados": tipos, "tipos_contiguos": tipos, "tipos_en_el_anio": tipos,
            "turno": [Opcion(t.id, t.nombre) for t in turnos.turnos(db, incluir_inactivos=True)],
            "ubicacion": sedes, "sede": sedes, "tipo_de_contrato": [Opcion(c, c) for c in contratos]}


def al_publicar(db, politica: dict) -> None:
    from app.services.ausencias import cupos
    cupos.sembrar_politica(db, politica)


def ejemplos(db, usuario) -> dict:
    from app.services.ausencias import ejemplos as ej
    return {"tablas": [], "politicas": [ej.politica_de_ejemplo()]}


registrar(Dominio(
    clave="ausencias", etiqueta="Ausencias", campos=CAMPOS, contexto=contexto, cargar=cargar,
    historicos=historicos, propietario=lambda a: a.user_id, resumen=resumen,
    tipo_de_aprobacion="leave", cumple_requisito=cumple_requisito, ejemplos=ejemplos,
    resultados_propios=(CUPO, SALDO_NEGATIVO, REDONDEO), resolver_propio=resolver_propio, admite_lista_de_espera=True,
    usos_de_tabla=(Opcion("derecho", "Derecho de un saldo de ausencias (por país, ciudad y tipo o contrato)"),),
    tipos_de_documento=tipos_de_documento, opciones_dinamicas=opciones_dinamicas, al_publicar=al_publicar,
))
