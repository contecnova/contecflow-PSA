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
