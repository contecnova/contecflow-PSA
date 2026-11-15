"""Dominio `gastos` del motor de políticas (tareas #26 y #27).

Mapea `Expense` al catálogo del motor. El envío del gasto lo evalúa
(`app/services/gastos_politicas.py`); aquí solo vive lo que el motor necesita
saber del gasto:

- los CAMPOS que una política puede usar, incluidos los calculados: importe
  por asistente, total del día (todas las categorías o la del gasto), total
  del viaje, tarifa por km, fin de semana, festivo, cliente y facturabilidad
  del proyecto, rol, departamento, equipo y grado de quien gasta;
- cómo se cumple un requisito: `require_attachment` con `tipos_de_documento`
  pide al menos un justificante de ALGUNO de esos tipos (varios resultados
  `require_attachment` se exigen todos);
- el uso `kilometraje` de una tabla de referencia: la tarifa por km del país
  (y ciudad) del gasto, que el servidor usa para calcular el importe;
- los ejemplos que un administrador puede cargar («Cargar ejemplos»).

Los importes que suman varios gastos (día, viaje) se convierten a la moneda de
ESTE gasto al tipo de cambio de la fecha de cada uno; si falta un tipo de
cambio el valor queda vacío y la condición, indeterminada (aviso, nunca 1:1).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.services.politicas.catalogo import Campo, Dominio, Opcion, registrar

_CATEGORIAS = (("travel", "Viajes"), ("accommodation", "Alojamiento"), ("meals", "Comidas"),
               ("software", "Software"), ("hardware", "Hardware"), ("training", "Formación"),
               ("subcontract", "Subcontratación"), ("other", "Otros"))

_CONVERTIDO = "Se compara en la moneda de la condición, al tipo de cambio de la fecha del gasto"

CAMPOS = [
    Campo("categoria", "Categoría", "enum", opciones=tuple(Opcion(v, e) for v, e in _CATEGORIAS),
          categoria_de_tabla=True),
    Campo("importe", "Importe", "importe", ayuda=_CONVERTIDO),
    Campo("importe_local", "Importe en su moneda (sin convertir)", "numero",
          ayuda="La cifra tal cual, en la moneda del gasto: úsala junto a «Moneda»"),
    Campo("moneda", "Moneda", "texto", operadores=("eq", "ne", "in", "not_in")),
    Campo("asistentes", "Asistentes (incluida quien paga)", "numero"),
    Campo("importe_por_asistente", "Importe por asistente", "importe", ayuda=_CONVERTIDO),
    Campo("importe_dia", "Total del día (todas las categorías)", "importe",
          ayuda="Este gasto más los demás de la misma persona y fecha (salvo rechazados)"),
    Campo("importe_dia_categoria", "Total del día en su categoría", "importe",
          ayuda="Este gasto más los demás de la misma persona, fecha y categoría (salvo rechazados)"),
    Campo("viaje", "Viaje", "enum", operadores=("eq", "ne", "in", "not_in"),
          ayuda="Los viajes que ya tienen gastos"),
    Campo("importe_viaje", "Total del viaje", "importe",
          ayuda="Este gasto más los demás del mismo viaje y persona (salvo rechazados)"),
    Campo("km", "Kilómetros", "numero"),
    Campo("tarifa_km", "Tarifa por km", "importe", ayuda="Importe ÷ kilómetros"),
    Campo("fecha", "Fecha del gasto", "fecha"),
    Campo("fin_de_semana", "En fin de semana", "booleano"),
    Campo("festivo", "En día festivo", "booleano",
          ayuda="Festivos de la empresa (Ajustes); uno con país solo cuenta en ese país"),
    Campo("pais", "País", "pais"),
    Campo("ciudad", "Ciudad", "ciudad"),
    Campo("proyecto", "Proyecto", "entidad", entidad="proyecto"),
    Campo("cliente", "Cliente del proyecto", "entidad", entidad="cliente"),
    Campo("proyecto_facturable", "Proyecto facturable", "booleano"),
    Campo("facturable", "Facturable al cliente", "booleano", asignable=True),
    Campo("descripcion", "Descripción", "texto"),
    Campo("notas", "Justificación (notas)", "texto"),
    Campo("justificantes", "Justificantes adjuntos", "numero"),
    Campo("persona", "Persona", "entidad", entidad="usuario"),
    Campo("rol", "Rol de quien gasta", "entidad", entidad="rol"),
    Campo("departamento", "Departamento", "entidad", entidad="departamento"),
    Campo("equipo", "Equipo", "entidad", entidad="equipo"),
    Campo("grado", "Grado de quien gasta", "enum", operadores=("eq", "ne", "in", "not_in"),
          ayuda="Los grados de la ficha de cada persona"),
]

#: Uso de una tabla de referencia de gastos además de las reglas.
USO_KILOMETRAJE = "kilometraje"
NO_RECHAZADO = ("draft", "submitted", "approved", "reimbursed")


def _usuario(db, user_id):
    from app.models.user import User
    return db.query(User).filter(User.id == user_id).first() if user_id else None


def _valor(x):
    return str(getattr(x, "value", x)) if x is not None else None


def _tipo(db, desde: str, hacia: str, fecha: date, cache: dict) -> Optional[float]:
    desde, hacia = (desde or "").upper(), (hacia or "").upper()
    if not desde or not hacia or desde == hacia:
        return 1.0
    clave = (desde, hacia, fecha)
    if clave not in cache:
        from app.services.currency_rates_service import get_rate, get_rate_inverse
        fila = get_rate(db, desde, hacia, fecha)
        if fila and fila.rate:
            cache[clave] = float(fila.rate)
        else:
            inv = get_rate_inverse(db, desde, hacia, fecha)
            cache[clave] = (1.0 / float(inv.rate)) if inv and inv.rate else None
    return cache[clave]


def _total(db, e, *filtros) -> Optional[dict]:
    """Este gasto más los de la misma persona que cumplan `filtros`, en la moneda de este."""
    from app.models.expenses import Expense, ExpenseStatus
    moneda = (e.currency or "").upper() or None
    otros = db.query(Expense.amount, Expense.currency, Expense.expense_date).filter(
        Expense.user_id == e.user_id, Expense.id != e.id, Expense.is_active.is_(True),
        Expense.status.in_([ExpenseStatus(s) for s in NO_RECHAZADO]), *filtros).all()
    total, cache = float(e.amount or 0), {}
    for importe, mon, fecha in otros:
        tipo = _tipo(db, mon or moneda, moneda, fecha or e.expense_date, cache)
        if tipo is None:
            return None
        total += float(importe or 0) * tipo
    return {"cantidad": round(total, 2), "moneda": moneda}


def _festivo(db, e, pais: Optional[str]) -> bool:
    from app.models.settings import Holiday
    if not e.expense_date:
        return False
    for (aplica,) in db.query(Holiday.applies_to).filter(Holiday.date == e.expense_date).all():
        if not (aplica or "").strip() or (pais and aplica.strip().upper() == pais):
            return True
    return False


def documentos(db, e) -> list[Optional[str]]:
    """El tipo de cada justificante (None si no lo tiene; el antiguo `receipt_url` cuenta como uno sin tipo)."""
    from app.models.expenses import ExpenseAttachment
    tipos = [t for (t,) in db.query(ExpenseAttachment.document_type).filter(ExpenseAttachment.expense_id == e.id).all()]
    return tipos + ([None] if e.receipt_url else [])


def contexto(db, e) -> dict:
    from app.models.expenses import Expense
    from app.models.project import Project
    u = _usuario(db, e.user_id)
    rol = _valor(getattr(u, "role", None))
    pais = (e.country or "").upper() or None
    moneda = (e.currency or "").upper() or None
    importe = float(e.amount or 0)
    asistentes = int(e.attendees) if e.attendees and e.attendees > 0 else 1
    proyecto = db.query(Project.client_id, Project.is_billable).filter(Project.id == e.project_id).first() \
        if e.project_id else None
    dia = [Expense.expense_date == e.expense_date] if e.expense_date else [Expense.id.is_(None)]
    trip = (e.trip or "").strip()
    return {
        "categoria": _valor(e.category),
        "importe": {"cantidad": importe, "moneda": moneda},
        "importe_local": importe,
        "moneda": moneda,
        "asistentes": asistentes,
        "importe_por_asistente": {"cantidad": round(importe / asistentes, 2), "moneda": moneda},
        "importe_dia": _total(db, e, *dia) if e.expense_date else None,
        "importe_dia_categoria": _total(db, e, *dia, Expense.category == e.category) if e.expense_date else None,
        "viaje": trip or None,
        "importe_viaje": _total(db, e, Expense.trip == trip) if trip else None,
        "km": e.km,
        "tarifa_km": {"cantidad": round(importe / float(e.km), 4), "moneda": moneda} if e.km else None,
        "fecha": e.expense_date,
        "fin_de_semana": bool(e.expense_date and e.expense_date.isoweekday() >= 6),
        "festivo": _festivo(db, e, pais),
        "pais": pais,
        "ciudad": e.city,
        "proyecto": e.project_id,
        "cliente": proyecto[0] if proyecto else None,
        "proyecto_facturable": bool(proyecto[1]) if proyecto else False,
        "facturable": bool(e.is_billable),
        "descripcion": e.description,
        "notas": e.notes,
        "justificantes": len(documentos(db, e)),
        "persona": e.user_id,
        "rol": rol,
        "departamento": getattr(u, "department", None),
        "equipo": getattr(u, "team", None),
        "grado": getattr(u, "grade", None),
        "_sujeto": {"usuario_id": e.user_id, "rol": rol, "departamento": getattr(u, "department", None),
                    "equipo": getattr(u, "team", None), "pais": pais, "ciudad": e.city},
        "_fecha": e.expense_date,
    }


def cargar(db, entidad_id: str):
    from app.models.expenses import Expense
    return db.query(Expense).filter(Expense.id == entidad_id).first()


def historicos(db, desde: Optional[date], hasta: Optional[date], limite: int) -> list:
    """Gastos enviados alguna vez (no borradores), los más recientes primero."""
    from app.models.expenses import Expense, ExpenseStatus
    q = db.query(Expense).filter(Expense.is_active.is_(True), Expense.status != ExpenseStatus.draft)
    if desde:
        q = q.filter(Expense.expense_date >= desde)
    if hasta:
        q = q.filter(Expense.expense_date <= hasta)
    return q.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).limit(limite).all()


def resumen(e) -> str:
    return f"{e.code} · {e.description or ''} · {float(e.amount or 0):.2f} {e.currency or ''}".strip()


def cumple_requisito(db, e, requisito: dict) -> bool:
    if requisito.get("tipo") == "require_justification":
        return bool((e.notes or "").strip())
    if requisito.get("tipo") == "require_attachment":
        tipos = documentos(db, e)
        pedidos = set(requisito.get("tipos_de_documento") or [])
        return bool(tipos) if not pedidos else any(t in pedidos for t in tipos)
    return True


def aplicar_campo(db, e, campo: str, valor) -> None:
    if campo == "facturable":
        e.is_billable = bool(valor)


def opciones_dinamicas(db) -> dict:
    """Opciones de los campos `enum` que dependen de la empresa: grados y viajes que ya existen."""
    from app.models.expenses import Expense
    from app.models.user import User
    grados = sorted({g for (g,) in db.query(User.grade).filter(User.is_active.is_(True)).distinct() if g})
    viajes = sorted({v for (v,) in db.query(Expense.trip).filter(Expense.is_active.is_(True)).distinct() if v})[:500]
    return {"grado": [Opcion(g, g) for g in grados], "viaje": [Opcion(v, v) for v in viajes]}


def tarifa_por_km(db, e) -> Optional[dict]:
    """La tarifa por km de la tabla de uso «kilometraje» para el país/ciudad y fecha del gasto.

    Devuelve {"cantidad", "moneda", "tabla", "fila"} o None si no hay tabla o fila.
    """
    from app.models.politicas import TablaDeReferencia
    from app.services.politicas import catalogo
    from app.services.politicas.condiciones import Evaluador, Indeterminado
    from app.services.politicas.motor import cargar_tablas
    tabla = db.query(TablaDeReferencia).filter(TablaDeReferencia.dominio == "gastos",
                                               TablaDeReferencia.uso == USO_KILOMETRAJE) \
        .order_by(TablaDeReferencia.updated_at.desc()).first()
    if tabla is None:
        return None
    ev = Evaluador(db, catalogo.dominio("gastos"), cargar_tablas(db, [tabla.id]))
    ctx = {"categoria": _valor(e.category), "_fecha": e.expense_date,
           "_sujeto": {"pais": (e.country or "").upper() or None, "ciudad": e.city}}
    try:
        valor, fila = ev.valor_de_tabla(tabla.id, ctx)
    except Indeterminado:
        return None
    if isinstance(valor, dict):
        return {"cantidad": float(valor["cantidad"]), "moneda": valor.get("moneda"), "tabla": tabla.nombre}
    return {"cantidad": float(valor), "moneda": None, "tabla": tabla.nombre}


# ── Ejemplos («Cargar ejemplos»: se crean como borrador) ─────────────────────

def _c(campo, operador, valor=None, referencia=None) -> dict:
    d = {"tipo": "condicion", "campo": campo, "operador": operador}
    if valor is not None:
        d["valor"] = valor
    if referencia is not None:
        d["referencia"] = referencia
    return d


def _y(*hijos) -> dict:
    return {"tipo": "grupo", "op": "and", "negar": False, "hijos": list(hijos)}


def _regla(nombre, condicion, resultados=(), exceso=None) -> dict:
    return {"nombre": nombre, "activa": True, "detener": False, "condicion": condicion,
            "resultados": list(resultados), "exceso": exceso}


def _tabla(clave):
    return {"tipo": "tabla", "tabla": clave}


def _fila(pais, ciudad, valor, moneda, categoria=None, desde="2026-01-01"):
    return {"pais": pais, "ciudad": ciudad, "categoria": categoria, "valor": valor, "moneda": moneda,
            "vigente_desde": desde, "vigente_hasta": None}


def ejemplos(db, usuario) -> dict:
    """Cuatro políticas reales de una empresa, con sus tablas por país y ciudad.

    A quién se informa de los viajes caros sale de los datos: el departamento
    cuyo nombre contiene «financ»/«finanz» si existe; si no, el rol admin.
    """
    from app.core.config import settings
    from app.models.user import User
    eur = settings.DEFAULT_CURRENCY or "EUR"
    deps = sorted({d for (d,) in db.query(User.department).filter(User.is_active.is_(True)).distinct() if d})
    finanzas = next((d for d in deps if "financ" in d.lower() or "finanz" in d.lower()), None)
    a_finanzas = {"tipo": "departamento", "valor": finanzas} if finanzas else {"tipo": "rol", "valor": "admin"}
    tablas = [
        {"clave": "comidas", "nombre": "Comidas por asistente (país y ciudad)", "tipo_de_valor": "importe",
         "moneda": eur, "uso": None,
         "descripcion": "Tope de una comida por asistente. La fila sin país vale para el resto.",
         "filas": [_fila("PL", None, 120, "PLN"), _fila("PL", "Warszawa", 160, "PLN"), _fila("ES", None, 35, "EUR"),
                   _fila("ES", "Madrid", 45, "EUR"), _fila("FR", None, 40, "EUR"), _fila("DE", None, 40, "EUR"),
                   _fila(None, None, 40, "EUR")]},
        {"clave": "hotel", "nombre": "Hotel por noche (país y ciudad)", "tipo_de_valor": "importe", "moneda": eur,
         "uso": None, "descripcion": "Tope de una noche de hotel.",
         "filas": [_fila("PL", None, 450, "PLN"), _fila("PL", "Warszawa", 600, "PLN"), _fila("ES", None, 120, "EUR"),
                   _fila("ES", "Madrid", 160, "EUR"), _fila("ES", "Barcelona", 170, "EUR"),
                   _fila("FR", "Paris", 220, "EUR"), _fila(None, None, 150, "EUR")]},
        {"clave": "km", "nombre": "Tarifa por km (país)", "tipo_de_valor": "importe", "moneda": eur,
         "uso": USO_KILOMETRAJE, "descripcion": "Importe por km de los gastos de kilometraje.",
         "filas": [_fila("ES", None, 0.26, "EUR"), _fila("PT", None, 0.36, "EUR"), _fila("DE", None, 0.30, "EUR"),
                   _fila("PL", None, 1.15, "PLN")]},
    ]
    nivel = lambda n: {"tipo": "add_approval_levels", "niveles": n}  # noqa: E731
    politicas = [
        {"nombre": "Comidas: tope por asistente según país y ciudad", "prioridad": 200,
         "descripcion": "Una comida puede costar por asistente hasta el valor de la tabla (p. ej. Polonia 120 PLN). "
                        "Hasta un 20 % por encima pide un nivel más de aprobación; más del 20 %, dos y una explicación.",
         "reglas": [_regla("Comida por encima de la tabla",
                           _y(_c("categoria", "eq", "meals"),
                              _c("importe_por_asistente", "pct_over", 0, _tabla("comidas"))),
                           exceso={"campo": "importe_por_asistente", "referencia": _tabla("comidas"), "bandas": [
                               {"desde": 0, "hasta": 20, "resultados": [nivel(1)]},
                               {"desde": 20, "hasta": None, "resultados": [
                                   nivel(2), {"tipo": "require_justification",
                                              "mensaje": "Explica por qué la comida supera el tope en más de un 20 %"}]}]})]},
        {"nombre": "Justificantes según importe", "prioridad": 150,
         "descripcion": "Ticket o factura desde 30; factura desde 250; lista de asistentes en comidas de 3 o más.",
         "reglas": [
             _regla("Ticket o factura desde 30", _y(_c("importe", "gt", {"cantidad": 30, "moneda": eur})),
                    [{"tipo": "require_attachment", "tipos_de_documento": ["receipt", "ticket", "invoice"],
                      "mensaje": "Adjunta el ticket o la factura"}]),
             _regla("Factura desde 250", _y(_c("importe", "gt", {"cantidad": 250, "moneda": eur})),
                    [{"tipo": "require_attachment", "tipos_de_documento": ["invoice"],
                      "mensaje": "Desde 250 hace falta la factura"}]),
             _regla("Lista de asistentes", _y(_c("categoria", "eq", "meals"), _c("asistentes", "gte", 3)),
                    [{"tipo": "require_attachment", "tipos_de_documento": ["attendees"],
                      "mensaje": "Adjunta la lista de asistentes"}])]},
        {"nombre": "Viajes caros: informar a finanzas", "prioridad": 100,
         "descripcion": "Viajes y alojamiento por encima de 1.000 se informan a finanzas (no paran el gasto).",
         "reglas": [_regla("Viaje por encima de 1.000",
                           _y(_c("categoria", "in", ["travel", "accommodation"]),
                              _c("importe", "gt", {"cantidad": 1000, "moneda": eur})),
                           [{"tipo": "notify", "destinatarios": [a_finanzas], "canales": ["app", "email"],
                             "mensaje": "Viaje por encima de 1.000"}])]},
        {"nombre": "Hoteles y fines de semana", "prioridad": 100,
         "descripcion": "Hotel por encima de la tabla: hasta un 15 % se avisa; más, un nivel de aprobación. "
                        "Comidas en fin de semana o festivo: hay que explicarlas.",
         "reglas": [
             _regla("Hotel por encima de la tabla",
                    _y(_c("categoria", "eq", "accommodation"), _c("importe", "pct_over", 0, _tabla("hotel"))),
                    exceso={"campo": "importe", "referencia": _tabla("hotel"), "bandas": [
                        {"desde": 0, "hasta": 15, "resultados": [{"tipo": "warn", "mensaje": "Hotel algo por encima de la tabla"}]},
                        {"desde": 15, "hasta": None, "resultados": [nivel(1)]}]}),
             _regla("Comida en fin de semana o festivo",
                    {"tipo": "grupo", "op": "and", "negar": False, "hijos": [
                        _c("categoria", "eq", "meals"),
                        {"tipo": "grupo", "op": "or", "negar": False, "hijos": [
                            _c("fin_de_semana", "eq", True), _c("festivo", "eq", True)]}]},
                    [{"tipo": "require_justification", "mensaje": "Explica la comida en fin de semana o festivo"}])]},
    ]
    return {"tablas": tablas, "politicas": politicas}


registrar(Dominio(
    clave="gastos", etiqueta="Gastos", campos=CAMPOS, contexto=contexto, cargar=cargar,
    historicos=historicos, propietario=lambda e: e.user_id, resumen=resumen,
    tipo_de_aprobacion="expense", cumple_requisito=cumple_requisito, aplicar_campo=aplicar_campo,
    opciones_dinamicas=opciones_dinamicas, usos_de_tabla=(Opcion(USO_KILOMETRAJE, "Tarifa por km de los gastos"),),
    ejemplos=ejemplos,
))
