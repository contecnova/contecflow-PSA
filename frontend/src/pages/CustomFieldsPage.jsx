import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const FIELD_TYPES = [
  { value: 'text',    label: 'Texto',            icon: '📝' },
  { value: 'number',  label: 'Número',           icon: '🔢' },
  { value: 'date',    label: 'Fecha',            icon: '📅' },
  { value: 'select',  label: 'Selección',        icon: '📋' },
  { value: 'url',     label: 'URL / Enlace',     icon: '🔗' },
  { value: 'boolean', label: 'Sí / No',          icon: '✅' },
  { value: 'user',    label: 'Usuario',          icon: '👤' },
]

const panelStyle = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, padding: '20px 24px' }
const inputStyle = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const labelStyle = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

function FieldForm({ field, projectId, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!field?.id
  const [form, setForm] = useState({
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
    mutationFn: d => isEdit
      ? api.patch(`/custom-fields/${projectId}/${field.id}`, d).then(r => r.data)
      : api.post(`/custom-fields/${projectId}`, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['custom-fields', projectId]); onClose() },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al guardar el campo'),
  })

  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const autoKey = name => name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '')

  const addOption = () => {
    if (optionInput.trim() && !form.options.includes(optionInput.trim())) {
      set('options')([...form.options, optionInput.trim()])
      setOptionInput('')
    }
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar campo' : 'Nuevo campo personalizado'}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={labelStyle}>Nombre del campo</label>
          <input style={inputStyle} value={form.name} onChange={e => {
            const n = e.target.value
            setForm(f => ({ ...f, name: n, field_key: isEdit ? f.field_key : autoKey(n) }))
          }} placeholder="Ej: Severidad, Cliente final, Sprint objetivo" />
        </div>

        <div>
          <label style={labelStyle}>Clave (field_key)</label>
          <input style={{ ...inputStyle, fontFamily: 'monospace', fontSize: 12 }}
            value={form.field_key}
            onChange={e => set('field_key')(e.target.value.toLowerCase().replace(/\s+/g, '_'))}
            placeholder="severidad" disabled={isEdit} />
          {isEdit && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3 }}>La clave no se puede cambiar una vez creado</div>}
        </div>

        <div>
          <label style={labelStyle}>Tipo de campo</label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
            {FIELD_TYPES.map(t => (
              <button key={t.value} onClick={() => set('field_type')(t.value)}
                style={{ padding: '8px 4px', borderRadius: 8, border: `1px solid ${form.field_type === t.value ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: form.field_type === t.value ? 'var(--accent-muted)' : 'var(--surface-3)', color: form.field_type === t.value ? 'var(--accent)' : 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11, textAlign: 'center' }}>
                <div style={{ fontSize: 16, marginBottom: 2 }}>{t.icon}</div>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {form.field_type === 'select' && (
          <div>
            <label style={labelStyle}>Opciones del selector</label>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
              {form.options.map(o => (
                <span key={o} style={{ background: 'var(--accent-glow)', border: '1px solid #00d4ff40', borderRadius: 20, padding: '3px 10px', fontSize: 12, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  {o}
                  <button onClick={() => set('options')(form.options.filter(x => x !== o))}
                    style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: 14 }}>×</button>
                </span>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input style={{ ...inputStyle, flex: 1 }} value={optionInput}
                onChange={e => setOptionInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addOption()}
                placeholder="Escribe una opción y pulsa Enter" />
              <Button onClick={addOption}>+</Button>
            </div>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
            <input type="checkbox" checked={form.is_required} onChange={e => set('is_required')(e.target.checked)} />
            <span>Campo obligatorio</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
            <input type="checkbox" checked={form.show_in_list} onChange={e => set('show_in_list')(e.target.checked)} />
            <span>Visible en lista de tareas</span>
          </label>
        </div>

        <div>
          <label style={labelStyle}>Orden de visualización</label>
          <input type="number" style={{ ...inputStyle, width: 100 }} value={form.sort_order}
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

export default function CustomFieldsPage() {
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.get('/projects').then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })

  const { data: fields = [], isLoading } = useQuery({
    queryKey: ['custom-fields', selectedProject],
    queryFn: () => api.get(`/custom-fields/${selectedProject}`).then(r => r.data).catch(() => []),
    enabled: !!selectedProject,
  })

  const { mutate: deleteField } = useMutation({
    mutationFn: fid => api.delete(`/custom-fields/${selectedProject}/${fid}`),
    onSuccess: () => qc.invalidateQueries(['custom-fields', selectedProject]),
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al eliminar el campo'),
  })

  const selectedProj = projects.find(p => p.id === selectedProject)

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        title="Campos personalizados"
        subtitle={t('custom_fields.subtitle')}
        actions={selectedProject && (
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Nuevo campo</Button>
        )}
      />

      {/* Selector de proyecto */}
      <div style={{ ...panelStyle, marginBottom: 24 }}>
        <label style={labelStyle}>Proyecto</label>
        <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
          style={{ ...inputStyle, width: 360 }}>
          <option value="">Selecciona un proyecto...</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!selectedProject && (
        <EmptyState icon="🗂" title="Selecciona un proyecto" description="Los campos personalizados se configuran por proyecto" />
      )}

      {selectedProject && isLoading && <Spinner />}

      {selectedProject && !isLoading && fields.length === 0 && (
        <div style={{ ...panelStyle, textAlign: 'center', padding: '48px 24px' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🗂</div>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Sin campos personalizados</div>
          <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 20 }}>
            Crea campos propios para este proyecto: severidad, cliente, sprint objetivo, URL de diseño, etc.
          </div>
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Crear primer campo</Button>
        </div>
      )}

      {selectedProject && fields.length > 0 && (
        <div style={panelStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>{fields.length} campos — {selectedProj?.name}</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>Estos campos aparecen en todas las tareas de este proyecto</div>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #1e2d45' }}>
                {['Campo', 'Clave', 'Tipo', 'Obligatorio', 'En lista', 'Acciones'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '8px 12px', fontSize: 11, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fields.map((f, i) => {
                const type = FIELD_TYPES.find(t => t.value === f.field_type)
                return (
                  <tr key={f.id} style={{ borderBottom: '1px solid #1e2d45', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.03)' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 500 }}>{f.name}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 11, color: 'var(--text-2)' }}>{f.field_key}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span>{type?.icon}</span>
                        <span style={{ color: 'var(--text-2)' }}>{type?.label}</span>
                        {f.field_type === 'select' && f.options?.length > 0 && (
                          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>({f.options.length} opciones)</span>
                        )}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, background: f.is_required ? 'var(--danger-bg)' : 'rgba(255,255,255,0.06)', color: f.is_required ? 'var(--danger)' : 'var(--text-3)' }}>
                        {f.is_required ? 'Obligatorio' : 'Opcional'}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, background: f.show_in_list ? 'var(--accent-muted)' : 'rgba(255,255,255,0.06)', color: f.show_in_list ? 'var(--accent)' : 'var(--text-3)' }}>
                        {f.show_in_list ? 'Sí' : 'No'}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button onClick={() => { setEditing(f); setShowForm(true) }}
                          style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>
                          Editar
                        </button>
                        <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar el campo "${f.name}"? Los valores guardados se perderán.`, onConfirm: () => deleteField(f.id), danger: true }) }}
                          style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>
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
          <div style={{ marginTop: 20, padding: '14px 16px', background: 'var(--surface-0)', borderRadius: 8, border: '1px solid #1a2640' }}>
            <div style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>Tipos disponibles</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {FIELD_TYPES.map(t => (
                <div key={t.value} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-2)' }}>
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
    </div>
  )
}
