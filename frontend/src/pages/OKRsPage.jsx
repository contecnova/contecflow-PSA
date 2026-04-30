/**
 * OKRsPage — Objectives & Key Results
 * Vista árbol: Objectives con Key Results expandibles, progreso en tiempo real, check-ins
 */
import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { okrsApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Trophy } from 'lucide-react'
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
  })
  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize: "var(--text-base)",
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit
      ? okrsApi.update(obj.id, d)
      : okrsApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['okrs'] }); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar objetivo' : 'Nuevo objetivo'} width={540}>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <div>
          <label style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Título *</label>
          <input value={form.title} onChange={e => setForm(f => ({...f, title:e.target.value}))}
            style={IS} placeholder="Ej: Incrementar retencion de clientes" autoFocus />
        </div>
        <div>
          <label style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Descripción</label>
          <textarea value={form.description} onChange={e => setForm(f => ({...f, description:e.target.value}))}
            rows={2} style={{ ...IS, resize:'vertical' }} placeholder="Descripcion del objetivo..." />
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:10 }}>
          <div>
            <label style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Periodo</label>
            <select value={form.period} onChange={e => setForm(f => ({...f, period:e.target.value}))} style={IS}>
              {PERIOD_OPTS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Año</label>
            <input type="number" value={form.year} onChange={e => setForm(f => ({...f, year:parseInt(e.target.value)}))} style={IS} />
          </div>
          <div>
            <label style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Estado</label>
            <select value={form.status} onChange={e => setForm(f => ({...f, status:e.target.value}))} style={IS}>
              {Object.entries(STATUS_CFG).map(([v,c]) => <option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
        </div>
        <div style={{ display:'flex', justifyContent:'flex-end', gap:10, marginTop:4 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}>
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
    objective_id: objective.id, title:'', kr_type:'percentage',
    target_value:100, current_value:0, unit:'', notes:''
  })
  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize: "var(--text-base)",
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }

  const { mutate, isPending } = useMutation({
    mutationFn: d => okrsApi.createKR(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['okrs'] }); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open onClose={onClose} title={`Nuevo KR — ${objective.title}`} width={480}>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <div>
          <label style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Descripción del resultado *</label>
          <input value={form.title} onChange={e => setForm(f => ({...f, title:e.target.value}))}
            style={IS} placeholder="Ej: Aumentar NPS a 60" autoFocus />
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:10 }}>
          <div>
            <label style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Tipo</label>
            <select value={form.kr_type} onChange={e => setForm(f => ({...f, kr_type:e.target.value}))} style={IS}>
              {Object.entries(KR_TYPE_CFG).map(([v,c]) => <option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Objetivo</label>
            <input type="number" value={form.target_value}
              onChange={e => setForm(f => ({...f, target_value:parseFloat(e.target.value)}))} style={IS} />
          </div>
          <div>
            <label style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Unidad</label>
            <input value={form.unit} onChange={e => setForm(f => ({...f, unit:e.target.value}))}
              style={IS} placeholder="%, puntos, unidades..." />
          </div>
        </div>
        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}>
            Añadir KR
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
    <PageShell>
      <PageHeader
        icon={<Trophy size={18} />}
        title={t('okrs.title')}
        subtitle={t('okrs.subtitle')}
        actions={
          <div style={{ display:'flex', gap:10, alignItems:'center' }}>
            <select value={period} onChange={e => setPeriod(e.target.value)}
              style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
                borderRadius:8, padding:'7px 12px', color:'var(--text-1)',
                fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit' }}>
              <option value="">Todos los periodos</option>
              {PERIOD_OPTS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            <select value={year} onChange={e => setYear(parseInt(e.target.value))}
              style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
                borderRadius:8, padding:'7px 12px', color:'var(--text-1)',
                fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit' }}>
              {[2024,2025,2026].map(y => <option key={y} value={y}>{y}</option>)}
            </select>
            <Button onClick={() => { setEditingObj(null); setShowObjModal(true) }}>
              + Nuevo objetivo
            </Button>
          </div>
        }
      />

      {/* KPI cards */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12, marginBottom:24 }}>
        {[
          { label:'Objetivos activos', value:totalObjs, color:'var(--accent)' },
          { label:'Progreso medio', value:`${avgProgress}%`, color: avgProgress >= 60 ? 'var(--success)' : 'var(--warning)' },
          { label:'En camino (≥60%)', value:onTrack, color:'var(--success)' },
        ].map(kpi => (
          <div key={kpi.label} style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
            borderRadius:12, padding:'16px 20px' }}>
            <div style={{ fontSize: "var(--text-2xl-em)", fontWeight:800, color:kpi.color,
              fontFamily: 'var(--font-mono)' }}>{kpi.value}</div>
            <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', marginTop:2 }}>{kpi.label}</div>
          </div>
        ))}
      </div>

      {isLoading ? <Spinner /> : objectives.length === 0 ? (
        <EmptyState icon="🎯" title="Sin objetivos" description="Crea tu primer OKR para alinear al equipo" />
      ) : (
        objectives.map(obj => (
          <ObjectiveCard key={obj.id} obj={obj}
            onEdit={o => { setEditingObj(o); setShowObjModal(true) }}
            onAddKR={setAddKRFor}
            onDeleteObj={id => { openConfirmGlobal({ message: '¿Eliminar este objetivo y todos sus KRs?', onConfirm: () => deleteObj(id), danger: true }) }}
            onDeleteKR={id => { openConfirmGlobal({ message: '¿Eliminar este KR?', onConfirm: () => deleteKR(id), danger: true }) }}
          />
        ))
      )}

      {showObjModal && (
        <ObjModal obj={editingObj} onClose={() => { setShowObjModal(false); setEditingObj(null) }} />
      )}
      {addKRFor && <KRModal objective={addKRFor} onClose={() => setAddKRFor(null)} />}
    </PageShell>
  )
}
