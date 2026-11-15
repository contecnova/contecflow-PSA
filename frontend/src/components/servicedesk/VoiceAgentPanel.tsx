/**
 * VoiceAgentPanel.jsx — IVR / Voice Agent management for Service Desk.
 *
 * Backend endpoints:
 *   GET    /sd/voice/config                              -> { greeting, language, max_silence_seconds, dtmf_menu, intent_keywords }
 *   PUT    /sd/voice/config                              { greeting?, language?, max_silence_seconds?, dtmf_menu?, intent_keywords? }
 *   GET    /sd/voice/sessions?status=active|closed       -> { sessions: [...] }
 *   POST   /sd/voice/sessions                            { caller_id, channel } -> { session, greeting }
 *   POST   /sd/voice/sessions/{id}/turn                  { speaker, text } -> session
 *   POST   /sd/voice/sessions/{id}/close                 { resolution } -> session
 *   POST   /sd/voice/sessions/{id}/ticket                -> { id, number, ... }
 *
 * Cómo funciona:
 *   1. Se crea una sesión por llamada (caller_id, channel: phone|sip|web).
 *   2. Cada turno se clasifica por intent vía keywords (incident/query/urgent/agent/unknown).
 *      Twilio puede usar el webhook /sd/voice/webhook/twilio para crear sesiones automáticas.
 *   3. Las entidades (email, ticket ref, urgency words) se extraen de los turnos del usuario.
 *   4. Se puede crear un Ticket real desde el resumen de la conversación.
 *   5. Cierre con resolución: resolved / transferred / abandoned / voicemail.
 *   6. La configuración es por organización (greeting, idioma, menú DTMF, keywords de intent).
 */
import { useState, useEffect, useMemo } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { voiceAgentApi } from '../../services/api'
import type { ConfigDelAgenteDeVoz, SesionDeVoz, TurnoDeVoz } from '../../services/api/tipos-analitica'
import { useAppT } from '../../i18n/AppLangContext'
import { Phone, Mic, StopCircle, Plus, ExternalLink, Edit2, Trash2 } from 'lucide-react'
import { Card, Button, Tabs, Spinner, EmptyState, Modal } from '../ui'
import { useToast } from '../../context/ToastContext'
import { localeActivo } from '../../utils/helpers'
import { POLL_LIVE_MS } from '../../constants/timings'
import { useOrgSettings } from '../../hooks/useOrgSettings'
import './VoiceAgentPanel.css'
import { chipColor } from '../../utils/estilos'

type VoiceTurn = TurnoDeVoz
type VoiceEntities = SesionDeVoz['entities']
type VoiceSession = SesionDeVoz
/** Borrador del editor: lo que el usuario va cambiando antes de guardar. */
type VoiceAgentConfig = Partial<ConfigDelAgenteDeVoz>

const INTENT_COLORS: Record<string, string> = {
  incident: 'var(--danger)',
  query:    'var(--accent)',
  urgent:   'var(--orange)',
  agent:    'var(--purple)',
  unknown:  'var(--text-3)',
}

const RESOLUTION_LABEL: Record<string, string> = {
  resolved:    'Resuelta',
  transferred: 'Transferida',
  abandoned:   'Abandonada',
  voicemail:   'Buzón de voz',
}

const RESOLUTION_COLOR: Record<string, string> = {
  resolved:    'var(--success)',
  transferred: 'var(--accent)',
  abandoned:   'var(--text-3)',
  voicemail:   'var(--purple)',
}

const STATUS_COLOR: Record<string, string> = {
  active: 'var(--success)',
  closed: 'var(--text-3)',
}

// ── Sesión activa ──────────────────────────────────────────────────────────────

interface ActiveSessionCardProps {
  session: VoiceSession
  onClose: (resolution: string) => void
  onCreateTicket: () => void
  onAddTurn: (text: string) => void
  sending: boolean
  closing: boolean
  creatingTicket: boolean
  openTicket: (id: string | number) => void
}

