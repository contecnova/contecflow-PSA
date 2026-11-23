/**
 * SelectRico (18-11-2026): un desplegable cuyas opciones llevan icono, color y
 * descripción, con el mismo aspecto cerrado que `Select`.
 *
 * Para cuando el `<select>` nativo se queda corto (no pinta iconos ni colores)
 * y una fila de radios ocupa demasiado: tipos de ausencia, categorías,
 * prioridades con color… Accesible como un listbox (WAI-ARIA «select-only
 * combobox»): el botón lleva `role="combobox"`, la lista `role="listbox"`;
 * flechas, Inicio/Fin, Intro/Espacio, Escape, Tab y búsqueda tecleando.
 */
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import './SelectRico.css'
import { avisarCambio } from './useCambiosSinGuardar'

export interface OpcionRica {
  valor: string
  etiqueta: string
  /** Icono (lucide) que va delante. */
  icono?: ReactNode
  /** Color de la marca (token o hex): pinta el icono y una pastilla suave. */
  color?: string
  /** Texto secundario bajo la etiqueta (solo en la lista). */
  descripcion?: string
  deshabilitada?: boolean
}

export interface SelectRicoProps {
  label?: string
  valor: string | null | undefined
  onChange: (valor: string) => void
  opciones: OpcionRica[]
  placeholder?: string
  error?: ReactNode
  hint?: ReactNode
  disabled?: boolean
  required?: boolean
  id?: string
  className?: string
  'aria-label'?: string
}

const MS_BUSQUEDA = 600

