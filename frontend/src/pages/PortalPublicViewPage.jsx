import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import axios from 'axios'

const API = axios.create({ baseURL: '/api/v1' })

export default function PortalPublicViewPage() {
  const { token } = useParams()
  const { data, isLoading, error } = useQuery({
    queryKey: ['portal-public-view', token],
    queryFn: () => API.get(`/portal/view/${token}`).then(r => r.data),
    enabled: !!token,
  })

  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#0b1220', color: '#e5edf8', fontFamily: "'Inter', system-ui, sans-serif" }}>
        Cargando estado del proyecto...
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#0b1220', color: '#e5edf8', fontFamily: "'Inter', system-ui, sans-serif" }}>
        <div style={{ maxWidth: 520, padding: 24, border: '1px solid #1e2d45', borderRadius: 12, background: '#111a2b' }}>
          <h1 style={{ marginTop: 0 }}>Enlace no valido</h1>
          <p style={{ color: '#9eb0c8' }}>Este enlace ha expirado o no existe.</p>
        </div>
      </div>
    )
  }

  const project = data.project || {}
  const milestones = data.milestones || []
  const deliverables = data.deliverables || []

  return (
    <div style={{ minHeight: '100vh', background: 'radial-gradient(circle at top, #14233e, #0b1220)', color: '#e5edf8', fontFamily: "'Inter', system-ui, sans-serif", padding: '32px 20px' }}>
      <div style={{ maxWidth: 980, margin: '0 auto' }}>
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 12, letterSpacing: '.08em', textTransform: 'uppercase', color: '#7dd3fc', fontWeight: 700 }}>Estado publico</div>
          <h1 style={{ margin: '8px 0 6px', fontSize: 34 }}>{project.name || 'Proyecto'}</h1>
          <div style={{ color: '#9eb0c8', fontSize: 14 }}>Codigo: {project.code || '—'} · Estado: {project.status || '—'}</div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
          <div style={{ border: '1px solid #22324f', borderRadius: 12, padding: 16, background: '#101b2f' }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Hitos</div>
            {milestones.length === 0 ? (
              <div style={{ color: '#9eb0c8', fontSize: 13 }}>Sin hitos publicados.</div>
            ) : (
              milestones.map(m => (
                <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '8px 0', borderBottom: '1px solid #1b2a46' }}>
                  <span>{m.name}</span>
                  <span style={{ color: m.is_completed ? '#22c55e' : '#f59e0b' }}>{m.is_completed ? 'Completado' : (m.due_date || 'Pendiente')}</span>
                </div>
              ))
            )}
          </div>

          <div style={{ border: '1px solid #22324f', borderRadius: 12, padding: 16, background: '#101b2f' }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Entregables</div>
            {deliverables.length === 0 ? (
              <div style={{ color: '#9eb0c8', fontSize: 13 }}>Sin entregables publicados.</div>
            ) : (
              deliverables.map(d => (
                <div key={d.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '8px 0', borderBottom: '1px solid #1b2a46' }}>
                  <span>{d.name}</span>
                  <span style={{ color: d.status === 'approved' ? '#22c55e' : '#93c5fd' }}>{d.status || 'pending'}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
