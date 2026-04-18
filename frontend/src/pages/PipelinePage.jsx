import { useState, useRef, useCallback } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Modal, Spinner, ClientSelect, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { Megaphone } from 'lucide-react'
import { fmtCurrency, fmtDate, extractErr} from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const STAGES = [
  { id: 'lead',         label: 'Lead',          color: 'var(--text-2)' },
  { id: 'qualification',label: 'Cualificación', color: 'var(--accent)' },
  { id: 'proposal',     label: 'Propuesta',     color: 'var(--purple)' },
  { id: 'negotiation',  label: 'Negociación',   color: 'var(--warning)' },
  { id: 'won',          label: 'Ganada',        color: 'var(--success)' },
  { id: 'lost',         label: 'Perdida',       color: 'var(--danger)' },
]

const ACTIVE_STAGES = STAGES.filter(s => !['won','lost','cancelled'].includes(s.id))

function OppCard({ opp, onClick, onStageDrop }) {
  const stage = STAGES.find(s => s.id === opp.stage) || STAGES[0]
  const wasDragged = useRef(false)
  const dragState = useRef(null)

  const handleMouseDown = (e) => {
    if (e.button !== 0) return
    wasDragged.current = false
    const startX = e.clientX, startY = e.clientY
    let ghost = null

    const onMove = (mv) => {
      const dx = mv.clientX - startX, dy = mv.clientY - startY
      if (!ghost && (Math.abs(dx) > 5 || Math.abs(dy) > 5)) {
        wasDragged.current = true
        ghost = document.createElement('div')
        ghost.id = '__opp_ghost__'
        ghost.style.cssText = `position:fixed;z-index:9999;pointer-events:none;background:var(--surface-2);border:1.5px solid ${stage.color};border-radius:10px;padding:10px 14px;font-size:13px;font-weight:700;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;box-shadow:0 8px 32px rgba(0,0,0,.5);opacity:.92;`
        ghost.textContent = opp.name
        document.body.appendChild(ghost)
        dragState.current = opp
      }
      if (ghost) {
        ghost.style.left = (mv.clientX + 12) + 'px'
        ghost.style.top  = (mv.clientY - 16) + 'px'
      }
      // highlight target column
      document.querySelectorAll('[data-stage-drop]').forEach(col => {
        const rect = col.getBoundingClientRect()
        const over = mv.clientX >= rect.left && mv.clientX <= rect.right &&
                     mv.clientY >= rect.top  && mv.clientY <= rect.bottom
        col.style.background = over ? 'rgba(79,142,247,0.07)' : ''
        col.style.outline    = over ? '2px dashed var(--accent)' : ''
      })
    }

    const onUp = (uv) => {
      if (ghost) { ghost.remove(); ghost = null }
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      // find drop target
      document.querySelectorAll('[data-stage-drop]').forEach(col => {
        col.style.background = ''
        col.style.outline = ''
        const rect = col.getBoundingClientRect()
        if (uv.clientX >= rect.left && uv.clientX <= rect.right &&
            uv.clientY >= rect.top  && uv.clientY <= rect.bottom) {
          const targetStage = col.getAttribute('data-stage-drop')
          if (targetStage && targetStage !== opp.stage) {
            onStageDrop(opp.id, targetStage)
          }
        }
      })
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  return (
    <div
      onMouseDown={handleMouseDown}
      onClick={() => { if (!wasDragged.current) onClick(opp) }}
      style={{ background: 'var(--surface-2)', border: `1px solid ${stage.color}25`, borderRadius: 10, padding: '12px 14px', cursor: 'grab', marginBottom: 8, transition: 'all 0.15s', userSelect: 'none' }}
      onMouseEnter={e => e.currentTarget.style.borderColor = stage.color + '60'}
      onMouseLeave={e => e.currentTarget.style.borderColor = stage.color + '25'}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{opp.name}</div>
      <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 8 }}>{opp.client_name}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
        <span style={{ color: 'var(--success)', fontFamily: "'Space Mono', monospace" }}>{opp.expected_revenue ? fmtCurrency(opp.expected_revenue) : '—'}</span>
        <span style={{ color: stage.color, fontWeight: 700 }}>{opp.probability}%</span>
      </div>
      {opp.expected_close_date && (
        <div style={{ fontSize: 11, color: new Date(opp.expected_close_date) < new Date() ? 'var(--danger)' : 'var(--text-2)', marginTop: 4 }}>
          📅 {fmtDate(opp.expected_close_date)}
        </div>
      )}
      {opp.owner_name && <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>👤 {opp.owner_name}</div>}
    </div>
  )
}

