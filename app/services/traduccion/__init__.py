"""Traduccion en tiempo real operador <-> cliente (16-11-2026).

Submodulos (se importan explicitamente; este paquete no importa nada para que
los modelos puedan usar `idiomas` sin ciclos):

- `idiomas`: codigos admitidos, normalizacion y deteccion local (sin red).
- `ajustes`: lectura de los ajustes en vivo `TRANSLATION_*` por empresa.
- `glosario`: terminos de la empresa, su aplicacion y su huella.
- `cache`: la cache por (texto, origen, destino, glosario).
- `proveedores`: la interfaz comun y los proveedores (IA de la app, DeepL, Azure).
- `servicio`: `traducir(...)`: habilitado, deteccion, cache, tope de gasto,
  proveedor y degradacion (sin traduccion -> original con motivo).
- `mensajes`: traduccion de mensajes guardados (comentarios, tickets, canales,
  chat interno) al idioma de quien mira, con su acceso comprobado.
- `salida`: idioma del cliente, vista previa y lo que se envia al cliente.
- `kb`: versiones de los articulos en los idiomas del portal, con revision.
- `textos_del_sistema`: textos que genera el sistema (tickets de ALM) en el
  idioma de cada cual.
"""
