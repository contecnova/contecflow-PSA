"""«Del ticket al PR»: un agente de código propone el arreglo de un ticket o tarea como PR.

Módulo OPCIONAL por empresa, apagado por defecto (módulo `ticket_pr` de la
gobernanza de IA: sin fila, apagado). Guía, riesgos y controles:
docs/integraciones/TICKET_A_PR.md.

Piezas (cada una detrás de una interfaz para poder cambiarla y probarla sin
Docker, sin Git y sin modelo reales):

- `config`: configuración por empresa (`app_settings` `ticket_pr.config`) sobre
  los valores de la plataforma (`TICKET_PR_*`), y credenciales cifradas
  (almacén de integraciones, proveedor `ticket_pr`).
- `motor`: interfaz `MotorDeAgente` (plan de solo lectura y build) con el
  registro de motores; `opencode` es el primero y `MotorSimulado` el de los tests.
- `sandbox`: contenedor efímero por ejecución (Docker): sin red salvo un proxy de
  salida con lista blanca, sin secretos de la plataforma, usuario sin
  privilegios, raíz de solo lectura, límites y destrucción al terminar. Sin
  Docker, nada se ejecuta.
- `git_clientes`: GitHub (token de instalación de la GitHub App, alcance mínimo)
  y GitLab (token de proyecto): bajar el árbol de la rama base, crear la rama
  `contecflow/<ticket>-<id>` con un commit por API, abrir el PR y publicar el
  estado `contecflow/cab` que bloquea el merge hasta que el CAB aprueba.
- `diff`: comparación de árboles, ficheros protegidos, detector de secretos y límites.
- `instruccion`: la instrucción a partir del ticket con los datos personales ocultos.
- `servicio`: el flujo (lanzar, plan, aprobación, build, PR, cambio, CAB,
  cancelación, límites, coste, auditoría).
- `prueba`: prueba de conexión real (Docker, imágenes, Git, modelo) con `verificado`.
"""
