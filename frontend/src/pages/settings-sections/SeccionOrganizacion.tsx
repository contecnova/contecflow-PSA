/**
 * Secciones de vacaciones, numeración, oficinas, departamentos y áreas.
 * Troceado de SettingsPageSections.tsx sin cambio de comportamiento (23-11-2026).
 */
import React, { useState, type SetStateAction } from 'react'
import { Link } from 'react-router-dom'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi, advancedConfigApi } from '../../services/settingsApi'
import { useAuth } from '../../context/AuthContext'
import { presupuestosApi } from '../../services/api'
import { Button, Checkbox, Input, Pulsable, Select, Spinner, EmptyState } from '../../components/ui'
import { Building2, Pencil, Trash2, Check, X, Palmtree, Hash, Compass } from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import SeccionDeAjustes from './SeccionDeAjustes'
import { RuntimeGroupEditor, CLAVE_MAXIMO_VACACIONES } from './SettingsAdvancedSections'
import { useOrgSettings, usePropuestas } from '../../hooks/useOrgSettings'
import { timezoneOptions } from '../../constants/timezones'
import { type DepartmentForm, type NumberingSeq, type Office, type OfficeForm, type VacationBalance } from './tiposDeAjustes'
import { ENTITY_KEYS } from './SeccionCamposDeEntidad'

// ── Vacaciones: derecho anual por persona ──────────────────────────────────────
/**
 * 18-11-2026 (reorganización de Configuración): solo el derecho anual
 * (`user_vacation_balances.days_entitled`, PATCH /advanced-config/vacation-balances),
 * que es lo que el motor de Ausencias lee como ficha. Se quitan:
 * - las «políticas de vacaciones» (`vacation_policies`): ningún servicio las lee;
 * - las columnas tomados/pendientes/disponibles: el saldo se calculaba aquí con
 *   otra fórmula que en Ausencias (sin arrastre, ajustes ni prorrateo). El saldo
 *   bueno está en Configuración → Ausencias → Personas y saldos.
 */
export function VacationSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  // 19-11-2026: el máximo es el ajuste de la empresa (VACATION_MAX_DAYS_ENTITLED, antes 60 fijo);
  // lo edita aquí quien administra la empresa (la escritura de ajustes es require_admin).
  const maxDias = usePropuestas().vacation_max_days_entitled
  const esAdmin = useAuth().puede('org.administrar')
  const { data: balances = [] } = useQuery<VacationBalance[]>({ queryKey: ['vacation-balances', year], queryFn: () => advancedConfigApi.getVacationBalances(year).then(r => r.data) })
  const { mutate: updateBalance } = useMutation({ mutationFn: ({ userId, days }: { userId: string; days: number }) => advancedConfigApi.updateVacationBalance(userId, year, days), onSuccess: () => { qc.invalidateQueries({ queryKey: ['vacation-balances', year] }); qc.invalidateQueries({ queryKey: ['vacation-balance-my'] }); } , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})

  return (
    <SeccionDeAjustes icon={<Palmtree size={18} />} title={t('settings_sections.vacaciones_titulo')} description={t('ajustes.vacaciones_desc')}>
      <div className="u-row-between u-mb-12">
        <Link to="/settings/ausencias?sub=personas" className="set-enlace">{t('ajustes.ver_saldos')}</Link>
        <Select suelto placeholder={false} value={year} onChange={e => setYear(+e.target.value)} className="set-select-sm" aria-label={t('settings_sections.anio')}>
          {[currentYear - 1, currentYear, currentYear + 1].map(y => <option key={y} value={y}>{y}</option>)}
        </Select>
      </div>
      {esAdmin && (
        <div className="u-mb-12">
          <RuntimeGroupEditor groupId="locale" solo={[CLAVE_MAXIMO_VACACIONES]} />
        </div>
      )}
      <div className="ds-card ds-card--plano">
        <div className="set-bal-row set-bal-row--2 set-bal-head">
          <span>{t('settings_sections.persona')}</span><span>{t('settings_sections.asignados')}</span>
        </div>
        {balances.map(b => (
          <div key={b.user_id} className="set-bal-row set-bal-row--2">
            <div>
              <div className="u-base-600">{b.user_name}</div>
              {b.department && <div className="u-text2-xs">{b.department}</div>}
            </div>
            <Input type="number" aria-label={t('settings_sections.dias_asignados_de', { nombre: b.user_name })} defaultValue={b.days_entitled} min="0" max={maxDias} onBlur={e => updateBalance({ userId: b.user_id, days: +e.target.value })} inputClassName="set-threshold set-threshold--full" />
          </div>
        ))}
      </div>
    </SeccionDeAjustes>
  )
}

