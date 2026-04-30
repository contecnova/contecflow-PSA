/**
 * BiO365Panel — Office 365 productivity analytics.
 * Conecta con /api/v1/bi/o365/*
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { Cloud, RefreshCw, Settings } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const REPORTS = [
  { key: 'teams_activity',    label: 'Teams'      },
  { key: 'sharepoint_activity', label: 'SharePoint' },
  { key: 'onedrive_activity', label: 'OneDrive'   },
  { key: 'email_activity',    label: 'Email'      },
  { key: 'user_adoption',     label: 'Adopción'   },
]

const S = {
  card:  { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: '20px 24px' },
  input: { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box' },
  btn:   { padding: '7px 14px', borderRadius: 8, background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' },
  label: { fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 },
}

export default function BiO365Panel() {
  const t             = useAppT()
  const { tokens }    = useChartTheme()
  const qc            = useQueryClient()
  const [tab,          setTab]          = useState('reports')
  const [selectedReport, setSelectedReport] = useState('teams_activity')
  const [configForm,   setConfigForm]   = useState({ tenant_id: '', client_id: '', client_secret: '', enabled: true })
  const [configLoaded, setConfigLoaded] = useState(false)

  const { data: config } = useQuery({
    queryKey: ['bi-o365-config'],
    queryFn:  () => api.get('/bi/o365/config').then(r => r.data),
    onSuccess: (d) => {
      if (!configLoaded) {
        setConfigForm({ tenant_id: d.tenant_id ?? '', client_id: d.client_id ?? '', client_secret: '', enabled: d.enabled ?? true })
        setConfigLoaded(true)
      }
    },
  })

  const { data: reportData } = useQuery({
    queryKey: ['bi-o365-report', selectedReport],
    queryFn:  () => api.get(`/bi/o365/reports/${selectedReport}`).then(r => r.data),
    enabled:  tab === 'reports',
  })

  const { data: adoptionData } = useQuery({
    queryKey: ['bi-o365-adoption'],
    queryFn:  () => api.get('/bi/o365/adoption').then(r => r.data),
    enabled:  tab === 'adoption',
  })

  const saveConfigMutation = useMutation({
    mutationFn: (data) => api.put('/bi/o365/config', data).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['bi-o365-config'] }),
  })

  const syncMutation = useMutation({
    mutationFn: () => api.post('/bi/o365/sync', { client_secret: configForm.client_secret }).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['bi-o365-report', selectedReport] }),
  })

  const rows = reportData?.rows ?? reportData?.data ?? []

  const TAB_NAV = [
    { id: 'reports',  label: 'Reportes' },
    { id: 'adoption', label: 'Adopción' },
    { id: 'config',   label: 'Configuración' },
  ]

  return (
    <div style={S.card}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: '#4f8ef718', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
            <Cloud size={16} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--text-1)' }}>
              {t('bi.o365.title', 'Office 365 Analytics')}
            </h3>
            <p style={{ margin: 0, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>Productividad y adopción de Microsoft 365</p>
          </div>
        </div>
        <button
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending || !config?.enabled || !configForm.client_secret}
          style={{ ...S.btn, display: 'flex', alignItems: 'center', gap: 6, opacity: (syncMutation.isPending || !config?.enabled || !configForm.client_secret) ? 0.5 : 1 }}
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
            {REPORTS.map(r => (
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
        adoptionData ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
            {Object.entries(adoptionData).map(([k, v]) => (
              <div key={k} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '12px 16px', textAlign: 'center' }}>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 6, textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</div>
                <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 700, color: 'var(--text-1)' }}>
                  {typeof v === 'number' ? v.toLocaleString() : String(v ?? '—')}
                </div>
              </div>
            ))}
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
                  (no se guarda — solo se usa durante la sincronización)
                </span>
              </label>
              <input type="password" value={configForm.client_secret} onChange={e => setConfigForm(f => ({ ...f, client_secret: e.target.value }))} placeholder="••••••••" style={S.input} />
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: "var(--text-base)", cursor: 'pointer', color: 'var(--text-1)' }}>
              <input type="checkbox" checked={configForm.enabled} onChange={e => setConfigForm(f => ({ ...f, enabled: e.target.checked }))} />
              Sincronización habilitada
            </label>
            <button
              onClick={() => saveConfigMutation.mutate(configForm)}
              disabled={saveConfigMutation.isPending}
              style={{ ...S.btn, opacity: saveConfigMutation.isPending ? 0.7 : 1 }}
            >
              {saveConfigMutation.isPending ? 'Guardando...' : t('common.save', 'Guardar')}
            </button>
          </div>
          {config?.last_sync_at && (
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
              Último sync: {new Date(config.last_sync_at).toLocaleString()}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
