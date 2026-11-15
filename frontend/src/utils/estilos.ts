import type { CSSProperties } from 'react'

/**
 * Valor de longitud para una propiedad CSS personalizada.
 *
 * React añade `px` a los números de las propiedades de `style`, pero NO a las
 * propiedades personalizadas (`'--x': 24` llega como `24`, no `24px`). Las
 * clases que consumen `var(--x)` en una longitud (width, gap, padding…) reciben
 * por aquí el mismo valor que daba el estilo en línea: número → `Npx`; cadena
 * (`'50%'`, `'calc(…)'`) → tal cual; `undefined`/`null` → `undefined` (React no
 * emite la propiedad).
 */
export function px(valor: number | string | null | undefined): string | undefined {
  if (valor === null || valor === undefined) return undefined
  return typeof valor === 'number' ? `${valor}px` : valor
}

/** Color de dato para `.chip-dato` (index.css): texto, fondo al 15 % y borde al 30 % de ese color. */
export const chipColor = (color: string): CSSProperties => ({ '--chip-color': color } as CSSProperties)

/** Medidas de un esqueleto (`.dashkit-sk`): número → px, cadena tal cual. */
export const medidasDeEsqueleto = (ancho: number | string, alto: number | string, radio: number | string = 6): CSSProperties =>
  ({ '--sk-w': px(ancho), '--sk-h': px(alto), '--sk-r': px(radio) } as CSSProperties)