// ── Numbering section ─────────────────────────────────────────────────────────
export function NumberingSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: seqs = [], isLoading } = useQuery<NumberingSeq[]>({ queryKey: ['numbering-seqs'], queryFn: () => advancedConfigApi.getNumbering().then(r => r.data) })
  const { mutate: update } = useMutation({ mutationFn: ({ entity, data }: { entity: string; data: NumberingSeq }) => advancedConfigApi.updateNumbering(entity, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['numbering-seqs'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: reset } = useMutation({ mutationFn: advancedConfigApi.resetNumbering, onSuccess: () => qc.invalidateQueries({ queryKey: ['numbering-seqs'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const entityLabel = (e: string) => (ENTITY_KEYS[e] ? t(ENTITY_KEYS[e]) : e)

  return (
    <SeccionDeAjustes icon={<Hash size={18} />} title={t('settings_sections.numeracion_titulo')} description={t('settings_sections.numeracion_desc')}>
      {isLoading ? <Spinner /> : (
        <div className="u-stack-10">
          {seqs.map(s => (
            <div key={s.entity} className="set-item set-seq">
              <div className="set-seq-name">
                <div className="set-seq-title">{entityLabel(s.entity)}</div>
                <div className="set-seq-preview">{s.next_preview}</div>
              </div>
              <div className="set-seq-fields">
                <div><label htmlFor={`${idCampo}-${s.entity}-c1038`} className="set-label set-label--xs">{t('settings_sections.prefijo')}</label><Input aria-label={t('settings_sections.prefijo')} id={`${idCampo}-${s.entity}-c1038`} defaultValue={s.prefix} onBlur={e => update({ entity: s.entity, data: { ...s, prefix: e.target.value } })} placeholder={t('settings_sections.prefijo')} inputClassName="set-input set-input--w70" /></div>
                <div><label id={`${idCampo}-${s.entity}-etc1039`} htmlFor={`${idCampo}-${s.entity}-c1039`} className="set-label set-label--xs" title={t('settings_sections.separador')}>{t('settings_sections.sep')}</label><Input id={`${idCampo}-${s.entity}-c1039`} aria-labelledby={`${idCampo}-${s.entity}-etc1039`} defaultValue={s.separator} onBlur={e => update({ entity: s.entity, data: { ...s, separator: e.target.value } })} inputClassName="set-input set-input--w40" /></div>
                <div><label id={`${idCampo}-${s.entity}-etc1040`} htmlFor={`${idCampo}-${s.entity}-c1040`} className="set-label set-label--xs">{t('settings.digitos')}</label><Input id={`${idCampo}-${s.entity}-c1040`} aria-labelledby={`${idCampo}-${s.entity}-etc1040`} type="number" min="1" max="8" defaultValue={s.padding} onBlur={e => update({ entity: s.entity, data: { ...s, padding: +e.target.value } })} inputClassName="set-input set-input--w60" /></div>
                <Checkbox className="set-check-muted" label={t('settings.incluir_ano')} checked={!!s.include_year} onChange={m => update({ entity: s.entity, data: { ...s, include_year: m } })} />
              </div>
              <div className="set-shrink0">
                <div className="u-text2-xs-mb4">{t('settings_sections.contador', { valor: s.current_value })}</div>
                <Pulsable onClick={() => { openConfirmGlobal({ message: t('settings_sections.confirmar_resetear', { entidad: entityLabel(s.entity) }), onConfirm: () => reset(s.entity), danger: true }) }} className="set-btn-delete set-btn-delete--md">{t('settings_sections.resetear')}</Pulsable>
              </div>
            </div>
          ))}
        </div>
      )}
    </SeccionDeAjustes>
  )
}

// ── Offices section ───────────────────────────────────────────────────────────
export function OfficesSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { timezone: defaultTimezone } = useOrgSettings()
  const { data: offices = [] } = useQuery<Office[]>({ queryKey: ['offices'], queryFn: () => advancedConfigApi.getOffices().then(r => r.data) })
  const { mutate: create } = useMutation({ mutationFn: advancedConfigApi.createOffice, onSuccess: () => qc.invalidateQueries({ queryKey: ['offices'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: update } = useMutation({ mutationFn: ({ id, data }: { id: string; data: OfficeForm }) => advancedConfigApi.updateOffice(id, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['offices'] }); setEditingId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: del } = useMutation({ mutationFn: advancedConfigApi.deleteOffice, onSuccess: () => qc.invalidateQueries({ queryKey: ['offices'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [ui, setUi] = useState<{ form: OfficeForm; editingId: string | null; editForm: OfficeForm }>({
    form: { name: '', country: '', city: '', timezone: defaultTimezone },
    editingId: null,
    editForm: { name: '', country: '', city: '', timezone: defaultTimezone },
  })
  const { form, editingId, editForm } = ui
  const setForm = (v: SetStateAction<OfficeForm>) => setUi(s => ({ ...s, form: typeof v === 'function' ? v(s.form) : v }))
  const setEditingId = (v: SetStateAction<string | null>) => setUi(s => ({ ...s, editingId: typeof v === 'function' ? v(s.editingId) : v }))
  const setEditForm = (v: SetStateAction<OfficeForm>) => setUi(s => ({ ...s, editForm: typeof v === 'function' ? v(s.editForm) : v }))

  return (
    <SeccionDeAjustes icon={<Building2 size={18} />} title={t('settings_sections.sedes_titulo')} description={t('settings_sections.sedes_desc')}>
      <div className="set-stack-mb16">
        {offices.map(o => (
          <div key={o.id}>
            {editingId === o.id ? (
              <div className="set-edit-panel">
                <div className="set-fld-name"><label id={`${idCampo}-${o.id}-etc1457`} htmlFor={`${idCampo}-${o.id}-c1457`} className="set-label">{t('common.name')} *</label>
                  <Input id={`${idCampo}-${o.id}-c1457`} aria-labelledby={`${idCampo}-${o.id}-etc1457`} value={editForm.name} onChange={e => setEditForm(f=>({...f,name:e.target.value}))} autoFocus inputClassName="set-input" /></div>
                <div className="set-fld-sm"><label id={`${idCampo}-${o.id}-etc1459`} htmlFor={`${idCampo}-${o.id}-c1459`} className="set-label">{t('settings.pais')}</label>
                  <Input id={`${idCampo}-${o.id}-c1459`} aria-labelledby={`${idCampo}-${o.id}-etc1459`} value={editForm.country} onChange={e => setEditForm(f=>({...f,country:e.target.value}))} inputClassName="set-input" /></div>
                <div className="set-fld-sm"><label id={`${idCampo}-${o.id}-etc1461`} htmlFor={`${idCampo}-${o.id}-c1461`} className="set-label">{t('settings_sections.ciudad')}</label>
                  <Input id={`${idCampo}-${o.id}-c1461`} aria-labelledby={`${idCampo}-${o.id}-etc1461`} value={editForm.city} onChange={e => setEditForm(f=>({...f,city:e.target.value}))} inputClassName="set-input" /></div>
                <div className="set-fld-tz"><label id={`${idCampo}-${o.id}-etc1463`} htmlFor={`${idCampo}-${o.id}-c1463`} className="set-label">{t('settings.timezone')}</label>
                  <Select suelto placeholder={false} id={`${idCampo}-${o.id}-c1463`} value={editForm.timezone} onChange={e => setEditForm(f=>({...f,timezone:e.target.value}))} className="set-input">
                    {timezoneOptions(editForm.timezone).map(tz => <option key={tz} value={tz}>{tz}</option>)}
                  </Select></div>
                <div className="set-actions-inline">
                  <Pulsable onClick={() => update({ id: o.id, data: editForm })} disabled={!editForm.name} className="set-btn-save"><Check size={13} aria-hidden /> {t('common.save')}</Pulsable>
                  <Pulsable onClick={() => setEditingId(null)} className="set-btn-cancel">{t('common.cancel')}</Pulsable>
                </div>
              </div>
            ) : (
              <div className="set-item">
                <span className="set-icon-xl" aria-hidden="true"><Building2 size={22} /></span>
                <div className="u-flex1">
                  <div className="u-base-700">{o.name}</div>
                  <div className="u-text2-xs">{o.city}{o.country ? `, ${o.country}` : ''} · {o.timezone}</div>
                </div>
                <Pulsable onClick={() => { setEditingId(o.id); setEditForm({ name:o.name, country:o.country||'', city:o.city||'', timezone:o.timezone||defaultTimezone }) }} className="set-btn-edit" aria-label={t('settings_sections.editar_x', { nombre: o.name })} title={t('common.edit')}><Pencil size={14} aria-hidden /></Pulsable>
                <Pulsable onClick={() => openConfirmGlobal({ title: t('settings_sections.eliminar_x', { nombre: o.name }), message: t('settings_sections.confirmar_eliminar_x', { nombre: o.name }), danger: true, onConfirm: () => del(o.id) })} className="set-btn-delete" aria-label={t('settings_sections.eliminar_x', { nombre: o.name })} title={t('common.delete')}><Trash2 size={14} aria-hidden /></Pulsable>
              </div>
            )}
          </div>
        ))}
        {offices.length === 0 && <EmptyState svgIcon={<Building2 size={36} />} title={t('settings.sin_sedes_registradas')} description={t('settings_sections.sedes_vacio_desc')} />}
      </div>
      <div className="set-add-panel">
        <div className="set-flex2"><label htmlFor={`${idCampo}-c1491`} className="set-label">{t('common.name')} *</label><Input aria-label={t('common.name')} id={`${idCampo}-c1491`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder={t('settings.nombre_de_la_sede')} inputClassName="set-input" /></div>
        <div className="u-flex1"><label htmlFor={`${idCampo}-pais`} className="set-label">{t('settings.pais')}</label><Input aria-label={t('settings.pais')} id={`${idCampo}-pais`} value={form.country} onChange={e => setForm(f => ({ ...f, country: e.target.value }))} placeholder={t('settings.pais')} inputClassName="set-input" /></div>
        <div className="u-flex1"><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('settings_sections.ciudad')}</label><Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.city} onChange={e => setForm(f => ({ ...f, city: e.target.value }))} inputClassName="set-input" /></div>
        <div className="u-flex1"><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings.timezone')}</label><Select suelto placeholder={false} id={`${idCampo}-2`} value={form.timezone} onChange={e => setForm(f => ({ ...f, timezone: e.target.value }))} className="set-input">{timezoneOptions(form.timezone).map(tz => <option key={tz} value={tz}>{tz}</option>)}</Select></div>
        <Button onClick={() => { create(form, { onSuccess: () => setForm({ name: '', country: '', city: '', timezone: defaultTimezone }) }) }} disabled={!form.name}>{t('settings.anadir')}</Button>
      </div>
    </SeccionDeAjustes>
  )
}

// ── Departments & Holidays (existing) ─────────────────────────────────────────
export function DepartmentsSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data = [], isLoading } = useQuery({ queryKey: ['departments'], queryFn: () => settingsApi.getDepartments().then(r => r.data) })
  // Revisión 2026-11: un departamento pertenece a un área (base del presupuesto del área).
  const { data: areas = [] } = useQuery({ queryKey: ['areas'], queryFn: () => presupuestosApi.areas() })
  const nombreDeArea = (id?: string | null) => areas.find(a => a.id === id)?.name
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['departments'] }); qc.invalidateQueries({ queryKey: ['areas'] }) }
  const { mutate: create } = useMutation({ mutationFn: settingsApi.createDepartment, onSuccess: refrescar, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: update } = useMutation({ mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) => settingsApi.updateDepartment(id, data), onSuccess: () => { refrescar(); setEditingId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: del } = useMutation({ mutationFn: settingsApi.deleteDepartment, onSuccess: refrescar, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [ui, setUi] = useState<{ form: DepartmentForm; editingId: string | null; editForm: DepartmentForm }>({
    form: { name: '', description: '', area_id: '' },
    editingId: null,
    editForm: { name: '', description: '', area_id: '' },
  })
  const { form, editingId, editForm } = ui
  const setForm = (v: SetStateAction<DepartmentForm>) => setUi(s => ({ ...s, form: typeof v === 'function' ? v(s.form) : v }))
  const setEditingId = (v: SetStateAction<string | null>) => setUi(s => ({ ...s, editingId: typeof v === 'function' ? v(s.editingId) : v }))
  const setEditForm = (v: SetStateAction<DepartmentForm>) => setUi(s => ({ ...s, editForm: typeof v === 'function' ? v(s.editForm) : v }))
  const selectorDeArea = (valor: string, onChange: (v: string) => void) => (
    <Select suelto placeholder={t('settings.sin_area')} value={valor} onChange={e => onChange(e.target.value)} aria-label={t('settings.area_del_departamento')} className="set-input set-input--f2 set-input--compact">
      {areas.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
    </Select>
  )
  return (
    <>
    <AreasSection />
    <SeccionDeAjustes icon={<Building2 size={18} />} title={t('settings.departments')} description={t('settings_sections.departamentos_desc')}>
      {isLoading ? <Spinner /> : (
        <div className="set-stack-mb12">
          {data.map(d => (
            <div key={d.id}>
              {editingId === d.id ? (
                <div className="set-edit-panel set-edit-panel--center">
                  <Input value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                    className="set-input--f2" inputClassName="set-input set-input--compact" placeholder={t('settings.nombre_del_departamento')} aria-label={t('settings.nombre_del_departamento')} autoFocus />
                  <Input value={editForm.description} onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                    className="set-input--f3" inputClassName="set-input set-input--compact" placeholder={t('common.description')} aria-label={t('settings.descripcion_del_departamento')} />
                  {selectorDeArea(editForm.area_id, v => setEditForm(f => ({ ...f, area_id: v })))}
                  <Pulsable onClick={() => update({ id: d.id, data: { ...editForm, area_id: editForm.area_id || null } })} disabled={!editForm.name} className="set-btn-save set-btn-confirm-light" aria-label={t('common.save')} title={t('common.save')}><Check size={14} aria-hidden /></Pulsable>
                  <Pulsable onClick={() => setEditingId(null)} className="set-btn-cancel set-btn-cancel--sm" aria-label={t('common.cancel')} title={t('common.cancel')}><X size={14} aria-hidden /></Pulsable>
                </div>
              ) : (
                <div className="set-item set-item--wrap">
                  <span className="set-dept-name">{d.name}</span>
                  {nombreDeArea(d.area_id) && <span className="set-area-tag">{nombreDeArea(d.area_id)}</span>}
                  {d.description && <span className="u-text2-sm">{d.description}</span>}
                  <Pulsable onClick={() => { setEditingId(d.id); setEditForm({ name: d.name, description: d.description || '', area_id: d.area_id || '' }) }} className="set-btn-edit" aria-label={t('settings_sections.editar_x', { nombre: d.name })} title={t('common.edit')}><Pencil size={14} aria-hidden /></Pulsable>
                  <Pulsable onClick={() => openConfirmGlobal({ title: t('settings_sections.eliminar_x', { nombre: d.name }), message: t('settings_sections.confirmar_eliminar_x', { nombre: d.name }), danger: true, onConfirm: () => del(d.id) })} className="set-btn-delete" aria-label={t('settings_sections.eliminar_x', { nombre: d.name })} title={t('common.delete')}><Trash2 size={14} aria-hidden /></Pulsable>
                </div>
              )}
            </div>
          ))}
          {data.length === 0 && <div className="set-empty-base">{t('settings.sin_departamentos')}</div>}
        </div>
      )}
      <div className="set-add-inline">
        <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="set-input--f2" inputClassName="set-input" placeholder={t('settings.nombre_del_departamento')} aria-label={t('settings.nombre_del_departamento')} />
        <Input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} className="set-input--f2" inputClassName="set-input" placeholder={t('common.description')} aria-label={t('settings.descripcion_del_departamento')} />
        {selectorDeArea(form.area_id, v => setForm(f => ({ ...f, area_id: v })))}
        <Button onClick={() => { create({ ...form, area_id: form.area_id || null }, { onSuccess: () => setForm({ name: '', description: '', area_id: '' }) }) }} disabled={!form.name}>{t('settings.anadir')}</Button>
      </div>
    </SeccionDeAjustes>
    </>
  )
}

function AreasSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: areas = [], isLoading } = useQuery({ queryKey: ['areas'], queryFn: () => presupuestosApi.areas() })
  const [nombre, setNombre] = useState('')
  const [editando, setEditando] = useState<{ id: string; name: string } | null>(null)
  // 23-11-2026 (04b B5): devuelve si fue bien; el formulario solo se limpia/cierra con éxito.
  const ejecutar = async (f: () => Promise<unknown>): Promise<boolean> => {
    try { await f(); qc.invalidateQueries({ queryKey: ['areas'] }); qc.invalidateQueries({ queryKey: ['departments'] }); return true }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)); return false }
  }
  return (
    <SeccionDeAjustes icon={<Compass size={18} />} title={t('settings.areas')} description={t('settings.areas_ayuda')}>
      {isLoading ? <Spinner /> : (
        <div className="set-stack-mb12">
          {areas.map(a => (
            <div key={a.id} className="set-item set-item--wrap">
              {editando?.id === a.id ? (
                <>
                  <Input value={editando.name} onChange={e => setEditando({ id: a.id, name: e.target.value })} aria-label={t('settings.nombre_del_area')} className="set-input--f2" inputClassName="set-input set-input--compact" autoFocus />
                  <Pulsable onClick={() => ejecutar(() => presupuestosApi.guardarArea({ name: editando.name }, a.id)).then(ok => { if (ok) setEditando(null) })} disabled={!editando.name.trim()} className="set-btn-save set-btn-confirm-light" aria-label={t('common.save')} title={t('common.save')}><Check size={14} aria-hidden /></Pulsable>
                  <Pulsable onClick={() => setEditando(null)} className="set-btn-cancel set-btn-cancel--sm" aria-label={t('common.cancel')} title={t('common.cancel')}><X size={14} aria-hidden /></Pulsable>
                </>
              ) : (
                <>
                  <span className="u-base-600">{a.name}</span>
                  <span className="set-area-depts">{a.departamentos.length ? a.departamentos.join(', ') : t('settings.area_sin_departamentos')}</span>
                  <Pulsable onClick={() => setEditando({ id: a.id, name: a.name })} className="set-btn-edit" aria-label={t('settings_sections.editar_x', { nombre: a.name })} title={t('common.edit')}><Pencil size={14} aria-hidden /></Pulsable>
                  <Pulsable onClick={() => openConfirmGlobal({ title: t('settings_sections.eliminar_x', { nombre: a.name }), message: t('settings_sections.confirmar_eliminar_x', { nombre: a.name }), danger: true, onConfirm: () => { void ejecutar(() => presupuestosApi.borrarArea(a.id)) } })} className="set-btn-delete" aria-label={t('settings_sections.eliminar_x', { nombre: a.name })} title={t('common.delete')}><Trash2 size={14} aria-hidden /></Pulsable>
                </>
              )}
            </div>
          ))}
          {areas.length === 0 && <div className="set-empty-base">{t('settings.sin_areas')}</div>}
        </div>
      )}
      <div className="set-add-inline">
        <Input value={nombre} onChange={e => setNombre(e.target.value)} className="set-input--f2" inputClassName="set-input" placeholder={t('settings.nombre_del_area')} aria-label={t('settings.nombre_del_area')} />
        <Button onClick={() => ejecutar(() => presupuestosApi.guardarArea({ name: nombre })).then(ok => { if (ok) setNombre('') })} disabled={!nombre.trim()}>{t('settings.anadir')}</Button>
      </div>
    </SeccionDeAjustes>
  )
}
