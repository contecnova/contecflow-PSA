import type { CSSProperties } from 'react'
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import axios from 'axios'
import { LangContext, TextosDeInterfazDelPortal, useLang, useEtiquetaEstado } from './portal-client/portalClientContext'
import { PORTAL_LANGUAGES } from '../i18n/portalTranslations'
import { fmtDate, fijarIdiomaDeFormato } from '../utils/helpers'
import { EmptyState } from '../components/ui'
import { Flag, Package } from 'lucide-react'
import { API_BASE_URL } from '../services/api/urls'
import './PortalPublicViewPage.css'

// Instancia propia y no el cliente de la app: vista pública por enlace, sin
// cookies de sesión ni refresco.
const API = axios.create({ baseURL: API_BASE_URL, timeout: 30000 })

// TODO type: backend portal/view response shape — currently consumed as unknown
interface PortalPublicView {
  project?: { id?: string; name?: string; code?: string; status?: string }
  milestones?: Array<{ id: string; name: string; is_completed?: boolean; due_date?: string | null }>
  deliverables?: Array<{ id: string; name: string; status?: string | null }>
}

/** Idioma de la vista pública (16-11-2026): la de un enlace no tiene sesión,
 *  así que se usa el último idioma del portal en este navegador o el del
 *  navegador, si es uno de los 8 del portal; si no, castellano. */
function idiomaDeLaVistaPublica(): string {
  const valido = (c?: string | null) => !!c && PORTAL_LANGUAGES.some(l => l.code === c)
  try {
    const guardado = localStorage.getItem('portal_lang')
    if (valido(guardado)) return guardado as string
  } catch { /* almacenamiento bloqueado */ }
  const nav = (typeof navigator !== 'undefined' ? navigator.language : 'es').slice(0, 2)
  return valido(nav) ? nav : 'es'
}

export default function PortalPublicViewPage(): JSX.Element {
  const idioma = idiomaDeLaVistaPublica()
  fijarIdiomaDeFormato(idioma)
  useEffect(() => () => fijarIdiomaDeFormato(null), [])
  return (
    <LangContext.Provider value={idioma}>
      <TextosDeInterfazDelPortal>
        <VistaPublica />
      </TextosDeInterfazDelPortal>
    </LangContext.Provider>
  )
}

function VistaPublica(): JSX.Element {
  const t = useLang()
  const etiquetaEstado = useEtiquetaEstado()
  const { token } = useParams<{ token: string }>()
  const { data, isLoading, error } = useQuery<PortalPublicView>({
    queryKey: ['portal-public-view', token],
    // Auditoría 2026-11: la respuesta es {data: {...}, meta}; se leía `r.data.project`
    // y la página salía vacía.
    queryFn: () => API.get(`/portal/view/${token}`).then(r => (r.data?.data ?? r.data) as PortalPublicView),
    enabled: !!token,
  })

  if (isLoading) {
    return (
      <div className="ppv-grid">
        {t('portal_public.loading')}
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="ppv-grid">
        <div className="ppv-card">
          <h1 className="ppv-title">{t('portal_public.invalid_link_title')}</h1>
          <p className="u-text2">{t('portal_public.invalid_link_message')}</p>
        </div>
      </div>
    )
  }

  const project = data.project || {}
  const milestones = data.milestones || []
  const deliverables = data.deliverables || []

  return (
    <div className="ppv-card-2">
      <div className="ppv-box">
        <div className="ppv-text">
          <div className="ppv-text-accent-sm-strong">{t('portal_public.public_status')}</div>
          <h1 className="ppv-title-34">{project.name || t('portal_public.project_fallback')}</h1>
          <div className="ppv-text-muted-md">{t('portal_public.code_label')}: {project.code || '—'} · {t('portal_public.status_label')}: {project.status ? etiquetaEstado(project.status) : '—'}</div>
        </div>

        <div className="ppv-grid-2">
          <div className="ppv-card-3">
            <div className="ppv-text-lg-strong">{t('portal_public.milestones')}</div>
            {milestones.length === 0 ? (
              <EmptyState icon={<Flag size={28} />} title={t('portal_public.no_milestones')} />
            ) : (
              milestones.map(m => (
                <div className="ppv-row" key={m.id}>
                  <span>{m.name}</span>
                  <span className="ppv-text-2" style={{ '--ppv-text-2-color': m.is_completed ? 'var(--success)' : 'var(--warning)' } as CSSProperties}>{m.is_completed ? t('portal_public.completed') : (m.due_date ? fmtDate(m.due_date) : t('portal_public.pending'))}</span>
                </div>
              ))
            )}
          </div>

          <div className="ppv-card-3">
            <div className="ppv-text-lg-strong">{t('portal_public.deliverables')}</div>
            {deliverables.length === 0 ? (
              <EmptyState icon={<Package size={28} />} title={t('portal_public.no_deliverables')} />
            ) : (
              deliverables.map(d => (
                <div className="ppv-row" key={d.id}>
                  <span>{d.name}</span>
                  <span className="ppv-text-3" style={{ '--ppv-text-3-color': d.status === 'approved' ? 'var(--success)' : 'var(--accent)' } as CSSProperties}>{d.status ? etiquetaEstado(d.status) : t('portal_public.deliverable_pending')}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
