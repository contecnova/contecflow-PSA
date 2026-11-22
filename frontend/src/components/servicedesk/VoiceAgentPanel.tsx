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
 *
 * 19-11-2026: la pestaña «Configuración» (saludo, idioma, teclas, palabras
 * clave) vive en Configuración → Service desk → Agente de voz
 * (`/settings/sd-voz`, ConfigAgenteDeVoz.tsx). Aquí quedan solo las sesiones,
 * sin botón «Configurar».
 */
import { useState, useMemo, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { voiceAgentApi } from '../../services/api'
import type { SesionDeVoz, TurnoDeVoz } from '../../services/api/tipos-analitica'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { Phone, Mic, PhoneOff, Plus, ExternalLink, Mail, Link2, Send, Ticket } from 'lucide-react'
import { Card, Button, Pulsable, Select, Spinner, EmptyState, Modal, Section, Input } from '../ui'
import StatusBadge from '../ui/StatusBadge'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { fmtDateTime, formateadorDeFecha } from '../../utils/helpers'
import { POLL_LIVE_MS } from '../../constants/timings'
import './VoiceAgentPanel.css'

type VoiceTurn = TurnoDeVoz
type VoiceEntities = SesionDeVoz['entities']
type VoiceSession = SesionDeVoz

const INTENT_KIND: Record<string, StatusBadgeKind> = {
  incident: 'danger', query: 'accent', urgent: 'orange', agent: 'purple', unknown: 'neutral',
}
const RESOLUTION_KIND: Record<string, StatusBadgeKind> = {
  resolved: 'success', transferred: 'accent', abandoned: 'neutral', voicemail: 'purple',
}
const RESOLUCIONES = ['resolved', 'transferred', 'abandoned', 'voicemail']
const CANALES = ['phone', 'sip', 'web']

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
  const [historyFilter, setHistoryFilter] = useState<string>('') // '' | 'active' | 'closed'
  const [detailSession, setDetailSession] = useState<VoiceSession | null>(null)

  const { data: sessionsData, isLoading } = useQuery({
    queryKey: ['voice-sessions', historyFilter],
    queryFn: () => voiceAgentApi.listSessions(historyFilter ? { status: historyFilter } : {}).then(r => r.data),
    refetchInterval: POLL_LIVE_MS,
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
          <div className="u-stack-16">
            {/* Nueva llamada */}
            <div className="u-stack-8">
              <div className="ds-eyebrow">{t('sd.voice.new_session')}</div>
              <div className="vap-fila">
                <div className="ui-field vap-fila__campo">
                  <label htmlFor={`${id}-numero`} className="campo-etiqueta">{t('voiceagent.numero_que_llama')}</label>
                  <Input id={`${id}-numero`} type="tel" placeholder="+34 600 000 000" value={callerInput} onChange={e => setCallerInput(e.target.value)} inputClassName="campo-form" />
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
      </Section>

      <SessionDetailModal
        session={detailSession}
        onClose={() => setDetailSession(null)}
        openTicket={(tid) => { setDetailSession(null); openTicket(tid) }}
      />
    </Card>
  )
}
