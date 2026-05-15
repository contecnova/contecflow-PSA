import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import axios from 'axios'
import { useAppT } from '../i18n/AppLangContext'

const API = axios.create({ baseURL: '/api/v1', timeout: 30000 })

export default function PortalPublicViewPage() {
  const t = useAppT()
  const { token } = useParams()
  const { data, isLoading, error } = useQuery({
    queryKey: ['portal-public-view', token],
    queryFn: () => API.get(`/portal/view/${token}`).then(r => r.data),
    enabled: !!token,
  })

  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--surface-0)', color: 'var(--text-1)', fontFamily: 'var(--font-sans)' }}>
        {t('portal_public.loading')}
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--surface-0)', color: 'var(--text-1)', fontFamily: 'var(--font-sans)' }}>
        <div style={{ maxWidth: 520, padding: 24, border: '1px solid var(--surface-4)', borderRadius: 12, background: 'var(--surface-2)' }}>
          <h1 style={{ marginTop: 0 }}>{t('portal_public.invalid_link_title')}</h1>
          <p style={{ color: 'var(--text-2)' }}>{t('portal_public.invalid_link_message')}</p>
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
          <div style={{ fontSize: "var(--text-sm)", letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--accent)', fontWeight: 700 }}>{t('portal_public.public_status')}</div>
          <h1 style={{ margin: '8px 0 6px', fontSize: "var(--text-34)" }}>{project.name || t('portal_public.project_fallback')}</h1>
          <div style={{ color: 'var(--text-2)', fontSize: "var(--text-md)" }}>{t('portal_public.code_label')}: {project.code || '—'} · {t('portal_public.status_label')}: {project.status || '—'}</div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
          <div style={{ border: '1px solid var(--surface-4)', borderRadius: 12, padding: 16, background: 'var(--surface-2)' }}>
            <div style={{ fontSize: "var(--text-lg)", fontWeight: 700, marginBottom: 12 }}>{t('portal_public.milestones')}</div>
            {milestones.length === 0 ? (
              <div style={{ color: 'var(--text-2)', fontSize: "var(--text-base)" }}>{t('portal_public.no_milestones')}</div>
            ) : (
              milestones.map(m => (
                <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-base)", padding: '8px 0', borderBottom: '1px solid var(--surface-4)' }}>
                  <span>{m.name}</span>
                  <span style={{ color: m.is_completed ? 'var(--success)' : 'var(--warning)' }}>{m.is_completed ? t('portal_public.completed') : (m.due_date || t('portal_public.pending'))}</span>
                </div>
              ))
            )}
          </div>

          <div style={{ border: '1px solid var(--surface-4)', borderRadius: 12, padding: 16, background: 'var(--surface-2)' }}>
            <div style={{ fontSize: "var(--text-lg)", fontWeight: 700, marginBottom: 12 }}>{t('portal_public.deliverables')}</div>
            {deliverables.length === 0 ? (
              <div style={{ color: 'var(--text-2)', fontSize: "var(--text-base)" }}>{t('portal_public.no_deliverables')}</div>
            ) : (
              deliverables.map(d => (
                <div key={d.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-base)", padding: '8px 0', borderBottom: '1px solid var(--surface-4)' }}>
                  <span>{d.name}</span>
                  <span style={{ color: d.status === 'approved' ? 'var(--success)' : 'var(--accent)' }}>{d.status || t('portal_public.deliverable_pending')}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
