import { useCallback, useState } from 'react'
import type { CSSProperties, Dispatch, SetStateAction } from 'react'
import type { ZodSchema } from 'zod'
import {
  getFieldErrorStyle,
  validateSchema,
  type FieldErrors,
  type ValidationResult,
} from '../utils/formValidation'

export interface UseFormValidationResult<T> {
  errors: FieldErrors
  setErrors: Dispatch<SetStateAction<FieldErrors>>
  clearFieldError: (field: string) => void
  validateForm: (values: unknown) => ValidationResult<T>
  inputStyle: (baseStyle: CSSProperties, field: string) => CSSProperties
}

export function useFormValidation<T>(schema: ZodSchema<T>): UseFormValidationResult<T> {
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

  const inputStyle = useCallback((baseStyle: CSSProperties, field: string): CSSProperties => (
    getFieldErrorStyle(baseStyle, !!errors[field])
  ), [errors])

  return {
    errors,
    setErrors,
    clearFieldError,
    validateForm,
    inputStyle,
  }
}