export function SelectRico({ label, valor, onChange, opciones, placeholder, error, hint, disabled, required, id, className, 'aria-label': ariaLabel }: SelectRicoProps) {
  const auto = useId()
  const base = id ?? `sr-${auto}`
  const [abierto, setAbierto] = useState(false)
  const [activa, setActiva] = useState(-1)
  const raiz = useRef<HTMLDivElement>(null)
  const lista = useRef<HTMLUListElement>(null)
  const busqueda = useRef({ texto: '', hasta: 0 })

  const elegida = useMemo(() => opciones.find(o => o.valor === valor), [opciones, valor])
  const habilitadas = useMemo(() => opciones.map((o, i) => (o.deshabilitada ? -1 : i)).filter(i => i >= 0), [opciones])

  useEffect(() => {
    if (!abierto) return
    const fuera = (e: PointerEvent) => { if (!raiz.current?.contains(e.target as Node)) setAbierto(false) }
    document.addEventListener('pointerdown', fuera)
    return () => document.removeEventListener('pointerdown', fuera)
  }, [abierto])

  useEffect(() => {
    if (abierto && activa >= 0) lista.current?.querySelector<HTMLElement>(`[data-i="${activa}"]`)?.scrollIntoView?.({ block: 'nearest' })
  }, [abierto, activa])

  const abrir = () => {
    if (disabled) return
    const i = opciones.findIndex(o => o.valor === valor)
    setActiva(i >= 0 ? i : (habilitadas[0] ?? -1))
    setAbierto(true)
  }
  const elegir = (i: number) => {
    const o = opciones[i]
    if (!o || o.deshabilitada) return
    onChange(o.valor)
    // No es un control nativo: avisa al dialogo (cambios sin guardar).
    if (o.valor !== valor) avisarCambio(raiz.current)
    setAbierto(false)
  }
  const mover = (paso: number) => {
    if (!habilitadas.length) return
    const pos = habilitadas.indexOf(activa)
    const sig = pos < 0 ? 0 : Math.min(habilitadas.length - 1, Math.max(0, pos + paso))
    setActiva(habilitadas[sig])
  }
  const buscar = (letra: string) => {
    const ahora = Date.now()
    const b = busqueda.current
    b.texto = (ahora < b.hasta ? b.texto : '') + letra.toLowerCase()
    b.hasta = ahora + MS_BUSQUEDA
    const i = opciones.findIndex(o => !o.deshabilitada && o.etiqueta.toLowerCase().startsWith(b.texto))
    if (i >= 0) { if (!abierto) setAbierto(true); setActiva(i) }
  }

  const teclas = (e: KeyboardEvent<HTMLButtonElement>) => {
    switch (e.key) {
      case 'ArrowDown': e.preventDefault(); if (abierto) mover(1); else abrir(); break
      case 'ArrowUp': e.preventDefault(); if (abierto) mover(-1); else abrir(); break
      case 'Home': if (abierto) { e.preventDefault(); setActiva(habilitadas[0] ?? -1) } break
      case 'End': if (abierto) { e.preventDefault(); setActiva(habilitadas[habilitadas.length - 1] ?? -1) } break
      case 'Enter': case ' ':
        e.preventDefault()
        if (abierto) elegir(activa); else abrir()
        break
      case 'Escape': if (abierto) { e.preventDefault(); e.stopPropagation(); setAbierto(false) } break
      case 'Tab': if (abierto) { elegir(activa); } break
      default:
        if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) buscar(e.key)
    }
  }

  const marca = (o: OpcionRica | undefined) => o && (
    <span className="sr-marca" style={o.color ? { '--sr-color': o.color } as React.CSSProperties : undefined}>
      {o.icono && <span className="sr-icono" aria-hidden>{o.icono}</span>}
      <span className="sr-etiqueta">{o.etiqueta}</span>
    </span>
  )

  const idLista = `${base}-lista`
  const idsDescritos = [hint ? `${base}-hint` : '', error ? `${base}-error` : ''].filter(Boolean).join(' ') || undefined

  return (
    <div ref={raiz} className={`ui-field sr${className ? ` ${className}` : ''}`}>
      {label && <label id={`${base}-label`} htmlFor={base} className="uiinde-estiloetiqueta">{label}</label>}
      <button type="button" id={base} className={`sr-control${error ? ' sr-control--error' : ''}`}
        role="combobox" aria-haspopup="listbox" aria-expanded={abierto} aria-controls={idLista}
        aria-activedescendant={abierto && activa >= 0 ? `${base}-op-${activa}` : undefined}
        aria-label={label ? undefined : ariaLabel} aria-labelledby={label ? `${base}-label ${base}` : undefined}
        aria-invalid={error ? true : undefined} aria-required={required || undefined} aria-describedby={idsDescritos}
        disabled={disabled} onClick={() => (abierto ? setAbierto(false) : abrir())} onKeyDown={teclas}>
        {elegida ? marca(elegida) : <span className="sr-placeholder">{placeholder ?? ''}</span>}
        <ChevronDown size={16} className={`sr-flecha${abierto ? ' sr-flecha--abierta' : ''}`} aria-hidden />
      </button>
      {abierto && (
        <ul ref={lista} id={idLista} role="listbox" className="sr-lista" aria-labelledby={label ? `${base}-label` : undefined} aria-label={label ? undefined : ariaLabel}>
          {opciones.map((o, i) => (
            // eslint-disable-next-line jsx-a11y/click-events-have-key-events -- el teclado lo lleva el combobox (aria-activedescendant), como pide WAI-ARIA
            <li key={o.valor} id={`${base}-op-${i}`} data-i={i} role="option" aria-selected={o.valor === valor}
              aria-disabled={o.deshabilitada || undefined}
              className={`sr-opcion${i === activa ? ' sr-opcion--activa' : ''}${o.valor === valor ? ' sr-opcion--elegida' : ''}`}
              onPointerEnter={() => !o.deshabilitada && setActiva(i)}
              onPointerDown={e => e.preventDefault()}
              onClick={() => elegir(i)}>
              <span className="sr-opcion-texto">
                {marca(o)}
                {o.descripcion && <span className="sr-descripcion">{o.descripcion}</span>}
              </span>
              {o.valor === valor && <Check size={15} className="sr-check" aria-hidden />}
            </li>
          ))}
        </ul>
      )}
      {hint && <div id={`${base}-hint`} className="u-text3-xs">{hint}</div>}
      {error && <div id={`${base}-error`} role="alert" className="u-field-error">{error}</div>}
    </div>
  )
}

export default SelectRico
