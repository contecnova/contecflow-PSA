"""Periodo libre en informes (16-11-2026).

Hasta ahora cada informe decidía su ventana con un ``days: int`` (o ``hours``,
``lookback_days``, ``period_days``…) y la pantalla ofrecía 7/30/90 días. Este
módulo es la pieza común para pedir **cualquier** intervalo, con la
granularidad que tenga sentido para el dato, sin romper a los clientes que ya
mandan ``days``.

Contrato de la API
------------------
Un endpoint de informe declara::

    p: Periodo = Depends(periodo(dias_por_defecto=30, granularidades=CON_HORA))

y acepta en la query string:

* ``desde`` / ``hasta``: ISO 8601 (``2026-11-01``, ``2026-11-01T08:00``,
  ``2026-11-01T08:00:00+01:00``, ``…Z``). Intervalo semiabierto
  ``[desde, hasta)``. Sin zona, se interpretan en ``tz`` o, si no viene, en la
  zona de la petición (usuario → empresa → UTC, ``app/core/timezone_context``).
  Sin ``hasta`` = ahora; sin ``desde`` = ``hasta`` menos los días por defecto.
* ``granularidad``: ``hour | day | week | month | auto`` (por defecto ``auto``).
* ``tz``: zona IANA con la que se agrupa y se interpretan las fechas sin zona.
* ``comparar``: ``true`` para pedir también el periodo anterior de igual
  duración (solo donde el informe lo soporta, ``comparable=True``).
* ``days`` (o el alias histórico del endpoint: ``hours``, ``lookback_days``,
  ``period_days``, ``start_date``/``end_date``…): compatibilidad. ``days=N`` es
  «los últimos N días hasta ahora» y solo se usa si no llega ``desde``.

Los umbrales (rango máximo, puntos máximos por granularidad, objetivo de
``auto``) son ajustes en caliente del grupo ``informes``
(``app/services/settings_service/_catalogo.py``), por empresa.

Errores: ``422`` con ``detail = {"code": "periodo.<motivo>", "message": …,
"params": {…}}``. El frontend traduce ``code`` (``periodo_err.<motivo>``).

Agrupación temporal
-------------------
``expresion_de_bucket(db, columna, p)`` da una expresión SQL que devuelve la
clave del tramo (``YYYY-MM-DDTHH:MI`` en hora local de ``p.zona``):

* PostgreSQL: ``date_trunc`` sobre ``timezone(zona, columna)``.
* SQLite: una función registrada en la conexión (``cf_periodo_bucket``) que
  ejecuta **la misma** ``clave_de_bucket`` de Python que se usa al agrupar en
  memoria, de modo que las tres vías dan exactamente la misma clave.

``p.rellenar(filas)`` completa la serie con todos los tramos del periodo
(los vacíos con ceros) y añade a cada punto su instante ISO con desfase.
"""
from __future__ import annotations

import inspect
import logging
import math
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.errores import ErrorDeDominio

logger = logging.getLogger("contecflow.periodo")

UTC = timezone.utc

# ── Granularidades ────────────────────────────────────────────────────────────
HORA, DIA, SEMANA, MES = "hour", "day", "week", "month"
AUTO = "auto"
#: De más fina a más gruesa. El orden importa para ``auto``.
GRANULARIDADES: Tuple[str, ...] = (HORA, DIA, SEMANA, MES)
#: Dato con instante (tickets, eventos, accesos, uso, IA…).
CON_HORA: Tuple[str, ...] = GRANULARIDADES
#: Dato de calendario sin hora (imputaciones, gastos, facturas por fecha…).
SIN_HORA: Tuple[str, ...] = (DIA, SEMANA, MES)
#: Dato mensual (presupuestos, cierres).
SOLO_MES: Tuple[str, ...] = (MES,)

_SEGUNDOS = {HORA: 3600, DIA: 86400, SEMANA: 7 * 86400, MES: 30.4375 * 86400}

#: Claves de los ajustes en caliente (grupo ``informes``).
AJUSTE_MAX_DIAS = "PERIODO_MAX_DIAS"
AJUSTE_MAX_PUNTOS = {
    HORA: "PERIODO_MAX_PUNTOS_HORA",
    DIA: "PERIODO_MAX_PUNTOS_DIA",
    SEMANA: "PERIODO_MAX_PUNTOS_SEMANA",
    MES: "PERIODO_MAX_PUNTOS_MES",
}
AJUSTE_AUTO_PUNTOS = "PERIODO_AUTO_MAX_PUNTOS"

