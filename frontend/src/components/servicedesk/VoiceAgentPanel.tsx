/**
 * VoiceAgentPanel — asistente de llamadas (IVR) del Service Desk.
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
 *
 * 16-11-2026 (pasada de diseño): Card + Section con icono, StatusBadge con
 * los valores traducidos (estado, motivo, canal, quién habla y cierre salían
 * como código: `active`, `incident`, `phone`, `user`), filtro con `ds-input`
 * (eran botones segmentados), EmptyState con icono lucide (era 📞), iconos
 * lucide en vez de ✉ 🔗 ×, sin la ruta del webhook visible y sin textos
 * fijos en castellano («Editar», «Cerrar», «Todas», «Sesión», errores).
 * Fechas y horas con el formateador del idioma.
 */
import { useState, useEffect, useMemo, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { voiceAgentApi } from '../../services/api'
import type { ConfigDelAgenteDeVoz, SesionDeVoz, TurnoDeVoz } from '../../services/api/tipos-analitica'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { Phone, Mic, PhoneOff, Plus, ExternalLink, Pencil, Trash2, Mail, Link2, X, Send, Ticket } from 'lucide-react'
import { Card, Button, IconButton, Pulsable, Select, Tabs, Spinner, EmptyState, Modal, Section } from '../ui'
import StatusBadge from '../ui/StatusBadge'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { fmtDateTime, formateadorDeFecha } from '../../utils/helpers'
import { POLL_LIVE_MS } from '../../constants/timings'
import { useOrgSettings } from '../../hooks/useOrgSettings'
import './VoiceAgentPanel.css'

type VoiceTurn = TurnoDeVoz
type VoiceEntities = SesionDeVoz['entities']
type VoiceSession = SesionDeVoz
/** Borrador del editor: lo que el usuario va cambiando antes de guardar. */
type VoiceAgentConfig = Partial<ConfigDelAgenteDeVoz>

const INTENT_KIND: Record<string, StatusBadgeKind> = {
  incident: 'danger', query: 'accent', urgent: 'orange', agent: 'purple', unknown: 'neutral',
}
const RESOLUTION_KIND: Record<string, StatusBadgeKind> = {
  resolved: 'success', transferred: 'accent', abandoned: 'neutral', voicemail: 'purple',
}
const RESOLUCIONES = ['resolved', 'transferred', 'abandoned', 'voicemail']
const CANALES = ['phone', 'sip', 'web']
const INTENTS = ['incident', 'query', 'urgent', 'agent']

const horaCorta = (iso?: string | null) => (iso ? formateadorDeFecha({ hour: '2-digit', minute: '2-digit' }).format(new Date(iso)) : '')

/** Insignias de estado, motivo, cierre y canal de una sesión. */
function EtiquetasDeSesion({ session }: { session: VoiceSession }) {
  const t = useAppT()
  return (
    <>
      <StatusBadge kind={session.status === 'active' ? 'success' : 'neutral'} dot caps={false}>{etiquetaCodigo(t, 'voiceagent.estado', session.status)}</StatusBadge>
      {session.intent && <StatusBadge kind={INTENT_KIND[session.intent] || 'neutral'} caps={false}>{etiquetaCodigo(t, 'voiceagent.intent', session.intent)}</StatusBadge>}
      {session.resolution && <StatusBadge kind={RESOLUTION_KIND[session.resolution] || 'neutral'} caps={false}>{etiquetaCodigo(t, 'voiceagent.resolucion', session.resolution)}</StatusBadge>}
      {session.channel && <span className="u-text3-xs">{etiquetaCodigo(t, 'voiceagent.canal', session.channel)}</span>}
    </>
  )
}

/** Datos sacados de la conversación (correo, ticket citado, palabras de urgencia). */
function Entidades({ entities }: { entities: VoiceEntities }) {
  if (!(entities.email || entities.ticket_ref || entities.urgency_words?.length)) return null
  return (
    <div className="u-wrap-6">
      {entities.email && <StatusBadge kind="accent" caps={false}><Mail size={11} aria-hidden="true" /> {entities.email}</StatusBadge>}
      {entities.ticket_ref && <StatusBadge kind="purple" caps={false}><Link2 size={11} aria-hidden="true" /> {entities.ticket_ref}</StatusBadge>}
      {(entities.urgency_words || []).map((w, i) => <StatusBadge key={i} kind="orange" caps={false}>{w}</StatusBadge>)}
    </div>
  )
}

/** La conversación, turno a turno. */
function Transcripcion({ transcript }: { transcript: VoiceTurn[] }) {
  const t = useAppT()
  if (transcript.length === 0) return <div className="vap-vacio">{t('voiceagent.sin_turnos_registrados_todavia')}</div>
  return (
    <div className="vap-chat">
      {transcript.map((turn, i) => {
        const lado = turn.speaker === 'user' ? 'user' : turn.speaker === 'bot' ? 'bot' : 'otro'
        return (
          <div key={i} className={`vap-turno vap-turno--${lado}`}>
            <div className="vap-turno__quien">
              {etiquetaCodigo(t, 'voiceagent.hablante', turn.speaker)}{turn.ts ? ` · ${horaCorta(turn.ts)}` : ''}
            </div>
            <div className="vap-turno__texto">{turn.text}</div>
          </div>
        )
      })}
    </div>
  )
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
  const enviar = () => { if (turnText.trim()) { onAddTurn(turnText.trim()); setTurnText('') } }

  return (
    <div className="ds-card vap-activa">
      <div className="vap-activa__cab">
        <div className="vap-activa__quien">
          <Mic size={14} aria-hidden="true" className="vap-icono-accent" />
          <span className="vap-numero">{session.caller_id}</span>
          <EtiquetasDeSesion session={session} />
        </div>
        <div className="u-wrap-center-8">
          {session.ticket_id ? (
            <Button size="sm" variant="ghost" icon={<ExternalLink size={13} />} onClick={() => openTicket(session.ticket_id!)}>{t('voiceagent.ver_ticket')}</Button>
          ) : (
            <Button size="sm" variant="secondary" icon={<Ticket size={13} />} onClick={onCreateTicket} loading={creatingTicket}>{t('sd.voice.create_ticket')}</Button>
          )}
          <Button size="sm" variant="secondary" icon={<PhoneOff size={13} />} onClick={() => setShowCloseConfirm(v => !v)}>{t('voiceagent.cerrar_sesion')}</Button>
        </div>
      </div>

      {showCloseConfirm && (
        <div className="vap-cierre">
          <label className="u-text2-sm" htmlFor={`vap-cierre-${session.id}`}>{t('voiceagent.cerrar_como')}</label>
          <Select suelto placeholder={false} id={`vap-cierre-${session.id}`} value={resolution} onChange={e => setResolution(e.target.value)}>
            {RESOLUCIONES.map(id => <option key={id} value={id}>{etiquetaCodigo(t, 'voiceagent.resolucion', id)}</option>)}
          </Select>
          <Button size="sm" loading={closing} onClick={() => onClose(resolution)}>{t('voiceagent.confirmar_cierre')}</Button>
          <Button size="sm" variant="ghost" onClick={() => setShowCloseConfirm(false)}>{t('common.cancel')}</Button>
        </div>
      )}

      <Entidades entities={session.entities || {}} />
      <Transcripcion transcript={session.transcript || []} />

      {session.status === 'active' && (
        <div className="vap-fila">
          <input aria-label={t('voiceagent.anadir_turno_texto_del_usuario')}
            type="text"
            placeholder={t('voiceagent.anadir_turno_texto_del_usuario')}
            value={turnText}
            onChange={e => setTurnText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') enviar() }}
            className="ds-input vap-fila__campo"
          />
          <Button size="sm" icon={<Send size={13} />} onClick={enviar} disabled={!turnText.trim() || sending} loading={sending}>{t('chat.send')}</Button>
        </div>
      )}
    </div>
  )
}

// ── Configuración (saludo, idioma, menú de teclas, palabras clave) ─────────────

interface ConfigEditorProps {
  config: VoiceAgentConfig | undefined | null
  onSave: (draft: VoiceAgentConfig) => void
  saving: boolean
}

/** Idiomas (BCP-47) que ofrece el selector del agente de voz, con su nombre en su idioma. */
const VOICE_LANGUAGES: Array<[string, string]> = [
  ['es-ES', 'Español (es-ES)'], ['en-US', 'English (en-US)'], ['ca-ES', 'Català (ca-ES)'], ['fr-FR', 'Français (fr-FR)'], ['pt-PT', 'Português (pt-PT)'],
]

function ConfigEditor({ config, onSave, saving }: ConfigEditorProps) {
  const t = useAppT()
  const id = useId()
  const [draft, setDraft] = useState<VoiceAgentConfig | null>(null)
  const [newKey, setNewKey] = useState<string>('')
  const [newLabel, setNewLabel] = useState<string>('')
  const [newIntent, setNewIntent] = useState<string>('incident')
  const [editingIntent, setEditingIntent] = useState<string | null>(null)
  const [newKw, setNewKw] = useState<string>('')
  // Sin idioma configurado: el de la empresa, en la variante que ofrece el selector.
  const { language: idiomaOrg } = useOrgSettings()
  const idiomaPorDefecto = VOICE_LANGUAGES.find(([l]) => l.split('-')[0] === idiomaOrg)?.[0] ?? VOICE_LANGUAGES[0][0]

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

  if (!draft) return <div className="vap-cargando"><Spinner /></div>

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
  const opcionesIntent = INTENTS.map(i => <option key={i} value={i}>{etiquetaCodigo(t, 'voiceagent.intent', i)}</option>)

  return (
    <div className="u-stack-16">
      <div className="ui-field">
        <label htmlFor={`${id}-saludo`} className="campo-etiqueta">{t('sd.voice.greeting')}</label>
        <textarea id={`${id}-saludo`} rows={2} value={draft.greeting} onChange={e => setField('greeting', e.target.value)} className="campo-form vap-textarea" />
      </div>

      <div className="vap-dos">
        <div className="ui-field">
          <label htmlFor={`${id}-idioma`} className="campo-etiqueta">{t('voiceagent.idioma_bcp_47')}</label>
          <Select suelto placeholder={false} id={`${id}-idioma`} value={draft.language} onChange={e => setField('language', e.target.value)} className="campo-form">
            {VOICE_LANGUAGES.map(([code, nombre]) => <option key={code} value={code}>{nombre}</option>)}
          </Select>
        </div>
        <div className="ui-field">
          <label htmlFor={`${id}-silencio`} className="campo-etiqueta">{t('voiceagent.silencio_maximo_segundos')}</label>
          <input id={`${id}-silencio`} type="number" min={1} max={120} value={draft.max_silence_seconds}
            onChange={e => setField('max_silence_seconds', Number(e.target.value))} className="campo-form" />
        </div>
      </div>

      {/* Menú de teclas */}
      <div className="u-stack-8">
        <div className="campo-etiqueta">{t('sd.voice.dtmf_menu')}</div>
        {Object.entries(draft.dtmf_menu || {}).length === 0 && (
          <div className="u-text3-xs">{t('voiceagent.sin_opciones_dtmf_configuradas')}</div>
        )}
        {Object.entries(draft.dtmf_menu || {}).map(([key, val]) => (
          <div key={key} className="vap-tecla">
            <span className="vap-tecla__num">{key}</span>
            <input aria-label={t('voiceagent.etiqueta_de_tecla', { n: key })} type="text" value={val.label}
              onChange={e => setDraft(d => ({ ...(d as VoiceAgentConfig), dtmf_menu: { ...(d as VoiceAgentConfig).dtmf_menu, [key]: { ...val, label: e.target.value } } }))}
              className="ds-input vap-fila__campo" />
            <Select suelto placeholder={false} aria-label={t('voiceagent.motivo_de_tecla', { n: key })} value={val.intent}
              onChange={e => setDraft(d => ({ ...(d as VoiceAgentConfig), dtmf_menu: { ...(d as VoiceAgentConfig).dtmf_menu, [key]: { ...val, intent: e.target.value } } }))}
              className="vap-select">
              {opcionesIntent}
            </Select>
            <IconButton ariaLabel={t('common.delete')} title={t('common.delete')} onClick={() => removeDtmf(key)} className="vap-icono-btn">
              <Trash2 size={14} aria-hidden="true" />
            </IconButton>
          </div>
        ))}
        <div className="vap-fila">
          <input aria-label={t('voiceagent.tecla_ej_4')} type="text" placeholder={t('voiceagent.tecla_ej_4')} value={newKey}
            onChange={e => setNewKey(e.target.value)} maxLength={2} className="ds-input vap-tecla__nueva" />
          <input aria-label={t('voiceagent.etiqueta_visible')} type="text" placeholder={t('voiceagent.etiqueta_visible')} value={newLabel}
            onChange={e => setNewLabel(e.target.value)} className="ds-input vap-fila__campo" />
          <Select suelto placeholder={false} aria-label={t('voiceagent.motivo')} value={newIntent} onChange={e => setNewIntent(e.target.value)} className="vap-select">
            {opcionesIntent}
          </Select>
          <Button size="sm" variant="secondary" icon={<Plus size={13} />} onClick={addDtmf} disabled={!newKey.trim() || !newLabel.trim()}>{t('voiceagent.anadir_tecla')}</Button>
        </div>
      </div>

      {/* Palabras clave por motivo */}
      <div className="u-stack-8">
        <div className="campo-etiqueta">{t('voiceagent.keywords_por_intent')}</div>
        <div className="u-text3-xs">{t('voiceagent.si_la_transcripcion_del_usuario_contiene_alguna')}</div>
        {INTENTS.map(intent => {
          const kws = (draft.intent_keywords || {})[intent] || []
          const isEditing = editingIntent === intent
          return (
            <div key={intent} className="vap-motivo">
              <div className="vap-motivo__cab">
                <StatusBadge kind={INTENT_KIND[intent]} caps={false}>{etiquetaCodigo(t, 'voiceagent.intent', intent)}</StatusBadge>
                <span className="u-text3-xs">{t('voiceagent.n_palabras', { n: kws.length })}</span>
                <span className="ds-toolbar__spacer" />
                <Button size="xs" variant="ghost" icon={isEditing ? <X size={12} /> : <Pencil size={12} />}
                  onClick={() => { setEditingIntent(isEditing ? null : intent); setNewKw('') }}>
                  {isEditing ? t('voiceagent.terminar') : t('common.edit')}
                </Button>
              </div>
              <div className="u-wrap-6">
                {kws.map(kw => (
                  <span key={kw} className="vap-palabra">
                    {kw}
                    {isEditing && (
                      <IconButton onClick={() => removeKeyword(intent, kw)} className="vap-palabra__quitar"
                        ariaLabel={t('voiceagent.quitar_palabra', { p: kw })} title={t('voiceagent.quitar_palabra', { p: kw })}>
                        <X size={11} aria-hidden="true" />
                      </IconButton>
                    )}
                  </span>
                ))}
              </div>
              {isEditing && (
                <div className="vap-fila">
                  <input aria-label={t('voiceagent.nueva_keyword')} type="text" placeholder={t('voiceagent.nueva_keyword')} value={newKw}
                    onChange={e => setNewKw(e.target.value)} onKeyDown={e => e.key === 'Enter' && addKeyword(intent)} className="ds-input vap-fila__campo" />
                  <Button size="sm" variant="secondary" icon={<Plus size={13} />} onClick={() => addKeyword(intent)} disabled={!newKw.trim()}>{t('voiceagent.anadir')}</Button>
                </div>
              )}
            </div>
          )
        })}
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
  return (
    <Modal open title={t('voiceagent.sesion_de', { n: session.caller_id })} onClose={onClose} width={620}>
      <div className="u-stack-12">
        <div className="u-wrap-center-8"><EtiquetasDeSesion session={session} /></div>
        <div className="vap-meta">
          {session.created_at && <span><span className="u-text3">{t('voiceagent.inicio')}</span> {fmtDateTime(session.created_at)}</span>}
          {session.closed_at && <span><span className="u-text3">{t('voiceagent.cierre')}</span> {fmtDateTime(session.closed_at)}</span>}
          {session.ticket_id && (
            <Button size="xs" variant="ghost" icon={<ExternalLink size={12} />} onClick={() => openTicket(session.ticket_id!)}>{t('voiceagent.ver_ticket_vinculado')}</Button>
          )}
        </div>
        {(session.entities?.email || session.entities?.ticket_ref || session.entities?.urgency_words?.length) && (
          <div className="u-stack-6">
            <div className="campo-etiqueta">{t('voiceagent.entidades_extraidas')}</div>
            <Entidades entities={session.entities || {}} />
          </div>
        )}
        <div className="u-stack-6">
          <div className="campo-etiqueta">{t('voiceagent.transcripcion_turnos', { n: transcript.length })}</div>
          <Transcripcion transcript={transcript} />
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
  const id = useId()

  const [activeSessionId, setActiveSessionId] = useState<string | number | null>(null)
  const [callerInput, setCallerInput] = useState<string>('')
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
    onError: (e: unknown) => toast.error(errDetail(e) || t('voiceagent.error_iniciar')),
  })

  const addTurnMutation = useMutation({
    mutationFn: ({ id: sid, text }: { id: string | number; text: string }) => voiceAgentApi.addTurn(sid, { speaker: 'user', text }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['voice-sessions'] }),
    onError: (e: unknown) => toast.error(errDetail(e) || t('voiceagent.error_turno')),
  })

  const closeMutation = useMutation({
    mutationFn: ({ id: sid, resolution }: { id: string | number; resolution: string }) => voiceAgentApi.closeSession(sid, { resolution }).then(r => r.data),
    onSuccess: (data: { resolution?: string }) => {
      toast.success(t('voiceagent.sesion_cerrada_resolution_label', { RESOLUTION_LABEL: etiquetaCodigo(t, 'voiceagent.resolucion', data?.resolution || '') }))
      setActiveSessionId(null)
      qc.invalidateQueries({ queryKey: ['voice-sessions'] })
    },
    onError: (e: unknown) => toast.error(errDetail(e) || t('voiceagent.error_cerrar')),
  })

  const createTicketMutation = useMutation({
    mutationFn: (sid: string | number) => voiceAgentApi.createTicket(sid).then(r => r.data),
    onSuccess: (data: { number?: string }) => {
      toast.success(t('voiceagent.ticket_number_creado_desde_la_sesion', { number: data.number }))
      qc.invalidateQueries({ queryKey: ['voice-sessions'] })
    },
    onError: (e: unknown) => toast.error(errDetail(e) || t('voiceagent.error_ticket')),
  })

  const saveConfigMutation = useMutation({
    mutationFn: (cfg: VoiceAgentConfig) => voiceAgentApi.updateConfig(cfg).then(r => r.data),
    onSuccess: () => {
      toast.success(t('etl.guardado'))
      qc.invalidateQueries({ queryKey: ['voice-config'] })
    },
    onError: (e: unknown) => toast.error(errDetail(e) || t('voiceagent.error_guardar')),
  })

  const openTicket = (ticketId: string | number) => navigate(`/service-desk?ticket=${ticketId}`)
  const activas = sessions.filter((s: VoiceSession) => s.status === 'active').length
  const cerradas = sessions.filter((s: VoiceSession) => s.status === 'closed').length
  const lista = sessions.filter((s: VoiceSession) => s.id !== activeSessionId).slice(0, 30)

  return (
    <Card>
      <Section
        title={<span className="vap-titulo"><Phone size={16} aria-hidden="true" />{t('service_desk.tab_voice')}</span>}
        subtitle={t('voiceagent.desc')}
        actions={<>
          <StatusBadge kind="success" dot caps={false}>{t('voiceagent.n_activas', { n: activas })}</StatusBadge>
          <StatusBadge kind="neutral" caps={false}>{t('voiceagent.n_cerradas', { n: cerradas })}</StatusBadge>
        </>}
      >
        <Tabs
          items={[
            { id: 'sessions', label: t('sd.voice.sessions') },
            { id: 'config',   label: t('sd.voice.config') },
          ]}
          active={tab}
          onChange={setTab}
          ariaLabel={t('service_desk.tab_voice')}
        />

        {tab === 'sessions' && (
          <div className="u-stack-16">
            {/* Nueva llamada */}
            <div className="u-stack-8">
              <div className="ds-eyebrow">{t('sd.voice.new_session')}</div>
              <div className="vap-fila">
                <div className="ui-field vap-fila__campo">
                  <label htmlFor={`${id}-numero`} className="campo-etiqueta">{t('voiceagent.numero_que_llama')}</label>
                  <input id={`${id}-numero`} type="tel" placeholder="+34 600 000 000" value={callerInput}
                    onChange={e => setCallerInput(e.target.value)} className="campo-form" />
                </div>
                <div className="ui-field">
                  <label htmlFor={`${id}-canal`} className="campo-etiqueta">{t('voiceagent.canal_lbl')}</label>
                  <Select suelto placeholder={false} id={`${id}-canal`} value={channel} onChange={e => setChannel(e.target.value)} className="campo-form vap-select">
                    {CANALES.map(c => <option key={c} value={c}>{etiquetaCodigo(t, 'voiceagent.canal', c)}</option>)}
                  </Select>
                </div>
                <Button
                  onClick={() => createSessionMutation.mutate({ caller_id: callerInput.trim(), channel })}
                  disabled={createSessionMutation.isPending || !callerInput.trim()}
                  loading={createSessionMutation.isPending}
                  icon={<Plus size={14} />}
                >{t('voiceagent.iniciar')}</Button>
              </div>
              <div className="u-text3-xs">{t('voiceagent.llamadas_reales')}</div>
            </div>

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

            {/* Sesiones recientes */}
            <div className="u-stack-8">
              <div className="ds-toolbar">
                <div className="ds-eyebrow">{t('voiceagent.sesiones_recientes')}</div>
                <span className="ds-toolbar__spacer" />
                <Select suelto placeholder={false} aria-label={t('voiceagent.filtrar')} value={historyFilter} onChange={e => setHistoryFilter(e.target.value)} className="vap-select">
                  <option value="">{t('voiceagent.todas')}</option>
                  <option value="active">{t('voiceagent.solo_activas')}</option>
                  <option value="closed">{t('voiceagent.solo_cerradas')}</option>
                </Select>
              </div>

              {isLoading ? (
                <div className="vap-cargando"><Spinner /></div>
              ) : lista.length === 0 ? (
                <EmptyState icon={<Phone size={28} />} title={t('sd.voice.no_sessions')} description={t('voiceagent.sin_sesiones_desc')} />
              ) : (
                <ul className="vap-lista">
                  {lista.map((s: VoiceSession) => (
                    <li key={s.id}>
                      <Pulsable className="vap-sesion"
                        onClick={() => { if (s.status === 'active') setActiveSessionId(s.id); else setDetailSession(s) }}>
                        <span className="vap-sesion__datos">
                          <span className="vap-numero">{s.caller_id}</span>
                          <span className="u-text3-xs">{s.created_at ? fmtDateTime(s.created_at) : ''}</span>
                          <span className="u-text3-xs">{t('voiceagent.n_turnos', { n: (s.transcript || []).length })}</span>
                        </span>
                        <span className="u-wrap-center-8">
                          <EtiquetasDeSesion session={s} />
                          {s.ticket_id && <StatusBadge kind="accent" caps={false}><Ticket size={11} aria-hidden="true" /> {t('voiceagent.ticket')}</StatusBadge>}
                        </span>
                      </Pulsable>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        {tab === 'config' && (
          <ConfigEditor
            config={config}
            onSave={(draft: VoiceAgentConfig) => saveConfigMutation.mutate(draft)}
            saving={saveConfigMutation.isPending}
          />
        )}
      </Section>

      <SessionDetailModal
        session={detailSession}
        onClose={() => setDetailSession(null)}
        openTicket={(tid) => { setDetailSession(null); openTicket(tid) }}
      />
    </Card>
  )
}
