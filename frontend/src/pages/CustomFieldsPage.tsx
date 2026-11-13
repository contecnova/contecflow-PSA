import { useState, useId } from 'react'
import type { CSSProperties} from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, customFieldsApi } from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { SlidersHorizontal } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

interface FieldTypeDef {
  value: string
  label: string
  icon: string
}

interface ProjectItem {
  id: string | number
  name?: string
}

interface CustomField {
  id: string | number
  name: string
  field_key: string
  field_type: string
  options?: string[]
  is_required?: boolean
  show_in_list?: boolean
  sort_order?: number
}

interface FieldFormState {
  name: string
  field_key: string
  field_type: string
  options: string[]
  is_required: boolean
  show_in_list: boolean
  sort_order: number
}

const FIELD_TYPES: FieldTypeDef[] = [
  { value: 'text',    label: 'Texto',            icon: '📝' },
  { value: 'number',  label: 'Número',           icon: '🔢' },
  { value: 'date',    label: 'Fecha',            icon: '📅' },
  { value: 'select',  label: 'Selección',        icon: '📋' },
  { value: 'url',     label: 'URL / Enlace',     icon: '🔗' },
  { value: 'boolean', label: 'Sí / No',          icon: '✅' },
  { value: 'user',    label: 'Usuario',          icon: '👤' },
]

const panelStyle: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 24px' }
const inputStyle: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const labelStyle: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

