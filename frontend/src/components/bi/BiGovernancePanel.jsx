/**
 * BiGovernancePanel.jsx — BI Governance management panel.
 * Policies, audit log, GDPR config overview.
 * Connects to /api/v1/bi/governance/* endpoints.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { Shield, Plus, RefreshCw } from 'lucide-react'

const POLICY_TYPES = ['data_retention', 'access_control', 'classification', 'export_restriction', 'masking']

export default function BiGovernancePanel() {
  const t = useAppT()
  const { dark } = useChartTheme()
  const qc = useQueryClient()
  const [tab, setTab] = useState('policies')
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', policy_type: 'data_retention', rules: {} })

  const { data: policiesData } = useQuery({
    queryKey: ['bi-gov-policies'],
    queryFn: () => api.get('/bi/governance/policies').then(r => r.data),
  })

  const { data: auditData, refetch: refetchAudit } = useQuery({
    queryKey: ['bi-gov-audit'],
    queryFn: () => api.get('/bi/governance/audit').then(r => r.data),
    enabled: tab === 'audit',
  })

  const { data: configData } = useQuery({
    queryKey: ['bi-gov-config'],
    queryFn: () => api.get('/bi/governance/config').then(r => r.data),
  })

  const createPolicyMutation = useMutation({
    mutationFn: (data) => api.post('/bi/governance/policies', data).then(r => r.data),
    onSuccess: () => { setShowCreate(false); qc.invalidateQueries({ queryKey: ['bi-gov-policies'] }) },
  })

  const cardCls = `rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`
  const policies = policiesData?.policies ?? policiesData?.items ?? []
  const auditItems = auditData?.items ?? auditData?.events ?? []

  return (
    <div className={cardCls}>
      <div className="flex items-center gap-2 mb-4">
        <Shield className="w-5 h-5 text-amber-500" />
        <h2 className="text-lg font-bold">{t('bi.governance.title', 'Gobernanza BI')}</h2>
      </div>

      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700 mb-5">
        {[['policies', 'Políticas'], ['audit', 'Auditoría'], ['config', 'Configuración']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === id ? 'border-amber-500 text-amber-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'policies' && (
        <div className="space-y-3">
          <div className="flex justify-end">
            <button onClick={() => setShowCreate(v => !v)}
              className="flex items-center gap-1 px-3 py-1.5 rounded bg-amber-600 text-white text-sm hover:bg-amber-700">
              <Plus className="w-4 h-4" /> Nueva política
            </button>
          </div>

          {showCreate && (
            <div className={`rounded-lg border p-4 ${dark ? 'bg-gray-800 border-gray-700' : 'bg-amber-50 border-amber-200'}`}>
              <div className="grid grid-cols-2 gap-2 mb-3">
                <input type="text" placeholder="Nombre de la política"
                  value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className={`col-span-2 rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-700 border-gray-600' : 'bg-white border-gray-300'}`} />
                <select value={form.policy_type} onChange={e => setForm(f => ({ ...f, policy_type: e.target.value }))}
                  className={`col-span-2 rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-700 border-gray-600' : 'bg-white border-gray-300'}`}>
                  {POLICY_TYPES.map(pt => <option key={pt} value={pt}>{pt}</option>)}
                </select>
              </div>
              <div className="flex gap-2">
                <button onClick={() => createPolicyMutation.mutate(form)} disabled={!form.name || createPolicyMutation.isPending}
                  className="px-4 py-1.5 rounded bg-amber-600 text-white text-sm disabled:opacity-50 hover:bg-amber-700">
                  Crear
                </button>
                <button onClick={() => setShowCreate(false)} className="px-4 py-1.5 rounded text-sm text-gray-500">Cancelar</button>
              </div>
            </div>
          )}

          <div className="space-y-2">
            {policies.map(p => (
              <div key={p.id} className={`flex items-center justify-between px-4 py-3 rounded-lg border ${dark ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                <div>
                  <p className="font-medium text-sm">{p.name}</p>
                  <p className="text-xs text-gray-400">{p.policy_type}</p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${p.enabled || p.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                  {p.enabled || p.active ? 'Activa' : 'Inactiva'}
                </span>
              </div>
            ))}
            {!policies.length && <p className="text-sm text-gray-400">Sin políticas configuradas</p>}
          </div>
        </div>
      )}

      {tab === 'audit' && (
        <div className="space-y-3">
          <div className="flex justify-end">
            <button onClick={() => refetchAudit()} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
              <RefreshCw className="w-3.5 h-3.5" /> Actualizar
            </button>
          </div>
          <div className="space-y-1.5 max-h-64 overflow-y-auto">
            {auditItems.map((ev, i) => (
              <div key={i} className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs ${dark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                <span className={`px-2 py-0.5 rounded font-bold ${dark ? 'bg-amber-900 text-amber-300' : 'bg-amber-100 text-amber-700'}`}>
                  {ev.action || 'view'}
                </span>
                <span className="flex-1 truncate">{ev.resource || ev.dataset_id || '—'}</span>
                <span className="text-gray-400">{ev.user_id || '—'}</span>
                <span className="text-gray-400 flex-shrink-0">{ev.accessed_at ? new Date(ev.accessed_at).toLocaleString() : ''}</span>
              </div>
            ))}
            {!auditItems.length && <p className="text-sm text-gray-400">Sin eventos de auditoría</p>}
          </div>
        </div>
      )}

      {tab === 'config' && configData && (
        <div className="space-y-2 text-sm">
          {Object.entries(configData).map(([k, v]) => (
            <div key={k} className={`flex justify-between px-3 py-2 rounded ${dark ? 'bg-gray-800' : 'bg-gray-50'}`}>
              <span className="text-gray-500">{k}</span>
              <span className="font-medium">{typeof v === 'boolean' ? (v ? '✓' : '✗') : String(v ?? '—')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
