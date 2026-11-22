/**
 * Campos del expediente de la definición del flujo de demanda (22-11-2026):
 * clave, etiqueta en tres idiomas, tipo, opciones (con select), crítico
 * (versionado: original del cliente frente a refinado), quién lo rellena,
 * visibilidad para el cliente y campo de políticas. También el mínimo para
 * enviar (`submit_required`) y la ejecución al aprobar (`execution`).
 */
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { Button, Checkbox, GrupoDeOpciones, Input, Select } from '../ui'
import type { CampoDeFlujo, CatalogoDeDemanda, DefinicionDeFlujo, OpcionDeCampo } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import { CamposI18n, opcionesDe } from './comunes'
import { campoNuevo, mover, siguienteClave } from './utilDemanda'
import './demanda.css'

function Opciones({ campo, onChange }: { campo: CampoDeFlujo; onChange: (c: CampoDeFlujo) => void }) {
  const t = useAppT()
  const ops = campo.options || []
  const poner = (i: number, o: OpcionDeCampo) => onChange({ ...campo, options: ops.map((x, j) => j === i ? o : x) })
  return (
    <div className="dem-bloque">
      <div className="dem-bloque__titulo">{t('demanda.cfg_opciones')}</div>
      {ops.map((o, i) => (
        <div key={i} className="dem-rejilla">
          <Input label={t('demanda.cfg_valor')} inputClassName="u-mono dem-mono" value={o.value} onChange={e => poner(i, { ...o, value: e.target.value })} />
          <div className="dem-rejilla__doble"><CamposI18n etiqueta={t('demanda.cfg_etiqueta')} valor={o.label} onChange={l => poner(i, { ...o, label: l })} /></div>
          <div><Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => onChange({ ...campo, options: ops.filter((_, j) => j !== i) })}>{t('demanda.cfg_quitar')}</Button></div>
        </div>
      ))}
      <div><Button size="xs" variant="subtle" icon={<Plus size={12} />} onClick={() => onChange({ ...campo, options: [...ops, { value: '', label: { es: '', en: '', zh: '' } }] })}>{t('demanda.cfg_anadir_opcion')}</Button></div>
    </div>
  )
}

export default function EditorDeCampos({ def, catalogo, onChange }: { def: DefinicionDeFlujo; catalogo: CatalogoDeDemanda; onChange: (d: DefinicionDeFlujo) => void }) {
  const t = useAppT()
  const tipos = catalogo.field_types.length ? catalogo.field_types : ['text', 'textarea', 'number', 'money', 'date', 'select', 'boolean']
  const modos = catalogo.execution_modes.length ? catalogo.execution_modes : ['backlog', 'new_project', 'portfolio']
  const poner = (i: number, c: CampoDeFlujo) => onChange({ ...def, fields: def.fields.map((x, j) => j === i ? c : x) })
  const quitar = (i: number) => {
    const k = def.fields[i].key
    onChange({
      ...def,
      fields: def.fields.filter((_, j) => j !== i),
      submit_required: def.submit_required.filter(x => x !== k),
      phases: def.phases.map(f => ({ ...f, required_fields: (f.required_fields || []).filter(x => x !== k), internal_editable: (f.internal_editable || []).filter(x => x !== k) })),
    })
  }
  return (
    <div className="dem-editor">
      {def.fields.map((c, i) => (
        <div key={i} className="dem-bloque">
          <div className="dem-fila dem-fila--entre">
            <span className="u-mono dem-mono">{c.key || '—'}</span>
            <span className="dem-fila">
              <Button size="xs" variant="ghost" aria-label={t('demanda.cfg_subir')} disabled={i === 0} icon={<ArrowUp size={12} />} onClick={() => onChange({ ...def, fields: mover(def.fields, i, -1) })} />
              <Button size="xs" variant="ghost" aria-label={t('demanda.cfg_bajar')} disabled={i === def.fields.length - 1} icon={<ArrowDown size={12} />} onClick={() => onChange({ ...def, fields: mover(def.fields, i, 1) })} />
              <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => quitar(i)}>{t('demanda.cfg_quitar_campo')}</Button>
            </span>
          </div>
          <div className="dem-rejilla">
            <Input label={t('demanda.cfg_clave')} required inputClassName="u-mono dem-mono" value={c.key} onChange={e => poner(i, { ...c, key: e.target.value })} />
            <Select label={t('demanda.cfg_tipo_campo')} placeholder={false} value={c.type} onChange={e => poner(i, { ...c, type: e.target.value })} options={opcionesDe(t, 'campo_tipo', tipos)} />
            <Select label={t('demanda.cfg_propietario')} placeholder={false} value={c.owner} onChange={e => poner(i, { ...c, owner: e.target.value })} options={opcionesDe(t, 'propietario', ['client', 'internal'])} />
            <Input label={t('demanda.cfg_campo_politicas')} hint={t('demanda.cfg_campo_politicas_ayuda')} inputClassName="u-mono dem-mono" value={c.policy_field ?? ''} onChange={e => poner(i, { ...c, policy_field: e.target.value || null })} />
          </div>
          <CamposI18n etiqueta={t('demanda.cfg_etiqueta')} valor={c.label} requeridoEs onChange={l => poner(i, { ...c, label: l })} />
          {c.type === 'select' && <Opciones campo={c} onChange={n => poner(i, n)} />}
          <div className="dem-rejilla">
            <Checkbox label={t('demanda.cfg_critico')} ayuda={t('demanda.cfg_critico_ayuda')} checked={!!c.critical} onChange={ok => poner(i, { ...c, critical: ok })} />
            <Checkbox label={t('demanda.cfg_visible_cliente')} checked={c.client_visible !== false} onChange={ok => poner(i, { ...c, client_visible: ok })} />
          </div>
        </div>
      ))}
      <div><Button size="sm" variant="subtle" icon={<Plus size={13} />} onClick={() => onChange({ ...def, fields: [...def.fields, campoNuevo(siguienteClave('campo', def.fields.map(f => f.key)))] })}>{t('demanda.cfg_anadir_campo')}</Button></div>
      {def.fields.length > 0 && (
        <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_submit_required')} valor={def.submit_required} onChange={v => onChange({ ...def, submit_required: v })}
          opciones={def.fields.map(c => ({ valor: c.key, titulo: c.label.es || c.key }))} />
      )}
      <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_ejecucion')} valor={def.execution} onChange={v => onChange({ ...def, execution: v })}
        opciones={opcionesDe(t, 'modo', modos).map(o => ({ valor: o.value, titulo: o.label }))} />
    </div>
  )
}
