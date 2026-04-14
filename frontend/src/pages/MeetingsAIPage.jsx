import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const card = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }
const fs = { width: '100%', background: 'var(--surface-1)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }

const PLATFORMS = [
  { id: 'teams',  label: 'Microsoft Teams', icon: '💠' },
  { id: 'zoom',   label: 'Zoom',            icon: '📹' },
  { id: 'meet',   label: 'Google Meet',     icon: '🎥' },
  { id: 'slack',  label: 'Slack Huddle',    icon: '💬' },
  { id: 'presencial', label: 'Presencial',  icon: '👥' },
  { id: 'otro',   label: 'Otro',            icon: '🎙' },
]

const DEMO_TRANSCRIPT = `Pedro: Buenas, arrancamos. El objetivo de hoy es revisar el estado del Q3 y planificar el Q4.
María: Tengo los datos de rendimiento. Estamos al 78% de las entregas planificadas. Hay dos proyectos en riesgo.
Pedro: ¿Cuáles?
María: Alpha está retrasado por los problemas de infraestructura. Carlos, ¿puedes revisar eso esta semana?
Carlos: Sí, lo tengo en el radar. Lo resolveré antes del viernes.
Pedro: Bien. Y el proyecto Beta, necesitamos actualizar el contrato con el cliente antes del 30 de este mes. Ana, ¿puedes encargarte?
Ana: Confirmado, lo gestiono yo.
Pedro: Siguiente punto: el equipo necesita formación en las nuevas herramientas de testing. Luis, ¿coordinas tú con RRHH?
Luis: Sin problema, esta semana lo organizo.
Pedro: Resumiendo: Carlos revisa infraestructura de Alpha antes del viernes, Ana actualiza el contrato de Beta antes del 30, y Luis organiza la formación. Cerramos.`

function ProcessModal({ onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ title: '', transcript: '', platform: 'teams', participants: '', duration_minutes: '' })
  const s = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const { mutate: process, isPending } = useMutation({
    mutationFn: d => api.post('/meetings/process', d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['ai-meetings']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open title="Procesar reunión con IA" onClose={onClose} width={700}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Título *</label>
          <input value={form.title} onChange={s('title')} style={fs} placeholder="Sprint Review Q3 · Kickoff Proyecto Alpha..." />
        </div>

        <div>
          <label style={ls}>Plataforma</label>
          <select value={form.platform} onChange={s('platform')} style={fs}>
            {PLATFORMS.map(p => <option key={p.id} value={p.id}>{p.icon} {p.label}</option>)}
          </select>
        </div>

        <div>
          <label style={ls}>Duración (minutos)</label>
          <input type="number" value={form.duration_minutes} onChange={s('duration_minutes')} style={fs} placeholder="45" />
        </div>

        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Participantes (separados por coma)</label>
          <input value={form.participants} onChange={s('participants')} style={fs} placeholder="Pedro García, María López, Carlos Ruiz..." />
        </div>

        <div style={{ gridColumn: '1/-1' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
            <label style={{ ...ls, marginBottom: 0 }}>Transcripción *</label>
            <button onClick={() => setForm(f => ({ ...f, transcript: DEMO_TRANSCRIPT, title: f.title || 'Demo — Reunión Q3 Review', participants: 'Pedro García, María López, Carlos Ruiz, Ana Torres, Luis Vega' }))}
              style={{ background: 'transparent', border: 'none', fontSize: 11, color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit' }}>
              📋 Usar demo
            </button>
          </div>
          <textarea value={form.transcript} onChange={s('transcript')} rows={10}
            style={{ ...fs, resize: 'vertical', lineHeight: 1.5 }}
            placeholder="Pega aquí la transcripción completa de la reunión..." />
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button onClick={() => process(form)} disabled={isPending || !form.transcript.trim() || !form.title.trim()}>
          {isPending ? '⏳ Procesando con IA...' : '✨ Procesar con IA'}
        </Button>
      </div>
    </Modal>
  )
}

export default function MeetingsAIPage() {
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showProcess, setShowProcess] = useState(false)
  const [selected, setSelected] = useState(null)

  const { data: meetings = [], isLoading } = useQuery({
    queryKey: ['ai-meetings'],
    queryFn: () => api.get('/meetings').then(r => r.data),
  })
  const { data: detail } = useQuery({
    queryKey: ['ai-meeting', selected],
    queryFn: () => api.get(`/meetings/${selected}`).then(r => r.data),
    enabled: !!selected,
  })
  const { mutate: createTasks, isPending: creating } = useMutation({
    mutationFn: id => api.post(`/meetings/${id}/create-tasks`, {}).then(r => r.data),
    onSuccess: data => { qc.invalidateQueries(['ai-meeting', selected]); toast.success(`✅ ${data.tasks_created} tareas creadas en Clarive`) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const platCfg = p => PLATFORMS.find(x => x.id === p) || PLATFORMS[PLATFORMS.length - 1]

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        title="Meeting Assistant"
        subtitle="Transforma transcripciones en resúmenes, decisiones y tareas automáticamente"
        actions={<Button onClick={() => setShowProcess(true)}>＋ Procesar reunión</Button>}
      />

      {meetings.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24 }}>
          {[
            { icon: '🎙', label: 'Reuniones', value: meetings.length, color: 'var(--accent)' },
            { icon: '📋', label: 'Acciones totales', value: meetings.reduce((a, m) => a + (m.actions_count || 0), 0), color: 'var(--warning)' },
            { icon: '✅', label: 'Tareas creadas', value: meetings.reduce((a, m) => a + (m.created_actions || 0), 0), color: 'var(--success)' },
          ].map(k => (
            <div key={k.label} style={{ ...card, padding: '14px 18px', display: 'flex', gap: 12, alignItems: 'center' }}>
              <span style={{ fontSize: 24 }}>{k.icon}</span>
              <div>
                <div style={{ fontSize: 22, fontWeight: 800, color: k.color }}>{k.value}</div>
                <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{k.label}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 20 }}>
        {/* List */}
        <div>
          {isLoading ? <Spinner /> : meetings.length === 0 ? (
            <div style={{ ...card, padding: 32, textAlign: 'center' }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>🎙</div>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Sin reuniones procesadas</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 16 }}>Pega una transcripción y la IA extrae resumen, decisiones y tareas</div>
              <Button onClick={() => setShowProcess(true)}>Procesar primera reunión</Button>
            </div>
          ) : meetings.map(m => {
            const plat = platCfg(m.platform)
            return (
              <div key={m.id} onClick={() => setSelected(m.id)}
                style={{ ...card, padding: '14px 16px', marginBottom: 10, cursor: 'pointer', borderColor: selected === m.id ? 'var(--accent-glow)' : 'var(--surface-4)', background: selected === m.id ? 'var(--accent-muted)' : 'var(--surface-2)' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 8 }}>
                  <span style={{ fontSize: 18 }}>{plat.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.title}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{m.meeting_date?.slice(0, 10) || m.created_at?.slice(0, 10)}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12, background: m.status === 'done' ? 'var(--success-bg)' : 'var(--warning-bg)', color: m.status === 'done' ? 'var(--success)' : 'var(--warning)', fontWeight: 600 }}>
                    {m.status === 'done' ? '✅ Procesada' : '⏳ Procesando'}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{m.actions_count || 0} acciones</span>
                  {(m.created_actions || 0) > 0 && (
                    <span style={{ fontSize: 11, color: 'var(--success)' }}>{m.created_actions} tareas ↗</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Detail */}
        <div>
          {!selected ? (
            <div style={{ ...card, padding: 48, textAlign: 'center' }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🎙</div>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>Selecciona una reunión</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>O procesa una nueva transcripción para ver el análisis IA</div>
            </div>
          ) : !detail ? <Spinner /> : (
            <div>
              {/* Header */}
              <div style={{ ...card, padding: '18px 22px', marginBottom: 14 }}>
                <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 6 }}>{detail.title}</div>
                <div style={{ display: 'flex', gap: 14, fontSize: 12, color: 'var(--text-2)' }}>
                  {detail.platform && <span>{platCfg(detail.platform).icon} {platCfg(detail.platform).label}</span>}
                  {detail.duration_minutes && <span>⏱ {detail.duration_minutes} min</span>}
                  <span>📅 {detail.meeting_date?.slice(0, 10) || detail.created_at?.slice(0, 10)}</span>
                </div>
              </div>

              {/* Summary */}
              {detail.summary && (
                <div style={{ ...card, padding: '16px 20px', marginBottom: 14 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>📝 Resumen</div>
                  <div style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-2)' }}>{detail.summary}</div>
                </div>
              )}

              {/* Decisions */}
              {detail.decisions?.length > 0 && (
                <div style={{ ...card, padding: '16px 20px', marginBottom: 14 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
                    ✅ Decisiones ({detail.decisions.length})
                  </div>
                  {detail.decisions.map((d, i) => (
                    <div key={i} style={{ display: 'flex', gap: 10, padding: '8px 0', borderBottom: i < detail.decisions.length - 1 ? '1px solid #1e2d4530' : 'none', fontSize: 13 }}>
                      <span style={{ color: 'var(--success)', flexShrink: 0, marginTop: 1 }}>◆</span>
                      <span style={{ lineHeight: 1.5 }}>{d}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Actions */}
              {detail.actions?.length > 0 && (
                <div style={{ ...card, padding: '16px 20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      📋 Acciones ({detail.actions.length})
                    </div>
                    {detail.actions.some(a => !a.is_created) && (
                      <Button onClick={() => createTasks(selected)} disabled={creating}>
                        {creating ? 'Creando...' : '➕ Crear tareas en Clarive'}
                      </Button>
                    )}
                  </div>
                  {detail.actions.map(a => (
                    <div key={a.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 0', borderBottom: '1px solid #1e2d4530', alignItems: 'flex-start', gap: 12 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{a.description}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
                          {a.assignee_name && `👤 ${a.assignee_name}`}
                          {a.due_date_text && ` · 📅 ${a.due_date_text}`}
                          {a.priority && ` · ${a.priority}`}
                        </div>
                      </div>
                      <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 12, background: a.is_created ? 'var(--success-bg)' : 'var(--surface-3)', color: a.is_created ? 'var(--success)' : 'var(--text-2)', fontWeight: 600, flexShrink: 0 }}>
                        {a.is_created ? '✅ Creada' : 'Pendiente'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {showProcess && <ProcessModal onClose={() => setShowProcess(false)} />}
    </div>
  )
}
