import { forwardRef } from 'react'
import type { ChangeEvent, CSSProperties, FocusEvent } from 'react'
import { CampoFecha } from './SelectorDeFecha'

/**
 * <DateInput> — el campo de fecha compartido.
 *
 * 16-11-2026: por dentro ya no es un `<input type="date">` nativo (pintaba el
 * formato de la región del navegador, no el del idioma de la app) sino
 * `CampoFecha`, el selector propio del kit. La API no cambia, así que las
 * pantallas que lo usan cambian todas a la vez:
 *
 *   <DateInput value={f.desde} onChange={e => set(e.target.value)} className="ds-input" />
 *   <DateInput withTime value={f.inicio} onChange={…} />
 *
 * `value` y `e.target.value` siguen siendo 'YYYY-MM-DD' / 'YYYY-MM-DDTHH:MM'.
 * `onChange` recibe un evento con `target`/`currentTarget` `{ value, name, id }`
 * y solo cuando el valor está completo y es válido ('' al vaciar).
 */
export interface DateInputProps {
  /** `true` = fecha y hora. */
  withTime?: boolean
  value?: string | null
  defaultValue?: string
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void
  onBlur?: (e: FocusEvent<HTMLInputElement>) => void
  onFocus?: (e: FocusEvent<HTMLInputElement>) => void
  min?: string
  max?: string
  id?: string
  name?: string
  className?: string
  style?: CSSProperties
  placeholder?: string
  disabled?: boolean
  required?: boolean
  readOnly?: boolean
  autoFocus?: boolean
  title?: string
  /** Zona IANA (solo con hora): `value` es un instante ISO y se edita en esa zona. */
  zona?: string
  'aria-label'?: string
  'aria-labelledby'?: string
  'aria-describedby'?: string
  'aria-invalid'?: boolean | 'true' | 'false'
  'aria-required'?: boolean | 'true' | 'false'
  [atributoData: `data-${string}`]: string | undefined
}

/** Evento mínimo con la forma que leen los formularios (`e.target.value`, `e.target.name`). */
export function eventoDeCambio(valor: string, name?: string, id?: string): ChangeEvent<HTMLInputElement> {
  const target = { value: valor, name: name ?? '', id: id ?? '', type: 'text' } as unknown as HTMLInputElement
  return {
    target, currentTarget: target, type: 'change', bubbles: true, defaultPrevented: false,
    preventDefault: () => {}, stopPropagation: () => {}, persist: () => {}, isDefaultPrevented: () => false,
    isPropagationStopped: () => false, nativeEvent: new Event('change'),
  } as unknown as ChangeEvent<HTMLInputElement>
}

const DateInput = forwardRef<HTMLInputElement, DateInputProps>(function DateInput(
  { withTime = false, value, defaultValue, onChange, name, id, ...rest },
  ref,
) {
  return (
    <CampoFecha
      {...rest}
      refCampo={ref}
      id={id}
      name={name}
      modo={withTime ? 'fechaHora' : 'fecha'}
      value={value ?? defaultValue ?? ''}
      onChange={v => onChange?.(eventoDeCambio(v, name, id))}
    />
  )
})

export default DateInput
