/**
 * VoiceAgentPanel.jsx — IVR / Voice Agent management panel for Service Desk.
 * Connects to /api/v1/sd/voice/* endpoints.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { Phone, Mic, StopCircle, Plus } from 'lucide-react'

const INTENT_COLORS = {
  incident: 'text-red-500',
  query: 'text-blue-500',
  urgent: 'text-orange-600',
  agent: 'text-purple-500',
  unknown: 'text-gray-400',
}

export default function VoiceAgentPanel() {
  const t = useAppT()
  const { dark } = useChartTheme()
  const qc = useQueryClient()

  const [activeSessionId, setActiveSessionId] = useState(null)
  const [callerInput, setCallerInput] = useState('+34600000000')
  const [turnText, setTurnText] = useState('')
  const [tab, setTab] = useState('sessions') // sessions | config

  const { data: sessionsData, isLoading } = useQuery({
    queryKey: ['voice-sessions'],
    queryFn: () => api.get('/sd/voice/sessions').then(r => r.data),
    refetchInterval: 15_000,
  })

  const { data: config } = useQuery({
    queryKey: ['voice-config'],
    queryFn: () => api.get('/sd/voice/config').then(r => r.data),
    enabled: tab === 'config',
  })

  const createSessionMutation = useMutation({
    mutationFn: (payload) => api.post('/sd/voice/sessions', payload).then(r => r.data),
    onSuccess: (data) => {
      setActiveSessionId(data.session.id)
      qc.invalidateQueries({ queryKey: ['voice-sessions'] })
    },
  })

  const addTurnMutation = useMutation({
    mutationFn: ({ id, text }) => api.post(`/sd/voice/sessions/${id}/turn`, { speaker: 'user', text }).then(r => r.data),
    onSuccess: () => {
      setTurnText('')
      qc.invalidateQueries({ queryKey: ['voice-sessions'] })
    },
  })

  const closeMutation = useMutation({
    mutationFn: (id) => api.post(`/sd/voice/sessions/${id}/close`, { resolution: 'resolved' }).then(r => r.data),
    onSuccess: () => {
      setActiveSessionId(null)
      qc.invalidateQueries({ queryKey: ['voice-sessions'] })
    },
  })

  const createTicketMutation = useMutation({
    mutationFn: (id) => api.post(`/sd/voice/sessions/${id}/ticket`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['voice-sessions'] }),
  })

  const cardCls = `rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`
  const sessions = sessionsData?.sessions ?? []
  const activeSession = sessions.find(s => s.id === activeSessionId)

  return (
    <div className={cardCls}>
      <div className="flex items-center gap-2 mb-4">
        <Phone className="w-5 h-5 text-green-500" />
        <h2 className="text-lg font-bold">{t('sd.voice.title')}</h2>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700 mb-5">
        {['sessions', 'config'].map(tb => (
          <button
            key={tb}
            onClick={() => setTab(tb)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === tb ? 'border-green-500 text-green-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
          >
            {tb === 'sessions' ? t('sd.voice.sessions') : t('sd.voice.config')}
          </button>
        ))}
      </div>

      {tab === 'sessions' && (
        <div className="space-y-4">
          {/* New session */}
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="+34600000000"
              value={callerInput}
              onChange={e => setCallerInput(e.target.value)}
              className={`rounded border px-3 py-1.5 text-sm flex-1 ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <button
              onClick={() => createSessionMutation.mutate({ caller_id: callerInput, channel: 'phone' })}
              disabled={createSessionMutation.isPending}
              className="flex items-center gap-1 px-4 py-1.5 rounded bg-green-600 text-white text-sm hover:bg-green-700 disabled:opacity-50"
            >
              <Plus className="w-4 h-4" />
              {t('sd.voice.new_session')}
            </button>
          </div>

          {/* Active session live transcript */}
          {activeSession && (
            <div className={`rounded-lg border px-4 py-3 ${dark ? 'bg-gray-800 border-green-700' : 'bg-green-50 border-green-200'}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Mic className="w-4 h-4 text-green-500 animate-pulse" />
                  <span className="text-sm font-medium">{activeSession.caller_id}</span>
                  {activeSession.intent && (
                    <span className={`text-xs font-semibold ${INTENT_COLORS[activeSession.intent] ?? 'text-gray-400'}`}>
                      [{activeSession.intent}]
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => createTicketMutation.mutate(activeSession.id)}
                    className="text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
                  >
                    {t('sd.voice.create_ticket')}
                  </button>
                  <button
                    onClick={() => closeMutation.mutate(activeSession.id)}
                    className="text-gray-400 hover:text-red-500"
                    title="Cerrar sesión"
                  >
                    <StopCircle className="w-5 h-5" />
                  </button>
                </div>
              </div>
              {/* Transcript */}
              <div className="max-h-32 overflow-y-auto space-y-1 mb-2">
                {activeSession.transcript?.map((turn, i) => (
                  <div key={i} className={`text-xs ${turn.speaker === 'user' ? 'text-right' : 'text-left text-gray-500'}`}>
                    <span className={`inline-block px-2 py-1 rounded-lg ${turn.speaker === 'user' ? (dark ? 'bg-blue-900' : 'bg-blue-100') : (dark ? 'bg-gray-700' : 'bg-gray-200')}`}>
                      {turn.text}
                    </span>
                  </div>
                ))}
              </div>
              {/* Add turn */}
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder={t('sd.voice.type_text')}
                  value={turnText}
                  onChange={e => setTurnText(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && turnText && addTurnMutation.mutate({ id: activeSession.id, text: turnText })}
                  className={`rounded border px-2 py-1 text-xs flex-1 ${dark ? 'bg-gray-700 border-gray-600' : 'bg-white border-gray-300'}`}
                />
                <button
                  onClick={() => addTurnMutation.mutate({ id: activeSession.id, text: turnText })}
                  disabled={!turnText}
                  className="px-3 py-1 rounded bg-blue-600 text-white text-xs disabled:opacity-50"
                >
                  ↵
                </button>
              </div>
            </div>
          )}

          {/* Session history */}
          <div className="space-y-1.5">
            {sessions.filter(s => s.id !== activeSessionId).slice(0, 10).map(s => (
              <div
                key={s.id}
                onClick={() => s.status === 'active' && setActiveSessionId(s.id)}
                className={`flex items-center justify-between px-4 py-2 rounded-lg text-sm cursor-pointer ${dark ? 'bg-gray-800 hover:bg-gray-700' : 'bg-gray-50 hover:bg-gray-100'}`}
              >
                <span className="font-medium">{s.caller_id}</span>
                <div className="flex items-center gap-2">
                  {s.intent && <span className={`text-xs ${INTENT_COLORS[s.intent]}`}>{s.intent}</span>}
                  <span className={`text-xs px-2 py-0.5 rounded-full ${s.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                    {s.status}
                  </span>
                  {s.ticket_id && <span className="text-xs text-blue-500">ticket ✓</span>}
                </div>
              </div>
            ))}
            {!isLoading && !sessions.length && (
              <p className="text-sm text-gray-400">{t('sd.voice.no_sessions')}</p>
            )}
          </div>
        </div>
      )}

      {tab === 'config' && config && (
        <div className="space-y-3 text-sm">
          <div>
            <p className="font-medium mb-1">{t('sd.voice.greeting')}</p>
            <p className={`px-3 py-2 rounded ${dark ? 'bg-gray-800' : 'bg-gray-100'}`}>{config.greeting}</p>
          </div>
          <div>
            <p className="font-medium mb-1">{t('sd.voice.dtmf_menu')}</p>
            <div className="space-y-1">
              {Object.entries(config.dtmf_menu ?? {}).map(([key, val]) => (
                <div key={key} className={`flex gap-3 px-3 py-1.5 rounded text-xs ${dark ? 'bg-gray-800' : 'bg-gray-100'}`}>
                  <span className="font-mono font-bold">[{key}]</span>
                  <span>{val.label}</span>
                  <span className="text-gray-400">→ {val.intent}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
