/**
 * Piezas comunes de «Políticas y reglas»: datos del catálogo, etiquetas
 * traducidas y entradas de valor tipadas (importe con moneda, país, ciudad,
 * persona, rol, fecha, lista…). Nadie escribe JSON: cada tipo tiene su control.
 */
import { useId, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { politicasApi } from '../../services/api'
import type {
  CampoDeDominio, ClaseDeEntidad, Importe, Operador, OpcionesDePoliticas, ValorDeCondicion,
} from '../../services/api/tipos-politicas'
import { useAppLang } from '../../i18n/AppLangContext'
import { UserSelect, ProjectSelect, ClientSelect } from '../ui/EntitySelect'
import DateInput from '../ui/DateInput'
import { CampoFecha } from '../ui/SelectorDeFecha'
import { CODIGOS_DE_PAIS, nombreDePais } from '../../constants/paises'
import { STALE_5_MIN_MS } from '../../constants/timings'
import './politicas.css'
import { Select, Pulsable, Checkbox, Input } from '../ui'

export function useCatalogo() {
  return useQuery({ queryKey: ['politicas', 'catalogo'], queryFn: politicasApi.catalogo, staleTime: STALE_5_MIN_MS })
}
export function useOpciones() {
  return useQuery({ queryKey: ['politicas', 'opciones'], queryFn: politicasApi.opciones, staleTime: STALE_5_MIN_MS })
}

/** t() más etiquetas de los campos del dominio: la traducción si existe, la del dominio si no. */
export function useTextos() {
  const { t, translations, lang } = useAppLang()
  const pol = (translations?.pol ?? {}) as Record<string, unknown>
  const etiquetaDeCampo = (dominio: string, campo: CampoDeDominio | undefined, clave?: string) => {
    const k = `campo_${dominio}_${campo?.clave ?? clave}`
    return typeof pol[k] === 'string' ? (pol[k] as string) : (campo?.etiqueta ?? clave ?? '')
  }
  const etiquetaDeOpcion = (dominio: string, campo: CampoDeDominio, valor: string) => {
    const k = `opcion_${dominio}_${campo.clave}_${valor}`
    return typeof pol[k] === 'string' ? (pol[k] as string) : (campo.opciones.find(o => o.valor === valor)?.etiqueta ?? valor)
  }
  const pais = (codigo: string) => nombreDePais(codigo, lang)
  return { t, lang, etiquetaDeCampo, etiquetaDeOpcion, pais }
}

// ── Lista de valores con chips (departamentos, países, ubicaciones…) ─────────

export function ListaDeValores({ valores, onChange, opciones, etiqueta, placeholder, libre = false, mostrar }: {
  valores: string[]; onChange: (v: string[]) => void; opciones: string[]; etiqueta: string
  placeholder?: string; libre?: boolean; mostrar?: (v: string) => string
}) {
  const { t } = useTextos()
  const id = useId()
  const [texto, setTexto] = useState('')
  const ver = mostrar ?? ((v: string) => v)
  const anadir = (v: string) => {
    const limpio = v.trim()
    if (!limpio || valores.includes(limpio)) return
    if (!libre && !opciones.includes(limpio)) return
    onChange([...valores, limpio])
    setTexto('')
  }
  const tecla = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') { e.preventDefault(); anadir(texto) }
  }
  return (
    <div>
      <label className="uiinde-estiloetiqueta" htmlFor={id}>{etiqueta}</label>
      <div className="pol-fila">
        {valores.map(v => (
          <span key={v} className="pol-chip">
            {ver(v)}
            <Pulsable /* eslint-disable-line contec/sin-boton-de-icono-propio -- excepción: aspa de quitar dentro de un chip */ onClick={() => onChange(valores.filter(x => x !== v))} aria-label={t('pol.quitar_valor', { valor: ver(v) })}>
              <X size={12} aria-hidden />
            </Pulsable>
          </span>
        ))}
        <Input id={id} list={`${id}-l`} value={texto} placeholder={placeholder ?? t('pol.anadir')} onChange={e => { setTexto(e.target.value); if (opciones.includes(e.target.value)) anadir(e.target.value) }} onKeyDown={tecla} onBlur={() => libre && anadir(texto)} className="pol-campo--medio" />
        <datalist id={`${id}-l`}>
          {opciones.filter(o => !valores.includes(o)).map(o => <option key={o} value={o}>{ver(o)}</option>)}
        </datalist>
      </div>
    </div>
  )
}

export function SelectorDePais({ valor, onChange, etiqueta, vacio = true }: {
  valor: string | null | undefined; onChange: (v: string | null) => void; etiqueta: string; vacio?: boolean
}) {
  const { t, pais } = useTextos()
  const ordenados = [...CODIGOS_DE_PAIS].sort((a, b) => pais(a).localeCompare(pais(b)))
  return (
    <Select suelto className="pol-campo pol-campo--medio" aria-label={etiqueta} value={valor ?? ''} onChange={e => onChange(e.target.value || null)} placeholder={false}>
      {vacio && <option value="">{t('pol.cualquier_pais')}</option>}
      {ordenados.map(c => <option key={c} value={c}>{pais(c)} ({c})</option>)}
    </Select>
  )
}

