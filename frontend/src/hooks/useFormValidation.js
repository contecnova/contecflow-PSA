import { useCallback, useState } from 'react'
import { getFieldErrorStyle, validateSchema } from '../utils/formValidation'

export function useFormValidation(schema) {
  const [errors, setErrors] = useState({})

  const clearFieldError = useCallback((field) => {
    setErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }, [])

  const validateForm = useCallback((values) => {
    const result = validateSchema(schema, values)
    if (!result.success) {
      setErrors(result.errors)
      return result
    }
    setErrors({})
    return result
  }, [schema])

  const inputStyle = useCallback((baseStyle, field) => (
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
