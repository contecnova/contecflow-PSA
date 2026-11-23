/**
 * Sección de campos personalizados por entidad.
 * Troceado de SettingsPageSections.tsx sin cambio de comportamiento (23-11-2026).
 */
import React, { useState, type SetStateAction } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { advancedConfigApi } from '../../services/settingsApi'
import { Button, Checkbox, Input, Pulsable, Select, Spinner, EmptyState } from '../../components/ui'
import { Layers, Pencil, Trash2, Check, X, Hash, Puzzle, Type, Calendar, List, CheckSquare, Link2 } from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import SeccionDeAjustes from './SeccionDeAjustes'
import { type CustomField, type CustomFieldEdit, type CustomFieldForm } from './tiposDeAjustes'

export const ENTITY_KEYS: Record<string, string> = {
  project: 'settings_sections.ent_proyecto',
  task: 'settings_sections.ent_tarea',
  user: 'settings_sections.ent_usuario',
  client: 'settings_sections.ent_cliente',
  contract: 'settings_sections.ent_contrato',
  invoice: 'settings_sections.ent_factura',
  absence: 'settings_sections.ent_ausencia',
  document: 'settings_sections.ent_documento',
  risk: 'settings_sections.ent_riesgo',
  deliverable: 'settings_sections.ent_entregable',
  imputation: 'settings_sections.ent_imputacion',
  expense: 'settings_sections.ent_gasto',
  opportunity: 'settings_sections.ent_oportunidad',
  ticket: 'settings_sections.ent_ticket',
  change_request: 'settings_sections.ent_control_cambios',
}

const CUSTOM_FIELD_ENTITIES = ['project', 'task', 'user', 'client', 'contract', 'invoice', 'absence', 'document', 'risk', 'deliverable', 'imputation', 'expense', 'opportunity', 'ticket']

const FIELD_TYPE_KEYS: Record<string, string> = {
  text: 'settings_sections.tipo_texto',
  number: 'settings_sections.tipo_numero',
  date: 'settings_sections.tipo_fecha',
  select: 'settings_sections.tipo_selector',
  boolean: 'settings_sections.tipo_si_no',
  url: 'settings_sections.tipo_url',
}

