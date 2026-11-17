/**
 * Casillas, radios, interruptor y grupos de opciones del kit (16-11-2026).
 *
 * Nada de `<input type="checkbox|radio">` suelto en una pantalla: estas piezas
 * le dan la etiqueta asociada, el foco visible, el color del acento y el mismo
 * tamaño en toda la app. `GrupoDeOpciones` envuelve las clases
 * `ds-grupo-opciones` / `ds-opciones` / `ds-opcion` de index.css (tarjetas) o
 * las pinta en lista.
 */
import { useEffect, useId, useRef } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import './Opciones.css'

interface BaseCasilla {
  checked: boolean
  /** Recibe el nuevo estado y el evento. */
  onChange?: (marcado: boolean, e: ChangeEvent<HTMLInputElement>) => void
  /** Texto visible; sin él, `aria-label` es obligatorio. */
  label?: ReactNode
  /** Línea de ayuda bajo el texto. */
  ayuda?: ReactNode
  disabled?: boolean
  name?: string
  value?: string
  id?: string
  'aria-label'?: string
  'aria-describedby'?: string
  className?: string
  /** Como tarjeta (`ds-opcion`) en vez de en línea. */
  tarjeta?: boolean
  /** Marcas para tours y pruebas. */
  [atributoData: `data-${string}`]: string | undefined
}

export interface CheckboxProps extends BaseCasilla {
  /** Estado mixto (p. ej. «seleccionar todas» con algunas elegidas). */
  indeterminado?: boolean
}

function Casilla({ tipo, checked, onChange, label, ayuda, disabled, name, value, id, className, tarjeta, indeterminado, rol, ...resto }:
  BaseCasilla & { tipo: 'checkbox' | 'radio'; indeterminado?: boolean; rol?: 'switch' }) {
  const ref = useRef<HTMLInputElement>(null)
  const generado = useId()
  const idFinal = id ?? `casilla-${generado}`
  useEffect(() => { if (ref.current) ref.current.indeterminate = !!indeterminado }, [indeterminado])
  const control = (
    <input ref={ref} id={idFinal} type={tipo} role={rol} checked={checked} disabled={disabled} name={name} value={value}
      aria-checked={indeterminado ? 'mixed' : undefined}
      className={rol === 'switch' ? 'ui-switch__control' : 'ui-casilla__control'}
      onChange={e => onChange?.(e.target.checked, e)} {...resto} />
  )
  if (!label && !ayuda) return <span className={`ui-casilla ui-casilla--sola${className ? ` ${className}` : ''}`}>{control}</span>
  const base = tarjeta ? 'ds-opcion' : rol === 'switch' ? 'ui-casilla ui-switch' : 'ui-casilla'
  return (
    <label htmlFor={idFinal} className={`${base}${disabled ? ' ui-casilla--desactivada' : ''}${className ? ` ${className}` : ''}`}>
      {control}
      <span className="ui-casilla__texto">
        {label && <span className={tarjeta ? 'ds-opcion__titulo' : 'ui-casilla__titulo'}>{label}</span>}
        {ayuda && <span className={tarjeta ? 'ds-opcion__ayuda' : 'ui-casilla__ayuda'}>{ayuda}</span>}
      </span>
    </label>
  )
}

/** Casilla de verificación. `onChange(marcado, evento)`. */
export function Checkbox(props: CheckboxProps) {
  return <Casilla tipo="checkbox" {...props} />
}

/** Botón de opción suelto (lo normal es `GrupoDeOpciones tipo="radio"`). */
export function Radio(props: BaseCasilla) {
  return <Casilla tipo="radio" {...props} />
}

/** Interruptor encendido / apagado (`role="switch"`): para ajustes que se aplican al momento. */
export function Switch(props: Omit<BaseCasilla, 'tarjeta'>) {
  return <Casilla tipo="checkbox" rol="switch" {...props} />
}

export interface OpcionDeGrupo {
  valor: string
  titulo: ReactNode
  ayuda?: ReactNode
  disabled?: boolean
}

interface GrupoBase {
  /** Título del grupo (`<legend>`); sin él, `aria-label`. */
  leyenda?: ReactNode
  'aria-label'?: string
  opciones: OpcionDeGrupo[]
  name?: string
  disabled?: boolean
  /** `tarjetas` (por defecto, `ds-opcion`), `lista` (vertical) o `fila` (en línea). */
  forma?: 'tarjetas' | 'lista' | 'fila'
  className?: string
}

export type GrupoDeOpcionesProps =
  | (GrupoBase & { tipo?: 'radio'; valor: string; onChange: (valor: string) => void })
  | (GrupoBase & { tipo: 'checkbox'; valor: string[]; onChange: (valor: string[]) => void })

/** Grupo de radios (una opción) o de casillas (varias), con su leyenda. */
export function GrupoDeOpciones(props: GrupoDeOpcionesProps) {
  const { leyenda, opciones, disabled, forma = 'tarjetas', className } = props
  const generado = useId()
  const name = props.name ?? `grupo-${generado}`
  const tarjeta = forma === 'tarjetas'
  const claseOpciones = forma === 'tarjetas' ? 'ds-opciones' : forma === 'fila' ? 'ui-opciones-fila' : 'ui-opciones-lista'
  return (
    <fieldset className={`ds-grupo-opciones${className ? ` ${className}` : ''}`} aria-label={leyenda ? undefined : props['aria-label']}
      role={props.tipo === 'checkbox' ? undefined : 'radiogroup'}>
      {leyenda && <legend className="ds-eyebrow">{leyenda}</legend>}
      <div className={claseOpciones}>
        {opciones.map(o => {
          const comunes = { name, value: o.valor, label: o.titulo, ayuda: o.ayuda, tarjeta, disabled: disabled || o.disabled }
          if (props.tipo === 'checkbox') {
            const elegidos = props.valor
            return <Checkbox key={o.valor} {...comunes} checked={elegidos.includes(o.valor)}
              onChange={m => props.onChange(m ? [...elegidos, o.valor] : elegidos.filter(v => v !== o.valor))} />
          }
          return <Radio key={o.valor} {...comunes} checked={props.valor === o.valor} onChange={() => props.onChange(o.valor)} />
        })}
      </div>
    </fieldset>
  )
}
