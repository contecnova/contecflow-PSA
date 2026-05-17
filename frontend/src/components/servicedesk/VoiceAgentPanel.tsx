// @ts-nocheck
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
import React, { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { voiceAgentApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { Phone, Mic, StopCircle, Plus, ExternalLink, Edit2, Trash2 } from 'lucide-react'
import { Card, Button, Tabs, Spinner, EmptyState, Modal } from '../ui'
import { useToast } from '../../context/ToastContext'

// TODO type: voiceAgentApi payloads — needs shared types
interface VoiceTurn {
  id?: string | number
  speaker?: string
  text?: string
  intent?: string
  created_at?: string
  [k: string]: unknown
}

interface VoiceSession {
  id: string | number
  caller?: string
  caller_id?: string
  channel?: string
  status?: string
  created_at?: string
  ticket_id?: string | number | null
  ticket_number?: string | null
  turns?: VoiceTurn[]
  resolution?: string
  [k: string]: unknown
}

interface VoiceAgentConfig {
  greeting?: string
  language?: string
  max_silence_seconds?: number
  dtmf_menu?: Record<string, string>
  intent_keywords?: Record<string, string[]>
}

const INTENT_COLORS: Record<string, string> = {
  incident: 'var(--danger)',
  query:    'var(--accent)',
  urgent:   'var(--orange)',
  agent:    'var(--purple)',
  unknown:  'var(--text-3)',
}

const RESOLUTION_LABEL = {
  resolved:    'Resuelta',
  transferred: 'Transferida',
  abandoned:   'Abandonada',
  voicemail:   'Buzón de voz',
}

const RESOLUTION_COLOR = {
  resolved:    'var(--success)',
  transferred: 'var(--accent)',
  abandoned:   'var(--text-3)',
  voicemail:   'var(--purple)',
}

const STATUS_COLOR = {
  active: 'var(--success)',
  closed: 'var(--text-3)',
}

const fieldLabel = {
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  color: 'var(--text-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 6,
}
const inputBase = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '8px 12px',
  color: 'var(--text-1)',
  fontSize: 'var(--text-sm)',
  fontFamily: 'inherit',
  outline: 'none',
  boxSizing: 'border-box',
}
const chip = (color) => ({
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color,
  background: `color-mix(in srgb, ${color} 15%, transparent)`,
  border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
  borderRadius: 'var(--radius-full, 999px)',
  padding: '2px 9px',
  whiteSpace: 'nowrap',
})

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
  const [turnText, setTurnText] = useState<string>('')
  const [resolution, setResolution] = useState<string>('resolved')
  const [showCloseConfirm, setShowCloseConfirm] = useState<boolean>(false)

  const transcript = session.transcript || []
  const entities = session.entities || {}
  const hasEntities = entities.email || entities.ticket_ref || entities.urgency_words?.length

  return (
    <div style={{
      background: 'var(--surface-3)',
      border: '1px solid color-mix(in srgb, var(--success) 30%, var(--surface-4))',
      borderRadius: 12,
      padding: '14px 16px',
      marginBottom: 16,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <Mic size={14} style={{ color: 'var(--success)', flexShrink: 0 }} />
          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-1)', fontFamily: 'var(--font-mono)' }}>
            {session.caller_id}
          </span>
          <span style={chip(STATUS_COLOR[session.status] || 'var(--text-3)')}>{session.status}</span>
          {session.intent && (
            <span style={chip(INTENT_COLORS[session.intent] || INTENT_COLORS.unknown)}>{session.intent}</span>
          )}
          {session.channel && (
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>· {session.channel}</span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {session.ticket_id ? (
            <Button
              size="sm"
              variant="ghost"
              icon={<ExternalLink size={13} />}
              onClick={() => openTicket(session.ticket_id)}
            >Ver ticket</Button>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              onClick={onCreateTicket}
              loading={creatingTicket}
            >Crear ticket</Button>
          )}
          <button
            type="button"
            onClick={() => setShowCloseConfirm(v => !v)}
            title="Cerrar sesión"
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: 'var(--text-3)', padding: 4, display: 'inline-flex',
            }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--danger)' }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-3)' }}
          >
            <StopCircle size={18} />
          </button>
        </div>
      </div>

      {showCloseConfirm && (
        <div style={{
          background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '10px 12px', marginBottom: 12,
          display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
        }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>Cerrar como:</span>
          <select value={resolution} onChange={e => setResolution(e.target.value)}
            style={{ ...inputBase, width: 'auto', padding: '4px 10px' }}>
            {Object.entries(RESOLUTION_LABEL).map(([id, label]) => (
              <option key={id} value={id}>{label}</option>
            ))}
          </select>
          <Button
            size="sm"
            variant="danger"
            loading={closing}
            onClick={() => onClose(resolution)}
          >Confirmar cierre</Button>
          <Button size="sm" variant="secondary" onClick={() => setShowCloseConfirm(false)}>Cancelar</Button>
        </div>
      )}

      {/* Entities */}
      {hasEntities && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
          {entities.email && (
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '2px 8px' }}>
              ✉ {entities.email}
            </span>
          )}
          {entities.ticket_ref && (
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)', background: 'var(--accent-muted)', border: '1px solid color-mix(in srgb, var(--accent) 25%, transparent)', borderRadius: 6, padding: '2px 8px', fontFamily: 'var(--font-mono)' }}>
              🔗 {entities.ticket_ref}
            </span>
          )}
          {(entities.urgency_words || []).map((w, i) => (
            <span key={i} style={chip('var(--orange)')}>{w}</span>
          ))}
        </div>
      )}

      {/* Transcript */}
      <div style={{
        maxHeight: 220, overflowY: 'auto',
        background: 'var(--surface-1)',
        border: '1px solid var(--surface-4)',
        borderRadius: 8, padding: 10, marginBottom: 10,
        display: 'flex', flexDirection: 'column', gap: 6,
      }}>
        {transcript.length === 0 ? (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textAlign: 'center', padding: 16 }}>
            Sin turnos registrados todavía.
          </div>
        ) : transcript.map((turn, i) => {
          const isUser = turn.speaker === 'user'
          const isBot  = turn.speaker === 'bot'
          const align = isUser ? 'flex-end' : 'flex-start'
          const bg = isUser ? 'var(--accent-muted)' : isBot ? 'var(--surface-3)' : 'var(--surface-4)'
          const fg = isUser ? 'var(--accent)' : isBot ? 'var(--text-2)' : 'var(--text-1)'
          const border = isUser ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'
          return (
            <div key={i} style={{ display: 'flex', justifyContent: align }}>
              <div style={{ maxWidth: '78%' }}>
                <div style={{
                  fontSize: 'var(--text-2xs)', color: 'var(--text-3)',
                  textAlign: align === 'flex-end' ? 'right' : 'left', marginBottom: 2,
                  textTransform: 'uppercase', letterSpacing: '0.05em',
                }}>
                  {turn.speaker} {turn.ts && `· ${new Date(turn.ts).toLocaleTimeString()}`}
                </div>
                <span style={{
                  display: 'inline-block',
                  fontSize: 'var(--text-xs)',
                  padding: '5px 10px',
                  borderRadius: 8,
                  background: bg, color: fg,
                  border: `1px solid ${border}`,
                }}>{turn.text}</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Add turn (sólo si activa) */}
      {session.status === 'active' && (
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            placeholder="Añadir turno (texto del usuario)"
            value={turnText}
            onChange={e => setTurnText(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && turnText.trim()) {
                onAddTurn(turnText.trim())
                setTurnText('')
              }
            }}
            style={{ ...inputBase, flex: 1 }}
          />
          <Button
            size="sm"
            onClick={() => { if (turnText.trim()) { onAddTurn(turnText.trim()); setTurnText('') } }}
            disabled={!turnText.trim() || sending}
            loading={sending}
          >Enviar</Button>
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

function ConfigEditor({ config, onSave, saving }: ConfigEditorProps) {
  const t = useAppT()
  const [draft, setDraft] = useState<VoiceAgentConfig | null>(null)
  const [newKey, setNewKey] = useState<string>('')
  const [newLabel, setNewLabel] = useState<string>('')
  const [newIntent, setNewIntent] = useState<string>('incident')
  const [editingIntent, setEditingIntent] = useState<string | null>(null)
  const [newKw, setNewKw] = useState<string>('')

  useEffect(() => {
    if (config && !draft) setDraft({
      greeting: config.greeting || '',
      language: config.language || 'es-ES',
      max_silence_seconds: config.max_silence_seconds ?? 10,
      dtmf_menu: { ...(config.dtmf_menu || {}) },
      intent_keywords: Object.fromEntries(
        Object.entries(config.intent_keywords || {}).map(([k, v]) => [k, [...(v || [])]])
      ),
    })
  }, [config]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!draft) return <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>

  const setField = (k, v) => setDraft(d => ({ ...d, [k]: v }))

  const addDtmf = () => {
    if (!newKey.trim() || !newLabel.trim()) return
    setDraft(d => ({
      ...d,
      dtmf_menu: { ...d.dtmf_menu, [newKey.trim()]: { intent: newIntent, label: newLabel.trim() } }
    }))
    setNewKey(''); setNewLabel(''); setNewIntent('incident')
  }
  const removeDtmf = (key) => {
    setDraft(d => {
      const { [key]: _, ...rest } = d.dtmf_menu
      return { ...d, dtmf_menu: rest }
    })
  }
  const addKeyword = (intent) => {
    if (!newKw.trim()) return
    const kw = newKw.trim().toLowerCase()
    setDraft(d => ({
      ...d,
      intent_keywords: {
        ...d.intent_keywords,
        [intent]: [...new Set([...(d.intent_keywords[intent] || []), kw])],
      }
    }))
    setNewKw('')
  }
  const removeKeyword = (intent, kw) => {
    setDraft(d => ({
      ...d,
      intent_keywords: { ...d.intent_keywords, [intent]: (d.intent_keywords[intent] || []).filter(k => k !== kw) }
    }))
  }

  const intentList = Object.keys(INTENT_COLORS).filter(k => k !== 'unknown')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Greeting + idioma + silencio */}
      <div>
        <div style={fieldLabel}>{t('sd.voice.greeting', 'Saludo (greeting)')}</div>
        <textarea
          rows={2}
          value={draft.greeting}
          onChange={e => setField('greeting', e.target.value)}
          style={{ ...inputBase, resize: 'vertical' }}
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <div style={fieldLabel}>Idioma (BCP-47)</div>
          <select value={draft.language} onChange={e => setField('language', e.target.value)} style={inputBase}>
            <option value="es-ES">Español (es-ES)</option>
            <option value="en-US">English (en-US)</option>
            <option value="ca-ES">Català (ca-ES)</option>
            <option value="fr-FR">Français (fr-FR)</option>
            <option value="pt-PT">Português (pt-PT)</option>
          </select>
        </div>
        <div>
          <div style={fieldLabel}>Silencio máximo (segundos)</div>
          <input
            type="number" min={1} max={120}
            value={draft.max_silence_seconds}
            onChange={e => setField('max_silence_seconds', Number(e.target.value))}
            style={inputBase}
          />
        </div>
      </div>

      {/* Menú DTMF */}
      <div>
        <div style={fieldLabel}>{t('sd.voice.dtmf_menu', 'Menú DTMF (tonos del teclado)')}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 8 }}>
          {Object.entries(draft.dtmf_menu).length === 0 && (
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Sin opciones DTMF configuradas</div>
          )}
          {Object.entries(draft.dtmf_menu).map(([key, val]) => (
            <div key={key} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 12px',
              background: 'var(--surface-3)',
              border: '1px solid var(--surface-4)',
              borderRadius: 8, fontSize: 'var(--text-sm)',
            }}>
              <span style={{
                fontFamily: 'var(--font-mono)', fontWeight: 700,
                color: 'var(--accent)',
                background: 'var(--accent-muted)',
                borderRadius: 6, padding: '1px 7px',
                minWidth: 28, textAlign: 'center',
              }}>{key}</span>
              <input
                type="text"
                value={val.label}
                onChange={e => setDraft(d => ({ ...d, dtmf_menu: { ...d.dtmf_menu, [key]: { ...val, label: e.target.value } } }))}
                style={{ ...inputBase, flex: 1 }}
              />
              <select
                value={val.intent}
                onChange={e => setDraft(d => ({ ...d, dtmf_menu: { ...d.dtmf_menu, [key]: { ...val, intent: e.target.value } } }))}
                style={{ ...inputBase, width: 130 }}
              >
                {intentList.map(i => <option key={i} value={i}>{i}</option>)}
              </select>
              <button
                type="button"
                onClick={() => removeDtmf(key)}
                title="Eliminar"
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-3)', padding: 4 }}
                onMouseEnter={e => { e.currentTarget.style.color = 'var(--danger)' }}
                onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-3)' }}
              ><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
        <div style={{
          background: 'var(--surface-1)',
          border: '1px dashed var(--surface-4)',
          borderRadius: 8, padding: '10px 12px',
          display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap',
        }}>
          <input
            type="text" placeholder="Tecla (ej. 4)" value={newKey}
            onChange={e => setNewKey(e.target.value)}
            maxLength={2}
            style={{ ...inputBase, width: 80 }}
          />
          <input
            type="text" placeholder="Etiqueta visible" value={newLabel}
            onChange={e => setNewLabel(e.target.value)}
            style={{ ...inputBase, flex: '1 1 200px' }}
          />
          <select value={newIntent} onChange={e => setNewIntent(e.target.value)} style={{ ...inputBase, width: 130 }}>
            {intentList.map(i => <option key={i} value={i}>{i}</option>)}
          </select>
          <Button size="sm" variant="secondary" icon={<Plus size={13} />}
            onClick={addDtmf}
            disabled={!newKey.trim() || !newLabel.trim()}
          >Añadir tecla</Button>
        </div>
      </div>

      {/* Keywords por intent */}
      <div>
        <div style={fieldLabel}>Keywords por intent</div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 8 }}>
          Si la transcripción del usuario contiene alguna de estas palabras, se asigna ese intent automáticamente.
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {intentList.map(intent => {
            const kws = draft.intent_keywords[intent] || []
            const isEditing = editingIntent === intent
            const color = INTENT_COLORS[intent]
            return (
              <div key={intent} style={{
                background: 'var(--surface-3)',
                border: '1px solid var(--surface-4)',
                borderRadius: 8, padding: '10px 12px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                  <span style={chip(color)}>{intent}</span>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{kws.length} palabras</span>
                  <button
                    type="button"
                    onClick={() => { setEditingIntent(isEditing ? null : intent); setNewKw('') }}
                    style={{
                      marginLeft: 'auto',
                      background: 'transparent', border: 'none', cursor: 'pointer',
                      color: isEditing ? 'var(--accent)' : 'var(--text-3)',
                      padding: 4, display: 'inline-flex', gap: 4, alignItems: 'center',
                      fontFamily: 'inherit', fontSize: 'var(--text-xs)',
                    }}
                  ><Edit2 size={12} /> {isEditing ? 'Cerrar' : 'Editar'}</button>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {kws.map(kw => (
                    <span key={kw} style={{
                      fontSize: 'var(--text-xs)',
                      background: 'var(--surface-4)', color: 'var(--text-2)',
                      padding: '2px 8px', borderRadius: 999,
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                    }}>
                      {kw}
                      {isEditing && (
                        <button type="button" onClick={() => removeKeyword(intent, kw)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', padding: 0, lineHeight: 1, fontFamily: 'inherit' }}
                        >×</button>
                      )}
                    </span>
                  ))}
                </div>
                {isEditing && (
                  <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                    <input
                      type="text" placeholder="Nueva keyword" value={newKw}
                      onChange={e => setNewKw(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && addKeyword(intent)}
                      style={{ ...inputBase, flex: 1 }}
                    />
                    <Button size="sm" variant="secondary" onClick={() => addKeyword(intent)} disabled={!newKw.trim()}>Añadir</Button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Button variant="secondary" onClick={() => setDraft(null)}>Descartar cambios</Button>
        <Button onClick={() => onSave(draft)} loading={saving}>Guardar configuración</Button>
      </div>
    </div>
  )
}

// ── Modal de detalle de sesión cerrada ────────────────────────────────────────

function SessionDetailModal({ session, onClose, openTicket }: { session: VoiceSession | null; onClose: () => void; openTicket: (id: string | number) => void }) {
  if (!session) return null
  const transcript = session.transcript || []
  const entities = session.entities || {}
  return (
    <Modal open title={`Sesión ${session.caller_id}`} onClose={onClose} width={620}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          <span style={chip(STATUS_COLOR[session.status] || 'var(--text-3)')}>{session.status}</span>
          {session.intent && <span style={chip(INTENT_COLORS[session.intent] || INTENT_COLORS.unknown)}>{session.intent}</span>}
          {session.resolution && (
            <span style={chip(RESOLUTION_COLOR[session.resolution] || 'var(--text-3)')}>
              {RESOLUTION_LABEL[session.resolution] || session.resolution}
            </span>
          )}
          {session.channel && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>· {session.channel}</span>}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
          {session.created_at && <span><span style={{ color: 'var(--text-3)' }}>Inicio:</span> {new Date(session.created_at).toLocaleString()}</span>}
          {session.closed_at && <span><span style={{ color: 'var(--text-3)' }}>Cierre:</span> {new Date(session.closed_at).toLocaleString()}</span>}
          {session.ticket_id && (
            <button
              type="button"
              onClick={() => openTicket(session.ticket_id)}
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--accent)', padding: 0, fontFamily: 'inherit', textDecoration: 'underline', fontSize: 'var(--text-xs)' }}
            >Ver ticket vinculado ↗</button>
          )}
        </div>

        {(entities.email || entities.ticket_ref || entities.urgency_words?.length) && (
          <div>
            <div style={fieldLabel}>Entidades extraídas</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {entities.email && <span style={chip('var(--accent)')}>✉ {entities.email}</span>}
              {entities.ticket_ref && <span style={chip('var(--purple)')}>🔗 {entities.ticket_ref}</span>}
              {(entities.urgency_words || []).map((w, i) => <span key={i} style={chip('var(--orange)')}>{w}</span>)}
            </div>
          </div>
        )}

        <div>
          <div style={fieldLabel}>Transcripción ({transcript.length} turnos)</div>
          <div style={{
            maxHeight: 320, overflowY: 'auto',
            background: 'var(--surface-1)',
            border: '1px solid var(--surface-4)',
            borderRadius: 8, padding: 10,
            display: 'flex', flexDirection: 'column', gap: 6,
          }}>
            {transcript.length === 0 ? (
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textAlign: 'center', padding: 16 }}>
                Sin turnos registrados.
              </div>
            ) : transcript.map((turn, i) => {
              const isUser = turn.speaker === 'user'
              return (
                <div key={i} style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
                  <div style={{ maxWidth: '78%' }}>
                    <div style={{
                      fontSize: 'var(--text-2xs)', color: 'var(--text-3)',
                      textAlign: isUser ? 'right' : 'left', marginBottom: 2,
                      textTransform: 'uppercase', letterSpacing: '0.05em',
                    }}>
                      {turn.speaker} {turn.ts && `· ${new Date(turn.ts).toLocaleTimeString()}`}
                    </div>
                    <span style={{
                      display: 'inline-block', fontSize: 'var(--text-xs)',
                      padding: '5px 10px', borderRadius: 8,
                      background: isUser ? 'var(--accent-muted)' : 'var(--surface-3)',
                      color: isUser ? 'var(--accent)' : 'var(--text-2)',
                      border: `1px solid ${isUser ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'}`,
                    }}>{turn.text}</span>
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
    refetchInterval: 15_000,
  })

  const { data: config } = useQuery({
    queryKey: ['voice-config'],
    queryFn: () => voiceAgentApi.getConfig().then(r => r.data),
    enabled: tab === 'config',
  })

  const sessions = sessionsData?.sessions ?? []
  const activeSession = useMemo(
    () => sessions.find(s => s.id === activeSessionId),
    [sessions, activeSessionId],
  )

  const createSessionMutation = useMutation({
    mutationFn: (payload) => voiceAgentApi.createSession(payload).then(r => r.data),
    onSuccess: (data) => {
      setActiveSessionId(data.session?.id)
      toast.success(`Sesión iniciada · greeting: "${(data.greeting || '').slice(0, 60)}..."`)
      qc.invalidateQueries({ queryKey: ['voice-sessions'] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al iniciar sesión'),
  })

  const addTurnMutation = useMutation({
    mutationFn: ({ id, text }) => voiceAgentApi.addTurn(id, { speaker: 'user', text }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['voice-sessions'] }),
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al añadir turno'),
  })

  const closeMutation = useMutation({
    mutationFn: ({ id, resolution }) => voiceAgentApi.closeSession(id, { resolution }).then(r => r.data),
    onSuccess: (data) => {
      const r = data?.resolution
      toast.success(`Sesión cerrada · ${RESOLUTION_LABEL[r] || r}`)
      setActiveSessionId(null)
      qc.invalidateQueries({ queryKey: ['voice-sessions'] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al cerrar sesión'),
  })

  const createTicketMutation = useMutation({
    mutationFn: (id) => voiceAgentApi.createTicket(id).then(r => r.data),
    onSuccess: (data) => {
      toast.success(`Ticket ${data.number} creado desde la sesión`)
      qc.invalidateQueries({ queryKey: ['voice-sessions'] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al crear ticket'),
  })

  const saveConfigMutation = useMutation({
    mutationFn: (cfg) => voiceAgentApi.updateConfig(cfg).then(r => r.data),
    onSuccess: () => {
      toast.success('Configuración guardada')
      qc.invalidateQueries({ queryKey: ['voice-config'] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al guardar configuración'),
  })

  const openTicket = (ticketId) => navigate(`/service-desk?ticket=${ticketId}`)

  return (
    <Card style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Phone size={18} style={{ color: 'var(--success)' }} />
          <h2 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', margin: 0 }}>
            {t('sd.voice.title', 'Agente de voz / IVR')}
          </h2>
        </div>
        <div style={{ display: 'flex', gap: 6, fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
          <span style={chip('var(--accent)')}>{sessions.filter(s => s.status === 'active').length} activas</span>
          <span style={chip('var(--text-3)')}>{sessions.filter(s => s.status === 'closed').length} cerradas</span>
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
          <div style={{ marginBottom: 16 }}>
            <div style={fieldLabel}>{t('sd.voice.new_session', 'Iniciar sesión manual')}</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input
                type="text"
                placeholder="+34600000000"
                value={callerInput}
                onChange={e => setCallerInput(e.target.value)}
                style={{ ...inputBase, flex: '1 1 220px' }}
              />
              <select value={channel} onChange={e => setChannel(e.target.value)} style={{ ...inputBase, width: 130 }}>
                <option value="phone">phone</option>
                <option value="sip">sip</option>
                <option value="web">web</option>
              </select>
              <Button
                onClick={() => createSessionMutation.mutate({ caller_id: callerInput, channel })}
                disabled={createSessionMutation.isPending || !callerInput.trim()}
                loading={createSessionMutation.isPending}
                icon={<Plus size={14} />}
              >Iniciar</Button>
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 6 }}>
              Para llamadas reales: configura el webhook de Twilio en <span style={{ fontFamily: 'var(--font-mono)' }}>POST /sd/voice/webhook/twilio</span> con tu phone number.
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
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, gap: 10, flexWrap: 'wrap' }}>
            <div style={fieldLabel}>Sesiones recientes</div>
            <div style={{ display: 'flex', gap: 4 }}>
              {[['', 'Todas'], ['active', 'Activas'], ['closed', 'Cerradas']].map(([id, label]) => (
                <button
                  key={id || 'all'}
                  type="button"
                  onClick={() => setHistoryFilter(id)}
                  style={{
                    padding: '4px 10px',
                    fontSize: 'var(--text-xs)',
                    border: '1px solid',
                    borderColor: historyFilter === id ? 'var(--accent)' : 'var(--surface-4)',
                    background: historyFilter === id ? 'var(--accent-muted)' : 'transparent',
                    color: historyFilter === id ? 'var(--accent)' : 'var(--text-2)',
                    borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit',
                  }}
                >{label}</button>
              ))}
            </div>
          </div>

          {isLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
          ) : sessions.length === 0 ? (
            <EmptyState icon="📞" title={t('sd.voice.no_sessions', 'Sin sesiones')} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {sessions.filter(s => s.id !== activeSessionId).slice(0, 30).map(s => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => {
                    if (s.status === 'active') setActiveSessionId(s.id)
                    else setDetailSession(s)
                  }}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    width: '100%',
                    padding: '10px 14px',
                    background: 'var(--surface-3)',
                    border: '1px solid var(--surface-4)',
                    borderRadius: 8,
                    color: 'var(--text-1)',
                    fontFamily: 'inherit',
                    fontSize: 'var(--text-sm)',
                    textAlign: 'left',
                    cursor: 'pointer',
                    transition: 'border-color .15s, background .15s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-1)' }}>{s.caller_id}</span>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>· {s.channel}</span>
                    {s.created_at && (
                      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                        · {new Date(s.created_at).toLocaleString()}
                      </span>
                    )}
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                      · {(s.transcript || []).length} turnos
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                    {s.intent && (
                      <span style={chip(INTENT_COLORS[s.intent] || INTENT_COLORS.unknown)}>{s.intent}</span>
                    )}
                    {s.resolution && (
                      <span style={chip(RESOLUTION_COLOR[s.resolution] || 'var(--text-3)')}>
                        {RESOLUTION_LABEL[s.resolution] || s.resolution}
                      </span>
                    )}
                    <span style={chip(STATUS_COLOR[s.status] || 'var(--text-3)')}>{s.status}</span>
                    {s.ticket_id && <span style={chip('var(--accent)')}>ticket ✓</span>}
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
          onSave={(draft) => saveConfigMutation.mutate(draft)}
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