function FieldForm({ field, projectId, onClose }: { field: CustomField | null; projectId: string; onClose: () => void }) {
  const idCampo = useId()
  const traducir = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!field?.id
  const [form, setForm] = useState<FieldFormState>({
    name:         field?.name         || '',
    field_key:    field?.field_key    || '',
    field_type:   field?.field_type   || 'text',
    options:      field?.options      || [],
    is_required:  field?.is_required  || false,
    show_in_list: field?.show_in_list ?? true,
    sort_order:   field?.sort_order   || 0,
  })
  const [optionInput, setOptionInput] = useState('')

  const { mutate, isPending } = useMutation({
    mutationFn: (d: FieldFormState) => isEdit
      ? customFieldsApi.update(projectId, field.id, d).then(r => r.data)
      : customFieldsApi.create(projectId, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['custom-fields', projectId] }); onClose() },
    onError: (e: unknown) => toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Error al guardar el campo'),
  })

  const set = <K extends keyof FieldFormState>(k: K) => (v: FieldFormState[K]) => setForm(f => ({ ...f, [k]: v }))
  const autoKey = (name: string) => name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '')

  const addOption = () => {
    if (optionInput.trim() && !form.options.includes(optionInput.trim())) {
      set('options')([...form.options, optionInput.trim()])
      setOptionInput('')
    }
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar campo' : 'Nuevo campo personalizado'}>
      <div className="u-stack-14">
        <div>
          <label style={labelStyle}>{traducir('customfields.nombre_del_campo')}</label>
          <input style={inputStyle} value={form.name} onChange={e => {
            const n = e.target.value
            setForm(f => ({ ...f, name: n, field_key: isEdit ? f.field_key : autoKey(n) }))
          }} placeholder={traducir('customfields.nombre_visible_del_campo')} aria-label={traducir('customfields.nombre_visible_del_campo')} />
        </div>

        <div>
          <label id={`${idCampo}-eta106`} htmlFor={`${idCampo}-a106`} style={labelStyle}>Clave (field_key)</label>
          <input id={`${idCampo}-a106`} aria-labelledby={`${idCampo}-eta106`} style={{ ...inputStyle, fontFamily: 'var(--font-mono)', fontSize: "var(--text-sm)" }}
            value={form.field_key}
            onChange={e => set('field_key')(e.target.value.toLowerCase().replace(/\s+/g, '_'))}
            placeholder="clave_del_campo" disabled={isEdit} />
          {isEdit && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 3 }}>{traducir('customfields.la_clave_no_se_puede_cambiar_una')}</div>}
        </div>

        <div>
          <label style={labelStyle}>{traducir('customfields.tipo_de_campo')}</label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
            {FIELD_TYPES.map(t => (
              <button key={t.value} onClick={() => set('field_type')(t.value)}
                style={{ padding: '8px 4px', borderRadius: 8, border: `1px solid ${form.field_type === t.value ? 'var(--accent)' : 'var(--surface-4)'}`, background: form.field_type === t.value ? 'var(--accent-muted)' : 'var(--surface-3)', color: form.field_type === t.value ? 'var(--accent)' : 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: "var(--text-xs)", textAlign: 'center' }}>
                <div style={{ fontSize: "var(--text-lg)", marginBottom: 2 }}>{t.icon}</div>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {form.field_type === 'select' && (
          <div>
            <label style={labelStyle}>{traducir('customfields.opciones_del_selector')}</label>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
              {form.options.map((o) => (
                <span key={o} style={{ background: 'var(--accent-glow)', border: '1px solid var(--accent-border-strong)', borderRadius: 20, padding: '3px 10px', fontSize: "var(--text-sm)", color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  {o}
                  <button onClick={() => set('options')(form.options.filter(x => x !== o))}
                    style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: "var(--text-md)" }}>×</button>
                </span>
              ))}
            </div>
            <div className="u-row-8">
              <input style={{ ...inputStyle, flex: 1 }} value={optionInput}
                onChange={e => setOptionInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addOption()}
                placeholder={traducir('customfields.nueva_opcion')} aria-label={traducir('customfields.nueva_opcion')} />
              <Button onClick={addOption}>+</Button>
            </div>
          </div>
        )}

        <div className="u-grid2-12">
          <label className="u-row-center-8-pointer">
            <input type="checkbox" aria-label="Campo obligatorio" checked={form.is_required} onChange={e => set('is_required')(e.target.checked)} />
            <span>Campo obligatorio</span>
          </label>
          <label className="u-row-center-8-pointer">
            <input type="checkbox" aria-label={traducir('customfields.visible_en_lista_de_tareas')} checked={form.show_in_list} onChange={e => set('show_in_list')(e.target.checked)} />
            <span>{traducir('customfields.visible_en_lista_de_tareas')}</span>
          </label>
        </div>

        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>{traducir('customfields.orden_de_visualizacion')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="number" style={{ ...inputStyle, width: 100 }} value={form.sort_order}
            onChange={e => set('sort_order')(+e.target.value)} />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name || !form.field_key} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Crear campo'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function CustomFieldsPage(): JSX.Element {
  const idCampo = useId()
  const traducir = useAppT()
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState<string>('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<CustomField | null>(null)

  const { data: projectsRaw = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })
  const projects = projectsRaw as ProjectItem[]

  const { data: fieldsRaw = [], isLoading } = useQuery({
    queryKey: ['custom-fields', selectedProject],
    queryFn: () => customFieldsApi.list(selectedProject).then(r => r.data).catch(() => []),
    enabled: !!selectedProject,
  })
  const fields = fieldsRaw as CustomField[]

  const { mutate: deleteField } = useMutation({
    mutationFn: (fid: string | number) => customFieldsApi.delete(selectedProject, fid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['custom-fields', selectedProject] }),
    onError: (e: unknown) => toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Error al eliminar el campo'),
  })

  const selectedProj = projects.find((p) => String(p.id) === selectedProject)

  return (
    <PageShell>
      <PageHeader
        icon={<SlidersHorizontal size={18} />}
        title={_t('custom_fields.title')}
        subtitle={_t('custom_fields.subtitle')}
        actions={selectedProject && (
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>{traducir('customfields.nuevo_campo')}</Button>
        )}
      />

      {/* Selector de proyecto */}
      <div style={{ ...panelStyle, marginBottom: 24 }}>
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>Proyecto</label>
        <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
          style={{ ...inputStyle, width: 360 }}>
          <option value="">{traducir('customfields.selecciona_un_proyecto')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!selectedProject && (
        <EmptyState icon="🗂" title={traducir('customfields.selecciona_un_proyecto_2')} description="Elige un proyecto para gestionar sus campos personalizados" />
      )}

      {selectedProject && isLoading && <Spinner />}

      {selectedProject && !isLoading && fields.length === 0 && (
        <div style={{ ...panelStyle, textAlign: 'center', padding: '48px 24px' }}>
          <div className="u-empty-icon">🗂</div>
          <div style={{ fontSize: "var(--text-md-em)", fontWeight: 600, marginBottom: 8 }}>{traducir('customfields.sin_campos_personalizados')}</div>
          <div className="u-text2-base-mb20">
            {traducir('customfields.crea_campos_propios_para_este_proyecto_severidad')}
          </div>
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Crear primer campo</Button>
        </div>
      )}

      {selectedProject && fields.length > 0 && (
        <div style={panelStyle}>
          <div className="u-row-between-mb16">
            <div className="u-md-600">{fields.length} campos — {selectedProj?.name}</div>
            <div className="u-text2-sm">{traducir('customfields.estos_campos_aparecen_en_todas_las_tareas')}</div>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
            <thead>
              <tr className="u-border-b">
                {['Campo', 'Clave', 'Tipo', 'Obligatorio', 'En lista', 'Acciones'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '8px 12px', fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fields.map((f, i) => {
                const type = FIELD_TYPES.find(t => t.value === f.field_type)
                return (
                  <tr key={f.id} style={{ borderBottom: '1px solid var(--surface-4)', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.03)' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 500 }}>{f.name}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{f.field_key}</td>
                    <td className="u-pad-10-12">
                      <span className="u-row-center-6">
                        <span>{type?.icon}</span>
                        <span className="u-text2">{type?.label}</span>
                        {f.field_type === 'select' && f.options && f.options.length > 0 && (
                          <span className="u-text3-xs">({f.options.length} opciones)</span>
                        )}
                      </span>
                    </td>
                    <td className="u-pad-10-12">
                      <span style={{ fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 'var(--radius-sm)', background: f.is_required ? 'var(--danger-bg)' : 'rgba(255,255,255,0.06)', color: f.is_required ? 'var(--danger)' : 'var(--text-3)' }}>
                        {f.is_required ? 'Obligatorio' : 'Opcional'}
                      </span>
                    </td>
                    <td className="u-pad-10-12">
                      <span style={{ fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 'var(--radius-sm)', background: f.show_in_list ? 'var(--accent-muted)' : 'rgba(255,255,255,0.06)', color: f.show_in_list ? 'var(--accent)' : 'var(--text-3)' }}>
                        {f.show_in_list ? 'Sí' : 'No'}
                      </span>
                    </td>
                    <td className="u-pad-10-12" aria-label="Acciones">
                      <div className="u-row-8">
                        <button onClick={() => { setEditing(f); setShowForm(true) }}
                          style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>
                          Editar
                        </button>
                        <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar el campo "${f.name}"? Los valores guardados se perderán.`, onConfirm: () => deleteField(f.id), danger: true }) }}
                          style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>
                          Eliminar
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {/* Tipos de campo como referencia */}
          <div style={{ marginTop: 20, padding: '14px 16px', background: 'var(--surface-0)', borderRadius: 8, border: '1px solid var(--surface-4)' }}>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>Tipos disponibles</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {FIELD_TYPES.map(t => (
                <div key={t.value} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                  <span>{t.icon}</span><span>{t.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <FieldForm
          field={editing}
          projectId={selectedProject}
          onClose={() => { setShowForm(false); setEditing(null) }}
        />
      )}
    </PageShell>
  )
}