#: Formato de la clave de tramo (idéntico en PostgreSQL, SQLite y Python).
FORMATO_CLAVE = "%Y-%m-%dT%H:%M"
_FORMATO_PG = 'YYYY-MM-DD"T"HH24:MI'


# ── Errores ───────────────────────────────────────────────────────────────────
class ErrorDePeriodo(ErrorDeDominio):
    """422 con un código traducible: ``periodo.<motivo>``."""

    def __init__(self, motivo: str, mensaje: str, **params: Any) -> None:
        self.codigo = f"periodo.{motivo}"
        super().__init__(422, {"code": self.codigo, "message": mensaje, "params": params})


# ── Límites ───────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class LimitesDePeriodo:
    max_dias: int = 1830
    max_puntos: Mapping[str, int] = field(default_factory=lambda: {HORA: 744, DIA: 1100, SEMANA: 530, MES: 240})
    auto_max_puntos: int = 120

    def a_dict(self) -> dict:
        return {"max_dias": self.max_dias, "max_puntos": dict(self.max_puntos), "auto_max_puntos": self.auto_max_puntos}


def limites_de_periodo(db, org_id: Optional[str] = None) -> LimitesDePeriodo:
    """Lee los umbrales en caliente (empresa → global → ``Settings``)."""
    from app.services.settings_service.runtime import get_runtime_int

    base = LimitesDePeriodo()

    def _entero(clave: str, defecto: int) -> int:
        try:
            v = get_runtime_int(db, clave, org_id, default=defecto)
        except Exception:  # la tabla de ajustes caída no tumba un informe
            logger.debug("limites_de_periodo: no se pudo leer %s", clave, exc_info=True)
            v = defecto
        return v if v and v > 0 else defecto

    return LimitesDePeriodo(
        max_dias=_entero(AJUSTE_MAX_DIAS, base.max_dias),
        max_puntos={g: _entero(AJUSTE_MAX_PUNTOS[g], base.max_puntos[g]) for g in GRANULARIDADES},
        auto_max_puntos=_entero(AJUSTE_AUTO_PUNTOS, base.auto_max_puntos),
    )


# ── Zonas y tramos ────────────────────────────────────────────────────────────
def zona_de(nombre: Optional[str]) -> ZoneInfo | timezone:
    if not nombre:
        from app.core.timeutil import current_zone
        return current_zone()
    if nombre.upper() == "UTC":
        return UTC
    try:
        return ZoneInfo(nombre)
    except (ZoneInfoNotFoundError, ValueError):
        raise ErrorDePeriodo("zona_invalida", f"Zona horaria desconocida: {nombre}", tz=nombre)


def nombre_de_zona(zona) -> str:
    return getattr(zona, "key", None) or ("UTC" if zona in (UTC, timezone.utc) else str(zona))


def inicio_de_tramo_local(local: datetime, granularidad: str) -> datetime:
    """Inicio del tramo (hora local, sin tzinfo) que contiene ``local``."""
    local = local.replace(tzinfo=None, second=0, microsecond=0)
    if granularidad == HORA:
        return local.replace(minute=0)
    dia = local.replace(hour=0, minute=0)
    if granularidad == DIA:
        return dia
    if granularidad == SEMANA:  # lunes, como date_trunc('week') (ISO)
        return dia - timedelta(days=dia.weekday())
    if granularidad == MES:
        return dia.replace(day=1)
    raise ErrorDePeriodo("granularidad_invalida", f"Granularidad desconocida: {granularidad}", granularidad=granularidad)


def clave_de_bucket(instante: Any, zona, granularidad: str) -> Optional[str]:
    """Clave del tramo de un instante o de una fecha.

    * ``datetime`` sin zona: se toma como UTC (es como se guardan).
    * ``date``: es un día de calendario; no se convierte de zona.
    * ``str``: ISO (lo que entrega SQLite).
    """
    if instante is None:
        return None
    if isinstance(instante, str):
        texto = instante.strip().replace(" ", "T", 1)
        if len(texto) == 10:
            instante = date.fromisoformat(texto)
        else:
            instante = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    if isinstance(instante, datetime):
        if instante.tzinfo is None:
            instante = instante.replace(tzinfo=UTC)
        local = instante.astimezone(zona)
    elif isinstance(instante, date):
        local = datetime.combine(instante, time())
    else:
        return None
    return inicio_de_tramo_local(local, granularidad).strftime(FORMATO_CLAVE)


