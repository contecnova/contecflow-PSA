/**
 * BiO365Panel — Office 365 productivity analytics.
 * Conecta con /api/v1/bi/o365/*
 *
 * Revisión 2026-11: el secreto se guarda (cifrado) en vez de teclearlo en cada
 * sincronización; «Sincronizar» enseña lo que pasó con cada informe; la lista
 * de informes viene del servidor; y la adopción ya no pinta «[object Object]».
 */
import React, { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biO365Api } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { Cloud, RefreshCw, Settings } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { extractErr, localeActivo } from '../../utils/helpers'
import { useToast } from '../../context/ToastContext'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'


// TODO type: biO365Api config payload — needs shared type
interface O365Config {
  tenant_id?: string
  client_id?: string
  enabled?: boolean
  secret_puesto?: boolean
  reports?: string[]
  last_sync_at?: string | null
}

interface Adopcion {
  total_users?: number
  active_users?: number
  adoption_rate?: number
  by_product?: Record<string, number>
  fetched_at?: string | null
}

interface ResultadoSync { ok: boolean; error?: string; synced?: { report: string; ok: boolean; records?: number }[] }

interface O365ConfigForm {
  tenant_id: string
  client_id: string
  client_secret: string
  enabled: boolean
}

const S: Record<string, React.CSSProperties> = {
  card:  { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: '20px 24px' },
  input: { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box' },
  btn:   { padding: '7px 14px', borderRadius: 8, background: 'var(--accent)', color: 'var(--on-accent)', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' },
  label: { fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 },
}

export default function BiO365Panel() {
  const t             = useAppT()
  const toast         = useToast()
  const { tokens }    = useChartTheme()
  const qc            = useQueryClient()
  const [tab,          setTab]          = useState<string>('reports')
  const [selectedReport, setSelectedReport] = useState<string>('teams_activity')
  const [configForm,   setConfigForm]   = useState<O365ConfigForm>({ tenant_id: '', client_id: '', client_secret: '', enabled: true })
  const [configLoaded, setConfigLoaded] = useState<boolean>(false)

  const { data: config } = useQuery<O365Config>({
    queryKey: ['bi-o365-config'],
    queryFn:  () => biO365Api.getConfig().then(r => r.data),
  })

  useEffect(() => {
    if (config && !configLoaded) {
      setConfigForm({ tenant_id: config.tenant_id ?? '', client_id: config.client_id ?? '', client_secret: '', enabled: config.enabled ?? true })
      setConfigLoaded(true)
    }
  }, [config, configLoaded])

  const { data: reportData } = useQuery({
    queryKey: ['bi-o365-report', selectedReport],
    queryFn:  () => biO365Api.getReport(selectedReport, {}).then(r => r.data),
    enabled:  tab === 'reports',
  })

  const { data: adoptionData } = useQuery<Adopcion>({
    queryKey: ['bi-o365-adoption'],
    queryFn:  () => biO365Api.getAdoption().then(r => r.data),
    enabled:  tab === 'adoption',
  })

  const saveConfigMutation = useMutation({
    mutationFn: (data: O365ConfigForm) => biO365Api.saveConfig(data).then(r => r.data),
    onSuccess:  () => {
      setConfigForm(f => ({ ...f, client_secret: '' }))
      toast.success(t('bio365.guardado'))
      qc.invalidateQueries({ queryKey: ['bi-o365-config'] })
    },
    onError: (e) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const syncMutation = useMutation({
    mutationFn: () => biO365Api.triggerSync({}).then(r => r.data as ResultadoSync),
    onSuccess:  (r) => {
      const filas = (r.synced ?? []).reduce((n, x) => n + (x.records ?? 0), 0)
      if (r.ok) toast.success(t('bio365.sync_ok', { n: filas.toLocaleString(localeActivo()) }))
      else toast.error(t('bio365.sync_fallo', { error: r.error ?? '' }))
      qc.invalidateQueries({ queryKey: ['bi-o365-report'] })
      qc.invalidateQueries({ queryKey: ['bi-o365-adoption'] })
      qc.invalidateQueries({ queryKey: ['bi-o365-config'] })
    },
    onError: (e) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const puedeSincronizar = !!config?.enabled && !!config?.secret_puesto

  const rows = reportData?.rows ?? reportData?.data ?? []

  const TAB_NAV = [
    { id: 'reports',  label: t('bio365.tab_informes') },
    { id: 'adoption', label: t('bio365.tab_adopcion') },
    { id: 'config',   label: t('bio365.tab_configuracion') },
  ]

  return (
    <div style={S.card}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--accent-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
            <Cloud size={16} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--text-1)' }}>
              {t('bi.o365.title', 'Office 365 Analytics')}
            </h3>
            <p style={{ margin: 0, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{t('bio365.productividad_y_adopcion_de_microsoft_365')}</p>
          </div>
        </div>
        <button
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending || !puedeSincronizar}
          title={puedeSincronizar ? undefined : t('bio365.falta_configurar')}
          style={{ ...S.btn, display: 'flex', alignItems: 'center', gap: 6, opacity: (syncMutation.isPending || !puedeSincronizar) ? 0.5 : 1 }}
        >
          <RefreshCw size={12} style={{ animation: syncMutation.isPending ? 'spin 1s linear infinite' : 'none' }} />
          {t('bi.o365.sync', 'Sincronizar')}
        </button>
      </div>

      {/* Tab navigation */}
      <div style={{ display: 'flex', gap: 2, borderBottom: '1px solid var(--surface-4)', marginBottom: 20 }}>
        {TAB_NAV.map(({ id, label }) => (
          <button key={id} onClick={() => setTab(id)}
            style={{
              padding: '8px 16px', fontSize: "var(--text-sm)", fontWeight: tab === id ? 700 : 400,
              color: tab === id ? 'var(--accent)' : 'var(--text-2)',
              background: 'transparent', border: 'none',
              borderBottom: `2px solid ${tab === id ? 'var(--accent)' : 'transparent'}`,
              cursor: 'pointer', fontFamily: 'inherit', marginBottom: -1,
            }}>
            {label}
          </button>
        ))}
      </div>

      {/* Reportes tab */}
      {tab === 'reports' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {(config?.reports ?? []).map(key => ({ key, label: t(`bio365.informe_${key}`) })).map(r => (
              <button key={r.key} onClick={() => setSelectedReport(r.key)}
                style={{
                  padding: '5px 14px', borderRadius: 20, fontSize: "var(--text-xs)", fontWeight: selectedReport === r.key ? 700 : 400,
                  cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s',
                  border: `1.5px solid ${selectedReport === r.key ? 'var(--accent)' : 'var(--surface-4)'}`,
                  background: selectedReport === r.key ? 'var(--accent-muted)' : 'transparent',
                  color: selectedReport === r.key ? 'var(--accent)' : 'var(--text-2)',
                }}>
                {r.label}
              </button>
            ))}
          </div>

          {rows.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={rows.slice(0, 10)}>
                <XAxis dataKey={Object.keys(rows[0])[0]} tick={{ fontSize: "var(--text-3xs)", fill: tokens.textColor }} />
                <YAxis tick={{ fontSize: "var(--text-3xs)", fill: tokens.textColor }} />
                <Tooltip contentStyle={{ background: tokens.tooltipBg, border: 'none', borderRadius: 8, color: 'var(--text-1)' }} />
                <Bar dataKey={Object.keys(rows[0])[1] ?? 'value'} fill="var(--accent)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: "var(--text-sm)", padding: '32px 0' }}>
              {t('bi.o365.no_data', 'Sin datos — ejecuta una sincronización primero')}
            </div>
          )}
        </div>
      )}

      {/* Adopción tab */}
      {tab === 'adoption' && (
        adoptionData?.total_users ? (
          <div style={{ display: 'grid', gap: 14 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
              {([
                ['bio365.usuarios', adoptionData.total_users.toLocaleString(localeActivo())],
                ['bio365.activos', (adoptionData.active_users ?? 0).toLocaleString(localeActivo())],
                ['bio365.adopcion', `${(adoptionData.adoption_rate ?? 0).toLocaleString(localeActivo())} %`],
              ] as const).map(([k, v]) => (
                <div key={k} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '12px 16px', textAlign: 'center' }}>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 6 }}>{t(k)}</div>
                  <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 700, color: 'var(--text-1)' }}>{v}</div>
                </div>
              ))}
            </div>
            {Object.keys(adoptionData.by_product ?? {}).length > 0 && (
              <div>
                <div style={{ ...S.label, marginBottom: 8 }}>{t('bio365.licencias_por_producto')}</div>
                {Object.entries(adoptionData.by_product ?? {}).sort((a, b) => b[1] - a[1]).map(([prod, n]) => (
                  <div key={prod} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)', padding: '5px 0', borderTop: '1px solid var(--surface-4)' }}>
                    <span style={{ color: 'var(--text-2)' }}>{prod}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-1)' }}>{n.toLocaleString(localeActivo())}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center', padding: '32px 0' }}>
            {t('bi.o365.no_adoption', 'Sin datos de adopción disponibles')}
          </div>
        )
      )}

      {/* Configuración tab */}
      {tab === 'config' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Settings size={14} style={{ color: 'var(--text-3)' }} />
            <span style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>
              {t('bi.o365.graph_config', 'Microsoft Graph API')}
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 }}>
            <div>
              <label style={S.label}>Tenant ID</label>
              <input type="text" value={configForm.tenant_id} onChange={e => setConfigForm(f => ({ ...f, tenant_id: e.target.value }))} style={S.input} />
            </div>
            <div>
              <label style={S.label}>Client ID</label>
              <input type="text" value={configForm.client_id} onChange={e => setConfigForm(f => ({ ...f, client_id: e.target.value }))} style={S.input} />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={S.label}>
                Client Secret{' '}
                <span style={{ color: 'var(--warning)', fontWeight: 400, textTransform: 'none', fontSize: "var(--text-2xs)" }}>
                  {t('bio365.secreto_ayuda')}
                </span>
              </label>
              <input type="password" value={configForm.client_secret} onChange={e => setConfigForm(f => ({ ...f, client_secret: e.target.value }))} placeholder={config?.secret_puesto ? t('bio365.secreto_puesto') : ''} autoComplete="off" style={S.input} />
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: "var(--text-base)", cursor: 'pointer', color: 'var(--text-1)' }}>
              <input type="checkbox" checked={configForm.enabled} onChange={e => setConfigForm(f => ({ ...f, enabled: e.target.checked }))} />
              {t('bio365.sincronizacion_habilitada')}
            </label>
            <button
              onClick={() => saveConfigMutation.mutate(configForm)}
              disabled={saveConfigMutation.isPending}
              style={{ ...S.btn, opacity: saveConfigMutation.isPending ? 0.7 : 1 }}
            >
              {saveConfigMutation.isPending ? t('bio365.guardando') : t('common.save', 'Guardar')}
            </button>
          </div>
          {config?.last_sync_at && (
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
              {t('bio365.ultimo_sync')} {new Date(config.last_sync_at).toLocaleString(localeActivo())}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