function OppFormModal({ opp, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!opp?.id
  const [form, setForm] = useState({
    name: opp?.name || '',
    client_id:   opp?.client_id   || '',
    client_name: opp?.client_name || '',
    stage: opp?.stage || 'lead',
    probability: opp?.probability || 50,
    expected_revenue: opp?.expected_revenue || '',
    expected_margin_pct: opp?.expected_margin_pct || '',
    expected_hours: opp?.expected_hours || '',
    expected_close_date: opp?.expected_close_date || '',
    expected_start_date: opp?.expected_start_date || '',
    expected_duration_weeks: opp?.expected_duration_weeks || '',
    contact_name: opp?.contact_name || '',
    contact_email: opp?.contact_email || '',
    description: opp?.description || '',
    notes: opp?.notes || '',
    lost_reason: opp?.lost_reason || '',
  })

  const STAGE_PROB = { lead: 10, qualification: 25, proposal: 50, negotiation: 75, won: 100, lost: 0 }
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const { mutate, isPending } = useMutation({
    mutationFn: (data) => isEdit ? api.patch(`/pipeline/${opp.id}`, data) : api.post('/pipeline', data),
    onSuccess: () => { qc.invalidateQueries(['pipeline']); qc.invalidateQueries(['clients']); qc.invalidateQueries(['client-detail']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open title={isEdit ? `Editar: ${opp.name}` : 'Nueva Oportunidad'} onClose={onClose} width={620}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Nombre *</label>
          <input value={form.name} onChange={set('name')} style={fs} placeholder="Proyecto de migración cloud" />
        </div>
        <div>
          <label style={ls}>Cliente *</label>
          <ClientSelect
            value={form.client_id}
            onChange={(id, client) => setForm(f => ({ ...f, client_id: id, client_name: client ? client.name : '' }))}
            style={fs}
          />
        </div>
        <div>
          <label style={ls}>Contacto</label>
          <input value={form.contact_name} onChange={set('contact_name')} style={fs} placeholder="Juan García" />
        </div>
        <div>
          <label style={ls}>Etapa</label>
          <select value={form.stage} onChange={e => { setForm(f => ({ ...f, stage: e.target.value, probability: STAGE_PROB[e.target.value] || f.probability })) }} style={fs}>
            {STAGES.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Probabilidad %</label>
          <input type="number" min="0" max="100" value={form.probability} onChange={set('probability')} style={fs} />
        </div>
        <div>
          <label style={ls}>Revenue esperado (€)</label>
          <input type="number" value={form.expected_revenue} onChange={set('expected_revenue')} style={fs} placeholder="0" />
        </div>
        <div>
          <label style={ls}>Margen esperado %</label>
          <input type="number" value={form.expected_margin_pct} onChange={set('expected_margin_pct')} style={fs} placeholder="25" />
        </div>
        <div>
          <label style={ls}>Horas estimadas</label>
          <input type="number" value={form.expected_hours} onChange={set('expected_hours')} style={fs} placeholder="0" />
        </div>
        <div>
          <label style={ls}>Duración (semanas)</label>
          <input type="number" value={form.expected_duration_weeks} onChange={set('expected_duration_weeks')} style={fs} placeholder="0" />
        </div>
        <div>
          <label style={ls}>Fecha cierre estimada</label>
          <input type="date" value={form.expected_close_date} onChange={set('expected_close_date')} style={fs} />
        </div>
        <div>
          <label style={ls}>Inicio estimado</label>
          <input type="date" value={form.expected_start_date} onChange={set('expected_start_date')} style={fs} />
        </div>
        {(form.stage === 'lost') && (
          <div style={{ gridColumn: '1/-1' }}>
            <label style={ls}>Motivo de pérdida</label>
            <input value={form.lost_reason} onChange={set('lost_reason')} style={fs} placeholder="Precio, competencia..." />
          </div>
        )}
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Descripción</label>
          <textarea value={form.description} onChange={set('description')} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder="Descripción del proyecto..." />
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name || !form.client_id} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Crear oportunidad'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function OppDetailModal({ opp, onClose, onEdit }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [comment, setComment] = useState('')

  const { data: activities = [] } = useQuery({
    queryKey: ['opp-activities', opp.id],
    queryFn: () => api.get(`/pipeline/${opp.id}/activities`).then(r => r.data),
  })

  const { mutate: addActivity } = useMutation({
    mutationFn: () => api.post(`/pipeline/${opp.id}/activities`, { type: 'note', content: comment }),
    onSuccess: () => { qc.invalidateQueries(['opp-activities', opp.id]); setComment('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: del } = useMutation({
    mutationFn: () => api.delete(`/pipeline/${opp.id}`),
    onSuccess: () => { qc.invalidateQueries(['pipeline']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: convert, isPending: converting } = useMutation({
    mutationFn: () => api.post(`/pipeline/${opp.id}/convert`),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['pipeline'] })
      toast.success(`✅ Proyecto ${r.data.project_code} creado correctamente`)
      onClose()
    },
    onError: e => toast.error(extractErr(e, 'Error al convertir')),
  })

  const stage = STAGES.find(s => s.id === opp.stage) || STAGES[0]

  return (
    <Modal open title={opp.code + ' — ' + opp.name} onClose={onClose} width={640}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <span style={{ fontSize: 12, fontWeight: 700, padding: '3px 10px', borderRadius: 20, background: stage.color + '20', color: stage.color, border: `1px solid ${stage.color}40`, textTransform: 'uppercase' }}>{stage.label}</span>
        <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{opp.probability}% probabilidad</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Cliente', value: opp.client_name },
          { label: 'Revenue', value: opp.expected_revenue ? fmtCurrency(opp.expected_revenue) : '—' },
          { label: 'Ponderado', value: fmtCurrency(opp.weighted_revenue) },
          { label: 'Cierre estimado', value: opp.expected_close_date ? fmtDate(opp.expected_close_date) : '—' },
          { label: 'Duración', value: opp.expected_duration_weeks ? `${opp.expected_duration_weeks} semanas` : '—' },
          { label: 'Responsable', value: opp.owner_name || '—' },
        ].map(({ label, value }) => (
          <div key={label} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 3 }}>{label}</div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{value}</div>
          </div>
        ))}
      </div>
      {opp.description && <p style={{ color: 'var(--text-2)', fontSize: 13, marginBottom: 16, lineHeight: 1.6 }}>{opp.description}</p>}

      {/* Activities */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Actividad</div>
        <div style={{ maxHeight: 200, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
          {activities.map(a => (
            <div key={a.id} style={{ padding: '8px 12px', background: 'var(--surface-3)', borderRadius: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 3 }}>{a.user_name} · {a.created_at}</div>
              <div style={{ fontSize: 13 }}>{a.content}</div>
            </div>
          ))}
          {activities.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Sin actividad registrada</div>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input value={comment} onChange={e => setComment(e.target.value)} placeholder="Añadir nota..."
            style={{ flex: 1, background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit' }}
            onKeyDown={e => e.key === 'Enter' && comment && addActivity()} />
          <Button size="sm" onClick={() => addActivity()} disabled={!comment}>Añadir</Button>
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button variant="danger" size="sm" onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta oportunidad?', onConfirm: () => del(), danger: true }) }}>Eliminar</Button>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {!opp.project_id && opp.stage !== 'won' && opp.stage !== 'lost' && (
            <Button
              onClick={() => { openConfirmGlobal({ message: `¿Convertir "${opp.name}" en proyecto?\nSe creará un nuevo proyecto con los datos de esta oportunidad.`, onConfirm: () => convert() }) }}
              disabled={converting}
              loading={converting}
              style={{ background: 'var(--success)', border: 'none', color: '#fff' }}>
              🚀 Convertir a proyecto
            </Button>
          )}
          {opp.project_id && (
            <span style={{ fontSize: 12, color: 'var(--success)', fontWeight: 600 }}>
              ✅ Vinculado a proyecto
            </span>
          )}
          <Button variant="secondary" onClick={onClose}>Cerrar</Button>
          <Button onClick={() => { onClose(); onEdit(opp) }}>✏️ Editar</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function PipelinePage() {
  const t = useAppT()
  const { _hasRole } = useAuth()
  const qc = useQueryClient()
  const [view, setView] = useState('kanban')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(null)
  const [detail, setDetail] = useState(null)
  const [stageFilter, setStageFilter] = useState('')
  const toast = useToast()

  const { data: pipelineData, isLoading } = useQuery({
    queryKey: ['pipeline'],
    queryFn: () => api.get('/pipeline/pipeline').then(r => r.data),
  })

  const { data: allOpps = [] } = useQuery({
    queryKey: ['pipeline', stageFilter],
    queryFn: () => api.get('/pipeline', { params: stageFilter ? { stage: stageFilter } : {} }).then(r => r.data),
    enabled: view === 'list',
  })

  const { mutate: moveStage } = useMutation({
    mutationFn: ({ id, stage }) => api.patch(`/pipeline/${id}`, { stage }),
    onSuccess: () => qc.invalidateQueries(['pipeline']),
    onError: e => toast.error(extractErr(e, 'Error al mover oportunidad')),
  })

  const handleStageDrop = useCallback((oppId, targetStage) => {
    moveStage({ id: oppId, stage: targetStage })
  }, [moveStage])

  const summary = pipelineData?.summary || {}
  const stages = pipelineData?.stages || {}

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<Megaphone size={18} />}
        title={t('pipeline.title')}
        subtitle={t('pipeline.subtitle')}
        actions={
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ display: 'flex', background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, overflow: 'hidden' }}>
              {[['kanban', '⊞'], ['list', '☰']].map(([v, icon]) => (
                <button key={v} onClick={() => setView(v)} style={{ padding: '7px 14px', background: view === v ? 'var(--accent-muted)' : 'transparent', border: 'none', color: view === v ? 'var(--accent)' : 'var(--text-2)', fontSize: 14, cursor: 'pointer', fontFamily: 'inherit' }}>{icon}</button>
              ))}
            </div>
            <Button onClick={() => setShowCreate(true)} icon="＋">Nueva oportunidad</Button>
          </div>
        }
      />

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 24, flexWrap: 'wrap' }}>
        {[
          { label: 'Pipeline ponderado', value: fmtCurrency(summary.total_pipeline_weighted || 0), color: 'var(--accent)', icon: '💰' },
          { label: 'Ganado este año', value: fmtCurrency(summary.won_ytd || 0), color: 'var(--success)', icon: '🏆' },
          { label: 'Oportunidades abiertas', value: summary.open_opportunities || 0, color: 'var(--text-2)', icon: '📋' },
          { label: 'Tasa de éxito', value: `${summary.win_rate || 0}%`, color: summary.win_rate >= 50 ? 'var(--success)' : 'var(--warning)', icon: '🎯' },
        ].map(({ label, value, color, icon }) => (
          <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, padding: '14px 18px', flex: 1, minWidth: 140 }}>
            <div style={{ fontSize: 18, marginBottom: 6 }}>{icon}</div>
            <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "'Space Mono', monospace", color }}>{value}</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      {isLoading ? <Spinner /> : !isLoading && summary.open_opportunities === 0 && !Object.values(stages).some(s => s.count > 0) ? (
        <EmptyState icon="📣" title="No hay oportunidades en el pipeline" description="Crea tu primera oportunidad para comenzar a gestionar el proceso de ventas." ctaLabel="Nueva oportunidad" onCta={() => document.querySelector('[data-action=new-opp]')?.click()} />
      ) : view === 'kanban' ? (
      <div style={{ display: 'flex', gap: 14, overflowX: 'auto', paddingBottom: 16 }}>
          {ACTIVE_STAGES.map(stage => {
            const s = stages[stage.id] || { opportunities: [], count: 0, total_revenue: 0, weighted_revenue: 0 }
            return (
              <div key={stage.id} style={{ minWidth: 240, flex: 1 }}
                data-stage-drop={stage.id}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 8, border: `1px solid ${stage.color}30` }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: stage.color }} />
                  <span style={{ fontSize: 12, fontWeight: 700, color: stage.color, textTransform: 'uppercase', letterSpacing: '0.06em', flex: 1 }}>{stage.label}</span>
                  <span style={{ fontSize: 11, background: 'var(--surface-4)', color: 'var(--text-2)', borderRadius: 10, padding: '1px 7px' }}>{s.count}</span>
                </div>
                {s.count > 0 && (
                  <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 8, paddingLeft: 4 }}>
                    {fmtCurrency(s.weighted_revenue)} ponderado
                  </div>
                )}
                {s.opportunities.map(opp => (
                  <OppCard key={opp.id} opp={opp} onClick={setDetail} onStageDrop={handleStageDrop} />
                ))}
                {s.count === 0 && <div style={{ fontSize: 12, color: 'var(--text-3)', textAlign: 'center', padding: '20px 0' }}>Sin oportunidades</div>}
              </div>
            )
          })}
        </div>
      ) : (
        <div>
          <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
            <select value={stageFilter} onChange={e => setStageFilter(e.target.value)}
              style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="">Todas las etapas</option>
              {STAGES.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </div>
          <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 100px', gap: 16, padding: '10px 20px', borderBottom: '1px solid #1e2d45', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              <span>Oportunidad</span><span>Etapa</span><span>Revenue</span><span>Ponderado</span><span>Cierre</span><span></span>
            </div>
            {allOpps.map(opp => {
              const stage = STAGES.find(s => s.id === opp.stage) || STAGES[0]
              return (
                <div key={opp.id} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 100px', gap: 16, padding: '12px 20px', borderBottom: '1px solid #1e2d4530', alignItems: 'center', cursor: 'pointer' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  onClick={() => setDetail(opp)}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{opp.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{opp.client_name}</div>
                  </div>
                  <span style={{ fontSize: 12, color: stage.color, fontWeight: 700 }}>{stage.label}</span>
                  <span style={{ fontSize: 12, fontFamily: "'Space Mono', monospace" }}>{opp.expected_revenue ? fmtCurrency(opp.expected_revenue) : '—'}</span>
                  <span style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: 'var(--success)' }}>{fmtCurrency(opp.weighted_revenue)}</span>
                  <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{opp.expected_close_date ? fmtDate(opp.expected_close_date) : '—'}</span>
                  <button onClick={e => { e.stopPropagation(); setEditing(opp) }} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>Editar</button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {showCreate && <OppFormModal onClose={() => setShowCreate(false)} />}
      {editing && <OppFormModal opp={editing} onClose={() => setEditing(null)} />}
      {detail && !editing && <OppDetailModal opp={detail} onClose={() => setDetail(null)} onEdit={(o) => { setDetail(null); setEditing(o) }} />}
    </div>
  )
}