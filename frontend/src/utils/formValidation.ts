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

export interface ValidationResult<T> {
  success: boolean
  data: T | null
  errors: FieldErrors
}

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
