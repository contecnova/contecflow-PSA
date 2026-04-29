/**
 * BiGdprPanel.jsx — GDPR Compliance panel (consent, DSR, field masks).
 * Connects to /api/v1/bi/gdpr/* endpoints.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { Shield, CheckCircle, XCircle, RefreshCw } from 'lucide-react'

const STATUS_BADGE = {
  pending: 'bg-yellow-100 text-yellow-800',
  completed: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
}

export default function BiGdprPanel() {
  const t = useAppT()
  const { dark } = useChartTheme()
  const qc = useQueryClient()

  const [tab, setTab] = useState('dsr') // dsr | consent | masks
  const [dsrForm, setDsrForm] = useState({ user_id: '', request_type: 'erasure', notes: '' })
  const [maskForm, setMaskForm] = useState({ entity: 'user', field: 'email', mask_type: 'hash' })

  const { data: dsrData, isLoading: dsrLoading } = useQuery({
    queryKey: ['bi-gdpr-dsr'],
    queryFn: () => api.get('/bi/gdpr/dsr').then(r => r.data),
  })

  const createDsrMutation = useMutation({
    mutationFn: (payload) => api.post('/bi/gdpr/dsr', payload).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bi-gdpr-dsr'] })
      setDsrForm({ user_id: '', request_type: 'erasure', notes: '' })
    },
  })

  const resolveDsrMutation = useMutation({
    mutationFn: ({ id, status }) => api.patch(`/bi/gdpr/dsr/${id}`, { status }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-gdpr-dsr'] }),
  })

  const { data: masksData } = useQuery({
    queryKey: ['bi-gdpr-masks'],
    queryFn: () => api.get('/bi/gdpr/field-masks').then(r => r.data),
    enabled: tab === 'masks',
  })

  const createMaskMutation = useMutation({
    mutationFn: (payload) => api.post('/bi/gdpr/field-masks', payload).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-gdpr-masks'] }),
  })

  const cardCls = `rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`

  return (
    <div className={cardCls}>
      <div className="flex items-center gap-2 mb-4">
        <Shield className="w-5 h-5 text-blue-500" />
        <h2 className="text-lg font-bold">{t('bi.gdpr.title', 'Cumplimiento GDPR')}</h2>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 border-b border-gray-200 dark:border-gray-700">
        {['dsr', 'consent', 'masks'].map(tab_name => (
          <button
            key={tab_name}
            onClick={() => setTab(tab_name)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === tab_name ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
          >
            {tab_name === 'dsr' ? 'DSR' : tab_name === 'consent' ? t('bi.gdpr.consent', 'Consentimiento') : t('bi.gdpr.masks', 'Máscaras')}
          </button>
        ))}
      </div>

      {/* DSR Tab */}
      {tab === 'dsr' && (
        <div>
          {/* Create DSR form */}
          <div className="mb-5 grid grid-cols-1 sm:grid-cols-3 gap-3">
            <input
              placeholder="user-id"
              value={dsrForm.user_id}
              onChange={e => setDsrForm(f => ({ ...f, user_id: e.target.value }))}
              className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <select
              value={dsrForm.request_type}
              onChange={e => setDsrForm(f => ({ ...f, request_type: e.target.value }))}
              className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            >
              {['erasure', 'portability', 'rectification'].map(rt => <option key={rt} value={rt}>{rt}</option>)}
            </select>
            <button
              onClick={() => createDsrMutation.mutate(dsrForm)}
              disabled={createDsrMutation.isPending || !dsrForm.user_id}
              className="px-4 py-1.5 rounded bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {t('bi.gdpr.create_dsr', 'Nueva solicitud')}
            </button>
          </div>

          {/* DSR list */}
          {dsrLoading ? (
            <div className="text-gray-400 text-sm">Loading…</div>
          ) : (
            <div className="space-y-2">
              {(dsrData?.items ?? []).map(dsr => (
                <div key={dsr.id} className={`flex items-center justify-between px-4 py-2 rounded-lg ${dark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                  <div>
                    <span className="font-medium text-sm">{dsr.user_id}</span>
                    <span className="ml-2 text-xs text-gray-500">{dsr.request_type}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[dsr.status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {dsr.status}
                    </span>
                    {dsr.status === 'pending' && (
                      <button
                        onClick={() => resolveDsrMutation.mutate({ id: dsr.id, status: 'completed' })}
                        className="text-green-500 hover:text-green-700"
                        title="Mark completed"
                      >
                        <CheckCircle className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {!(dsrData?.items?.length) && <p className="text-sm text-gray-400">{t('bi.gdpr.no_dsr', 'No hay solicitudes')}</p>}
            </div>
          )}
        </div>
      )}

      {/* Masks Tab */}
      {tab === 'masks' && (
        <div>
          <div className="mb-5 grid grid-cols-3 gap-3">
            <input
              placeholder="entity (e.g. user)"
              value={maskForm.entity}
              onChange={e => setMaskForm(f => ({ ...f, entity: e.target.value }))}
              className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <input
              placeholder="field (e.g. email)"
              value={maskForm.field}
              onChange={e => setMaskForm(f => ({ ...f, field: e.target.value }))}
              className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <select
              value={maskForm.mask_type}
              onChange={e => setMaskForm(f => ({ ...f, mask_type: e.target.value }))}
              className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            >
              {['hash', 'redact', 'partial', 'encrypt'].map(mt => <option key={mt} value={mt}>{mt}</option>)}
            </select>
          </div>
          <button
            onClick={() => createMaskMutation.mutate(maskForm)}
            disabled={createMaskMutation.isPending}
            className="mb-4 px-4 py-1.5 rounded bg-purple-600 text-white text-sm hover:bg-purple-700 disabled:opacity-50"
          >
            {t('bi.gdpr.add_mask', 'Añadir máscara')}
          </button>
          <div className="space-y-2">
            {(masksData?.masks ?? masksData?.items ?? []).map((m, i) => (
              <div key={i} className={`flex gap-4 items-center px-4 py-2 rounded-lg text-sm ${dark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                <span className="font-mono">{m.entity}.{m.field}</span>
                <span className="text-gray-400">{m.mask_type}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'consent' && (
        <p className="text-sm text-gray-400">{t('bi.gdpr.consent_placeholder', 'Gestión de consentimientos — próximamente vista detallada por usuario.')}</p>
      )}
    </div>
  )
}
