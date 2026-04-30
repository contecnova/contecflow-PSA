import React, { useId } from 'react'
import { INPUT_STYLE, LABEL_STYLE } from '../../constants/theme'

/**
 * FormField — wrapper unificado para campos de formulario.
 *
 *   <FormField label="Nombre" required error={errors.name} hint="Mínimo 3 caracteres">
 *     <input value={...} onChange={...} />
 *   </FormField>
 *
 * Aplica:
 *   - label conectado por htmlFor/id (clónico al child)
 *   - aria-invalid + aria-describedby cuando hay error/hint
 *   - estilo INPUT_STYLE base si el child no tiene style
 *   - error inline debajo
 *   - "required" marker (asterisco rojo)
 *
 * Usa con cualquier <input>, <select>, <textarea>.
 */
export default function FormField({ label, required, error, hint, children, style }) {
  const autoId = useId()
  const child = React.Children.only(children)
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
      ...INPUT_STYLE,
      ...(error ? { borderColor: 'var(--danger)' } : null),
      ...(child.props.style || {}),
    },
  })

  return (
    <div style={style}>
      {label && (
        <label htmlFor={id} style={LABEL_STYLE}>
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
        <div id={hintId} style={{
          marginTop: 4, fontSize: 'var(--text-xs)', color: 'var(--text-3)',
        }}>
          {hint}
        </div>
      )}
    </div>
  )
}
