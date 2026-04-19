import { CHART } from '../constants/theme'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const COLORS = ['var(--text-2)','var(--accent)','var(--success)','var(--warning)','var(--danger)','var(--purple)','var(--warning)','var(--accent)',CHART.pink,CHART.lime]

const _DEP_TYPE_LABELS = {
  blocks:'Bloquea',blocked_by:'Bloqueada por',relates_to:'Relacionada',duplicates:'Duplica',cloned_from:'Clonada de'
}

function IssueTypeForm({ projectId, type, customFields, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!type?.id
  const [form, setForm] = useState({
    name:       type?.name        || '',
    value:      type?.value       || '',
    icon:       type?.icon        || '',
    color:      type?.color       || 'var(--text-2)',
    description:type?.description || '',
    is_subtask: type?.is_subtask  || false,
    sort_order: type?.sort_order  || 0,
    field_keys: type?.field_keys  || [],
  })
  const set = k => v => setForm(f => ({...f, [k]: v}))
  const autoValue = n => n.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'')

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit
      ? api.patch(`/issue-types/${projectId}/${type.id}`, d).then(r => r.data)
      : api.post(`/issue-types/${projectId}`, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['issue-types', projectId]); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  const toggleField = (key) => {
    set('field_keys')(form.field_keys.includes(key)
      ? form.field_keys.filter(k => k !== key)
      : [...form.field_keys, key])
  }

  const t = useAppT();
  return (
    <Modal open onClose={onClose} title={isEdit ? t('issue_types.edit_modal_title') : t('issue_types.new_modal_title')}>
      <div style={{display:'flex',flexDirection:'column',gap:14}}>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
          <div>
            <label style={ls}>Nombre</label>
            <input style={is} value={form.name} onChange={e => {
              const n = e.target.value
              setForm(f => ({...f, name:n, value: isEdit ? f.value : autoValue(n)}))
            }} placeholder={t(modulo.clave)} />
          </div>
          <div>
            <label style={ls}>Valor interno</label>
            <input style={{...is, fontFamily:'monospace', fontSize:12}} value={form.value}
              onChange={e => set('value')(e.target.value)} disabled={isEdit}
              placeholder={t(modulo.clave)} />
          </div>
        </div>

        <div style={{display:'grid',gridTemplateColumns:'80px 1fr',gap:12}}>
          <div>
            <label style={ls}>Icono</label>
            <input style={{...is, textAlign:'center', fontSize:20}} value={form.icon}
              onChange={e => set('icon')(e.target.value)} placeholder={t(modulo.clave)} />
          </div>
          <div>
            <label style={ls}>Color</label>
            <div style={{display:'flex',gap:8,flexWrap:'wrap',paddingTop:4}}>
              {COLORS.map(c => (
                <button key={c} onClick={() => set('color')(c)}
                  style={{width:28,height:28,borderRadius:'50%',background:c,border:form.color===c?'3px solid #fff':'2px solid transparent',cursor:'pointer'}} />
              ))}
              <input type="color" value={form.color} onChange={e => set('color')(e.target.value)}
                style={{width:28,height:28,borderRadius:'50%',border:'none',cursor:'pointer',padding:0}} />
            </div>
          </div>
        </div>

        <div>
          <label style={ls}>Descripción</label>
          <input style={is} value={form.description} onChange={e => set('description')(e.target.value)}
            placeholder={t(modulo.clave)} />
        </div>

        <label style={{display:'flex',alignItems:'center',gap:8,cursor:'pointer',fontSize:13}}>
          <input type="checkbox" checked={form.is_subtask} onChange={e => set('is_subtask')(e.target.checked)} />
          Puede usarse como subtarea de otra tarea
        </label>

        {customFields.length > 0 && (
          <div>
            <label style={ls}>Campos requeridos para este tipo</label>
            <div style={{display:'flex',flexWrap:'wrap',gap:8}}>
              {customFields.map(f => (
                <label key={f.field_key} style={{display:'flex',alignItems:'center',gap:6,cursor:'pointer',
                  padding:'4px 10px',borderRadius:6,border:`1px solid ${form.field_keys.includes(f.field_key)?'var(--accent-glow)':'var(--surface-4)'}`,
                  background:form.field_keys.includes(f.field_key)?'var(--accent-muted)':'transparent',fontSize:12}}>
                  <input type="checkbox" checked={form.field_keys.includes(f.field_key)}
                    onChange={() => toggleField(f.field_key)} style={{margin:0}} />
                  {f.name}
                </label>
              ))}
            </div>
          </div>
        )}

        <div style={{display:'flex',justifyContent:'flex-end',gap:10,marginTop:8}}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name || !form.value} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Crear tipo'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function IssueTypesPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [project, setProject] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.get('/projects').then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })
  const { data: types = [], isLoading } = useQuery({
    queryKey: ['issue-types', project],
    queryFn: () => api.get(`/issue-types/${project}`).then(r => r.data).catch(() => []),
    enabled: !!project,
  })
  const { data: customFields = [] } = useQuery({
    queryKey: ['custom-fields', project],
    queryFn: () => api.get(`/custom-fields/${project}`).then(r => r.data).catch(() => []),
    enabled: !!project,
  })

  const { mutate: initTypes, isPending: initing } = useMutation({
    mutationFn: () => api.post(`/issue-types/${project}/init`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries(['issue-types', project]),
    onError: e => toast.error(extractErr(e, 'Error al inicializar')),
  })
  const { mutate: deleteType } = useMutation({
    mutationFn: id => api.delete(`/issue-types/${project}/${id}`),
    onSuccess: () => qc.invalidateQueries(['issue-types', project]),
    onError: e => toast.error(extractErr(e, 'Error al eliminar')),
  })

  return (
    <div style={{padding:32}}>
      <PageHeader title={t('issue_types.title')} subtitle={t('issue_types.subtitle')}
        actions={project && types.length > 0 && (
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Nuevo tipo</Button>
        )} />

      <div style={{...ps, marginBottom:20}}>
        <label style={ls}>Proyecto</label>
        <select value={project} onChange={e => setProject(e.target.value)} style={{...is, width:360}}>
          <option value="">Selecciona un proyecto...</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!project && <EmptyState icon="🏷" title={t(modulo.clave)} description={t(modulo.clave)} />}
      {project && isLoading && <Spinner />}

      {project && !isLoading && types.length === 0 && (
        <div style={{...ps, textAlign:'center', padding:'48px 24px'}}>
          <div style={{fontSize:48, marginBottom:16}}>🏷</div>
          <div style={{fontSize:15, fontWeight:600, marginBottom:8}}>Sin tipos de issue</div>
          <div style={{fontSize:13, color:'var(--text-2)', marginBottom:24}}>
            Inicializa con los 7 tipos estándar (Historia, Tarea, Bug, Mejora, Épica, Subtarea, Spike)<br/>
            o crea tus propios tipos desde cero.
          </div>
          <div style={{display:'flex', gap:12, justifyContent:'center'}}>
            <Button onClick={() => initTypes()} disabled={initing}>
              {initing ? 'Inicializando...' : '⚡ Tipos estándar (7)'}
            </Button>
            <Button variant="secondary" onClick={() => { setEditing(null); setShowForm(true) }}>
              + Crear tipo custom
            </Button>
          </div>
        </div>
      )}

      {project && types.length > 0 && (
        <div>
          {/* Resumen visual */}
          <div style={{display:'flex', gap:10, flexWrap:'wrap', marginBottom:20}}>
            {types.map(t => (
              <div key={t.id} style={{background:'var(--surface-2)', border:`1px solid ${t.color}40`,
                borderRadius:10, padding:'12px 16px', minWidth:120, textAlign:'center'}}>
                <div style={{fontSize:28, marginBottom:4}}>{t.icon || '📌'}</div>
                <div style={{fontWeight:600, fontSize:13, color:t.color}}>{t.name}</div>
                <div style={{fontSize:11, color:'var(--text-3)', fontFamily:'monospace'}}>{t.value}</div>
                {t.is_subtask && <div style={{fontSize:10, color:'var(--text-2)', marginTop:4}}>subtarea</div>}
              </div>
            ))}
          </div>

          {/* Tabla detallada */}
          <div style={ps}>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16}}>
              <div style={{fontSize:14, fontWeight:600}}>{types.length} tipos de issue</div>
              <Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Nuevo tipo</Button>
            </div>
            <table style={{width:'100%', borderCollapse:'collapse', fontSize:13}}>
              <thead>
                <tr style={{borderBottom:'1px solid var(--surface-4)'}}>
                  {['Tipo','Valor','Descripción','Subtarea','Campos req.','Acciones'].map(h => (
                    <th key={h} style={{textAlign:'left', padding:'8px 12px', fontSize:11, color:'var(--text-2)',
                      textTransform:'uppercase', letterSpacing:'.06em'}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {types.map((t, i) => (
                  <tr key={t.id} style={{borderBottom:'1px solid #1a2640', background:i%2===0?'transparent':'rgba(255,255,255,0.02)'}}>
                    <td style={{padding:'10px 12px'}}>
                      <div style={{display:'flex', alignItems:'center', gap:10}}>
                        <div style={{width:32, height:32, borderRadius:8, background:t.color+'20',
                          display:'flex', alignItems:'center', justifyContent:'center', fontSize:16}}>
                          {t.icon || '📌'}
                        </div>
                        <span style={{fontWeight:600, color:t.color}}>{t.name}</span>
                      </div>
                    </td>
                    <td style={{padding:'10px 12px', fontFamily:'monospace', fontSize:11, color:'var(--text-2)'}}>{t.value}</td>
                    <td style={{padding:'10px 12px', color:'var(--text-2)', fontSize:12, maxWidth:220}}>
                      {t.description || '—'}
                    </td>
                    <td style={{padding:'10px 12px'}}>
                      <span style={{color: t.is_subtask ? 'var(--success)' : 'var(--text-3)', fontSize:13}}>
                        {t.is_subtask ? '✓' : '—'}
                      </span>
                    </td>
                    <td style={{padding:'10px 12px', fontSize:12, color:'var(--text-2)'}}>
                      {t.field_keys?.length > 0 ? t.field_keys.join(', ') : '—'}
                    </td>
                    <td style={{padding:'10px 12px'}}>
                      <div style={{display:'flex', gap:8}}>
                        <button onClick={() => { setEditing(t); setShowForm(true) }}
                          style={{background:'none', border:'1px solid var(--surface-4)', borderRadius:6,
                            padding:'4px 10px', color:'var(--text-2)', cursor:'pointer', fontSize:11}}>
                          Editar
                        </button>
                        <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar el tipo "${t.name}"? Las tareas de este tipo deberán reasignarse.`, onConfirm: () => deleteType(t.id), danger: true }) }}
                          style={{background:'none', border:'1px solid #ff475730', borderRadius:6,
                            padding:'4px 10px', color:'var(--danger)', cursor:'pointer', fontSize:11}}>
                          Eliminar
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div style={{marginTop:20, padding:'12px 16px', background:'var(--surface-1)', borderRadius:8,
              border:'1px solid #1a2640', fontSize:12, color:'var(--text-3)', lineHeight:1.7}}>
              <strong style={{color:'var(--text-2)'}}>Cómo usar:</strong> Asigna el campo <code style={{color:'var(--accent)'}}>issue_type</code> en tus tareas con el valor interno del tipo.
              Los tipos con campos requeridos exigen que esos campos estén rellenados al crear la tarea.
              Los tipos marcados como &quot;subtarea&quot; solo pueden ser hijo de otra tarea.
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <IssueTypeForm projectId={project} type={editing} customFields={customFields}
          onClose={() => { setShowForm(false); setEditing(null) }} />
      )}
    </div>
  )
}