function ActiveSessionCard({ session, onClose, onCreateTicket, onAddTurn, sending, closing, creatingTicket, openTicket }: ActiveSessionCardProps) {
  const t = useAppT()
  const [turnText, setTurnText] = useState<string>('')
  const [resolution, setResolution] = useState<string>('resolved')
  const [showCloseConfirm, setShowCloseConfirm] = useState<boolean>(false)

  const transcript: VoiceTurn[] = session.transcript || []
  const entities: VoiceEntities = session.entities || {}
  const hasEntities = entities.email || entities.ticket_ref || entities.urgency_words?.length

  return (
    <div className="voagpa-box-1">
      {/* Header */}
      <div className="voagpa-row-1">
        <div className="voagpa-row-2">
          <Mic size={14} className="voiceage-sx1" />
          <span className="voagpa-txt-1">
            {session.caller_id}
          </span>
          <span className="chip-dato" style={chipColor(STATUS_COLOR[session.status || ''] || 'var(--text-3)')}>{session.status}</span>
          {session.intent && (
            <span className="chip-dato" style={chipColor(INTENT_COLORS[session.intent] || INTENT_COLORS.unknown)}>{session.intent}</span>
          )}
          {session.channel && (
            <span className="u-text3-xs">· {session.channel}</span>
          )}
        </div>
        <div className="u-row-center-8">
          {session.ticket_id ? (
            <Button
              size="sm"
              variant="ghost"
              icon={<ExternalLink size={13} />}
              onClick={() => openTicket(session.ticket_id!)}
            >{t('voiceagent.ver_ticket')}</Button>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              onClick={onCreateTicket}
              loading={creatingTicket}
            >{t('sd.voice.create_ticket')}</Button>
          )}
          <button aria-label={t('voiceagent.cerrar_sesion')}
            type="button"
            onClick={() => setShowCloseConfirm(v => !v)}
            title={t('voiceagent.cerrar_sesion')}
            className="voagpa-row-3"
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--danger)' }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-3)' }}
          >
            <StopCircle size={18} />
          </button>
        </div>
      </div>

      {showCloseConfirm && (
        <div className="voagpa-row-4">
          <span className="u-text2-xs">{t('voiceagent.cerrar_como')}</span>
          <select value={resolution} onChange={e => setResolution(e.target.value)}
            className="voagpa-inputbase2">
            {Object.entries(RESOLUTION_LABEL).map(([id, label]) => (
              <option key={id} value={id}>{label}</option>
            ))}
          </select>
          <Button
            size="sm"
            variant="danger"
            loading={closing}
            onClick={() => onClose(resolution)}
          >{t('voiceagent.confirmar_cierre')}</Button>
          <Button size="sm" variant="secondary" onClick={() => setShowCloseConfirm(false)}>{t('common.cancel')}</Button>
        </div>
      )}

      {/* Entities */}
      {hasEntities && (
        <div className="voagpa-row-5">
          {entities.email && (
            <span className="voagpa-box-2">
              ✉ {entities.email}
            </span>
          )}
          {entities.ticket_ref && (
            <span className="voagpa-box-3">
              🔗 {entities.ticket_ref}
            </span>
          )}
          {(entities.urgency_words || []).map((w, i) => (
            <span key={i} className="chip-dato" style={chipColor('var(--orange)')}>{w}</span>
          ))}
        </div>
      )}

      {/* Transcript */}
      <div className="voagpa-stack-1">
        {transcript.length === 0 ? (
          <div className="voagpa-box-4">
            {t('voiceagent.sin_turnos_registrados_todavia')}
          </div>
        ) : transcript.map((turn, i) => {
          const isUser = turn.speaker === 'user'
          const isBot  = turn.speaker === 'bot'
          const align = isUser ? 'flex-end' : 'flex-start'
          const bg = isUser ? 'var(--accent-muted)' : isBot ? 'var(--surface-3)' : 'var(--surface-4)'
          const fg = isUser ? 'var(--accent)' : isBot ? 'var(--text-2)' : 'var(--text-1)'
          const border = isUser ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'
          return (
            <div className="voagpa-row-21 voice-agent-panel-e1" key={i} style={{ '--voice-agent-panel-justify-content': align } as CSSProperties}>
              <div className="voagpa-box-5">
                <div className={`voagpa-box-14 ${align === 'flex-end' ? 'voice-agent-panel-m2' : 'voice-agent-panel-m3'}`}>
                  {turn.speaker} {turn.ts && `· ${new Date(turn.ts).toLocaleTimeString(localeActivo())}`}
                </div>
                <span className="voagpa-box-15 voiceage-sx2 voice-agent-panel-e4" style={{ '--voice-agent-panel-background': bg, '--voice-agent-panel-color': fg, '--voice-agent-panel-border': `1px solid ${border}` } as CSSProperties}>{turn.text}</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Add turn (sólo si activa) */}
      {session.status === 'active' && (
        <div className="u-row-8">
          <input aria-label={t('voiceagent.anadir_turno_texto_del_usuario')}
            type="text"
            placeholder={t('voiceagent.anadir_turno_texto_del_usuario')}
            value={turnText}
            onChange={e => setTurnText(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && turnText.trim()) {
                onAddTurn(turnText.trim())
                setTurnText('')
              }
            }}
            className="voagpa-inputbase3"
          />
          <Button
            size="sm"
            onClick={() => { if (turnText.trim()) { onAddTurn(turnText.trim()); setTurnText('') } }}
            disabled={!turnText.trim() || sending}
            loading={sending}
          >{t('chat.send')}</Button>
        </div>
      )}
    </div>
  )
}

