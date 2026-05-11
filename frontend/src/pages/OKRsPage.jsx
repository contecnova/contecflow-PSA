/**
 * OKRsPage — Objectives & Key Results
 * Vista árbol: Objectives con Key Results expandibles, progreso en tiempo real, check-ins
 */
import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { okrsApi, usersApi, projectsApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, Page } from '../components/ui'
import { Trophy, Plus } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'

const PERIOD_OPTS = ['Q1','Q2','Q3','Q4','H1','H2','annual']
const KR_TYPE_CFG = {
  percentage: { icon:'%', label:'Porcentaje', unit:'%' },
  number:     { icon:'#', label:'Número',     unit:'' },
  boolean:    { icon:'✓', label:'Sí/No',      unit:'' },
  currency:   { icon:'€', label:'Importe',    unit:'€' },
}
const STATUS_CFG = {
  draft:     { color:'var(--text-3)',   label:'Borrador' },
  active:    { color:'var(--accent)',   label:'Activo' },
  completed: { color:'var(--success)',  label:'Completado' },
  cancelled: { color:'var(--danger)',   label:'Cancelado' },
}

function ProgressRing({ pct, size=44, stroke=4, color='var(--accent)' }) {
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const dash = (pct / 100) * circ
  return (
    <svg width={size} height={size} style={{ flexShrink:0 }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none"
        stroke="var(--surface-4)" strokeWidth={stroke} />
      <circle cx={size/2} cy={size/2} r={r} fill="none"
        stroke={color} strokeWidth={stroke}
        strokeDasharray={`${dash} ${circ}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`} />
      <text x={size/2} y={size/2+1} textAnchor="middle" dominantBaseline="central"
        style={{ fontSize: size > 40 ? 11 : 9, fontWeight:700,
          fill: color, fontFamily: 'var(--font-mono)' }}>
        {Math.round(pct)}%
      </text>
    </svg>
  )
}

function KRRow({ kr, _onCheckin, onDelete }) {
  const [showCheckin, setShowCheckin] = useState(false)
  const [checkinVal, setCheckinVal] = useState(kr.current_value ?? 0)
  const [checkinNote, setCheckinNote] = useState('')
  const toast = useToast()
  const qc = useQueryClient()
  const typeCfg = KR_TYPE_CFG[kr.kr_type] || KR_TYPE_CFG.percentage

  const { mutate: submitCheckin, isPending } = useMutation({
    mutationFn: () => okrsApi.checkin(kr.id, { value: parseFloat(checkinVal), note: checkinNote }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['okrs'] })
      setShowCheckin(false)
      toast.success('Progreso actualizado')
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const pct = kr.progress ?? 0
  const color = pct >= 100 ? 'var(--success)' : pct >= 60 ? 'var(--accent)' : pct >= 30 ? 'var(--warning)' : 'var(--danger)'

  return (
    <div style={{ marginLeft:24, marginBottom:6 }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, padding:'8px 12px',
        background:'var(--surface-3)', borderRadius:8, border:'1px solid var(--surface-4)' }}>
        <ProgressRing pct={pct} size={36} stroke={3} color={color} />
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize: "var(--text-base)", color:'var(--text-1)', fontWeight:500 }}>{kr.title}</div>
          <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginTop:2 }}>
            {typeCfg.icon} {kr.current_value ?? 0} / {kr.target_value} {kr.unit || typeCfg.unit}
            {kr.owner_name && <span style={{ marginLeft:8 }}>· {kr.owner_name}</span>}
          </div>
        </div>
        <button onClick={() => setShowCheckin(s => !s)}
          style={{ background:'var(--accent-muted)', border:'1px solid var(--accent-border)',
            borderRadius:6, padding:'4px 10px', color:'var(--accent)',
            cursor:'pointer', fontSize: "var(--text-xs)", fontFamily:'inherit' }}>
          ↑ Actualizar
        </button>
        <button onClick={() => onDelete(kr.id)}
          style={{ background:'none', border:'none', color:'var(--text-3)',
            cursor:'pointer', fontSize: "var(--text-md)", padding:'0 4px' }}>×</button>
      </div>
      {showCheckin && (
        <div style={{ display:'flex', gap:8, padding:'8px 12px', marginTop:4,
          background:'var(--accent-muted)', border:'1px dashed var(--accent-border)',
          borderRadius:8, alignItems:'center' }}>
          <div style={{ flex:1 }}>
            <input type="number" value={checkinVal}
              onChange={e => setCheckinVal(e.target.value)}
              style={{ width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
                borderRadius:6, padding:'6px 10px', color:'var(--text-1)',
                fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit' }}
              placeholder={`Nuevo valor (actual: ${kr.current_value})`} />
          </div>
          <div style={{ flex:2 }}>
            <input value={checkinNote} onChange={e => setCheckinNote(e.target.value)}
              style={{ width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
                borderRadius:6, padding:'6px 10px', color:'var(--text-1)',
                fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit' }}
              placeholder="Nota del check-in..." />
          </div>
          <Button onClick={() => submitCheckin()} disabled={isPending} loading={isPending} size="sm">
            Guardar
          </Button>
          <Button variant="secondary" onClick={() => setShowCheckin(false)} size="sm">✕</Button>
        </div>
      )}
    </div>
  )
}

function ObjectiveCard({ obj, onEdit, onAddKR, onDeleteObj, onDeleteKR }) {
  const [expanded, setExpanded] = useState(true)
  const statusCfg = STATUS_CFG[obj.status] || STATUS_CFG.draft
  const pct = obj.progress ?? 0
  const color = pct >= 100 ? 'var(--success)' : pct >= 60 ? 'var(--accent)' : pct >= 30 ? 'var(--warning)' : 'var(--danger)'

  return (
    <div style={{ background:'var(--surface-2)', border:`1px solid ${color}25`,
      borderRadius:12, padding:'14px 16px', marginBottom:12 }}>
      <div style={{ display:'flex', alignItems:'center', gap:12 }}>
        <button onClick={() => setExpanded(s => !s)}
          style={{ background:'none', border:'none', color:'var(--text-3)',
            cursor:'pointer', fontSize: "var(--text-lg)", padding:0, width:20, flexShrink:0 }}>
          {expanded ? '▾' : '▸'}
        </button>
        <ProgressRing pct={pct} size={48} stroke={4} color={color} />
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize: "var(--text-md-em)", fontWeight:700, color:'var(--text-1)' }}>{obj.title}</div>
          <div style={{ display:'flex', gap:8, marginTop:3, flexWrap:'wrap' }}>
            <span style={{ fontSize: "var(--text-xs)", color: statusCfg.color, fontWeight:700 }}>
              {statusCfg.label}
            </span>
            <span style={{ fontSize: "var(--text-xs)", color:'var(--text-3)' }}>
              {obj.period} {obj.year}
            </span>
            {obj.owner_name && (
              <span style={{ fontSize: "var(--text-xs)", color:'var(--text-2)' }}>· {obj.owner_name}</span>
            )}
            <span style={{ fontSize: "var(--text-xs)", color:'var(--text-3)' }}>
              {obj.key_results?.length || 0} KRs
            </span>
          </div>
        </div>
        <div style={{ display:'flex', gap:6, flexShrink:0 }}>
          <button onClick={() => onAddKR(obj)}
            style={{ background:'var(--accent-muted)', border:'1px solid var(--accent-border)',
              borderRadius:6, padding:'4px 10px', color:'var(--accent)',
              cursor:'pointer', fontSize: "var(--text-xs)", fontFamily:'inherit' }}>
            + KR
          </button>
          <button onClick={() => onEdit(obj)}
            style={{ background:'none', border:'1px solid var(--surface-4)',
              borderRadius:6, padding:'4px 8px', color:'var(--text-2)',
              cursor:'pointer', fontSize: "var(--text-xs)" }}>✏</button>
          <button onClick={() => onDeleteObj(obj.id)}
            style={{ background:'none', border:'1px solid var(--danger-border)',
              borderRadius:6, padding:'4px 8px', color:'var(--danger)',
              cursor:'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
        </div>
      </div>

      {expanded && obj.key_results?.length > 0 && (
        <div style={{ marginTop:10 }}>
          {obj.key_results.map(kr => (
            <KRRow key={kr.id} kr={kr} onDelete={onDeleteKR} />
          ))}
        </div>
      )}
      {expanded && (!obj.key_results || obj.key_results.length === 0) && (
        <div style={{ marginLeft:24, marginTop:8, fontSize: "var(--text-sm)", color:'var(--text-3)',
          fontStyle:'italic' }}>
          Sin Key Results — pulsa &quot;+ KR&quot; para añadir uno
        </div>
      )}
    </div>
  )
}

function ObjModal({ obj, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const isEdit = !!obj?.id
  const [form, setForm] = useState({
    title: obj?.title || '', description: obj?.description || '',
    period: obj?.period || 'Q1', year: obj?.year || new Date().getFullYear(),
    status: obj?.status || 'active',
    owner_id: obj?.owner_id || '',
    project_id: obj?.project_id || '',
    team_id: obj?.team_id || '',
  })

  const { data: users = [] } = useQuery({
    queryKey: ['okr-users-pick'],
    queryFn: () => usersApi.list({ page_size: 200 }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
  })
  const { data: projects = [] } = useQuery({
    queryKey: ['okr-projects-pick'],
    queryFn: () => projectsApi.list({ page_size: 200 }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
  })
  const { data: departments = [] } = useQuery({
    queryKey: ['okr-departments-pick'],
    queryFn: async () => {
      try {
        const { settingsApi } = await import('../services/settingsApi')
        const r = await settingsApi.getDepartments()
        return Array.isArray(r.data) ? r.data : []
      } catch { return [] }
    },
  })

  const { mutate, isPending } = useMutation({
    mutationFn: () => {
      // Limpiamos cadenas vacías → null para que el backend no falle al castear UUIDs.
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v === '' ? null : v])
      )
      return isEdit ? okrsApi.update(obj.id, payload) : okrsApi.create(payload)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['okrs'] }); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar objetivo' : 'Nuevo objetivo'} width={580}>
      <div className="ds-stack">
        <div className="ds-field">
          <label className="ds-field__label">Título *</label>
          <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            className="ds-input" placeholder="Ej: Incrementar retención de clientes" autoFocus />
        </div>
        <div className="ds-field">
          <label className="ds-field__label">Descripción</label>
          <textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            rows={2} className="ds-input" style={{ resize: 'vertical' }}
            placeholder="¿Qué problema resuelve y cómo se medirá su éxito?" />
        </div>

        {/* Asignaciones */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)' }}>
          <div className="ds-field">
            <label className="ds-field__label">Responsable</label>
            <select value={form.owner_id} onChange={e => setForm(f => ({ ...f, owner_id: e.target.value }))}
              className="ds-input">
              <option value="">— Sin asignar —</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name || u.username}</option>)}
            </select>
            <div className="ds-field__hint">Persona que rinde cuentas del objetivo</div>
          </div>
          <div className="ds-field">
            <label className="ds-field__label">Departamento / equipo</label>
            <select value={form.team_id} onChange={e => setForm(f => ({ ...f, team_id: e.target.value }))}
              className="ds-input">
              <option value="">— Compañía —</option>
              {departments.map(d => <option key={d.id || d.name} value={d.id || d.name}>{d.name || d}</option>)}
            </select>
            <div className="ds-field__hint">Vacío = OKR de empresa</div>
          </div>
        </div>

        <div className="ds-field">
          <label className="ds-field__label">Proyecto vinculado</label>
          <select value={form.project_id} onChange={e => setForm(f => ({ ...f, project_id: e.target.value }))}
            className="ds-input">
            <option value="">— Ninguno —</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code ? `${p.code} · ` : ''}{p.name}</option>)}
          </select>
          <div className="ds-field__hint">Si lo vinculas, los KRs pueden sincronizar progreso desde las tareas del proyecto.</div>
        </div>

        {/* Período + estado */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 'var(--space-2)' }}>
          <div className="ds-field">
            <label className="ds-field__label">Período</label>
            <select value={form.period} onChange={e => setForm(f => ({ ...f, period: e.target.value }))} className="ds-input">
              {PERIOD_OPTS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div className="ds-field">
            <label className="ds-field__label">Año</label>
            <input type="number" value={form.year}
              onChange={e => setForm(f => ({ ...f, year: parseInt(e.target.value) || f.year }))}
              className="ds-input" />
          </div>
          <div className="ds-field">
            <label className="ds-field__label">Estado</label>
            <select value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))} className="ds-input">
              {Object.entries(STATUS_CFG).map(([v, c]) => <option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)', marginTop: 4 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.title} loading={isPending}>
            {isEdit ? 'Guardar cambios' : 'Crear objetivo'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function KRModal({ objective, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    objective_id: objective.id, title: '', kr_type: 'percentage',
    target_value: 100, current_value: 0, unit: '',
    owner_id: '', due_date: '', notes: '',
  })

  const { data: users = [] } = useQuery({
    queryKey: ['okr-users-pick'],
    queryFn: () => usersApi.list({ page_size: 200 }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: () => {
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v === '' ? null : v])
      )
      // El KR siempre vive bajo un objective: aseguramos el id por si la limpieza lo borrara
      payload.objective_id = objective.id
      return okrsApi.createKR(payload)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['okrs'] }); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open onClose={onClose}
      title="Nuevo Key Result"
      subtitle={`Para el objetivo: ${objective.title}`}
      width={560}>
      <div className="ds-stack">
        <div className="ds-field">
          <label className="ds-field__label">Descripción del resultado *</label>
          <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            className="ds-input" placeholder="Ej: Aumentar NPS a 60" autoFocus />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 'var(--space-2)' }}>
          <div className="ds-field">
            <label className="ds-field__label">Tipo</label>
            <select value={form.kr_type} onChange={e => setForm(f => ({ ...f, kr_type: e.target.value }))} className="ds-input">
              {Object.entries(KR_TYPE_CFG).map(([v, c]) => <option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
          <div className="ds-field">
            <label className="ds-field__label">Meta</label>
            <input type="number" value={form.target_value}
              onChange={e => setForm(f => ({ ...f, target_value: parseFloat(e.target.value) || 0 }))}
              className="ds-input" />
          </div>
          <div className="ds-field">
            <label className="ds-field__label">Unidad</label>
            <input value={form.unit} onChange={e => setForm(f => ({ ...f, unit: e.target.value }))}
              className="ds-input" placeholder="%, puntos, €, NPS…" />
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)' }}>
          <div className="ds-field">
            <label className="ds-field__label">Responsable del KR</label>
            <select value={form.owner_id} onChange={e => setForm(f => ({ ...f, owner_id: e.target.value }))}
              className="ds-input">
              <option value="">— Hereda del objetivo —</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name || u.username}</option>)}
            </select>
          </div>
          <div className="ds-field">
            <label className="ds-field__label">Fecha límite</label>
            <input type="date" value={form.due_date}
              onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))}
              className="ds-input" />
          </div>
        </div>
        <div className="ds-field">
          <label className="ds-field__label">Notas (opcional)</label>
          <textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
            rows={2} className="ds-input" style={{ resize: 'vertical' }}
            placeholder="Detalles, criterios de éxito, dependencias…" />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.title} loading={isPending}>
            <Plus size={13} /> Añadir KR
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function OKRsPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [year, setYear] = useState(new Date().getFullYear())
  const [period, setPeriod] = useState('')
  const [showObjModal, setShowObjModal] = useState(false)
  const [editingObj, setEditingObj] = useState(null)
  const [addKRFor, setAddKRFor] = useState(null)

  const { data: objectives = [], isLoading } = useQuery({
    queryKey: ['okrs', year, period],
    queryFn: () => okrsApi.list({ year, ...(period && { period }) }).then(r => r.data),
  })

  const { mutate: deleteObj } = useMutation({
    mutationFn: id => okrsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okrs'] }),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: deleteKR } = useMutation({
    mutationFn: id => okrsApi.deleteKR(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okrs'] }),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const totalObjs = objectives.length
  const avgProgress = totalObjs > 0
    ? Math.round(objectives.reduce((s, o) => s + (o.progress || 0), 0) / totalObjs)
    : 0
  const onTrack = objectives.filter(o => (o.progress || 0) >= 60).length

  return (
    <Page
      icon={<Trophy size={18} />}
      title={t('okrs.title')}
      subtitle={t('okrs.subtitle')}
      actions={
        <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
          <select value={period} onChange={e => setPeriod(e.target.value)}
            className="ds-input" style={{ width: 'auto', minWidth: 140 }}>
            <option value="">Todos los periodos</option>
            {PERIOD_OPTS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <select value={year} onChange={e => setYear(parseInt(e.target.value))}
            className="ds-input" style={{ width: 'auto', minWidth: 100 }}>
            {[2024, 2025, 2026].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
          <Button onClick={() => { setEditingObj(null); setShowObjModal(true) }}>
            <Plus size={13} /> Nuevo objetivo
          </Button>
        </div>
      }
    >
      {/* KPI cards */}
      <div className="ds-grid-stats">
        {[
          { label: 'Objetivos activos', value: totalObjs, color: 'var(--accent)' },
          { label: 'Progreso medio',    value: `${avgProgress}%`, color: avgProgress >= 60 ? 'var(--success)' : 'var(--warning)' },
          { label: 'En camino (≥60%)',  value: onTrack, color: 'var(--success)' },
        ].map(kpi => (
          <div key={kpi.label} className="ds-card" style={{ padding: '14px 16px', gap: 4 }}>
            <div style={{ fontSize: 'var(--text-2xl-em)', fontWeight: 800, color: kpi.color,
              fontFamily: 'var(--font-mono)', lineHeight: 1.1 }}>{kpi.value}</div>
            <div className="ds-eyebrow">{kpi.label}</div>
          </div>
        ))}
      </div>

      {isLoading ? <Spinner /> : objectives.length === 0 ? (
        <EmptyState svgIcon={<Trophy size={36} />} title="Sin objetivos"
          description="Crea tu primer OKR para alinear al equipo. Un OKR define un objetivo cualitativo y 3-5 resultados clave medibles." />
      ) : (
        <div data-export-table="okrs-list" style={{ display:'flex', flexDirection:'column', gap:12 }}>
          {objectives.map(obj => (
            <ObjectiveCard key={obj.id} obj={obj}
              onEdit={o => { setEditingObj(o); setShowObjModal(true) }}
              onAddKR={setAddKRFor}
              onDeleteObj={id => { openConfirmGlobal({ message: '¿Eliminar este objetivo y todos sus KRs?', onConfirm: () => deleteObj(id), danger: true }) }}
              onDeleteKR={id => { openConfirmGlobal({ message: '¿Eliminar este KR?', onConfirm: () => deleteKR(id), danger: true }) }}
            />
          ))}
        </div>
      )}

      {showObjModal && (
        <ObjModal obj={editingObj} onClose={() => { setShowObjModal(false); setEditingObj(null) }} />
      )}
      {addKRFor && <KRModal objective={addKRFor} onClose={() => setAddKRFor(null)} />}
    </Page>
  )
}
