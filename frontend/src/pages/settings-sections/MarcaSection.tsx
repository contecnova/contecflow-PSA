/**
 * Marca de la empresa en los documentos (revisión 2026-11).
 *
 * `org_brandings` tenía API (`/orgs/{id}/branding`) y ninguna pantalla. Lo que
 * la lee, medido: los PDF (facturas, informes) con el nombre y tres colores
 * (`app/services/_pdf_marca.py`). Por eso aquí sólo están esos cuatro campos:
 * los demás de la API no los usa nada y editarlos no cambiaría nada.
 */
import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../../context/AuthContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { settingsApi } from '../../services/api'
import { extractErr } from '../../utils/helpers'
import './MarcaSection.css'

type Marca = { app_name?: string; primary_color?: string | null; accent_color?: string | null; text_color?: string | null; is_default?: boolean }
const CAMPOS = ['app_name', 'primary_color', 'accent_color', 'text_color'] as const

export default function MarcaSection() {
  const { t } = useAppLang()
  const { user } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const org = user?.organization_id as string | undefined
  const { data } = useQuery<Marca>({
    queryKey: ['branding', org], enabled: !!org,
    queryFn: () => settingsApi.branding(org as string).then(r => r.data as Marca),
  })
  const [form, setForm] = useState<Record<string, string>>({})
  useEffect(() => {
    if (data) setForm(Object.fromEntries(CAMPOS.map(c => [c, (data[c] as string) || ''])))
  }, [data])
  const guardar = async () => {
    try {
      const limpio = Object.fromEntries(Object.entries(form).filter(([, v]) => v.trim() !== ''))
      await settingsApi.saveBranding(org as string, limpio)
      toast.success(t('marca.guardada')); qc.invalidateQueries({ queryKey: ['branding', org] })
    } catch (e) { toast.error(extractErr(e, 'Error')) }
  }
  const restablecer = async () => {
    try { await settingsApi.resetBranding(org as string); qc.invalidateQueries({ queryKey: ['branding', org] }) }
    catch (e) { toast.error(extractErr(e, 'Error')) }
  }
  if (!org || !data) return null
  return (
    <div className="marcsect-grid-1">
      <p className="marcsect-box-1">{t('marca.intro')}</p>
      <label className="marcsect-grid-2">
        {t('marca.nombre')}
        <input aria-label={t('marca.nombre')} value={form.app_name || ''} onChange={e => setForm(f => ({ ...f, app_name: e.target.value }))} className="marcsect-campo" />
      </label>
      {(['primary_color', 'accent_color', 'text_color'] as const).map(c => (
        <label key={c} className="marcsect-row-1">
          <input type="color" aria-label={t(`marca.${c}`)} value={/^#[0-9a-f]{6}$/i.test(form[c] || '') ? form[c] : '#000000'}
            onChange={e => setForm(f => ({ ...f, [c]: e.target.value }))} className="marcsect-box-2" />
          <input aria-label={t(`marca.${c}`)} value={form[c] || ''} placeholder="#RRGGBB" onChange={e => setForm(f => ({ ...f, [c]: e.target.value }))} className="marcsect-campo2" />
          {t(`marca.${c}`)}
        </label>
      ))}
      <div aria-hidden className="marcsect-box-3">
        <div className="marcsect-box-6" style={{ background: form.primary_color || '#1f2937', color: form.text_color || '#ffffff' }}>
          {form.app_name || data.app_name} · {t('marca.ejemplo_factura')}
        </div>
        <div className="marcsect-box-7" style={{ background: form.accent_color || 'var(--accent)' }} />
      </div>
      <div className="u-row-8">
        <button type="button" onClick={guardar} className="marcsect-box-4">{t('marca.guardar')}</button>
        {!data.is_default && (
          <button type="button" onClick={restablecer} className="marcsect-box-5">{t('marca.restablecer')}</button>
        )}
      </div>
    </div>
  )
}
