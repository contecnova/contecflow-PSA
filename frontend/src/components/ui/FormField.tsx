import React, { useId } from 'react'
import type { CSSProperties, ReactElement, ReactNode } from 'react'
import './FormField.css'

/**
 * FormField — wrapper unificado para campos de formulario.
 *
 *   <FormField label="Nombre" required error={errors.name} hint="Mínimo 3 caracteres">
 *     <input value={...} onChange={...} />
 *   </FormField>
 */
export interface FormFieldProps {
  label?: ReactNode
  required?: boolean
  error?: ReactNode
  hint?: ReactNode
  children: ReactElement
  style?: CSSProperties
}

export default function FormField({ label, required, error, hint, children, style }: FormFieldProps) {
  const autoId = useId()
  const child = React.Children.only(children) as ReactElement<{
    id?: string
    className?: string
  }>
  const id = child.props.id || `f-${autoId}`
  const errorId = error ? `${id}-error` : undefined
  const hintId = hint && !error ? `${id}-hint` : undefined
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined

  const enhancedChild = React.cloneElement(child, {
    id,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': describedBy,
    'aria-required': required ? true : undefined,
    className: [`ui-form-field-control${error ? ' ui-form-field-control--error' : ''}`, child.props.className].filter(Boolean).join(' '),
  } as Partial<typeof child.props>)

  return (
    <div style={style}>
      {label && (
        <label htmlFor={id} className="ui-form-field-etiqueta">
          {label}
          {required && <span aria-hidden="true" className="uiformfiel-box-1">*</span>}
        </label>
      )}
      {enhancedChild}
      {error && (
        <div id={errorId} role="alert" className="uiformfiel-row-1">
          ⚠ {error}
        </div>
      )}
      {hint && !error && (
        <div id={hintId} className="u-hint">
          {hint}
        </div>
      )}
    </div>
  )
}
