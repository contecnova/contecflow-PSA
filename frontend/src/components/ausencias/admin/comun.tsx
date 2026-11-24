/**
 * Piezas comunes de la administración de ausencias: textos, color sin estilos
 * en línea (variable CSS fijada por ref), nombres por idioma y errores del API.
 */
import { useLayoutEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { useAppLang } from '../../../i18n/AppLangContext'
import type { Idioma } from '../../../services/api/tipos-ausencias'
import { COLOR_DATO_POR_DEFECTO } from '../../../constants/theme'
import { Checkbox, Input } from '../../ui'
import './ausencias-admin.css'

export const IDIOMAS: Idioma[] = ['es', 'en', 'zh']
export const DIAS_SEMANA = [1, 2, 3, 4, 5, 6, 7]

/** t() con el espacio `ausadm.` delante. */
export function useT() {
  const { t, lang } = useAppLang()
  const ta = (clave: string, params?: Record<string, unknown>) => t(`ausadm.${clave}`, params)
  return { t, ta, lang }
}

/** Fija `--aus-color` en el elemento (no hay estilos en línea en el JSX). */
export function useColorCss<T extends HTMLElement>(color: string | null | undefined) {
  const ref = useRef<T>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    if (color) el.style.setProperty('--aus-color', color)
    else el.style.removeProperty('--aus-color')
  }, [color])
  return ref
}

/** Un chip con el color del tipo o del turno. */
export function Muestra({ color, children, className = '', titulo }: {
  color: string | null | undefined; children?: ReactNode; className?: string; titulo?: string
}) {
  const ref = useColorCss<HTMLSpanElement>(color)
  return <span ref={ref} className={`ausadm-muestra ${className}`} title={titulo}>{children}</span>
}

/** El mensaje y la lista de errores de una respuesta del API (422 con `{message, errors}`). */
export function errorDe(e: unknown, defecto: string): { mensaje: string; errores: string[] } {
  const d = (e as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail
  if (!d) return { mensaje: defecto, errores: [] }
  if (typeof d === 'string') return { mensaje: d, errores: [] }
  if (Array.isArray(d)) {
    return { mensaje: defecto, errores: d.map(x => String((x as { msg?: string })?.msg ?? x)) }
  }
  const o = d as { message?: string; errors?: unknown[] }
  return { mensaje: o.message ?? defecto, errores: (o.errors ?? []).map(String) }
}

/** True si el formulario ya enseña algún error de campo (entonces el aviso general sobra). */
export const hayDeCampo = (c: { errores: Record<string, string> }) => Object.keys(c.errores).some(Boolean)

/** Error de validación del servidor junto a su campo (ver `useErroresDeCampo`). */
export function ErrorDeCampo({ texto }: { texto?: string }) {
  return texto ? <span className="u-field-error" role="alert">{texto}</span> : null
}

export function AvisoDeError({ error, defecto }: { error: unknown; defecto: string }) {
  if (!error) return null
  const { mensaje, errores } = errorDe(error, defecto)
  return (
    <div role="alert" className="ausadm-error">
      <strong>{mensaje}</strong>
      {errores.length > 0 && <ul>{errores.map(x => <li key={x}>{x}</li>)}</ul>}
    </div>
  )
}

/** Nombre en es, en y zh (tres entradas). */
export function NombresPorIdioma({ valor, onChange }: {
  valor: Partial<Record<Idioma, string>>; onChange: (v: Partial<Record<Idioma, string>>) => void
}) {
  const { ta } = useT()
  return (
    <fieldset className="ds-grupo-opciones ausadm-fieldset">
      <legend className="ausadm-etiqueta">{ta('nombre_por_idioma')}</legend>
      <div className="ausadm-grid-3">
        {IDIOMAS.map(l => (
          <Input key={l} label={ta(`idioma_${l}`)} aria-label={ta(`idioma_${l}`)} value={valor[l] ?? ''} lang={l} onChange={e => onChange({ ...valor, [l]: e.target.value })} />
        ))}
      </div>
    </fieldset>
  )
}

/** El nombre en el idioma actual, o el principal. */
export function nombreEn(n: { nombre: string; nombres?: Partial<Record<Idioma, string>> }, lang: string): string {
  return n.nombres?.[lang as Idioma] || n.nombre
}

export function Casilla({ etiqueta, valor, onChange, ayuda }: {
  etiqueta: string; valor: boolean; onChange: (v: boolean) => void; ayuda?: string
}) {
  return (
    <Checkbox className="ausadm-casilla" label={etiqueta} ayuda={ayuda} checked={valor} onChange={m => onChange(m)} />
  )
}

/** Fechas como texto AAAA-MM-DD sin zonas horarias. */
export function isoDe(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
export function mesDe(iso: string, desplazamiento = 0): { desde: string; hasta: string } {
  const [y, m] = iso.split('-').map(Number)
  const ini = new Date(y, m - 1 + desplazamiento, 1)
  const fin = new Date(ini.getFullYear(), ini.getMonth() + 1, 0)
  return { desde: isoDe(ini), hasta: isoDe(fin) }
}
export function diaDeLaSemana(iso: string): number {
  const [y, m, d] = iso.split('-').map(Number)
  const w = new Date(y, m - 1, d).getDay()
  return w === 0 ? 7 : w
}

/** El color de partida de un tipo o turno nuevo: el acento del tema (el
 * selector de color necesita #rrggbb; si el tema no lo da así, el de datos). */
export function colorPorDefecto(): string {
  const v = typeof document !== 'undefined'
    ? getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() : ''
  return /^#[0-9a-fA-F]{6}$/.test(v) ? v : COLOR_DATO_POR_DEFECTO
}
