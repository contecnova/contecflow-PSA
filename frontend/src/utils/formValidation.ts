import type { ZodIssue, ZodSchema } from 'zod'
import type { CSSProperties } from 'react'

export type FieldErrors = Record<string, string>

interface ZodErrorLike {
  issues: ZodIssue[]
}

export function getFirstIssueByField(error: ZodErrorLike): FieldErrors {
  const fieldErrors: FieldErrors = {}

  error.issues.forEach((issue) => {
    const field = issue.path?.[0]
    if (field !== undefined && field !== null) {
      const key = String(field)
      if (!(key in fieldErrors)) {
        fieldErrors[key] = issue.message
      }
    }
  })

  return fieldErrors
}

/**
 * El resultado de validar un formulario.
 *
 * Auditoría 2026-09: esto era una interfaz con `success: boolean` y
 * `data: T | null` como campos **independientes**, así que TypeScript no podía
 * saber que si hay éxito hay datos. Todos los sitios de llamada hacían
 *
 *     if (!result.success) return
 *     mutate(result.data)      // ← `T | null`, error en modo estricto
 *
 * y la única salida era un `!` o un cast en cada uno. Como unión discriminada
 * **el tipo dice lo que de verdad ocurre**, y los cuatro sitios dejan de
 * necesitar nada: `success` narra `data` sola.
 *
 * No es cosmética de tipos: la invariante «si validó, hay datos» estaba en la
 * cabeza de quien lo escribió y en ningún otro sitio.
 */
export type ValidationResult<T> =
  | { success: true;  data: T;    errors: FieldErrors }
  | { success: false; data: null; errors: FieldErrors }

export function validateSchema<T>(schema: ZodSchema<T>, values: unknown): ValidationResult<T> {
  const parsed = schema.safeParse(values)

  if (parsed.success) {
    return { success: true, data: parsed.data, errors: {} }
  }

  return {
    success: false,
    data: null,
    errors: getFirstIssueByField(parsed.error),
  }
}

export function getFieldErrorStyle(baseStyle: CSSProperties, hasError: boolean): CSSProperties {
  if (!hasError) return baseStyle

  return {
    ...baseStyle,
    border: '1px solid var(--danger)',
    boxShadow: '0 0 0 1px rgba(255, 71, 87, 0.18)',
  }
}