// ── Configuración (greeting, idioma, DTMF, keywords) ──────────────────────────

interface ConfigEditorProps {
  config: VoiceAgentConfig | undefined | null
  onSave: (draft: VoiceAgentConfig) => void
  saving: boolean
}

/** Idiomas (BCP-47) que ofrece el selector del agente de voz. */
const VOICE_LANGUAGES = ['es-ES', 'en-US', 'ca-ES', 'fr-FR', 'pt-PT']

function ConfigEditor({ config, onSave, saving }: ConfigEditorProps) {
  const t = useAppT()
  const [draft, setDraft] = useState<VoiceAgentConfig | null>(null)
  const [newKey, setNewKey] = useState<string>('')
  const [newLabel, setNewLabel] = useState<string>('')
  const [newIntent, setNewIntent] = useState<string>('incident')
  const [editingIntent, setEditingIntent] = useState<string | null>(null)
  const [newKw, setNewKw] = useState<string>('')
  // Sin idioma configurado: el de la empresa, en la variante que ofrece el selector.
  const { language: idiomaOrg } = useOrgSettings()
  const idiomaPorDefecto = VOICE_LANGUAGES.find(l => l.split('-')[0] === idiomaOrg) ?? VOICE_LANGUAGES[0]

  useEffect(() => {
    if (config && !draft) setDraft({
      greeting: config.greeting || '',
      language: config.language || idiomaPorDefecto,
      max_silence_seconds: config.max_silence_seconds ?? 10,
      dtmf_menu: { ...(config.dtmf_menu || {}) },
      intent_keywords: Object.fromEntries(
        Object.entries(config.intent_keywords || {}).map(([k, v]) => [k, [...(v || [])]])
      ),
    })
  }, [config]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!draft) return <div className="voagpa-row-6"><Spinner /></div>

  const setField = (k: string, v: unknown) => setDraft(d => ({ ...(d as VoiceAgentConfig), [k]: v }))

  const addDtmf = () => {
    if (!newKey.trim() || !newLabel.trim()) return
    setDraft(d => ({
      ...(d as VoiceAgentConfig),
      dtmf_menu: { ...(d as VoiceAgentConfig).dtmf_menu, [newKey.trim()]: { intent: newIntent, label: newLabel.trim() } }
    }))
    setNewKey(''); setNewLabel(''); setNewIntent('incident')
  }
  const removeDtmf = (key: string) => {
    setDraft(d => {
      const { [key]: _, ...rest } = (d as VoiceAgentConfig).dtmf_menu || {}
      return { ...(d as VoiceAgentConfig), dtmf_menu: rest }
    })
  }
  const addKeyword = (intent: string) => {
    if (!newKw.trim()) return
    const kw = newKw.trim().toLowerCase()
    setDraft(d => ({
      ...(d as VoiceAgentConfig),
      intent_keywords: {
        ...(d as VoiceAgentConfig).intent_keywords,
        [intent]: [...new Set([...(((d as VoiceAgentConfig).intent_keywords || {})[intent] || []), kw])],
      }
    }))
    setNewKw('')
  }
  const removeKeyword = (intent: string, kw: string) => {
    setDraft(d => ({
      ...(d as VoiceAgentConfig),
      intent_keywords: { ...(d as VoiceAgentConfig).intent_keywords, [intent]: (((d as VoiceAgentConfig).intent_keywords || {})[intent] || []).filter(k => k !== kw) }
    }))
  }

  const intentList = Object.keys(INTENT_COLORS).filter(k => k !== 'unknown')

  return (
    <div className="u-stack-16">
      {/* Greeting + idioma + silencio */}
      <div>
        <div className="voagpa-fieldlabel">{t('sd.voice.greeting', 'Saludo (greeting)')}</div>
        <textarea
          aria-label={t('sd.voice.greeting', 'Saludo (greeting)')}
          rows={2}
          value={draft.greeting}
          onChange={e => setField('greeting', e.target.value)}
          className="voagpa-inputbase4"
        />
      </div>

      <div className="u-grid2-12">
        <div>
          <div className="voagpa-fieldlabel">{t('voiceagent.idioma_bcp_47')}</div>
          <select value={draft.language} onChange={e => setField('language', e.target.value)} className="voagpa-inputbase">
            <option value="es-ES">{t('voiceagent.espanol_es_es')}</option>
            <option value="en-US">English (en-US)</option>
            <option value="ca-ES">Català (ca-ES)</option>
            <option value="fr-FR">Français (fr-FR)</option>
            <option value="pt-PT">Português (pt-PT)</option>
          </select>
        </div>
        <div>
          <div className="voagpa-fieldlabel">{t('voiceagent.silencio_maximo_segundos')}</div>
          <input
            aria-label={t('voiceagent.silencio_maximo_segundos')}
            type="number" min={1} max={120}
            value={draft.max_silence_seconds}
            onChange={e => setField('max_silence_seconds', Number(e.target.value))}
            className="voagpa-inputbase"
          />
        </div>
      </div>

      {/* Menú DTMF */}
      <div>
        <div className="voagpa-fieldlabel">{t('sd.voice.dtmf_menu', 'Menú DTMF (tonos del teclado)')}</div>
        <div className="voagpa-stack-2">
          {Object.entries(draft.dtmf_menu || {}).length === 0 && (
            <div className="u-text3-xs">{t('voiceagent.sin_opciones_dtmf_configuradas')}</div>
          )}
          {Object.entries(draft.dtmf_menu || {}).map(([key, val]) => (
            <div key={key} className="voagpa-row-7">
              <span className="voagpa-box-6">{key}</span>
              <input
                aria-label={`DTMF ${key}`}
                type="text"
                value={val.label}
                onChange={e => setDraft(d => ({ ...(d as VoiceAgentConfig), dtmf_menu: { ...(d as VoiceAgentConfig).dtmf_menu, [key]: { ...val, label: e.target.value } } }))}
                className="voagpa-inputbase3"
              />
              <select
                value={val.intent}
                onChange={e => setDraft(d => ({ ...(d as VoiceAgentConfig), dtmf_menu: { ...(d as VoiceAgentConfig).dtmf_menu, [key]: { ...val, intent: e.target.value } } }))}
                className="voagpa-inputbase5"
              >
                {intentList.map(i => <option key={i} value={i}>{i}</option>)}
              </select>
              <button aria-label={t('common.delete')}
                type="button"
                onClick={() => removeDtmf(key)}
                title={t('common.delete')}
                className="voagpa-box-7"
                onMouseEnter={e => { e.currentTarget.style.color = 'var(--danger)' }}
                onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-3)' }}
              ><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
        <div className="voagpa-row-8">
          <input aria-label={t('voiceagent.tecla_ej_4')}
            type="text" placeholder={t('voiceagent.tecla_ej_4')} value={newKey}
            onChange={e => setNewKey(e.target.value)}
            maxLength={2}
            className="voagpa-inputbase6"
          />
          <input aria-label={t('voiceagent.etiqueta_visible')}
            type="text" placeholder={t('voiceagent.etiqueta_visible')} value={newLabel}
            onChange={e => setNewLabel(e.target.value)}
            className="voagpa-inputbase7"
          />
          <select value={newIntent} onChange={e => setNewIntent(e.target.value)} className="voagpa-inputbase5">
            {intentList.map(i => <option key={i} value={i}>{i}</option>)}
          </select>
          <Button size="sm" variant="secondary" icon={<Plus size={13} />}
            onClick={addDtmf}
            disabled={!newKey.trim() || !newLabel.trim()}
          >{t('voiceagent.anadir_tecla')}</Button>
        </div>
      </div>

      {/* Keywords por intent */}
      <div>
        <div className="voagpa-fieldlabel">{t('voiceagent.keywords_por_intent')}</div>
        <div className="voagpa-box-8">
          {t('voiceagent.si_la_transcripcion_del_usuario_contiene_alguna')}
        </div>
        <div className="u-stack-8">
          {intentList.map(intent => {
            const kws = (draft.intent_keywords || {})[intent] || []
            const isEditing = editingIntent === intent
            const color = INTENT_COLORS[intent]
            return (
              <div key={intent} className="voagpa-box-9">
                <div className="voagpa-row-9">
                  <span className="chip-dato" style={chipColor(color)}>{intent}</span>
                  <span className="u-text3-xs">{kws.length} {t('voiceagent.palabras')}</span>
                  <button className={`voagpa-row-22 ${isEditing ? 'voice-agent-panel-m5' : 'voice-agent-panel-m6'}`}
                    type="button"
                    onClick={() => { setEditingIntent(isEditing ? null : intent); setNewKw('') }}
                  ><Edit2 size={12} /> {isEditing ? 'Cerrar' : 'Editar'}</button>
                </div>
                <div className="voagpa-row-10">
                  {kws.map(kw => (
                    <span key={kw} className="voagpa-row-11">
                      {kw}
                      {isEditing && (
                        <button type="button" onClick={() => removeKeyword(intent, kw)}
                          className="voagpa-box-10"
                        >×</button>
                      )}
                    </span>
                  ))}
                </div>
                {isEditing && (
                  <div className="voagpa-row-12">
                    <input aria-label={t('voiceagent.nueva_keyword')}
                      type="text" placeholder={t('voiceagent.nueva_keyword')} value={newKw}
                      onChange={e => setNewKw(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && addKeyword(intent)}
                      className="voagpa-inputbase3"
                    />
                    <Button size="sm" variant="secondary" onClick={() => addKeyword(intent)} disabled={!newKw.trim()}>{t('voiceagent.anadir')}</Button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      <div className="u-actions-8">
        <Button variant="secondary" onClick={() => setDraft(null)}>{t('voiceagent.descartar_cambios')}</Button>
        <Button onClick={() => onSave(draft)} loading={saving}>{t('voiceagent.guardar_configuracion')}</Button>
      </div>
    </div>
  )
}

// ── Modal de detalle de sesión cerrada ────────────────────────────────────────

function SessionDetailModal({ session, onClose, openTicket }: { session: VoiceSession | null; onClose: () => void; openTicket: (id: string | number) => void }) {
  const t = useAppT()
  if (!session) return null
  const transcript: VoiceTurn[] = session.transcript || []
  const entities: VoiceEntities = session.entities || {}
  return (
    <Modal open title={`Sesión ${session.caller_id}`} onClose={onClose} width={620}>
      <div className="u-stack-12">
        <div className="u-wrap-6">
          <span className="chip-dato" style={chipColor(STATUS_COLOR[session.status || ''] || 'var(--text-3)')}>{session.status}</span>
          {session.intent && <span className="chip-dato" style={chipColor(INTENT_COLORS[session.intent] || INTENT_COLORS.unknown)}>{session.intent}</span>}
          {session.resolution && (
            <span className="chip-dato" style={chipColor(RESOLUTION_COLOR[session.resolution] || 'var(--text-3)')}>
              {RESOLUTION_LABEL[session.resolution] || session.resolution}
            </span>
          )}
          {session.channel && <span className="u-text3-xs">· {session.channel}</span>}
        </div>
        <div className="voagpa-row-13">
          {session.created_at && <span><span className="u-text3">{t('voiceagent.inicio')}</span> {new Date(session.created_at).toLocaleString(localeActivo())}</span>}
          {session.closed_at && <span><span className="u-text3">{t('voiceagent.cierre')}</span> {new Date(session.closed_at).toLocaleString(localeActivo())}</span>}
          {session.ticket_id && (
            <button
              type="button"
              onClick={() => openTicket(session.ticket_id!)}
              className="voagpa-box-11"
            >{t('voiceagent.ver_ticket_vinculado')}</button>
          )}
        </div>

        {(entities.email || entities.ticket_ref || entities.urgency_words?.length) && (
          <div>
            <div className="voagpa-fieldlabel">{t('voiceagent.entidades_extraidas')}</div>
            <div className="u-wrap-6">
              {entities.email && <span className="chip-dato" style={chipColor('var(--accent)')}>✉ {entities.email}</span>}
              {entities.ticket_ref && <span className="chip-dato" style={chipColor('var(--purple)')}>🔗 {entities.ticket_ref}</span>}
              {(entities.urgency_words || []).map((w, i) => <span key={i} className="chip-dato" style={chipColor('var(--orange)')}>{w}</span>)}
            </div>
          </div>
        )}

        <div>
          <div className="voagpa-fieldlabel">{t('voiceagent.transcripcion_turnos', { n: transcript.length })}</div>
          <div className="voagpa-stack-3">
            {transcript.length === 0 ? (
              <div className="voagpa-box-4">
                {t('voiceagent.sin_turnos_registrados')}
              </div>
            ) : transcript.map((turn, i) => {
              const isUser = turn.speaker === 'user'
              return (
                <div className={`voagpa-row-21 ${isUser ? 'voice-agent-panel-m7' : 'voice-agent-panel-m8'}`} key={i}>
                  <div className="voagpa-box-5">
                    <div className={`voagpa-box-14 ${isUser ? 'voice-agent-panel-m2' : 'voice-agent-panel-m3'}`}>
                      {turn.speaker} {turn.ts && `· ${new Date(turn.ts).toLocaleTimeString(localeActivo())}`}
                    </div>
                    <span className={`voagpa-box-15 voiceage-sx2 voice-agent-panel-e9 ${isUser ? 'voice-agent-panel-m10' : 'voice-agent-panel-m11'}`} style={{ '--voice-agent-panel-border': `1px solid ${isUser ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>{turn.text}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </Modal>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function VoiceAgentPanel() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const navigate = useNavigate()

  const [activeSessionId, setActiveSessionId] = useState<string | number | null>(null)
  const [callerInput, setCallerInput] = useState<string>('+34600000000')
  const [channel, setChannel] = useState<string>('phone')
  const [tab, setTab] = useState<string>('sessions')
  const [historyFilter, setHistoryFilter] = useState<string>('') // '' | 'active' | 'closed'
  const [detailSession, setDetailSession] = useState<VoiceSession | null>(null)

  const { data: sessionsData, isLoading } = useQuery({
    queryKey: ['voice-sessions', historyFilter],
    queryFn: () => voiceAgentApi.listSessions(historyFilter ? { status: historyFilter } : {}).then(r => r.data),
    refetchInterval: POLL_LIVE_MS,
  })

  const { data: config } = useQuery({
    queryKey: ['voice-config'],
    queryFn: () => voiceAgentApi.getConfig().then(r => r.data),
    enabled: tab === 'config',
  })

  // useMemo (auditoría 2026-08, P1-6): con `?? []` / `|| []` esto creaba un
  // array nuevo en cada render, así que los useMemo/useEffect que lo tienen
  // como dependencia se reejecutaban SIEMPRE — no memoizaban nada.
  const sessions: VoiceSession[] = useMemo(
    () => sessionsData?.sessions ?? [],
    [sessionsData],
  )
  const activeSession = useMemo(
    () => sessions.find((s: VoiceSession) => s.id === activeSessionId),
    [sessions, activeSessionId],
  )

  const errDetail = (e: unknown): string | undefined =>
    (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail

  const createSessionMutation = useMutation({
    mutationFn: (payload: { caller_id: string; channel: string }) => voiceAgentApi.createSession(payload).then(r => r.data),
    onSuccess: (data) => {
      setActiveSessionId(data.session?.id ?? null)
      toast.success(t('voiceagent.sesion_iniciada_greeting_v1', { v1: (data.greeting || '').slice(0, 60) }))
      qc.invalidateQueries({ queryKey: ['voice-sessions'] })
    },
    onError: (e: unknown) => toast.error(errDetail(e) || 'Error al iniciar sesión'),
  })

  const addTurnMutation = useMutation({
    mutationFn: ({ id, text }: { id: string | number; text: string }) => voiceAgentApi.addTurn(id, { speaker: 'user', text }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['voice-sessions'] }),
    onError: (e: unknown) => toast.error(errDetail(e) || 'Error al añadir turno'),
  })

  const closeMutation = useMutation({
    mutationFn: ({ id, resolution }: { id: string | number; resolution: string }) => voiceAgentApi.closeSession(id, { resolution }).then(r => r.data),
    onSuccess: (data: { resolution?: string }) => {
      const r = data?.resolution || ''
      toast.success(t('voiceagent.sesion_cerrada_resolution_label', { RESOLUTION_LABEL: RESOLUTION_LABEL[r] || r }))
      setActiveSessionId(null)
      qc.invalidateQueries({ queryKey: ['voice-sessions'] })
    },
    onError: (e: unknown) => toast.error(errDetail(e) || 'Error al cerrar sesión'),
  })

  const createTicketMutation = useMutation({
    mutationFn: (id: string | number) => voiceAgentApi.createTicket(id).then(r => r.data),
    onSuccess: (data: { number?: string }) => {
      toast.success(t('voiceagent.ticket_number_creado_desde_la_sesion', { number: data.number }))
      qc.invalidateQueries({ queryKey: ['voice-sessions'] })
    },
    onError: (e: unknown) => toast.error(errDetail(e) || 'Error al crear ticket'),
  })

  const saveConfigMutation = useMutation({
    mutationFn: (cfg: VoiceAgentConfig) => voiceAgentApi.updateConfig(cfg).then(r => r.data),
    onSuccess: () => {
      toast.success(t('etl.guardado'))
      qc.invalidateQueries({ queryKey: ['voice-config'] })
    },
    onError: (e: unknown) => toast.error(errDetail(e) || 'Error al guardar configuración'),
  })

  const openTicket = (ticketId: string | number) => navigate(`/service-desk?ticket=${ticketId}`)

  return (
    <Card className="voiceage-sx3">
      <div className="voagpa-row-14">
        <div className="u-row-center-8">
          <Phone size={18} className="voiceage-sx4" />
          <h2 className="voagpa-box-12">
            {t('sd.voice.title', 'Agente de voz / IVR')}
          </h2>
        </div>
        <div className="voagpa-row-15">
          <span className="chip-dato" style={chipColor('var(--accent)')}>{sessions.filter((s: VoiceSession) => s.status === 'active').length} {t('voiceagent.activas')}</span>
          <span className="chip-dato" style={chipColor('var(--text-3)')}>{sessions.filter((s: VoiceSession) => s.status === 'closed').length} {t('voiceagent.cerradas')}</span>
        </div>
      </div>

      <Tabs
        items={[
          { id: 'sessions', label: t('sd.voice.sessions', 'Sesiones') },
          { id: 'config',   label: t('sd.voice.config', 'Configuración') },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel="Voice agent"
      />

      {tab === 'sessions' && (
        <div>
          {/* Crear sesión */}
          <div className="u-mb-16">
            <div className="voagpa-fieldlabel">{t('sd.voice.new_session', 'Iniciar sesión manual')}</div>
            <div className="u-wrap-8">
              <input
                aria-label="Caller ID"
                type="text"
                placeholder="+34600000000"
                value={callerInput}
                onChange={e => setCallerInput(e.target.value)}
                className="voagpa-inputbase8"
              />
              <select value={channel} onChange={e => setChannel(e.target.value)} className="voagpa-inputbase5">
                <option value="phone">phone</option>
                <option value="sip">sip</option>
                <option value="web">web</option>
              </select>
              <Button
                onClick={() => createSessionMutation.mutate({ caller_id: callerInput, channel })}
                disabled={createSessionMutation.isPending || !callerInput.trim()}
                loading={createSessionMutation.isPending}
                icon={<Plus size={14} />}
              >{t('timer.start')}</Button>
            </div>
            <div className="voagpa-box-13">
              {t('voiceagent.para_llamadas_reales_configura_el_webhook_de')} <span className="u-mono">POST /sd/voice/webhook/twilio</span> {t('voiceagent.con_tu_phone_number')}
            </div>
          </div>

          {/* Sesión activa */}
          {activeSession && activeSession.status === 'active' && (
            <ActiveSessionCard
              session={activeSession}
              onClose={(res) => closeMutation.mutate({ id: activeSession.id, resolution: res })}
              onCreateTicket={() => createTicketMutation.mutate(activeSession.id)}
              onAddTurn={(text) => addTurnMutation.mutate({ id: activeSession.id, text })}
              sending={addTurnMutation.isPending}
              closing={closeMutation.isPending}
              creatingTicket={createTicketMutation.isPending}
              openTicket={openTicket}
            />
          )}

          {/* Filtro + lista */}
          <div className="voagpa-row-16">
            <div className="voagpa-fieldlabel">{t('voiceagent.sesiones_recientes')}</div>
            <div className="voagpa-row-17">
              {[['', 'Todas'], ['active', 'Activas'], ['closed', 'Cerradas']].map(([id, label]) => (
                <button className={`voagpa-box-16 ${historyFilter === id ? 'voice-agent-panel-m12' : 'voice-agent-panel-m13'}`}
                  key={id || 'all'}
                  type="button"
                  onClick={() => setHistoryFilter(id)}
                >{label}</button>
              ))}
            </div>
          </div>

          {isLoading ? (
            <div className="voagpa-row-6"><Spinner /></div>
          ) : sessions.length === 0 ? (
            <EmptyState icon="📞" title={t('sd.voice.no_sessions', 'Sin sesiones')} />
          ) : (
            <div className="u-stack-6">
              {sessions.filter((s: VoiceSession) => s.id !== activeSessionId).slice(0, 30).map((s: VoiceSession) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => {
                    if (s.status === 'active') setActiveSessionId(s.id)
                    else setDetailSession(s)
                  }}
                  className="voagpa-row-18"
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)' }}
                >
                  <div className="voagpa-row-19">
                    <span className="voagpa-txt-2">{s.caller_id}</span>
                    <span className="u-text3-xs">· {s.channel}</span>
                    {s.created_at && (
                      <span className="u-text3-xs">
                        · {new Date(s.created_at).toLocaleString(localeActivo())}
                      </span>
                    )}
                    <span className="u-text3-xs">
                      · {(s.transcript || []).length} {t('voiceagent.turnos_2')}
                    </span>
                  </div>
                  <div className="voagpa-row-20">
                    {s.intent && (
                      <span className="chip-dato" style={chipColor(INTENT_COLORS[s.intent] || INTENT_COLORS.unknown)}>{s.intent}</span>
                    )}
                    {s.resolution && (
                      <span className="chip-dato" style={chipColor(RESOLUTION_COLOR[s.resolution] || 'var(--text-3)')}>
                        {RESOLUTION_LABEL[s.resolution] || s.resolution}
                      </span>
                    )}
                    <span className="chip-dato" style={chipColor(STATUS_COLOR[s.status || ''] || 'var(--text-3)')}>{s.status}</span>
                    {s.ticket_id && <span className="chip-dato" style={chipColor('var(--accent)')}>{t('voiceagent.ticket')}</span>}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'config' && (
        <ConfigEditor
          config={config}
          onSave={(draft: VoiceAgentConfig) => saveConfigMutation.mutate(draft)}
          saving={saveConfigMutation.isPending}
        />
      )}

      <SessionDetailModal
        session={detailSession}
        onClose={() => setDetailSession(null)}
        openTicket={(id) => { setDetailSession(null); openTicket(id) }}
      />
    </Card>
  )
}
