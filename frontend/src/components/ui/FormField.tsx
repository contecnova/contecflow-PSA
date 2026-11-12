import React, { useId } from 'react'
import type { CSSProperties, ReactElement, ReactNode } from 'react'
// TODO type: constants/theme.js still JS.
import { INPUT_STYLE, LABEL_STYLE } from '../../constants/theme'

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
    style?: CSSProperties
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
    style: {
      ...(INPUT_STYLE as CSSProperties),
      ...(error ? { borderColor: 'var(--danger)' } : null),
      ...(child.props.style || {}),
    },
  } as Partial<typeof child.props>)

  return (
    <div style={style}>
      {label && (
        <label htmlFor={id} style={LABEL_STYLE as CSSProperties}>
          {label}
          {required && <span aria-hidden="true" style={{ color: 'var(--danger)', marginLeft: 3 }}>*</span>}
        </label>
      )}
      {enhancedChild}
      {error && (
        <div id={errorId} role="alert" style={{
          marginTop: 4, fontSize: 'var(--text-xs)', color: 'var(--danger)',
          display: 'flex', alignItems: 'center', gap: 4,
        }}>
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
