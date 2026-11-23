"""Evaluación de árboles de condiciones, con la traza de cada comparación.

Formato (lo escribe la pantalla, nunca una persona):

    grupo     = {"tipo": "grupo", "op": "and" | "or", "negar": bool, "hijos": [nodo, …]}
    condición = {"tipo": "condicion", "campo": clave, "operador": op,
                 "valor": v, "valor2": v (between), "referencia": ref (pct_over)}
    ref       = {"tipo": "valor", "valor": v} | {"tipo": "campo", "campo": clave}
              | {"tipo": "tabla", "tabla_id": id}

Un importe es {"cantidad": float, "moneda": "EUR"}. Se compara SIEMPRE en la
moneda de la condición (o de la fila de la tabla), convirtiendo el importe de
la entidad con el tipo de cambio de la fecha de la entidad
(`currency_rates_service`, directo o inverso). Sin tipo de cambio la
condición queda INDETERMINADA (None), no se inventa un 1:1.

Lógica de tres valores: Y es falso si algún hijo es falso, indeterminado si
alguno lo es, y verdadero si no; O, al revés. Negar deja lo indeterminado
como está. Una regla solo encaja con verdadero; si su condición queda
indeterminada el motor añade un aviso (ver motor.py): falla hacia la revisión
humana, nunca hacia aprobar ni bloquear.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from app.services.politicas.catalogo import DOS_VALORES, LISTA, SIN_VALOR, Dominio
from app.core.codigos_de_error import ErrorConCodigo


class Indeterminado(Exception):
    """No se puede evaluar (falta un tipo de cambio, un valor de tabla…)."""


def _fecha(v) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def cargar_tablas(db, ids: list) -> dict:
    """Las tablas de referencia y sus filas (vive aquí y no en motor: motor importa este módulo)."""
    from app.models.politicas import FilaDeTablaDeReferencia, TablaDeReferencia
    salida: dict = {}
    if not ids:
        return salida
    tablas = {t.id: t for t in db.query(TablaDeReferencia).filter(TablaDeReferencia.id.in_(ids)).all()}
    for t in tablas.values():
        salida[t.id] = (t.tipo_de_valor, [])
    for f in db.query(FilaDeTablaDeReferencia).filter(FilaDeTablaDeReferencia.tabla_id.in_(list(tablas))).all():
        salida[f.tabla_id][1].append({"pais": f.pais, "ciudad": f.ciudad, "categoria": f.categoria, "valor": f.valor,
                                      "moneda": f.moneda, "vigente_desde": f.vigente_desde,
                                      "vigente_hasta": f.vigente_hasta})
    return salida


class Evaluador:
    """Evalúa condiciones de UN dominio contra UN contexto.

    Guarda en memoria los tipos de cambio y las filas de tabla que consulta:
    una evaluación (o una simulación entera) no repite consultas.
    """

    def __init__(self, db, dominio: Dominio, tablas: Optional[dict] = None):
        self.db = db
        self.dominio = dominio
        self.tablas = tablas if tablas is not None else {}   # tabla_id -> (tipo_de_valor, [filas dict])
        self._tipos: dict = {}

    # ── Tipos de cambio ─────────────────────────────────────────────────────
    def tipo_de_cambio(self, desde: str, hacia: str, fecha: date) -> float:
        desde, hacia = (desde or "").upper(), (hacia or "").upper()
        if not desde or not hacia or desde == hacia:
            return 1.0
        clave = (desde, hacia, fecha)
        if clave not in self._tipos:
            # Auditoría 22-11-2026 (A41): el resolutor único (también cruzado por EUR).
            from app.services.currency_rates_service import tipo_de_cambio
            self._tipos[clave] = tipo_de_cambio(self.db, desde, hacia, fecha)
        if self._tipos[clave] is None:
            raise Indeterminado(f"sin tipo de cambio {desde}→{hacia} a {fecha.isoformat()}")
        return self._tipos[clave]

    def convertir(self, importe: dict, moneda: str, fecha: date) -> float:
        cantidad = float(importe.get("cantidad") or 0)
        return cantidad * self.tipo_de_cambio(importe.get("moneda") or moneda, moneda, fecha)

    # ── Tablas de referencia ────────────────────────────────────────────────
    def valor_de_tabla(self, tabla_id: str, ctx: dict) -> tuple[dict, dict]:
        """La fila más específica vigente: (país, ciudad, categoría) > … > por defecto.

        Devuelve (valor tipado, fila). Especificidad: país 4, ciudad 2,
        categoría 1; gana la mayor y, a igualdad, la que empezó a regir más tarde.
        """
        if tabla_id not in self.tablas:
            self.tablas.update(cargar_tablas(self.db, [tabla_id]))
        if tabla_id not in self.tablas:
            raise Indeterminado("la tabla de referencia ya no existe")
        tipo, filas = self.tablas[tabla_id]
        sujeto = ctx.get("_sujeto") or {}
        pais, ciudad = (sujeto.get("pais") or "").upper(), (sujeto.get("ciudad") or "").strip().lower()
        cat_campo = next((c.clave for c in self.dominio.campos if c.categoria_de_tabla), None)
        categoria = str(ctx.get(cat_campo) or "") if cat_campo else ""
        fecha = ctx.get("_fecha")
        mejor, puntos_mejor = None, -1
        for f in filas:
            if f["pais"] and f["pais"].upper() != pais:
                continue
            if f["ciudad"] and (not f["pais"] or f["ciudad"].strip().lower() != ciudad):
                continue
            if f["categoria"] and f["categoria"] != categoria:
                continue
            if fecha and ((f["vigente_desde"] and f["vigente_desde"] > fecha) or
                          (f["vigente_hasta"] and f["vigente_hasta"] < fecha)):
                continue
            puntos = (4 if f["pais"] else 0) + (2 if f["ciudad"] else 0) + (1 if f["categoria"] else 0)
            if puntos > puntos_mejor or (puntos == puntos_mejor and (f["vigente_desde"] or date.min) >
                                         ((mejor or {}).get("vigente_desde") or date.min)):
                mejor, puntos_mejor = f, puntos
        if mejor is None:
            raise Indeterminado(f"la tabla no tiene valor para {pais or '—'}/{ciudad or '—'}/{categoria or '—'}")
        valor = {"cantidad": mejor["valor"], "moneda": mejor["moneda"]} if tipo == "importe" else mejor["valor"]
        return valor, mejor

    # ── Árbol ───────────────────────────────────────────────────────────────
    def evaluar(self, nodo: Optional[dict], ctx: dict, traza: list) -> Optional[bool]:
        if not nodo:
            return True
        if nodo.get("tipo") == "grupo":
            valores = [self.evaluar(h, ctx, traza) for h in (nodo.get("hijos") or [])]
            if not valores:
                r: Optional[bool] = True
            elif nodo.get("op") == "or":
                r = True if any(v is True for v in valores) else (None if any(v is None for v in valores) else False)
            else:
                r = False if any(v is False for v in valores) else (None if any(v is None for v in valores) else True)
            return (None if r is None else not r) if nodo.get("negar") else r
        return self._condicion(nodo, ctx, traza)

    def _condicion(self, c: dict, ctx: dict, traza: list) -> Optional[bool]:
        campo = self.dominio.campo(c.get("campo") or "")
        paso = {"campo": c.get("campo"), "etiqueta": campo.etiqueta if campo else c.get("campo"),
                "operador": c.get("operador"), "esperado": c.get("valor"), "esperado2": c.get("valor2"),
                "real": None, "cumple": None, "nota": None}
        traza.append(paso)
        if campo is None:
            paso["nota"] = "campo desconocido en el dominio"
            return None
        real = ctx.get(campo.clave)
        paso["real"] = real
        try:
            r = comparar(self, campo.tipo, c.get("operador"), real, c.get("valor"), c.get("valor2"),
                         c.get("referencia"), ctx, paso)
        except Indeterminado as exc:
            paso["nota"] = str(exc)
            r = None
        except (TypeError, ValueError) as exc:
            paso["nota"] = f"no comparable: {exc}"
            r = None
        paso["cumple"] = r
        return r

    def exceso_pct(self, campo_clave: str, referencia: dict, ctx: dict, detalle: dict) -> float:
        """Porcentaje en que el valor del campo supera la referencia (negativo si queda por debajo)."""
        campo = self.dominio.campo(campo_clave)
        if campo is None:
            raise Indeterminado(f"campo desconocido: {campo_clave}")
        real = ctx.get(campo.clave)
        if real is None:
            raise Indeterminado(f"{campo.etiqueta} sin valor")
        ref = self.referencia(referencia, ctx, detalle)
        fecha = ctx.get("_fecha")
        if campo.tipo == "importe":
            moneda = (ref or {}).get("moneda") or real.get("moneda")
            v, base = self.convertir(real, moneda, fecha), float((ref or {}).get("cantidad") or 0)
            detalle.update({"valor": round(v, 2), "referencia": round(base, 2), "moneda": moneda})
        else:
            v, base = float(real), float(ref)
            detalle.update({"valor": v, "referencia": base})
        if base <= 0:
            raise Indeterminado("la referencia es cero")
        pct = (v - base) / base * 100.0
        detalle["exceso_pct"] = round(pct, 2)
        return pct

    def referencia(self, ref: Optional[dict], ctx: dict, detalle: dict):
        ref = ref or {}
        if ref.get("tipo") == "tabla":
            valor, fila = self.valor_de_tabla(ref.get("tabla_id"), ctx)
            detalle["fila_de_tabla"] = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in fila.items()}
            return valor
        if ref.get("tipo") == "campo":
            return ctx.get(ref.get("campo"))
        return ref.get("valor")


_ORDEN = {"gt": lambda a, b: a > b, "gte": lambda a, b: a >= b, "lt": lambda a, b: a < b,
          "lte": lambda a, b: a <= b, "eq": lambda a, b: a == b, "ne": lambda a, b: a != b}


def _hora(v) -> str:
    """«9:5», «09:05», time → «09:05» (error si no es una hora)."""
    if hasattr(v, "hour"):
        return f"{v.hour:02d}:{v.minute:02d}"
    h, m = str(v).strip().split(":")[:2]
    return f"{int(h):02d}:{int(m):02d}"


def _norm_texto(v) -> str:
    return str(v if v is not None else "").strip().lower()


def comparar(ev: Evaluador, tipo: str, op: str, real: Any, valor: Any, valor2: Any,
             referencia: Optional[dict], ctx: dict, paso: dict) -> Optional[bool]:
    if op in SIN_VALOR:
        vacio = real is None or real == "" or real == []
        return vacio if op == "empty" else not vacio
    if op == "pct_over":
        detalle: dict = {}
        campo = paso.get("campo")
        pct = ev.exceso_pct(campo, referencia or {}, ctx, detalle)
        paso["detalle"] = detalle
        return pct > float(valor or 0)
    if real is None:
        # Sin valor no se cumple ninguna comparación positiva; «distinto de» sí.
        return op in ("ne", "not_in", "not_contains", "weekday_not_in")
    fecha_ctx = ctx.get("_fecha")
    if tipo == "importe":
        moneda = (valor or {}).get("moneda") or real.get("moneda")
        v = ev.convertir(real, moneda, fecha_ctx)
        paso["convertido"] = {"cantidad": round(v, 2), "moneda": moneda}
        a = float((valor or {}).get("cantidad") or 0)
        if op == "between":
            return a <= v <= float((valor2 or {}).get("cantidad") or 0)
        return _ORDEN[op](v, a)
    if tipo == "numero":
        v = float(real)
        if op in ("in", "not_in"):
            r = v in {float(x) for x in (valor or [])}
            return r if op == "in" else not r
        if op == "between":
            return float(valor) <= v <= float(valor2)
        return _ORDEN[op](v, float(valor))
    if tipo == "fecha":
        v = _fecha(real)
        if op in ("weekday_in", "weekday_not_in"):
            r = v.isoweekday() in {int(x) for x in (valor or [])}
            return r if op == "weekday_in" else not r
        if op == "between":
            return _fecha(valor) <= v <= _fecha(valor2)
        return _ORDEN[op](v, _fecha(valor))
    if tipo == "periodo":
        # real = {"desde", "hasta"} del contexto; la condición, otro periodo.
        desde, hasta = _fecha((real or {}).get("desde")), _fecha((real or {}).get("hasta"))
        a, b = _fecha(valor), _fecha(valor2)
        if desde is None or hasta is None or a is None or b is None:
            raise Indeterminado("periodo incompleto")
        solapa = desde <= b and hasta >= a
        if op in ("overlaps", "not_overlaps"):
            return solapa if op == "overlaps" else not solapa
        raise ErrorConCodigo("operador_no_admitido", detail=f"operador {op} no vale para un periodo", tipo="periodo", operador=op)
    if tipo == "booleano":
        return bool(real) == bool(valor)
    if tipo == "hora":
        # «HH:MM» con ceros a la izquierda se compara como texto (rev. 180).
        v, a = _hora(real), _hora(valor)
        if op == "between":
            return a <= v <= _hora(valor2)
        return _ORDEN[op](v, a)
    if isinstance(real, (list, tuple, set)):
        # Un campo con varios valores (grupos, tipos que solapan; rev. 180):
        # «es» / «está en» = alguno coincide; «no es» / «no está en» = ninguno.
        reales = {_norm_texto(x) for x in real}
        buscados = {_norm_texto(x) for x in (valor if isinstance(valor, (list, tuple)) else [valor])}
        if op in ("eq", "in"):
            return bool(reales & buscados)
        if op in ("ne", "not_in"):
            return not (reales & buscados)
        if op in ("contains", "not_contains"):
            r = any(_norm_texto(valor) in x for x in reales)
            return r if op == "contains" else not r
        raise ErrorConCodigo("operador_no_admitido", detail=f"operador {op} no vale para una lista", tipo="lista", operador=op)
    # texto, enum, entidad, pais, ciudad: comparación sin mayúsculas ni espacios.
    v = _norm_texto(real)
    if op in LISTA:
        r = v in {_norm_texto(x) for x in (valor or [])}
        return r if op == "in" else not r
    if op in ("contains", "not_contains"):
        r = _norm_texto(valor) in v
        return r if op == "contains" else not r
    if op == "eq":
        return v == _norm_texto(valor)
    if op == "ne":
        return v != _norm_texto(valor)
    raise ErrorConCodigo("operador_no_admitido", detail=f"operador {op} no vale para {tipo}", operador=op, tipo=tipo)


def validar_arbol(dominio: Dominio, nodo: Optional[dict], ruta: str, errores: list, prof: int = 0) -> None:
    """Errores de estructura y de tipo, con la ruta del nodo (la pantalla los señala)."""
    if not nodo:
        return
    if prof > 8:
        errores.append({"ruta": ruta, "mensaje": "demasiados niveles de grupos (máximo 8)"})
        return
    if nodo.get("tipo") == "grupo":
        if nodo.get("op") not in ("and", "or"):
            errores.append({"ruta": ruta, "mensaje": "el grupo debe ser «todas» (Y) o «alguna» (O)"})
        for i, h in enumerate(nodo.get("hijos") or []):
            validar_arbol(dominio, h, f"{ruta}.hijos[{i}]", errores, prof + 1)
        return
    campo = dominio.campo(nodo.get("campo") or "")
    if campo is None:
        errores.append({"ruta": ruta, "mensaje": f"campo desconocido: {nodo.get('campo')}"})
        return
    op = nodo.get("operador")
    if op not in campo.ops:
        errores.append({"ruta": ruta, "mensaje": f"«{campo.etiqueta}» no admite el operador {op}"})
        return
    if op in SIN_VALOR:
        return
    if op == "pct_over":
        ref = nodo.get("referencia") or {}
        if ref.get("tipo") not in ("valor", "campo", "tabla"):
            errores.append({"ruta": ruta, "mensaje": f"«{campo.etiqueta}»: falta la referencia del porcentaje"})
        elif ref.get("tipo") == "tabla" and not ref.get("tabla_id"):
            errores.append({"ruta": ruta, "mensaje": f"«{campo.etiqueta}»: elige la tabla de referencia"})
        return
    valor = nodo.get("valor")
    if valor is None or valor == "" or valor == []:
        errores.append({"ruta": ruta, "mensaje": f"«{campo.etiqueta}»: falta el valor"})
        return
    if op in DOS_VALORES and nodo.get("valor2") in (None, ""):
        errores.append({"ruta": ruta, "mensaje": f"«{campo.etiqueta}»: falta el segundo valor del intervalo"})
    if campo.tipo == "importe" and not (isinstance(valor, dict) and valor.get("moneda")):
        errores.append({"ruta": ruta, "mensaje": f"«{campo.etiqueta}»: el importe necesita moneda"})
    if campo.tipo == "enum" and campo.opciones:
        validos = {o.valor for o in campo.opciones}
        malos = [x for x in (valor if isinstance(valor, list) else [valor]) if x not in validos]
        if malos:
            errores.append({"ruta": ruta, "mensaje": f"«{campo.etiqueta}»: valor no válido {malos}"})
