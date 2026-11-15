import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, customFieldsApi } from '../services/api'
import type { CampoPersonalizado } from '../services/api/tipos-rendimiento'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { SlidersHorizontal } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { extractErr, fmtNumber } from '../utils/helpers'
import './CustomFieldsPage.css'

interface FieldTypeDef {
  value: string
  icon: string
}

interface ProjectItem {
  id: string | number
  name?: string
}

type CustomField = CampoPersonalizado

interface FieldFormState {
  name: string
  field_key: string
  field_type: string
  options: string[]
  is_required: boolean
  show_in_list: boolean
  sort_order: number
}

/** Tipos de campo; la etiqueta es `customfields.tipo_<value>`. */
const FIELD_TYPES: FieldTypeDef[] = [
  { value: 'text',    icon: '📝' },
  { value: 'number',  icon: '🔢' },
  { value: 'date',    icon: '📅' },
  { value: 'select',  icon: '📋' },
  { value: 'url',     icon: '🔗' },
  { value: 'boolean', icon: '✅' },
  { value: 'user',    icon: '👤' },
]

const COLUMNAS = ['col_campo', 'col_clave', 'col_tipo', 'col_obligatorio', 'col_en_lista', 'col_acciones'] as const

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
    onError: (e: unknown) => toast.error(extractErr(e, traducir('customfields.error_guardar'))),
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
    <Modal open onClose={onClose} title={isEdit ? traducir('customfields.editar_campo') : traducir('customfields.nuevo_campo_personalizado')}>
      <div className="u-stack-14">
        <div>
          <label id={`${idCampo}-et-nombre`} htmlFor={`${idCampo}-nombre`} className="cfl-label">{traducir('customfields.nombre_del_campo')}</label>
          <input id={`${idCampo}-nombre`} aria-labelledby={`${idCampo}-et-nombre`} className="cfl-input" value={form.name} onChange={e => {
            const n = e.target.value
            setForm(f => ({ ...f, name: n, field_key: isEdit ? f.field_key : autoKey(n) }))
          }} placeholder={traducir('customfields.nombre_visible_del_campo')} />
        </div>

        <div>
          <label id={`${idCampo}-et-clave`} htmlFor={`${idCampo}-clave`} className="cfl-label">{traducir('customfields.clave_field_key')}</label>
          <input id={`${idCampo}-clave`} aria-labelledby={`${idCampo}-et-clave`} className="cfl-input cfl-input--mono"
            value={form.field_key}
            onChange={e => set('field_key')(e.target.value.toLowerCase().replace(/\s+/g, '_'))}
            placeholder={traducir('customfields.clave_placeholder')} disabled={isEdit}
            aria-describedby={isEdit ? `${idCampo}-clave-ayuda` : undefined} />
          {isEdit && <div id={`${idCampo}-clave-ayuda`} className="cfl-hint">{traducir('customfields.la_clave_no_se_puede_cambiar_una')}</div>}
        </div>

        <div>
          <div id={`${idCampo}-tipo`} className="cfl-label">{traducir('customfields.tipo_de_campo')}</div>
          <div className="cfl-types" role="radiogroup" aria-labelledby={`${idCampo}-tipo`}>
            {FIELD_TYPES.map(ft => (
              <button key={ft.value} type="button" role="radio" aria-checked={form.field_type === ft.value}
                className="cfl-type" onClick={() => set('field_type')(ft.value)}>
                <span className="cfl-type__icon" aria-hidden="true">{ft.icon}</span>
                {traducir(`customfields.tipo_${ft.value}`)}
              </button>
            ))}
          </div>
        </div>

        {form.field_type === 'select' && (
          <div>
            <label id={`${idCampo}-et-opcion`} htmlFor={`${idCampo}-opcion`} className="cfl-label">{traducir('customfields.opciones_del_selector')}</label>
            <div className="cfl-options">
              {form.options.map((o) => (
                <span key={o} className="cfl-option">
                  {o}
                  <button type="button" className="cfl-option__remove"
                    aria-label={traducir('customfields.quitar_opcion', { opcion: o })}
                    onClick={() => set('options')(form.options.filter(x => x !== o))}>×</button>
                </span>
              ))}
            </div>
            <div className="u-row-8">
              <input id={`${idCampo}-opcion`} aria-labelledby={`${idCampo}-et-opcion`} className="cfl-input cfl-input--grow" value={optionInput}
                onChange={e => setOptionInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addOption() } }}
                placeholder={traducir('customfields.nueva_opcion')} />
              <Button onClick={addOption} title={traducir('customfields.anadir_opcion')}>+</Button>
            </div>
          </div>
        )}

        <div className="u-grid2-12">
          <label className="u-row-center-8-pointer">
            <input type="checkbox" aria-label={traducir('customfields.campo_obligatorio')} checked={form.is_required} onChange={e => set('is_required')(e.target.checked)} />
            <span>{traducir('customfields.campo_obligatorio')}</span>
          </label>
          <label className="u-row-center-8-pointer">
            <input type="checkbox" aria-label={traducir('customfields.visible_en_lista_de_tareas')} checked={form.show_in_list} onChange={e => set('show_in_list')(e.target.checked)} />
            <span>{traducir('customfields.visible_en_lista_de_tareas')}</span>
          </label>
        </div>

        <div>
          <label id={`${idCampo}-et-orden`} htmlFor={`${idCampo}-orden`} className="cfl-label">{traducir('customfields.orden_de_visualizacion')}</label>
          <input id={`${idCampo}-orden`} aria-labelledby={`${idCampo}-et-orden`} type="number" className="cfl-input cfl-input--order" value={form.sort_order}
            onChange={e => set('sort_order')(+e.target.value)} />
        </div>

        <div className="cfl-footer">
          <Button variant="secondary" onClick={onClose}>{traducir('customfields.cancelar')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name || !form.field_key} loading={isPending}>
            {isPending ? traducir('customfields.guardando') : isEdit ? traducir('customfields.guardar_cambios') : traducir('customfields.crear_campo')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function CustomFieldsPage(): JSX.Element {
  const idCampo = useId()
  const traducir = useAppT()
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

  const { data: fields = [], isLoading } = useQuery({
    queryKey: ['custom-fields', selectedProject],
    queryFn: () => customFieldsApi.list(selectedProject).then(r => r.data).catch((): CustomField[] => []),
    enabled: !!selectedProject,
  })

  const { mutate: deleteField } = useMutation({
    mutationFn: (fid: string | number) => customFieldsApi.delete(selectedProject, fid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['custom-fields', selectedProject] }),
    onError: (e: unknown) => toast.error(extractErr(e, traducir('customfields.error_eliminar'))),
  })

  const selectedProj = projects.find((p) => String(p.id) === selectedProject)
  const etiquetaTipo = (v: string) => FIELD_TYPES.some(ft => ft.value === v) ? traducir(`customfields.tipo_${v}`) : v

  return (
    <PageShell>
      <PageHeader
        icon={<SlidersHorizontal size={18} />}
        title={traducir('customfields.titulo')}
        subtitle={traducir('customfields.subtitulo')}
        actions={selectedProject && (
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>{traducir('customfields.nuevo_campo')}</Button>
        )}
      />

      {/* Selector de proyecto */}
      <div className="cfl-panel cfl-panel--selector">
        <label id={`${idCampo}-et-proyecto`} htmlFor={`${idCampo}-proyecto`} className="cfl-label">{traducir('customfields.proyecto')}</label>
        <select id={`${idCampo}-proyecto`} aria-labelledby={`${idCampo}-et-proyecto`} value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
          className="cfl-input cfl-input--project">
          <option value="">{traducir('customfields.selecciona_un_proyecto')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!selectedProject && (
        <EmptyState icon="🗂" title={traducir('customfields.selecciona_un_proyecto_2')} description={traducir('customfields.elige_proyecto_desc')} />
      )}

      {selectedProject && isLoading && <Spinner />}

      {selectedProject && !isLoading && fields.length === 0 && (
        <div className="cfl-panel cfl-panel--empty">
          <div className="u-empty-icon" aria-hidden="true">🗂</div>
          <div className="cfl-empty-title">{traducir('customfields.sin_campos_personalizados')}</div>
          <div className="u-text2-base-mb20">
            {traducir('customfields.crea_campos_propios_para_este_proyecto_severidad')}
          </div>
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>{traducir('customfields.crear_primer_campo')}</Button>
        </div>
      )}

      {selectedProject && fields.length > 0 && (
        <div className="cfl-panel">
          <div className="u-row-between-mb16">
            <div className="u-md-600">{traducir('customfields.n_campos_proyecto', { count: fmtNumber(fields.length, 0), proyecto: selectedProj?.name ?? '' })}</div>
            <div className="u-text2-sm">{traducir('customfields.estos_campos_aparecen_en_todas_las_tareas')}</div>
          </div>
          <div className="u-scroll-x">
            <table className="cfl-table">
              <thead>
                <tr className="u-border-b">
                  {COLUMNAS.map(h => <th key={h} scope="col">{traducir(`customfields.${h}`)}</th>)}
                </tr>
              </thead>
              <tbody>
                {fields.map((f) => {
                  const type = FIELD_TYPES.find(ft => ft.value === f.field_type)
                  return (
                    <tr key={f.id}>
                      <td className="cfl-name">{f.name}</td>
                      <td className="cfl-key">{f.field_key}</td>
                      <td>
                        <span className="u-row-center-6">
                          <span aria-hidden="true">{type?.icon}</span>
                          <span className="u-text2">{etiquetaTipo(f.field_type)}</span>
                          {f.field_type === 'select' && f.options && f.options.length > 0 && (
                            <span className="u-text3-xs">{traducir('customfields.n_opciones', { count: fmtNumber(f.options.length, 0) })}</span>
                          )}
                        </span>
                      </td>
                      <td>
                        <span className={f.is_required ? 'cfl-tag cfl-tag--danger' : 'cfl-tag'}>
                          {f.is_required ? traducir('customfields.obligatorio') : traducir('customfields.opcional')}
                        </span>
                      </td>
                      <td>
                        <span className={f.show_in_list ? 'cfl-tag cfl-tag--accent' : 'cfl-tag'}>
                          {f.show_in_list ? traducir('customfields.si') : traducir('customfields.no')}
                        </span>
                      </td>
                      <td>
                        <div className="u-row-8">
                          <button type="button" className="cfl-action"
                            aria-label={traducir('customfields.editar_campo_n', { nombre: f.name })}
                            onClick={() => { setEditing(f); setShowForm(true) }}>
                            {traducir('customfields.editar')}
                          </button>
                          <button type="button" className="cfl-action cfl-action--danger"
                            aria-label={traducir('customfields.eliminar_campo_n', { nombre: f.name })}
                            onClick={() => { openConfirmGlobal({ message: traducir('customfields.confirmar_eliminar', { nombre: f.name }), onConfirm: () => deleteField(f.id), danger: true }) }}>
                            {traducir('customfields.eliminar')}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Tipos de campo como referencia */}
          <div className="cfl-legend">
            <h2 className="cfl-legend__title">{traducir('customfields.tipos_disponibles')}</h2>
            <ul className="cfl-legend__list">
              {FIELD_TYPES.map(ft => (
                <li key={ft.value} className="cfl-legend__item">
                  <span aria-hidden="true">{ft.icon}</span><span>{traducir(`customfields.tipo_${ft.value}`)}</span>
                </li>
              ))}
            </ul>
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
