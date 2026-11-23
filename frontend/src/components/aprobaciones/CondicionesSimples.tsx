/**
 * Condiciones simples de aprobación, en pantalla (fase 2, rev. 166).
 *
 * El motor (`approval_engine.requests._condiciones_cumplidas`) entiende cuatro
 * claves: `amount_gt` y `amount_lt` (estrictas), `department` y `category`
 * (iguales). Las usan la condición de un paso (`step_condition`) y las reglas
 * de auto-aprobación de un flujo (`auto_approval_rules`). Antes se escribían
 * como JSON a mano (y el ejemplo de las reglas tenía otra forma, que el
 * servidor no entendía); aquí cada clave tiene su control y el JSON lo forma
 * la pantalla.
 *
 * Una condición de rama del diseñador gráfico (`{dominio, arbol}`) no se
 * edita aquí: se avisa y se conserva tal cual.
 */
import { useId } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { settingsApi } from '../../services/settingsApi'
import { Button, Select, Input } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import './aprobaciones.css'

export interface CondicionSimple { amount_gt?: number; amount_lt?: number; department?: string; category?: string }
export interface ReglaDeAutoaprobacion { label?: string; action: 'auto_approve'; conditions: CondicionSimple }

/** Lee un JSON guardado: el objeto, o null si es del diseñador gráfico o ilegible (se conserva). */
export function leerCondicion(raw: string | null | undefined): CondicionSimple | null {
  if (!raw) return {}
  try {
    const v = JSON.parse(raw)
    if (!v || typeof v !== 'object' || Array.isArray(v) || 'arbol' in v) return null
    return v as CondicionSimple
  } catch { /* accesorio: la condición guardada no es JSON; el editor simple no la puede mostrar (se trata como avanzada) */ return null }
}

export function escribirCondicion(c: CondicionSimple): string {
  const limpio = Object.fromEntries(Object.entries(c).filter(([, v]) => v !== undefined && v !== '' && v !== null))
  return Object.keys(limpio).length ? JSON.stringify(limpio) : ''
}

export function leerReglas(raw: string | null | undefined): ReglaDeAutoaprobacion[] {
  if (!raw) return []
  try {
    const v = JSON.parse(raw)
    return Array.isArray(v) ? v.map(r => ({ label: r?.label ?? '', action: 'auto_approve', conditions: r?.conditions ?? {} })) : []
  } catch { /* accesorio: reglas guardadas mal formadas; se parte de cero */ return [] }
}

/** Las reglas, sin claves vacías. Una regla sin condiciones se guarda, pero el motor no aprueba nada con ella. */
export function escribirReglas(reglas: ReglaDeAutoaprobacion[]): string {
  return reglas.length
    ? JSON.stringify(reglas.map(r => ({ ...r, conditions: JSON.parse(escribirCondicion(r.conditions) || '{}') })))
    : ''
}

function useDepartamentos() {
  return useQuery({ queryKey: ['departments-select'], queryFn: () => settingsApi.getDepartments().then(r => r.data) })
}

/** Los cuatro controles de una condición. */
export function EditorDeCondicion({ valor, onChange }: { valor: CondicionSimple; onChange: (c: CondicionSimple) => void }) {
  const t = useAppT()
  const id = useId()
  const depts = useDepartamentos()
  const num = (v: string) => (v === '' ? undefined : Number(v))
  return (
    <div className="apr-condicion">
      <label htmlFor={`${id}-gt`}><span className="apr-etiqueta">{t('aprob.importe_mayor_que')}</span>
        <Input id={`${id}-gt`} type="number" min={0} step="0.01" value={valor.amount_gt ?? ''} onChange={e => onChange({ ...valor, amount_gt: num(e.target.value) })} inputClassName="apr-campo" /></label>
      <label htmlFor={`${id}-lt`}><span className="apr-etiqueta">{t('aprob.importe_menor_que')}</span>
        <Input id={`${id}-lt`} type="number" min={0} step="0.01" value={valor.amount_lt ?? ''} onChange={e => onChange({ ...valor, amount_lt: num(e.target.value) })} inputClassName="apr-campo" /></label>
      <label htmlFor={`${id}-dep`}><span className="apr-etiqueta">{t('aprob.departamento')}</span>
        <Select suelto placeholder={false} id={`${id}-dep`} className="apr-campo" value={valor.department ?? ''}
          onChange={e => onChange({ ...valor, department: e.target.value || undefined })}>
          <option value="">{t('aprob.cualquiera')}</option>
          {(depts.data ?? []).filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
        </Select></label>
      <label htmlFor={`${id}-cat`}><span className="apr-etiqueta">{t('aprob.categoria')}</span>
        <Input id={`${id}-cat`} value={valor.category ?? ''} placeholder={t('aprob.cualquiera')} onChange={e => onChange({ ...valor, category: e.target.value || undefined })} inputClassName="apr-campo" /></label>
    </div>
  )
}

/** Condición de un paso: en pantalla, o el aviso si viene del diseñador gráfico. */
export function CondicionDePaso({ raw, onChange }: { raw: string; onChange: (raw: string) => void }) {
  const t = useAppT()
  const actual = leerCondicion(raw)
  if (actual === null) return <p className="apr-condiciones__ayuda">{t('aprob.condicion_del_disenador')}</p>
  return <EditorDeCondicion valor={actual} onChange={c => onChange(escribirCondicion(c))} />
}

/** Reglas de auto-aprobación de un flujo: lista de condiciones con su etiqueta. */
export function EditorDeReglasDeAutoaprobacion({ raw, onChange }: { raw: string; onChange: (raw: string) => void }) {
  const t = useAppT()
  const id = useId()
  const reglas = leerReglas(raw)
  const guardar = (r: ReglaDeAutoaprobacion[]) => onChange(escribirReglas(r))
  return (
    <div className="apr-reglas">
      {reglas.length === 0 && <p className="apr-condiciones__ayuda">{t('aprob.sin_reglas_auto')}</p>}
      {reglas.map((r, i) => (
        <fieldset key={i} className="ds-grupo-opciones apr-regla">
          <legend className="apr-etiqueta">{t('aprob.regla_n', { n: i + 1 })}</legend>
          <label htmlFor={`${id}-${i}-label`}><span className="apr-etiqueta">{t('aprob.etiqueta_regla')}</span>
            <Input id={`${id}-${i}-label`} value={r.label ?? ''} onChange={e => guardar(reglas.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} inputClassName="apr-campo" /></label>
          <EditorDeCondicion valor={r.conditions} onChange={c => guardar(reglas.map((x, j) => j === i ? { ...x, conditions: c } : x))} />
          <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} title={t('aprob.quitar_regla')}
            onClick={() => guardar(reglas.filter((_, j) => j !== i))}><span className="u-sr-only">{t('aprob.quitar_regla')}</span></Button>
        </fieldset>
      ))}
      <Button size="xs" variant="secondary" icon={<Plus size={12} />}
        onClick={() => guardar([...reglas, { label: '', action: 'auto_approve', conditions: {} }])}>
        {t('aprob.anadir_regla')}
      </Button>
      <p className="apr-condiciones__ayuda">{t('aprob.reglas_auto_ayuda')}</p>
    </div>
  )
}
