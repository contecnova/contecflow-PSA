/**
 * BiO365Panel.jsx — Office 365 productivity BI panel.
 * Connects to /api/v1/bi/o365/* endpoints.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { Cloud, RefreshCw, Settings, BarChart2 } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const REPORTS = [
  { key: 'teams_activity', label: 'Teams' },
  { key: 'sharepoint_activity', label: 'SharePoint' },
  { key: 'onedrive_activity', label: 'OneDrive' },
  { key: 'email_activity', label: 'Email' },
  { key: 'user_adoption', label: 'Adopción' },
]

export default function BiO365Panel() {
  const t = useAppT()
  const { dark, tokens } = useChartTheme()
  const qc = useQueryClient()
  const [tab, setTab] = useState('reports')
  const [selectedReport, setSelectedReport] = useState('teams_activity')
  const [configForm, setConfigForm] = useState({ tenant_id: '', client_id: '', client_secret: '', enabled: true })
  const [configLoaded, setConfigLoaded] = useState(false)

  const { data: config } = useQuery({
    queryKey: ['bi-o365-config'],
    queryFn: () => api.get('/bi/o365/config').then(r => r.data),
    onSuccess: (d) => { if (!configLoaded) { setConfigForm({ tenant_id: d.tenant_id ?? '', client_id: d.client_id ?? '', client_secret: '', enabled: d.enabled ?? true }); setConfigLoaded(true) } },
  })

  const { data: reportData } = useQuery({
    queryKey: ['bi-o365-report', selectedReport],
    queryFn: () => api.get(`/bi/o365/reports/${selectedReport}`).then(r => r.data),
    enabled: tab === 'reports',
  })

  const { data: adoptionData } = useQuery({
    queryKey: ['bi-o365-adoption'],
    queryFn: () => api.get('/bi/o365/adoption').then(r => r.data),
    enabled: tab === 'adoption',
  })

  const saveConfigMutation = useMutation({
    mutationFn: (data) => api.put('/bi/o365/config', data).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-o365-config'] }),
  })

  const syncMutation = useMutation({
    mutationFn: () => api.post('/bi/o365/sync').then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-o365-report', selectedReport] }),
  })

  const cardCls = `rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`
  const rows = reportData?.rows ?? reportData?.data ?? []

  return (
    <div className={cardCls}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Cloud className="w-5 h-5 text-blue-500" />
          <h2 className="text-lg font-bold">{t('bi.o365.title', 'Office 365 Analytics')}</h2>
        </div>
        <button
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending || !config?.enabled}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
          {t('bi.o365.sync', 'Sincronizar')}
        </button>
      </div>

      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700 mb-5">
        {[['reports', 'Reportes'], ['adoption', 'Adopción'], ['config', 'Configuración']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === id ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'reports' && (
        <div className="space-y-4">
          <div className="flex gap-2 flex-wrap">
            {REPORTS.map(r => (
              <button key={r.key} onClick={() => setSelectedReport(r.key)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${selectedReport === r.key ? 'bg-blue-600 text-white border-blue-600' : (dark ? 'border-gray-600 text-gray-300 hover:border-blue-400' : 'border-gray-300 text-gray-600 hover:border-blue-400')}`}>
                {r.label}
              </button>
            ))}
          </div>

          {rows.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={rows.slice(0, 10)}>
                <XAxis dataKey={Object.keys(rows[0])[0]} tick={{ fontSize: 9, fill: tokens.textColor }} />
                <YAxis tick={{ fontSize: 9, fill: tokens.textColor }} />
                <Tooltip contentStyle={{ background: tokens.tooltipBg, border: 'none', borderRadius: 8 }} />
                <Bar dataKey={Object.keys(rows[0])[1] ?? 'value'} fill="#3b82f6" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-400 py-8 text-center">{t('bi.o365.no_data', 'Sin datos — ejecuta una sincronización primero')}</p>
          )}
        </div>
      )}

      {tab === 'adoption' && (
        <div className="space-y-3">
          {adoptionData ? (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {Object.entries(adoptionData).map(([k, v]) => (
                <div key={k} className={`rounded-lg p-3 text-center ${dark ? 'bg-gray-800' : 'bg-blue-50'}`}>
                  <p className="text-xs text-gray-400 mb-1">{k.replace(/_/g, ' ')}</p>
                  <p className="text-xl font-bold">{typeof v === 'number' ? v.toLocaleString() : String(v ?? '—')}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400">{t('bi.o365.no_adoption', 'Sin datos de adopción disponibles')}</p>
          )}
        </div>
      )}

      {tab === 'config' && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 mb-1">
            <Settings className="w-4 h-4 text-gray-400" />
            <p className="text-sm font-medium">{t('bi.o365.graph_config', 'Microsoft Graph API')}</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Tenant ID</label>
              <input type="text" value={configForm.tenant_id}
                onChange={e => setConfigForm(f => ({ ...f, tenant_id: e.target.value }))}
                className={`w-full rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`} />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Client ID</label>
              <input type="text" value={configForm.client_id}
                onChange={e => setConfigForm(f => ({ ...f, client_id: e.target.value }))}
                className={`w-full rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`} />
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs text-gray-400 mb-1">Client Secret <span className="text-amber-500">(no se guarda — solo se usa durante la sincronización)</span></label>
              <input type="password" value={configForm.client_secret}
                onChange={e => setConfigForm(f => ({ ...f, client_secret: e.target.value }))}
                placeholder="••••••••"
                className={`w-full rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`} />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={configForm.enabled}
                onChange={e => setConfigForm(f => ({ ...f, enabled: e.target.checked }))}
                className="rounded" />
              Sincronización habilitada
            </label>
            <button
              onClick={() => saveConfigMutation.mutate(configForm)}
              disabled={saveConfigMutation.isPending}
              className="px-4 py-1.5 rounded bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {saveConfigMutation.isPending ? 'Guardando...' : t('common.save', 'Guardar')}
            </button>
          </div>
          {config?.last_sync && (
            <p className="text-xs text-gray-400">Último sync: {new Date(config.last_sync).toLocaleString()}</p>
          )}
        </div>
      )}
    </div>
  )
}
