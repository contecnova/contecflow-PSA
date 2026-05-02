import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import axios from 'axios'

const API = axios.create({ baseURL: '/api/v1', timeout: 30000 })

export default function PortalPublicViewPage() {
  const { token } = useParams()
  const { data, isLoading, error } = useQuery({
    queryKey: ['portal-public-view', token],
    queryFn: () => API.get(`/portal/view/${token}`).then(r => r.data),
    enabled: !!token,
  })

  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--surface-0)', color: 'var(--text-1)', fontFamily: 'var(--font-sans)' }}>
        Cargando estado del proyecto...
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--surface-0)', color: 'var(--text-1)', fontFamily: 'var(--font-sans)' }}>
        <div style={{ maxWidth: 520, padding: 24, border: '1px solid var(--surface-4)', borderRadius: 12, background: 'var(--surface-2)' }}>
          <h1 style={{ marginTop: 0 }}>Enlace no valido</h1>
          <p style={{ color: 'var(--text-2)' }}>Este enlace ha expirado o no existe.</p>
        </div>
      </div>
    )
  }

  const project = data.project || {}
  const milestones = data.milestones || []
  const deliverables = data.deliverables || []

  return (
    <div style={{ minHeight: '100vh', background: 'var(--surface-0)', color: 'var(--text-1)', fontFamily: 'var(--font-sans)', padding: '32px 20px' }}>
      <div style={{ maxWidth: 980, margin: '0 auto' }}>
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: "var(--text-sm)", letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--accent)', fontWeight: 700 }}>Estado publico</div>
          <h1 style={{ margin: '8px 0 6px', fontSize: "var(--text-34)" }}>{project.name || 'Proyecto'}</h1>
          <div style={{ color: 'var(--text-2)', fontSize: "var(--text-md)" }}>Codigo: {project.code || '—'} · Estado: {project.status || '—'}</div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
          <div style={{ border: '1px solid var(--surface-4)', borderRadius: 12, padding: 16, background: 'var(--surface-2)' }}>
            <div style={{ fontSize: "var(--text-lg)", fontWeight: 700, marginBottom: 12 }}>Hitos</div>
            {milestones.length === 0 ? (
              <div style={{ color: 'var(--text-2)', fontSize: "var(--text-base)" }}>Sin hitos publicados.</div>
            ) : (
              milestones.map(m => (
                <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-base)", padding: '8px 0', borderBottom: '1px solid var(--surface-4)' }}>
                  <span>{m.name}</span>
                  <span style={{ color: m.is_completed ? 'var(--success)' : 'var(--warning)' }}>{m.is_completed ? 'Completado' : (m.due_date || 'Pendiente')}</span>
                </div>
              ))
            )}
          </div>

          <div style={{ border: '1px solid var(--surface-4)', borderRadius: 12, padding: 16, background: 'var(--surface-2)' }}>
            <div style={{ fontSize: "var(--text-lg)", fontWeight: 700, marginBottom: 12 }}>Entregables</div>
            {deliverables.length === 0 ? (
              <div style={{ color: 'var(--text-2)', fontSize: "var(--text-base)" }}>Sin entregables publicados.</div>
            ) : (
              deliverables.map(d => (
                <div key={d.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-base)", padding: '8px 0', borderBottom: '1px solid var(--surface-4)' }}>
                  <span>{d.name}</span>
                  <span style={{ color: d.status === 'approved' ? 'var(--success)' : 'var(--accent)' }}>{d.status || 'pending'}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