def _sumar_mes(d: datetime, n: int = 1) -> datetime:
    m = d.month - 1 + n
    return d.replace(year=d.year + m // 12, month=m % 12 + 1)


def _siguiente_local(local: datetime, granularidad: str) -> datetime:
    if granularidad == HORA:
        return local + timedelta(hours=1)
    if granularidad == DIA:
        return local + timedelta(days=1)
    if granularidad == SEMANA:
        return local + timedelta(days=7)
    return _sumar_mes(local)


def _parsear_instante(valor: str, zona, nombre_param: str) -> datetime:
    texto = (valor or "").strip()
    try:
        if len(texto) == 10:
            dt = datetime.combine(date.fromisoformat(texto), time())
        else:
            dt = datetime.fromisoformat(texto.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        raise ErrorDePeriodo("fecha_invalida", f"Fecha no válida en «{nombre_param}»: {valor}", param=nombre_param, valor=valor)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zona)
    return dt.astimezone(UTC)


def _puntos(desde: datetime, hasta: datetime, granularidad: str) -> int:
    return max(1, math.ceil((hasta - desde).total_seconds() / _SEGUNDOS[granularidad]))


# ── El periodo ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Periodo:
    """Intervalo ``[desde, hasta)`` en UTC, con su zona y su granularidad resuelta."""

    desde: datetime
    hasta: datetime
    zona: Any = UTC
    granularidad: str = DIA
    pedida: str = AUTO
    admitidas: Tuple[str, ...] = GRANULARIDADES
    comparar: bool = False
    origen: str = "defecto"  # defecto | days | rango

    # Fechas y horas en las formas que usan las consultas
    @property
    def duracion(self) -> timedelta:
        return self.hasta - self.desde

    @property
    def dias(self) -> float:
        return self.duracion.total_seconds() / 86400

    @property
    def dias_enteros(self) -> int:
        """Días que abarca, redondeado hacia arriba (para servicios que aún piensan en días)."""
        return max(1, math.ceil(self.dias - 1e-9))

    @property
    def desde_naive(self) -> datetime:
        """``desde`` en UTC sin tzinfo (columnas ``DateTime`` sin zona, ``utcnow()``)."""
        return self.desde.astimezone(UTC).replace(tzinfo=None)

    @property
    def hasta_naive(self) -> datetime:
        return self.hasta.astimezone(UTC).replace(tzinfo=None)

    @property
    def desde_local(self) -> datetime:
        return self.desde.astimezone(self.zona)

    @property
    def hasta_local(self) -> datetime:
        return self.hasta.astimezone(self.zona)

    @property
    def fecha_desde(self) -> date:
        """Primer día (en la zona) para columnas ``Date``. Inclusivo."""
        return self.desde_local.date()

    @property
    def fecha_hasta(self) -> date:
        """Último día (en la zona) para columnas ``Date``. Inclusivo (``hasta`` es exclusivo)."""
        return (self.hasta_local - timedelta(microseconds=1)).date()

    @property
    def puntos(self) -> int:
        return _puntos(self.desde, self.hasta, self.granularidad)

    def contiene(self, instante: Any) -> bool:
        """Para filtrar en memoria. ``date`` se compara por día de calendario."""
        if instante is None:
            return False
        if isinstance(instante, datetime):
            i = instante if instante.tzinfo else instante.replace(tzinfo=UTC)
            return self.desde <= i < self.hasta
        if isinstance(instante, date):
            return self.fecha_desde <= instante <= self.fecha_hasta
        return False

    def anterior(self) -> "Periodo":
        """El periodo inmediatamente anterior, de la misma duración."""
        d = self.duracion
        return replace(self, desde=self.desde - d, hasta=self.desde, comparar=False)

    # Tramos
    def clave(self, instante: Any) -> Optional[str]:
        return clave_de_bucket(instante, self.zona, self.granularidad)

    def claves(self) -> List[str]:
        """Todas las claves de tramo del periodo, en orden (sin duplicados en cambios de hora)."""
        actual = inicio_de_tramo_local(self.desde_local, self.granularidad)
        fin_local = self.hasta_local.replace(tzinfo=None)
        salida: List[str] = []
        visto = set()
        tope = self.puntos + 3
        while actual < fin_local and len(salida) < tope:
            k = actual.strftime(FORMATO_CLAVE)
            if k not in visto:
                visto.add(k)
                salida.append(k)
            actual = _siguiente_local(actual, self.granularidad)
        return salida

    def instante_de_clave(self, clave: str) -> str:
        """ISO con desfase de la zona: lo que el frontend pinta en el eje."""
        local = datetime.strptime(clave, FORMATO_CLAVE)
        return local.replace(tzinfo=self.zona).isoformat()

    def rellenar(self, filas: Mapping[str, Any] | Iterable[Tuple[str, Any]],
                 vacio: Any = 0, campo: str = "valor") -> List[dict]:
        """Serie completa: un punto por tramo, con ``t`` (ISO) y ``clave``.

        ``filas``: ``{clave: valor}`` o pares ``(clave, valor)``. Si el valor es
        un ``dict`` se fusiona en el punto; si no, va en ``campo``. Los tramos
        sin fila llevan ``vacio`` (un ``dict`` de ceros para series múltiples).
        """
        datos = dict(filas.items() if isinstance(filas, Mapping) else filas)
        serie = []
        for k in self.claves():
            v = datos.get(k, vacio)
            punto = {"t": self.instante_de_clave(k), "clave": k}
            if isinstance(v, Mapping):
                punto.update(dict(v))
            else:
                punto[campo] = v
            serie.append(punto)
        return serie

    def agrupar(self, elementos: Iterable[Any], instante: Callable[[Any], Any],
                valor: Callable[[Any], float] = lambda _e: 1) -> Dict[str, float]:
        """Agrupa en memoria (misma clave que SQL): ``{clave: suma de valor}``."""
        acumulado: Dict[str, float] = {}
        for e in elementos:
            i = instante(e)
            if not self.contiene(i):
                continue
            k = self.clave(i)
            acumulado[k] = acumulado.get(k, 0) + (valor(e) or 0)
        return acumulado

    def a_dict(self) -> dict:
        """Lo que se devuelve al cliente para que sepa qué se ha calculado."""
        return {
            "desde": self.desde.isoformat(),
            "hasta": self.hasta.isoformat(),
            "zona": nombre_de_zona(self.zona),
            "granularidad": self.granularidad,
            "pedida": self.pedida,
            "admitidas": list(self.admitidas),
            "comparar": self.comparar,
            "origen": self.origen,
        }


# ── Resolución (pura, testeable sin FastAPI) ─────────────────────────────────
def resolver_granularidad(desde: datetime, hasta: datetime, pedida: str,
                          admitidas: Sequence[str], limites: LimitesDePeriodo,
                          validar_puntos: bool = True) -> str:
    pedida = (pedida or AUTO).lower()
    if pedida != AUTO and pedida not in GRANULARIDADES:
        raise ErrorDePeriodo("granularidad_invalida", f"Granularidad desconocida: {pedida}", granularidad=pedida)
    if pedida != AUTO and pedida not in admitidas:
        motivo = "hora_no_admitida" if pedida == HORA else "granularidad_no_admitida"
        raise ErrorDePeriodo(motivo, f"Este informe no admite la granularidad «{pedida}»",
                             granularidad=pedida, admitidas=list(admitidas))
    if pedida == AUTO:
        for g in admitidas:  # de fina a gruesa
            if _puntos(desde, hasta, g) <= limites.auto_max_puntos:
                return g
        elegida = admitidas[-1]
    else:
        elegida = pedida
    if validar_puntos:
        n = _puntos(desde, hasta, elegida)
        tope = limites.max_puntos.get(elegida, 0)
        if tope and n > tope:
            raise ErrorDePeriodo("demasiados_puntos",
                                 f"{n} puntos con granularidad «{elegida}»; el máximo es {tope}",
                                 granularidad=elegida, puntos=n, maximo=tope)
    return elegida


def resolver_periodo(*, desde: Optional[str] = None, hasta: Optional[str] = None,
                     granularidad: Optional[str] = None, dias: Optional[float] = None,
                     tz: Optional[str] = None, comparar: bool = False,
                     limites: Optional[LimitesDePeriodo] = None,
                     dias_por_defecto: float = 30, admitidas: Sequence[str] = GRANULARIDADES,
                     serie: bool = True, comparable: bool = False, sentido: str = "pasado",
                     ahora: Optional[datetime] = None, zona=None) -> Periodo:
    """Valida y construye el ``Periodo``. Lanza ``ErrorDePeriodo``."""
    limites = limites or LimitesDePeriodo()
    admitidas = tuple(g for g in GRANULARIDADES if g in admitidas) or GRANULARIDADES
    zona = zona if zona is not None else zona_de(tz)
    ahora = (ahora or datetime.now(UTC)).astimezone(UTC)
    pedida = (granularidad or AUTO).lower()

    if pedida == HORA and HORA not in admitidas:
        raise ErrorDePeriodo("hora_no_admitida", "Este informe tiene datos por día: no admite granularidad por hora",
                             granularidad=pedida, admitidas=list(admitidas))

    if desde or hasta:
        origen = "rango"
        d_hasta = _parsear_instante(hasta, zona, "hasta") if hasta else None
        d_desde = _parsear_instante(desde, zona, "desde") if desde else None
        if sentido == "futuro":
            d_desde = d_desde or ahora
            d_hasta = d_hasta or d_desde + timedelta(days=dias_por_defecto)
        else:
            d_hasta = d_hasta or (ahora if (d_desde is None or d_desde < ahora) else d_desde + timedelta(days=dias_por_defecto))
            d_desde = d_desde or d_hasta - timedelta(days=dias_por_defecto)
    else:
        n = dias if dias is not None else dias_por_defecto
        origen = "days" if dias is not None else "defecto"
        if n is None or n < 0 or (n == 0 and sentido != "futuro"):
            raise ErrorDePeriodo("dias_invalidos", "El número de días debe ser mayor que cero", dias=n)
        if sentido == "futuro":
            # `days=0` en un horizonte es «solo hoy»: hasta el final del día en la zona.
            fin_de_hoy = datetime.combine(ahora.astimezone(zona).date() + timedelta(days=1), time(), tzinfo=zona).astimezone(UTC)
            d_desde, d_hasta = ahora, (ahora + timedelta(days=n) if n > 0 else fin_de_hoy)
        else:
            d_desde, d_hasta = ahora - timedelta(days=n), ahora

    if d_desde >= d_hasta:
        raise ErrorDePeriodo("desde_mayor_que_hasta", "La fecha de inicio debe ser anterior a la de fin",
                             desde=d_desde.isoformat(), hasta=d_hasta.isoformat())
    dias_rango = (d_hasta - d_desde).total_seconds() / 86400
    if dias_rango > limites.max_dias + 1e-9:
        raise ErrorDePeriodo("rango_excedido", f"El periodo abarca {math.ceil(dias_rango)} días; el máximo es {limites.max_dias}",
                             dias=math.ceil(dias_rango), maximo=limites.max_dias)

    elegida = resolver_granularidad(d_desde, d_hasta, pedida, admitidas, limites, validar_puntos=serie)
    return Periodo(desde=d_desde, hasta=d_hasta, zona=zona, granularidad=elegida, pedida=pedida,
                   admitidas=admitidas, comparar=bool(comparar and comparable), origen=origen)


# ── Dependencia FastAPI ──────────────────────────────────────────────────────
def periodo(*, dias_por_defecto: float = 30, granularidades: Sequence[str] = CON_HORA,
            serie: bool = True, comparable: bool = False, sentido: str = "pasado",
            alias_dias: Sequence[str] = ("days",), alias_horas: Sequence[str] = (),
            alias_desde: Sequence[str] = (), alias_hasta: Sequence[str] = (),
            alias_granularidad: Optional[str] = None,
            dias_alias_max: Optional[int] = None) -> Callable[..., Periodo]:
    """Fábrica de la dependencia ``Periodo`` de un endpoint.

    * ``granularidades``: las que admite el dato (``CON_HORA``, ``SIN_HORA``, ``SOLO_MES``).
    * ``serie``: si devuelve serie temporal (valida el número de puntos).
    * ``comparable``: si sabe calcular el periodo anterior (``comparar=true``).
    * ``sentido``: ``futuro`` para horizontes (vencimientos, renovaciones).
    * ``alias_*``: nombres históricos del parámetro que el endpoint aceptaba.
      Los de días y horas son enteros; los de fechas, ISO.
    * ``alias_granularidad``: parámetro histórico con ``daily|weekly|monthly``.
    """
    from fastapi import Depends, Query
    from sqlalchemy.orm import Session

    from app.core.deps import get_current_user, get_db

    admitidas = tuple(g for g in GRANULARIDADES if g in granularidades)
    desc_gr = ", ".join(admitidas)

    P = inspect.Parameter
    params = [
        P("desde", P.KEYWORD_ONLY, default=Query(None, description="Inicio del periodo (ISO 8601, incluido). Sin zona: la de `tz` o la del usuario."), annotation=Optional[str]),
        P("hasta", P.KEYWORD_ONLY, default=Query(None, description="Fin del periodo (ISO 8601, excluido). Por defecto, ahora."), annotation=Optional[str]),
        P("granularidad", P.KEYWORD_ONLY, default=Query(None, description=f"auto o una de: {desc_gr}."), annotation=Optional[str]),
        P("tz", P.KEYWORD_ONLY, default=Query(None, description="Zona IANA para agrupar e interpretar fechas sin zona."), annotation=Optional[str]),
        P("comparar", P.KEYWORD_ONLY, default=Query(False, description="Calcular también el periodo anterior." if comparable else "No soportado en este informe; se ignora."), annotation=bool),
    ]
    # Cada alias va con un nombre interno seguro y `Query(alias=...)`: así vale
    # también un nombre histórico que es palabra reservada (`from`, `to`).
    internos: Dict[str, str] = {}

    def _alias(tipo: str, nombre: str, consulta, anotacion) -> None:
        interno = f"_{tipo}_{len(internos)}"
        internos[interno] = nombre
        params.append(P(interno, P.KEYWORD_ONLY, default=consulta, annotation=anotacion))

    minimo_dias = 0 if sentido == "futuro" else 1
    for nombre in alias_dias:
        _alias("dias", nombre, Query(None, alias=nombre, ge=minimo_dias, le=dias_alias_max, description="Compatibilidad: últimos N días (próximos, en un horizonte; si no llega `desde`)."), Optional[int])
    for nombre in alias_horas:
        _alias("horas", nombre, Query(None, alias=nombre, ge=1, description="Compatibilidad: últimas N horas (si no llega `desde`)."), Optional[int])
    for nombre in alias_desde:
        _alias("desde", nombre, Query(None, alias=nombre, description="Compatibilidad: igual que `desde`."), Optional[str])
    for nombre in alias_hasta:
        _alias("hasta", nombre, Query(None, alias=nombre, description="Compatibilidad: fecha final incluida (igual que `hasta` del día siguiente)."), Optional[str])
    if alias_granularidad:
        _alias("gran", alias_granularidad, Query(None, alias=alias_granularidad, description="Compatibilidad: daily, weekly o monthly."), Optional[str])
    params.append(P("db", P.KEYWORD_ONLY, default=Depends(get_db), annotation=Session))
    params.append(P("current_user", P.KEYWORD_ONLY, default=Depends(get_current_user), annotation=Any))

    _LEGADO = {"daily": DIA, "weekly": SEMANA, "monthly": MES, "hourly": HORA}

    def _dependencia(**kw) -> Periodo:
        desde = kw.get("desde")
        hasta = kw.get("hasta")
        def _de(tipo: str) -> list:
            return [kw.get(i) for i in internos if i.startswith(f"_{tipo}_")]

        if not desde:
            desde = next((v for v in _de("desde") if v), None)
        if not hasta:
            fin = next((v for v in _de("hasta") if v), None)
            if fin:
                # las fechas finales históricas eran inclusivas: hasta = día siguiente
                hasta = (date.fromisoformat(fin[:10]) + timedelta(days=1)).isoformat() if len(fin.strip()) == 10 else fin
        gran = kw.get("granularidad")
        legado = next((v for v in _de("gran") if v), None)
        if not gran and legado:
            gran = _LEGADO.get(str(legado).lower(), legado)
        dias = next((v for v in _de("dias") if v is not None), None)
        if dias is None:
            horas = next((v for v in _de("horas") if v is not None), None)
            if horas is not None:
                dias = horas / 24
        user = kw.get("current_user")
        org_id = str(getattr(user, "organization_id", "") or "") or None
        limites = limites_de_periodo(kw["db"], org_id)
        return resolver_periodo(desde=desde, hasta=hasta, granularidad=gran, dias=dias, tz=kw.get("tz"),
                                comparar=kw.get("comparar", False), limites=limites,
                                dias_por_defecto=dias_por_defecto, admitidas=admitidas, serie=serie,
                                comparable=comparable, sentido=sentido)

    _dependencia.__signature__ = inspect.Signature(params, return_annotation=Periodo)  # type: ignore[attr-defined]
    _dependencia.__name__ = "periodo"
    return _dependencia


# ── Agrupación en SQL ─────────────────────────────────────────────────────────
_SQLITE_FN = "cf_periodo_bucket"


def _sqlite_bucket(valor, zona: str, granularidad: str):
    try:
        return clave_de_bucket(valor, zona_de(zona) if zona else UTC, granularidad)
    except Exception:
        # Funcion de SQLite: lanzar aqui rompe la consulta entera. Un valor que no
        # es fecha queda fuera de todo tramo (NULL), y queda rastro.
        logger.debug("periodo: valor sin tramo en SQLite (%r, %s, %s)", valor, zona, granularidad, exc_info=True)
        return None


def registrar_funciones_sqlite(conexion_dbapi) -> None:
    """Registra ``cf_periodo_bucket`` en una conexión ``sqlite3`` (idempotente)."""
    try:
        conexion_dbapi.create_function(_SQLITE_FN, 3, _sqlite_bucket, deterministic=True)
    except TypeError:  # Python < 3.8 / sqlite antiguo sin `deterministic`
        conexion_dbapi.create_function(_SQLITE_FN, 3, _sqlite_bucket)


def _dialecto(db) -> str:
    try:
        return db.get_bind().dialect.name
    except Exception:
        logger.debug("periodo: sesion sin motor enlazado; se mira db.bind", exc_info=True)
        return getattr(getattr(getattr(db, "bind", None), "dialect", None), "name", "") or ""


def expresion_de_bucket(db, columna, p: Periodo, *, con_zona: Optional[bool] = None):
    """Expresión SQL con la clave del tramo de ``columna`` (``YYYY-MM-DDTHH:MI`` local).

    ``con_zona``: si la columna guarda instantes. Por defecto se deduce del tipo
    (``Date`` → no se convierte de zona; ``DateTime`` → instante UTC).
    """
    from sqlalchemy import Date, DateTime, func, literal

    tipo = getattr(columna, "type", None)
    es_fecha = isinstance(tipo, Date) and not isinstance(tipo, DateTime)
    nombre = nombre_de_zona(p.zona)
    if _dialecto(db) == "sqlite":
        try:
            registrar_funciones_sqlite(db.connection().connection.driver_connection)
        except AttributeError:
            registrar_funciones_sqlite(db.connection().connection.dbapi_connection)
        return getattr(func, _SQLITE_FN)(columna, literal(nombre), literal(p.granularidad))
    if es_fecha:
        local = func.cast(columna, DateTime())
    else:
        tz_col = getattr(tipo, "timezone", True) if con_zona is None else con_zona
        # timestamptz → timezone(zona, col) da la hora local; timestamp UTC sin zona
        # → primero se marca como UTC.
        base = columna if tz_col else func.timezone("UTC", columna)
        local = func.timezone(nombre, base)
    return func.to_char(func.date_trunc(p.granularidad, local), _FORMATO_PG)


def filtro_de_periodo(columna, p: Periodo):
    """Condición ``columna ∈ [desde, hasta)`` (por día de calendario si es ``Date``)."""
    from sqlalchemy import Date, DateTime, and_

    tipo = getattr(columna, "type", None)
    if isinstance(tipo, Date) and not isinstance(tipo, DateTime):
        return and_(columna >= p.fecha_desde, columna <= p.fecha_hasta)
    if getattr(tipo, "timezone", False):
        return and_(columna >= p.desde, columna < p.hasta)
    return and_(columna >= p.desde_naive, columna < p.hasta_naive)


def _registrar_en_motores() -> None:
    """Toda conexión SQLite nueva lleva la función de tramos (además del registro perezoso)."""
    try:
        import sqlite3

        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        @event.listens_for(Engine, "connect")
        def _al_conectar(conexion_dbapi, _registro):  # pragma: no cover - depende del motor
            if isinstance(conexion_dbapi, sqlite3.Connection):
                registrar_funciones_sqlite(conexion_dbapi)
    except Exception:  # pragma: no cover
        logger.debug("periodo: no se pudo registrar el listener de SQLite", exc_info=True)


_registrar_en_motores()
