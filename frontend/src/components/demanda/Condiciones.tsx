/**
 * Editor de condiciones (campo, operador, valor) con «cualquiera/todas» y
 * consulta de políticas: lo usa la fase condicional (22-11-2026).
 */
import { Plus, Trash2 } from 'lucide-react'
import { Button, Checkbox, Input, Select } from '../ui'
import type { CatalogoDeDemanda, CondicionDePuerta, DefinicionDeFlujo } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import { opcionesDe } from './comunes'
import './demanda.css'

export interface ValorDeCondiciones { conditions: CondicionDePuerta[]; match: string; use_policies?: boolean; policy_tag?: string }

const aValor = (s: string): unknown => s.trim() !== '' && !Number.isNaN(Number(s)) ? Number(s) : s === 'true' ? true : s === 'false' ? false : s

export default function EditorDeCondiciones({ valor, onChange, def, catalogo }: {
  valor: ValorDeCondiciones; onChange: (v: ValorDeCondiciones) => void; def: DefinicionDeFlujo; catalogo: CatalogoDeDemanda
}) {
  const t = useAppT()
  const ops = catalogo.condition_ops.length ? catalogo.condition_ops : ['gt', 'gte', 'lt', 'lte', 'eq', 'neq', 'in']
  const campos = def.fields.map(c => ({ value: c.key, label: `${c.label.es || c.key} (${c.key})` }))
  const poner = (i: number, c: CondicionDePuerta) => onChange({ ...valor, conditions: valor.conditions.map((x, j) => j === i ? c : x) })
  return (
    <div className="u-stack-12">
      {valor.conditions.map((c, i) => (
        <div key={i} className="dem-rejilla">
          <Select label={t('demanda.cfg_condicion_campo')} value={c.field} onChange={e => poner(i, { ...c, field: e.target.value })} options={campos} />
          <Select label={t('demanda.cfg_condicion_op')} placeholder={false} value={c.op} onChange={e => poner(i, { ...c, op: e.target.value })} options={opcionesDe(t, 'op', ops)} />
          <Input label={t('demanda.cfg_condicion_valor')} value={c.value === null || c.value === undefined ? '' : String(c.value)} onChange={e => poner(i, { ...c, value: aValor(e.target.value) })} />
          <div><Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => onChange({ ...valor, conditions: valor.conditions.filter((_, j) => j !== i) })}>{t('demanda.cfg_quitar')}</Button></div>
        </div>
      ))}
      <div><Button size="xs" variant="subtle" icon={<Plus size={12} />} onClick={() => onChange({ ...valor, conditions: [...valor.conditions, { field: def.fields[0]?.key ?? '', op: ops[0], value: '' }] })}>{t('demanda.cfg_anadir_condicion')}</Button></div>
      <div className="dem-rejilla">
        <Select label={t('demanda.cfg_match')} placeholder={false} value={valor.match} onChange={e => onChange({ ...valor, match: e.target.value })} options={opcionesDe(t, 'match', ['any', 'all'])} />
        <Input label={t('demanda.cfg_etiqueta_politica')} value={valor.policy_tag ?? ''} onChange={e => onChange({ ...valor, policy_tag: e.target.value || undefined })} />
      </div>
      <Checkbox label={t('demanda.cfg_usar_politicas')} ayuda={t('demanda.cfg_usar_politicas_ayuda')} checked={!!valor.use_policies} onChange={ok => onChange({ ...valor, use_policies: ok })} />
    </div>
  )
}
