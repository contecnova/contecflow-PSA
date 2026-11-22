"""Clientes internos (rev. 193, docs/CLIENTES_INTERNOS.md).

Un cliente interno es un `Client` con `kind="interno"`: un departamento, una
unidad de negocio, una filial o un centro de coste de la propia compañía.

- `unidades`: validación de la ficha, quién es de la unidad (deducido de RR. HH.)
  y su papel; alcance (cada persona ve solo sus unidades).
- `costes`: coste de una unidad por fuente (horas, precio cerrado, catálogo,
  licencias, equipos, software, reparto de servicios compartidos).
- `presupuesto`: presupuesto anual y consumo con el semáforo de `umbrales`.
- `cargos`: showback, nota de cargo interna (chargeback) e intercompañía;
  exceso de presupuesto con aprobación y segregación.
- `gobierno`: SLA/OLA, satisfacción, adopción, beneficios, roles.
- `portal`: portal interno (lo de mis unidades).
- `paneles`: cuadro de dirección.
- `peticiones`: «pedir proyecto o servicio» por el flujo de demanda.
- `cumplimiento`: controles del informe de cumplimiento.
"""
