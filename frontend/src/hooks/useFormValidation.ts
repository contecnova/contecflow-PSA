import { useCallback, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { ZodType } from 'zod'
import {
  validateSchema,
  type FieldErrors,
  type ValidationResult,
} from '../utils/formValidation'

export interface UseFormValidationResult<T> {
  errors: FieldErrors
  setErrors: Dispatch<SetStateAction<FieldErrors>>
  clearFieldError: (field: string) => void
  validateForm: (values: unknown) => ValidationResult<T>
  /** Clases de un campo: `base` y, si `field` tiene error, `campo-form--error` (borde y halo de error). */
  inputClass: (base: string, field: string) => string
}

export function useFormValidation<T>(schema: ZodType<T>): UseFormValidationResult<T> {
  const [errors, setErrors] = useState<FieldErrors>({})

  const clearFieldError = useCallback((field: string) => {
    setErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }, [])

  const validateForm = useCallback((values: unknown): ValidationResult<T> => {
    const result = validateSchema(schema, values)
    if (!result.success) {
      setErrors(result.errors)
      return result
    }
    setErrors({})
    return result
  }, [schema])

  const inputClass = useCallback((base: string, field: string): string => (
    errors[field] ? `${base} campo-form--error` : base
  ), [errors])

  return {
    errors,
    setErrors,
    clearFieldError,
    validateForm,
    inputClass,
  }
}
