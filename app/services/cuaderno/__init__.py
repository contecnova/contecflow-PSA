"""«Mi cuaderno» (migración 202, docs/CUADERNO.md).

Módulos:
- `config`: configuración de la empresa (etiquetas por defecto, baja, papelera, IA).
- `acceso`: quién lee o edita qué (privado por defecto; ni el administrador entra).
- `contenido`: validar el JSON del editor, sacar texto, casillas, etiquetas y enlaces;
  Markdown y PDF.
- `servicio`: árbol, páginas, orden, papelera, búsqueda, tareas y etiquetas.
- `compartir`: compartir cuaderno o sección con personas, equipos o departamentos.
- `acciones`: chips vivos (`#`, `@`), de nota a acción y enlaces de vuelta.
- `adjuntos`: adjuntos, imágenes, dibujos y voz.
- `ia`: resumir, extraer tareas y ordenar ideas con el proveedor de la empresa.
- `plantillas`, `exportar`, `rgpd`, `reuniones`, `colaboracion`, `trabajos`.

Los servicios no confirman salvo que se diga; confirma la ruta.
"""
