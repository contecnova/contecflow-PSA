"""Constantes de negocio del producto: un solo sitio.

Auditoria 2026-11 (barrido «nada en duro»). Valores que se repetian escritos a
mano en muchos ficheros. No son ajustes de operador (esos viven en
`app.core.config.Settings` y en el catalogo de ajustes en tiempo de ejecucion):
son reglas del producto que tienen que valer lo mismo en todas partes, y que si
cambian lo hacen en un unico sitio.

Un valor que un operador o una empresa quiera cambiar NO va aqui: va a
`Settings` (o a un ajuste por organizacion) y aqui, como mucho, su respaldo.
"""
from __future__ import annotations

#: Nombre comercial del producto en la salida que ve una persona (asuntos de
#: correo, pies de PDF, emisor TOTP, valores por defecto de marca). La marca de
#: cada empresa (`OrgBranding.app_name`) manda sobre esto cuando existe.
#: Los identificadores tecnicos (nombres de logger, prefijos de claves Redis,
#: nombres de metricas, cabeceras `X-Contecflow-*`) NO usan esta constante a
#: proposito: son contratos internos o con integraciones y no deben cambiar
#: con la marca.
NOMBRE_DEL_PRODUCTO = "Contecflow"

#: Nombre completo, para los textos que nombran la plataforma entera.
NOMBRE_COMPLETO_DEL_PRODUCTO = f"{NOMBRE_DEL_PRODUCTO} PSA"

#: Tope de `page_size` / `limit` que acepta un listado paginado de la API. El
#: valor por defecto de cada listado lo decide cada endpoint; el tope es comun.
MAX_TAMANO_DE_PAGINA = 200

#: Horas productivas al año de una persona cuando su ficha de coste no dice
#: otra cosa (año laboral menos vacaciones, festivos, bajas y formacion). Es la
#: base de `coste/hora = coste anual / horas productivas`.
HORAS_PRODUCTIVAS_ANUALES_POR_DEFECTO = 1700.0

#: Sobrecoste de empresa sobre el salario bruto (seguridad social y otros)
#: cuando ni la ficha ni el preset del pais dicen otra cosa. 0.32 = 32 %.
#: Los presets por pais (`country_employer_costs.json`) mandan sobre esto.
PORCENTAJE_COSTE_EMPRESA_POR_DEFECTO = 0.32
