/**
 * Puesta en marcha de la empresa (revisión 2026-11, lo que contecmind tenía).
 *
 * Cada punto lo mide el servidor sobre los datos de la empresa
 * (`GET /settings/setup-checklist`); aquí solo se enseña y se lleva a la
 * pantalla donde se resuelve.
 */
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAppLang } from '../../i18n/AppLangContext'
import { settingsApi } from '../../services/api'
import './PuestaEnMarchaSection.css'

type Punto = { id: string; done: boolean; required: boolean; link: string | null; measured: Record<string, unknown> }
type Lista = { items: Punto[]; required_done: number; required_total: number; recommended_done: number; recommended_total: number }

export default function PuestaEnMarchaSection() {
  const { t } = useAppLang()
  const navigate = useNavigate()
  const { data, isLoading } = useQuery<Lista>({
    queryKey: ['setup-checklist'],
    queryFn: () => settingsApi.setupChecklist().then(r => r.data as Lista),
  })
  if (isLoading || !data) return <div className="u-text3-sm">…</div>
  const fila = (p: Punto) => (
    <div key={p.id} className="puenmase-row-1">
      <span className="puenmase-txt-2" aria-hidden style={{ color: p.done ? 'var(--success)' : p.required ? 'var(--warning)' : 'var(--text-3)' }}>{p.done ? '✓' : '○'}</span>
      <div className="u-flex1">
        <div className="u-600">{t('puesta.' + p.id)}</div>
        <div className="u-text3-xs">{t('puesta.' + p.id + '_ayuda')}</div>
      </div>
      <span className="puenmase-txt-3" style={{ color: p.done ? 'var(--success)' : 'var(--text-3)' }}>{t(p.done ? 'puesta.hecho' : 'puesta.pendiente')}</span>
      {!p.done && p.link && (
        <button type="button" onClick={() => navigate(p.link as string)}
          className="puenmase-box-1">
          {t('puesta.configurar')}
        </button>
      )}
    </div>
  )
  return (
    <div>
      <p className="u-text2-sm">{t('puesta.intro')}</p>
      <h3 className="puenmase-txt-1">{t('puesta.necesarios', { hechos: data.required_done, total: data.required_total })}</h3>
      <div className="puenmase-caja">{data.items.filter(p => p.required).map(fila)}</div>
      <h3 className="puenmase-txt-1">{t('puesta.recomendados', { hechos: data.recommended_done, total: data.recommended_total })}</h3>
      <div className="puenmase-caja">{data.items.filter(p => !p.required).map(fila)}</div>
    </div>
  )
}
