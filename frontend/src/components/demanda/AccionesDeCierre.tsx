/**
 * Acciones al cerrar el expediente (`on_close_actions`, 22-11-2026): crear
 * proyecto, petición de cambio, propuesta de cartera, tarea, ticket, cambio
 * ITSM, petición de compra (cola de compras de ALM) o Executive Summary. Cada acción dice cuándo se dispara (aprobada, rechazada, siempre).
 */
import { Plus, Trash2 } from 'lucide-react'
import { Button, Input, Select } from '../ui'
import type { AccionDeCierre, CatalogoDeDemanda, DefinicionDeFlujo, PlantillaDeResumen } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaDe, opcionesDe } from './comunes'
import EditorDePlantillaResumen from './PlantillaResumen'
import './demanda.css'

const POR_DEFECTO = ['create_project', 'create_change_request', 'create_portfolio_proposal', 'create_task', 'create_ticket', 'create_itsm_change', 'executive_summary', 'create_purchase']

export default function AccionesDeCierre({ def, catalogo, onChange }: { def: DefinicionDeFlujo; catalogo: CatalogoDeDemanda; onChange: (d: DefinicionDeFlujo) => void }) {
  const t = useAppT()
  const acciones = def.on_close_actions || []
  const tipos = catalogo.close_actions?.length ? catalogo.close_actions : POR_DEFECTO
  const poner = (i: number, a: AccionDeCierre) => onChange({ ...def, on_close_actions: acciones.map((x, j) => j === i ? a : x) })
  const params = (a: AccionDeCierre) => a.params || {}
  const ponerParam = (i: number, a: AccionDeCierre, k: string, v: unknown) => poner(i, { ...a, params: { ...params(a), [k]: v } })
  return (
    <div className="dem-editor">
      <p className="plan-muted">{t('demanda.cfg_cierre_ayuda')}</p>
      {acciones.map((a, i) => (
        <div key={i} className="dem-bloque">
          <div className="dem-rejilla">
            <Select label={t('demanda.cfg_accion')} placeholder={false} value={a.action} onChange={e => poner(i, { ...a, action: e.target.value, params: {} })}
              options={tipos.map(x => ({ value: x, label: etiquetaDe(t, 'accion', x) }))} />
            <Select label={t('demanda.cfg_cuando')} placeholder={false} value={a.when} onChange={e => poner(i, { ...a, when: e.target.value })} options={opcionesDe(t, 'cuando', ['approved', 'rejected', 'any'])} />
            <div><Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => onChange({ ...def, on_close_actions: acciones.filter((_, j) => j !== i) })}>{t('demanda.cfg_quitar')}</Button></div>
          </div>
          {(a.action === 'create_task' || a.action === 'create_ticket' || a.action === 'create_purchase') && (
            <div className="dem-rejilla">
              <Input label={t('demanda.cfg_param_titulo')} value={String(params(a).title ?? '')} onChange={e => ponerParam(i, a, 'title', e.target.value)} />
              {a.action === 'create_task' && <Input label={t('demanda.cfg_param_proyecto')} inputClassName="u-mono dem-mono" value={String(params(a).project_id ?? '')} onChange={e => ponerParam(i, a, 'project_id', e.target.value || undefined)} />}
              {a.action === 'create_task' && <Select label={t('demanda.cfg_param_asignado')} value={String(params(a).assignee_id ?? '')} onChange={e => ponerParam(i, a, 'assignee_id', e.target.value || undefined)} options={catalogo.users} />}
              {a.action === 'create_ticket' && <Input label={t('demanda.cfg_param_tipo_ticket')} value={String(params(a).ticket_type ?? '')} onChange={e => ponerParam(i, a, 'ticket_type', e.target.value)} />}
            </div>
          )}
          {a.action === 'executive_summary' && (
            <EditorDePlantillaResumen def={def} valor={params(a) as PlantillaDeResumen} onChange={v => poner(i, { ...a, params: v as Record<string, unknown> })} />
          )}
        </div>
      ))}
      <div><Button size="sm" variant="subtle" icon={<Plus size={13} />} onClick={() => onChange({ ...def, on_close_actions: [...acciones, { action: tipos[0], when: 'approved', params: {} }] })}>{t('demanda.cfg_anadir_accion')}</Button></div>
    </div>
  )
}