// ── Custom fields section ─────────────────────────────────────────────────────
export function CustomFieldsSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: fields = [], isLoading } = useQuery<CustomField[]>({ queryKey: ['custom-fields'], queryFn: () => advancedConfigApi.getCustomFields(undefined).then(r => r.data) })
  const { mutate: createField } = useMutation({ mutationFn: advancedConfigApi.createCustomField, onSuccess: () => qc.invalidateQueries({ queryKey: ['custom-fields'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: updateField } = useMutation({ mutationFn: ({ id, data }: { id: string; data: CustomFieldEdit }) => advancedConfigApi.updateCustomField(id, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['custom-fields'] }); setEditingFieldId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: deleteField } = useMutation({ mutationFn: advancedConfigApi.deleteCustomField, onSuccess: () => qc.invalidateQueries({ queryKey: ['custom-fields'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [ui, setUi] = useState<{ editingFieldId: string | null; editFieldForm: CustomFieldEdit; form: CustomFieldForm }>({
    editingFieldId: null,
    editFieldForm: { name: '', is_required: false, placeholder: '' },
    form: { entity: 'project', name: '', field_key: '', field_type: 'text', is_required: false, placeholder: '' },
  })
  const { editingFieldId, editFieldForm, form } = ui
  const setEditingFieldId = (v: SetStateAction<string | null>) => setUi(s => ({ ...s, editingFieldId: typeof v === 'function' ? v(s.editingFieldId) : v }))
  const setEditFieldForm = (v: SetStateAction<CustomFieldEdit>) => setUi(s => ({ ...s, editFieldForm: typeof v === 'function' ? v(s.editFieldForm) : v }))
  const setForm = (v: SetStateAction<CustomFieldForm>) => setUi(s => ({ ...s, form: typeof v === 'function' ? v(s.form) : v }))
  const entityLabel = (e: string) => (ENTITY_KEYS[e] ? t(ENTITY_KEYS[e]) : e)
  const typeLabel = (ty: string) => (FIELD_TYPE_KEYS[ty] ? t(FIELD_TYPE_KEYS[ty]) : ty)
  const TYPE_ICONS: Record<string, React.ReactNode> = { text: <Type size={18} />, number: <Hash size={18} />, date: <Calendar size={18} />, select: <List size={18} />, boolean: <CheckSquare size={18} />, url: <Link2 size={18} /> }
  const byEntity = fields.reduce<Record<string, CustomField[]>>((a, f) => { if (!a[f.entity]) a[f.entity] = []; a[f.entity].push(f); return a }, {})

  return (
    <SeccionDeAjustes icon={<Puzzle size={18} />} title={t('settings.custom_fields')} description={t('settings_sections.campos_desc')}>
      {isLoading ? <Spinner /> : (
        <div className="u-mb-20">
          {Object.entries(byEntity).map(([entity, entityFields]) => (
            <div key={entity} className="u-mb-16">
              <div className="set-group-title">
                {entityLabel(entity)}
              </div>
              <div className="u-stack-6">
                {entityFields.map(f => (
                  <React.Fragment key={f.id}>
                    <div className="set-item set-field-row">
                      <span className="set-icon-lg" aria-hidden="true">{TYPE_ICONS[f.field_type] || <Type size={18} />}</span>
                      <div className="u-flex1">
                        <span className="u-base-600">{f.name}</span>
                        <span className="ds-codigo set-key">{f.field_key}</span>
                        {f.is_required && <span className="set-required">*{t('settings_sections.obligatorio_min')}</span>}
                      </div>
                      <span className="u-text2-xs">{typeLabel(f.field_type)}</span>
                      <Pulsable onClick={() => { setEditingFieldId(f.id); setEditFieldForm({ name: f.name, is_required: f.is_required, placeholder: f.placeholder||'' }) }} className="set-btn-edit" aria-label={t('settings_sections.editar_x', { nombre: f.name })} title={t('common.edit')}><Pencil size={14} aria-hidden /></Pulsable>
                      <Pulsable onClick={() => openConfirmGlobal({ title: t('settings_sections.eliminar_x', { nombre: f.name }), message: t('settings_sections.confirmar_eliminar_x', { nombre: f.name }), danger: true, onConfirm: () => deleteField(f.id) })} className="set-btn-delete" aria-label={t('settings_sections.eliminar_x', { nombre: f.name })} title={t('common.delete')}><Trash2 size={14} aria-hidden /></Pulsable>
                    </div>
                    {editingFieldId === f.id && (
                      <div className="set-edit-strip">
                        <Input value={editFieldForm.name} onChange={e=>setEditFieldForm(f=>({...f,name:e.target.value}))}
                          className="set-input--f2" inputClassName="set-input" placeholder={t('settings.nombre_del_campo')} aria-label={t('settings.nombre_del_campo')} autoFocus />
                        <Input value={editFieldForm.placeholder} onChange={e=>setEditFieldForm(f=>({...f,placeholder:e.target.value}))}
                          className="set-input--f2" inputClassName="set-input" placeholder={t('settings.placeholder_del_campo')} aria-label={t('settings.placeholder_del_campo')} />
                        <Checkbox className="set-check-nowrap" label={t('settings_sections.obligatorio')} checked={editFieldForm.is_required}
                          onChange={m=>setEditFieldForm(f=>({...f,is_required:m}))} />
                        <Pulsable onClick={() => updateField({ id: f.id, data: editFieldForm })} disabled={!editFieldForm.name} className="set-btn-save set-btn-save--sm"><Check size={13} aria-hidden /> {t('common.save')}</Pulsable>
                        <Pulsable onClick={() => setEditingFieldId(null)} className="set-btn-cancel set-btn-cancel--sm" aria-label={t('common.cancel')} title={t('common.cancel')}><X size={14} aria-hidden /></Pulsable>
                      </div>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          ))}
          {fields.length === 0 && <EmptyState svgIcon={<Layers size={36} />} title={t('settings.empty_custom_fields_title')} description={t('settings.empty_custom_fields_desc')} />}
        </div>
      )}
      <div className="set-add-panel-basic">
        <div className="set-add-title">{t('settings.anadir_campo_personalizado')}</div>
        <div className="set-grid-add-field">
          <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('settings_sections.entidad')}</label><Select suelto placeholder={false} id={`${idCampo}-1`} value={form.entity} onChange={e => setForm(f => ({ ...f, entity: e.target.value }))} className="set-input">{CUSTOM_FIELD_ENTITIES.map(e => <option key={e} value={e}>{entityLabel(e)}</option>)}</Select></div>
          <div><label htmlFor={`${idCampo}-c1150`} className="set-label">{t('common.name')}</label><Input aria-label={t('common.name')} id={`${idCampo}-c1150`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value, field_key: e.target.value.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') }))} placeholder={t('settings.nombre_del_campo')} inputClassName="set-input" /></div>
          <div><label htmlFor={`${idCampo}-c1151`} className="set-label">{t('settings_sections.clave')}</label><Input aria-label={t('settings_sections.clave')} id={`${idCampo}-c1151`} value={form.field_key} onChange={e => setForm(f => ({ ...f, field_key: e.target.value }))} placeholder={t('settings_sections.clave_interna')} inputClassName="set-input" /></div>
          <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings_sections.tipo')}</label><Select suelto placeholder={false} id={`${idCampo}-2`} value={form.field_type} onChange={e => setForm(f => ({ ...f, field_type: e.target.value }))} className="set-input">{Object.keys(FIELD_TYPE_KEYS).map(ty => <option key={ty} value={ty}>{typeLabel(ty)}</option>)}</Select></div>
          <Button onClick={() => { createField(form, { onSuccess: () => setForm({ entity: form.entity, name: '', field_key: '', field_type: 'text', is_required: false, placeholder: '' }) }) }} disabled={!form.name || !form.field_key}>{t('settings.anadir')}</Button>
        </div>
      </div>
    </SeccionDeAjustes>
  )
}