export function SelectorDeMoneda({ valor, onChange, opciones, etiqueta }: {
  valor: string | null | undefined; onChange: (v: string) => void; opciones: OpcionesDePoliticas | undefined; etiqueta: string
}) {
  const monedas = opciones?.monedas ?? []
  return (
    <Select suelto className="pol-campo pol-campo--corto" aria-label={etiqueta} value={valor ?? opciones?.moneda_por_defecto ?? ''}
      onChange={e => onChange(e.target.value)} placeholder={false}>
      {monedas.map(m => <option key={m} value={m}>{m}</option>)}
    </Select>
  )
}

export function EntradaDeImporte({ valor, onChange, opciones, etiqueta }: {
  valor: Importe | null | undefined; onChange: (v: Importe) => void; opciones: OpcionesDePoliticas | undefined; etiqueta: string
}) {
  const { t } = useTextos()
  const moneda = valor?.moneda ?? opciones?.moneda_por_defecto ?? ''
  return (
    <span className="pol-fila">
      <Input type="number" step="0.01" min={0} aria-label={etiqueta} value={valor?.cantidad ?? ''} onChange={e => onChange({ cantidad: Number(e.target.value), moneda })} className="pol-campo--corto" />
      <SelectorDeMoneda valor={moneda} opciones={opciones} etiqueta={t('pol.moneda_de', { campo: etiqueta })}
        onChange={m => onChange({ cantidad: valor?.cantidad ?? 0, moneda: m })} />
    </span>
  )
}

/** Selector de una entidad según su clase (persona, proyecto, rol, departamento…). */
export function SelectorDeEntidad({ clase, valor, onChange, opciones, etiqueta }: {
  clase: ClaseDeEntidad; valor: string | null | undefined; onChange: (v: string) => void
  opciones: OpcionesDePoliticas | undefined; etiqueta: string
}) {
  const { t } = useTextos()
  if (clase === 'usuario') return <span aria-label={etiqueta}><UserSelect value={valor ?? ''} onChange={id => onChange(id)} placeholder={t('pol.elige_persona')} /></span>
  if (clase === 'proyecto') return <span aria-label={etiqueta}><ProjectSelect value={valor ?? ''} onChange={(id: string) => onChange(id)} placeholder={t('pol.elige_proyecto')} /></span>
  if (clase === 'cliente') return <span aria-label={etiqueta}><ClientSelect value={valor ?? ''} onChange={(id: string) => onChange(id)} placeholder={t('pol.elige_cliente')} /></span>
  const lista = clase === 'rol' ? opciones?.roles : clase === 'departamento' ? opciones?.departamentos
    : clase === 'equipo' ? opciones?.equipos : (opciones?.grupos ?? []).map(g => g.id)
  const mostrar = (v: string) => clase === 'grupo' ? (opciones?.grupos.find(g => g.id === v)?.nombre ?? v)
    : clase === 'rol' ? t(`pol.rol_${v}`) : v
  return (
    <Select suelto className="pol-campo pol-campo--medio" aria-label={etiqueta} value={valor ?? ''} onChange={e => onChange(e.target.value)} placeholder={t('pol.elige')}>
      {(lista ?? []).map(v => <option key={v} value={v}>{mostrar(v)}</option>)}
    </Select>
  )
}

const DIAS = [1, 2, 3, 4, 5, 6, 7]

/** Las opciones de un campo `enum`: las fijas del catálogo y, si las hay, las
 * que dependen de la empresa (rev. 167: tipos de ausencia, turnos, oficinas). */
export function opcionesDeCampo(dominio: string, campo: CampoDeDominio, opciones: OpcionesDePoliticas | undefined) {
  const dinamicas = opciones?.opciones_de_campos?.[dominio]?.[campo.clave] ?? []
  return [...campo.opciones, ...dinamicas.filter(d => !campo.opciones.some(o => o.valor === d.valor))]
}

