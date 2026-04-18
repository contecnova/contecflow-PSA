/**
 * PerformanceReviewsPage — Evaluaciones de rendimiento 360°
 * Ciclos de evaluación, formularios de scoring, histórico
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useToast } from '../context/ToastContext'
import { extractErr, fmtDate } from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'

const STATUS_CFG = {
  draft:     { color:'var(--text-3)',  bg:'var(--surface-4)',    label:'Borrador' },
  active:    { color:'var(--accent)',  bg:'var(--accent-muted)', label:'Activo' },
  closed:    { color:'var(--success)', bg:'rgba(29,158,117,.15)',label:'Cerrado' },
}
const REVIEW_TYPE = {
  self:    { icon:'👤', label:'Autoevaluación' },
  peer:    { icon:'👥', label:'Par' },
  manager: { icon:'👔', label:'Manager' },
  upward:  { icon:'⬆', label:'Upward' },
}
const DIMENSIONS = [
  { key:'score_quality',    label:'Calidad del trabajo' },
  { key:'score_delivery',   label:'Cumplimiento de plazos' },
  { key:'score_teamwork',   label:'Trabajo en equipo' },
  { key:'score_leadership', label:'Liderazgo' },
  { key:'score_innovation', label:'Innovación' },
]

function ScoreBar({ value, max=5 }) {
  const pct = value ? (value / max) * 100 : 0
  const color = pct >= 80 ? 'var(--success)' : pct >= 60 ? 'var(--accent)' : pct >= 40 ? 'var(--warning)' : 'var(--danger)'
  return (
    <div style={{ display:'flex', alignItems:'center', gap:8 }}>
      <div style={{ flex:1, height:6, background:'var(--surface-4)', borderRadius:3 }}>
        <div style={{ width:`${pct}%`, height:'100%', background:color, borderRadius:3 }} />
      </div>
      <span style={{ fontSize:12, fontWeight:700, color, minWidth:24, textAlign:'right',
        fontFamily:"'Space Mono',monospace" }}>{value ? value.toFixed(1) : '—'}</span>
    </div>
  )
}

function ReviewForm({ review, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [scores, setScores] = useState({
    score_quality:    review.score_quality    ?? '',
    score_delivery:   review.score_delivery   ?? '',
    score_teamwork:   review.score_teamwork   ?? '',
    score_leadership: review.score_leadership ?? '',
    score_innovation: review.score_innovation ?? '',
    strengths:    review.strengths    || '',
    improvements: review.improvements || '',
    goals_next:   review.goals_next   || '',
  })
  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45',
    borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: d => api.patch(`/performance/reviews/${review.id}`, d),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['perf-my-reviews'] }),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: submit, isPending: submitting } = useMutation({
    mutationFn: () => api.post(`/performance/reviews/${review.id}/submit`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['perf-my-reviews'] }); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const typeCfg = REVIEW_TYPE[review.review_type] || REVIEW_TYPE.peer

  return (
    <Modal open onClose={onClose}
      title={`${typeCfg.icon} Evaluación de ${review.reviewee_name}`} width={600}>
      <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
        {/* Puntuaciones */}
        <div style={{ background:'var(--surface-3)', borderRadius:10, padding:16 }}>
          <div style={{ fontSize:12, fontWeight:700, color:'var(--text-2)',
            textTransform:'uppercase', letterSpacing:'0.07em', marginBottom:12 }}>
            Puntuaciones (1–5)
          </div>
          {DIMENSIONS.map(({ key, label }) => (
            <div key={key} style={{ display:'grid', gridTemplateColumns:'1fr 1fr',
              gap:10, alignItems:'center', marginBottom:10 }}>
              <label style={{ fontSize:13, color:'var(--text-1)' }}>{label}</label>
              <div style={{ display:'flex', gap:4 }}>
                {[1,2,3,4,5].map(n => (
                  <button key={n} onClick={() => setScores(s => ({...s, [key]: n}))}
                    style={{ width:32, height:32, borderRadius:6,
                      background: scores[key] >= n ? 'var(--accent)' : 'var(--surface-4)',
                      border: scores[key] >= n ? '1px solid var(--accent)' : '1px solid #1e2d45',
                      color: scores[key] >= n ? '#fff' : 'var(--text-3)',
                      cursor:'pointer', fontSize:12, fontWeight:700 }}>
                    {n}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Texto libre */}
        {[
          { key:'strengths',    label:'Puntos fuertes', ph:'¿Qué hace especialmente bien?' },
          { key:'improvements', label:'Áreas de mejora', ph:'¿Qué podría mejorar?' },
          { key:'goals_next',   label:'Objetivos próximo periodo', ph:'¿Qué debería focalizarse?' },
        ].map(({ key, label, ph }) => (
          <div key={key}>
            <label style={{ fontSize:11, fontWeight:700, color:'var(--text-2)',
              textTransform:'uppercase', letterSpacing:'0.07em',
              display:'block', marginBottom:4 }}>{label}</label>
            <textarea value={scores[key]} onChange={e => setScores(s => ({...s, [key]:e.target.value}))}
              rows={3} style={{ ...IS, resize:'vertical' }} placeholder={ph} />
          </div>
        ))}

        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={() => save(scores)} disabled={saving} loading={saving}>
            Guardar borrador
          </Button>
          <Button onClick={() => { save(scores, { onSuccess: () => submit() }) }}
            disabled={submitting || saving}>
            Enviar evaluación
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function CycleCard({ cycle, onActivate, onClose }) {
  const { data: reviews = [], isLoading } = useQuery({
    queryKey: ['perf-cycle-reviews', cycle.id],
    queryFn: () => api.get(`/performance/cycles/${cycle.id}/reviews`).then(r => r.data).catch(() => []),
    enabled: cycle.status === 'active' || cycle.status === 'closed',
  })
  const statusCfg = STATUS_CFG[cycle.status] || STATUS_CFG.draft
  const [expanded, setExpanded] = useState(false)

  const avgScore = reviews.length > 0
    ? (reviews.filter(r => r.score_overall).reduce((s, r) => s + (r.score_overall || 0), 0)
       / reviews.filter(r => r.score_overall).length).toFixed(1)
    : null

  return (
    <div style={{ background:'var(--surface-2)', border:'1px solid #1e2d45',
      borderRadius:12, padding:'16px 20px', marginBottom:12 }}>
      <div style={{ display:'flex', alignItems:'center', gap:12 }}>
        <button onClick={() => setExpanded(s => !s)}
          style={{ background:'none', border:'none', color:'var(--text-3)',
            cursor:'pointer', fontSize:16, padding:0 }}>
          {expanded ? '▾' : '▸'}
        </button>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:15, fontWeight:700 }}>{cycle.name}</div>
          <div style={{ display:'flex', gap:8, marginTop:2 }}>
            <span style={{ fontSize:11, fontWeight:700, padding:'1px 8px', borderRadius:20,
              background: statusCfg.bg, color: statusCfg.color }}>
              {statusCfg.label}
            </span>
            {cycle.start_date && <span style={{ fontSize:11, color:'var(--text-2)' }}>
              {fmtDate(cycle.start_date)} – {fmtDate(cycle.end_date)}
            </span>}
            <span style={{ fontSize:11, color:'var(--text-2)' }}>
              {cycle.pending} pendientes · {cycle.submitted} enviadas
            </span>
            {avgScore && <span style={{ fontSize:11, color:'var(--accent)', fontWeight:700 }}>
              Media: {avgScore}/5
            </span>}
          </div>
        </div>
        <div style={{ display:'flex', gap:8 }}>
          {cycle.status === 'draft' && (
            <Button size="sm" onClick={() => onActivate(cycle.id)}>Activar</Button>
          )}
          {cycle.status === 'active' && (
            <Button size="sm" variant="secondary" onClick={() => onClose(cycle.id)}>Cerrar ciclo</Button>
          )}
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop:12 }}>
          {isLoading ? <Spinner /> : reviews.length === 0 ? (
            <div style={{ fontSize:12, color:'var(--text-3)', padding:'8px 0' }}>
              Sin evaluaciones en este ciclo
            </div>
          ) : (
            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(280px,1fr))', gap:8, marginTop:8 }}>
              {reviews.map(r => (
                <div key={r.id} style={{ background:'var(--surface-3)', borderRadius:8,
                  padding:'10px 12px', border:'1px solid var(--surface-4)' }}>
                  <div style={{ display:'flex', justifyContent:'space-between', marginBottom:6 }}>
                    <div>
                      <span style={{ fontSize:12, fontWeight:700 }}>{r.reviewee_name}</span>
                      <span style={{ fontSize:11, color:'var(--text-2)', marginLeft:6 }}>
                        {REVIEW_TYPE[r.review_type]?.icon} {REVIEW_TYPE[r.review_type]?.label}
                      </span>
                    </div>
                    <span style={{ fontSize:10, color: r.status === 'submitted' ? 'var(--success)' : 'var(--text-3)',
                      fontWeight:600 }}>
                      {r.status === 'submitted' ? '✓ Enviado' : '⏳ Pendiente'}
                    </span>
                  </div>
                  {r.score_overall && (
                    <div>
                      <ScoreBar value={r.score_overall} />
                    </div>
                  )}
                  <div style={{ fontSize:11, color:'var(--text-3)', marginTop:4 }}>
                    por {r.reviewer_name}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function NewCycleModal({ onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({ name:'', start_date:'', end_date:'' })
  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45',
    borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const { mutate, isPending } = useMutation({
    mutationFn: d => api.post('/performance/cycles', d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['perf-cycles'] }); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  return (
    <Modal open onClose={onClose} title="Nuevo ciclo de evaluación" width={480}>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <div>
          <label style={{ fontSize:11, fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Nombre *</label>
          <input value={form.name} onChange={e => setForm(f => ({...f, name:e.target.value}))}
            style={IS} placeholder="Ej: Evaluación Q2 2025" autoFocus />
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
          <div>
            <label style={{ fontSize:11, fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Inicio</label>
            <input type="date" value={form.start_date} onChange={e => setForm(f => ({...f, start_date:e.target.value}))} style={IS} />
          </div>
          <div>
            <label style={{ fontSize:11, fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:4 }}>Fin</label>
            <input type="date" value={form.end_date} onChange={e => setForm(f => ({...f, end_date:e.target.value}))} style={IS} />
          </div>
        </div>
        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name} loading={isPending}>
            Crear ciclo
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function PerformanceReviewsPage() {
  const t = useAppT()
  const { _user } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('cycles')
  const [showNewCycle, setShowNewCycle] = useState(false)
  const [editingReview, setEditingReview] = useState(null)

  const { data: cycles = [], isLoading: loadingCycles } = useQuery({
    queryKey: ['perf-cycles'],
    queryFn: () => api.get('/performance/cycles').then(r => r.data).catch(() => []),
  })
  const { data: myReviews = [], isLoading: loadingMine } = useQuery({
    queryKey: ['perf-my-reviews'],
    queryFn: () => api.get('/performance/my-reviews').then(r => r.data).catch(() => []),
    enabled: tab === 'pending',
  })

  const { mutate: activate } = useMutation({
    mutationFn: id => api.post(`/performance/cycles/${id}/activate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['perf-cycles'] }),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: closeCycle } = useMutation({
    mutationFn: id => api.post(`/performance/cycles/${id}/close`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['perf-cycles'] }),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const TABS = [
    { id:'cycles',  label:'📋 Ciclos' },
    { id:'pending', label:`⏳ Mis evaluaciones${myReviews.length > 0 ? ` (${myReviews.length})` : ''}` },
  ]

  return (
    <div style={{ padding:32 }}>
      <PageHeader
        title={t('performance.title')}
        subtitle={t('performance.subtitle')}
        actions={
          tab === 'cycles' && (
            <Button onClick={() => setShowNewCycle(true)}>+ {t('performance.new_cycle') || 'Nuevo ciclo'}</Button>
          )
        }
      />

      {/* Tabs */}
      <div style={{ display:'flex', gap:6, marginBottom:24 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding:'8px 16px', borderRadius:8, fontSize:12, fontWeight:600,
              border: `1px solid ${tab===t.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
              background: tab===t.id ? 'var(--accent-muted)' : 'transparent',
              color: tab===t.id ? 'var(--accent)' : 'var(--text-2)',
              cursor:'pointer', fontFamily:'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Ciclos */}
      {tab === 'cycles' && (
        loadingCycles ? <Spinner /> : cycles.length === 0 ? (
          <EmptyState icon="📋" title="Sin ciclos de evaluación"
            description="Crea un ciclo para lanzar evaluaciones de rendimiento 360°" />
        ) : (
          cycles.map(c => (
            <CycleCard key={c.id} cycle={c}
              onActivate={id => activate(id)}
              onClose={id => closeCycle(id)} />
          ))
        )
      )}

      {/* Mis evaluaciones pendientes */}
      {tab === 'pending' && (
        loadingMine ? <Spinner /> : myReviews.length === 0 ? (
          <EmptyState icon="✅" title="Sin evaluaciones pendientes"
            description="No tienes evaluaciones que rellenar en este momento" />
        ) : (
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {myReviews.map(r => (
              <div key={r.id} style={{ display:'flex', alignItems:'center', gap:12,
                padding:'12px 16px', background:'var(--surface-2)',
                border:'1px solid #1e2d45', borderRadius:10 }}>
                <div style={{ fontSize:24 }}>{REVIEW_TYPE[r.review_type]?.icon || '📋'}</div>
                <div style={{ flex:1 }}>
                  <div style={{ fontSize:14, fontWeight:700 }}>
                    Evaluar a {r.reviewee_name}
                  </div>
                  <div style={{ fontSize:12, color:'var(--text-2)', marginTop:2 }}>
                    {REVIEW_TYPE[r.review_type]?.label}
                  </div>
                </div>
                <Button onClick={() => setEditingReview(r)}>Rellenar evaluación</Button>
              </div>
            ))}
          </div>
        )
      )}

      {showNewCycle && <NewCycleModal onClose={() => setShowNewCycle(false)} />}
      {editingReview && <ReviewForm review={editingReview} onClose={() => setEditingReview(null)} />}
    </div>
  )
}
