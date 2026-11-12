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
  const campo = { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 10px', color: 'var(--text-1)', fontFamily: 'inherit', fontSize: 'var(--text-sm)' } as const
  return (
    <div style={{ display: 'grid', gap: 14, maxWidth: 640 }}>
      <p style={{ margin: 0, fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{t('marca.intro')}</p>
      <label style={{ display: 'grid', gap: 4, fontSize: 'var(--text-sm)' }}>
        {t('marca.nombre')}
        <input value={form.app_name || ''} onChange={e => setForm(f => ({ ...f, app_name: e.target.value }))} style={campo} />
      </label>
      {(['primary_color', 'accent_color', 'text_color'] as const).map(c => (
        <label key={c} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 'var(--text-sm)' }}>
          <input type="color" aria-label={t(`marca.${c}`)} value={/^#[0-9a-f]{6}$/i.test(form[c] || '') ? form[c] : '#000000'}
            onChange={e => setForm(f => ({ ...f, [c]: e.target.value }))} style={{ width: 40, height: 30, border: 'none', background: 'none' }} />
          <input value={form[c] || ''} placeholder="#RRGGBB" onChange={e => setForm(f => ({ ...f, [c]: e.target.value }))} style={{ ...campo, width: 110, fontFamily: 'var(--font-mono)' }} />
          {t(`marca.${c}`)}
        </label>
      ))}
      <div aria-hidden style={{ borderRadius: 8, overflow: 'hidden', border: '1px solid var(--surface-4)' }}>
        <div style={{ background: form.primary_color || '#1f2937', color: form.text_color || '#ffffff', padding: '10px 14px', fontWeight: 700 }}>
          {form.app_name || data.app_name} · {t('marca.ejemplo_factura')}
        </div>
        <div style={{ height: 4, background: form.accent_color || 'var(--accent)' }} />
      </div>
      <div className="u-row-8">
        <button type="button" onClick={guardar} style={{ padding: '7px 14px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'var(--on-accent)', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>{t('marca.guardar')}</button>
        {!data.is_default && (
          <button type="button" onClick={restablecer} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>{t('marca.restablecer')}</button>
        )}
      </div>
    </div>
  )
}