/** El control de valor adecuado al tipo del campo y al operador. */
export function EntradaDeValor({ dominio, campo, operador, valor, onChange, opciones, etiqueta }: {
  dominio: string; campo: CampoDeDominio; operador: Operador; valor: ValorDeCondicion | undefined
  onChange: (v: ValorDeCondicion) => void; opciones: OpcionesDePoliticas | undefined; etiqueta: string
}) {
  const { t, etiquetaDeOpcion, pais } = useTextos()
  if (operador === 'weekday_in' || operador === 'weekday_not_in') {
    const dias = (Array.isArray(valor) ? valor : []) as number[]
    return (
      <span className="pol-fila" role="group" aria-label={etiqueta}>
        {DIAS.map(d => (
          <Checkbox key={d} className="pol-chip" label={t(`pol.dia_${d}`)} checked={dias.includes(d)}
            onChange={m => onChange(m ? [...dias, d].sort() : dias.filter(x => x !== d))} />
        ))}
      </span>
    )
  }
  if (operador === 'in' || operador === 'not_in') {
    const lista = (Array.isArray(valor) ? valor : []).map(String)
    const delEnum = opcionesDeCampo(dominio, campo, opciones)
    const ops = campo.tipo === 'enum' ? delEnum.map(o => o.valor)
      : campo.tipo === 'pais' ? CODIGOS_DE_PAIS
      : campo.tipo === 'ciudad' ? opciones?.ciudades ?? []
      : campo.entidad === 'rol' ? opciones?.roles ?? []
      : campo.entidad === 'departamento' ? opciones?.departamentos ?? []
      : campo.entidad === 'equipo' ? opciones?.equipos ?? []
      : opciones?.monedas ?? []
    const libre = !['enum', 'pais'].includes(campo.tipo) && !['rol'].includes(campo.entidad ?? '')
    const mostrar = (v: string) => campo.tipo === 'enum'
      ? (campo.opciones.some(o => o.valor === v) ? etiquetaDeOpcion(dominio, campo, v) : (delEnum.find(o => o.valor === v)?.etiqueta ?? v))
      : campo.tipo === 'pais' ? pais(v) : campo.entidad === 'rol' ? t(`pol.rol_${v}`) : v
    return <ListaDeValores valores={lista} onChange={v => onChange(campo.tipo === 'numero' ? v.map(Number) : v)}
      opciones={ops} etiqueta={etiqueta} libre={libre} mostrar={mostrar} />
  }
  switch (campo.tipo) {
    case 'importe':
      return <EntradaDeImporte valor={valor as Importe | null} onChange={onChange} opciones={opciones} etiqueta={etiqueta} />
    case 'numero':
      return <Input type="number" aria-label={etiqueta} value={(valor as number | null) ?? ''} onChange={e => onChange(e.target.value === '' ? null : Number(e.target.value))} inputClassName="pol-campo pol-campo--corto" />
    case 'hora':
      return <CampoFecha modo="hora" className="pol-campo pol-campo--corto" aria-label={etiqueta} value={(valor as string | null) ?? ''}
        onChange={v => onChange(v || null)} />
    case 'fecha':
    case 'periodo':
      return <DateInput className="pol-campo" aria-label={etiqueta} value={(valor as string | null) ?? ''} onChange={e => onChange(e.target.value)} />
    case 'booleano':
      return (
        <Select suelto className="pol-campo pol-campo--corto" aria-label={etiqueta} value={valor ? 'si' : 'no'} onChange={e => onChange(e.target.value === 'si')} placeholder={false}>
          <option value="si">{t('pol.si')}</option><option value="no">{t('pol.no')}</option>
        </Select>
      )
    case 'enum':
      return (
        <Select suelto className="pol-campo pol-campo--medio" aria-label={etiqueta} value={(valor as string) ?? ''} onChange={e => onChange(e.target.value)} placeholder={t('pol.elige')}>
          {opcionesDeCampo(dominio, campo, opciones).map(o => (
            <option key={o.valor} value={o.valor}>
              {campo.opciones.some(f => f.valor === o.valor) ? etiquetaDeOpcion(dominio, campo, o.valor) : o.etiqueta}
            </option>
          ))}
        </Select>
      )
    case 'pais':
      return <SelectorDePais valor={valor as string} onChange={v => onChange(v)} etiqueta={etiqueta} vacio={false} />
    case 'entidad':
      return <SelectorDeEntidad clase={campo.entidad ?? 'usuario'} valor={valor as string} onChange={onChange} opciones={opciones} etiqueta={etiqueta} />
    case 'ciudad':
    case 'texto':
    default: {
      const lista = campo.tipo === 'ciudad' ? opciones?.ciudades ?? [] : []
      return (
        <>
          <Input aria-label={etiqueta} list={`ciudades-${campo.clave}`} value={(valor as string) ?? ''} onChange={e => onChange(e.target.value)} inputClassName="pol-campo pol-campo--medio" />
          {lista.length > 0 && <datalist id={`ciudades-${campo.clave}`}>{lista.map(c => <option key={c} value={c} />)}</datalist>}
        </>
      )
    }
  }
}

/** Texto legible de un valor (simulador, explicación, historial). */
export function textoDeValor(v: unknown, pais?: (c: string) => string): string {
  if (v === null || v === undefined || v === '') return '—'
  if (Array.isArray(v)) return v.map(x => textoDeValor(x, pais)).join(', ')
  if (typeof v === 'object' && v && 'cantidad' in v) {
    const i = v as Importe
    return `${Number(i.cantidad).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${i.moneda ?? ''}`.trim()
  }
  if (typeof v === 'boolean') return v ? '✓' : '✗'
  if (typeof v === 'string' && pais && /^[A-Z]{2}$/.test(v)) return pais(v)
  return String(v)
}
