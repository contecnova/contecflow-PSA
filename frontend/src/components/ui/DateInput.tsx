import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'

/**
 * <DateInput> — el campo de fecha compartido.
 *
 * Sustituye a los `<input type="date">` / `<input type="datetime-local">`
 * sueltos (auditoría 2026-11, #31: 128 campos de fecha sin componente común).
 * Acepta todas las props de un `<input>` salvo `type`:
 *
 *   <DateInput value={f.desde} onChange={e => set(e.target.value)} style={campo} />
 *   <DateInput withTime value={f.inicio} onChange={…} />
 *
 * Lo que aporta frente al `<input>` suelto:
 *  - `max` por defecto en el año 9999: el navegador deja teclear años de 5-6
 *    cifras («202555-01-01») que la API rechaza o guarda mal.
 *  - la clase `ds-date-input`, que hace que el icono del calendario siga al
 *    tema (claro/oscuro) en lugar de pintarse negro sobre fondo oscuro.
 */
export interface DateInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  /** `true` = fecha y hora (`datetime-local`). */
  withTime?: boolean
}

const DateInput = forwardRef<HTMLInputElement, DateInputProps>(function DateInput(
  { withTime = false, max, className, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      type={withTime ? 'datetime-local' : 'date'}
      max={max ?? (withTime ? '9999-12-31T23:59' : '9999-12-31')}
      className={className ? `ds-date-input ${className}` : 'ds-date-input'}
      {...rest}
    />
  )
})

export default DateInput
