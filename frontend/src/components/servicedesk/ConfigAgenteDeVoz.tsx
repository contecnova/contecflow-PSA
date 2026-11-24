/**
 * Sección «Agente de voz» de Configuración (`/settings/sd-voz`, 19-11-2026).
 *
 * Antes era la pestaña «Configuración» de Service desk → Herramientas → Voz
 * (VoiceAgentPanel). Saludo, idioma, silencio máximo, menú de teclas (DTMF)
 * y palabras clave por motivo. Las sesiones de llamada siguen en el módulo.
 *
 * Escritura: PUT /sd/voice/config, `require_admin`; la sección pide
 * `sd.administrar`. Auditado desde el 19-11-2026 (`sd_voice_config`, antes y
 * después; antes no quedaba rastro).
 */
import { useState, useEffect, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { voiceAgentApi } from '../../services/api'
import type { ConfigDelAgenteDeVoz } from '../../services/api/tipos-analitica'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { Pencil, Plus, Trash2, X } from 'lucide-react'
import { Button, IconButton, Select, Spinner, Textarea, Input } from '../ui'
import StatusBadge from '../ui/StatusBadge'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { useOrgSettings } from '../../hooks/useOrgSettings'
import './VoiceAgentPanel.css'

/** Borrador del editor: lo que el usuario va cambiando antes de guardar. */
type VoiceAgentConfig = Partial<ConfigDelAgenteDeVoz>

const INTENT_KIND: Record<string, StatusBadgeKind> = {
  incident: 'danger', query: 'accent', urgent: 'orange', agent: 'purple', unknown: 'neutral',
}
const INTENTS = ['incident', 'query', 'urgent', 'agent']

export default function ConfigAgenteDeVoz() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: config } = useQuery({
    queryKey: ['voice-config'],
    queryFn: () => voiceAgentApi.getConfig().then(r => r.data),
  })
  const guardar = useMutation({
    mutationFn: (cfg: VoiceAgentConfig) => voiceAgentApi.updateConfig(cfg).then(r => r.data),
    onSuccess: () => {
      toast.success(t('etl.guardado'))
      qc.invalidateQueries({ queryKey: ['voice-config'] })
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('voiceagent.error_guardar'))),
  })
  return <ConfigEditor config={config} onSave={draft => guardar.mutate(draft)} saving={guardar.isPending} />
}

// ── Configuración (saludo, idioma, menú de teclas, palabras clave) ─────────────

/** Idiomas (BCP-47) que ofrece el selector del agente de voz, con su nombre en su idioma. */
const VOICE_LANGUAGES: Array<[string, string]> = [
  ['es-ES', 'Español (es-ES)'], ['en-US', 'English (en-US)'], ['ca-ES', 'Català (ca-ES)'], ['fr-FR', 'Français (fr-FR)'], ['pt-PT', 'Português (pt-PT)'],
]

function ConfigEditor({ config, onSave, saving }: { config: VoiceAgentConfig | undefined | null; onSave: (draft: VoiceAgentConfig) => void; saving: boolean }) {
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

  // Borrador a partir de lo guardado. 19-11-2026: «Descartar cambios» vuelve a
  // lo guardado (antes dejaba el borrador vacío y la pantalla en «cargando»).
  const desdeGuardado = (c: VoiceAgentConfig): VoiceAgentConfig => ({
    greeting: c.greeting || '',
    language: c.language || idiomaPorDefecto,
    max_silence_seconds: c.max_silence_seconds ?? 10,
    dtmf_menu: { ...(c.dtmf_menu || {}) },
    intent_keywords: Object.fromEntries(
      Object.entries(c.intent_keywords || {}).map(([k, v]) => [k, [...(v || [])]])
    ),
  })
  useEffect(() => {
    if (config && !draft) setDraft(desdeGuardado(config))
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
        <Textarea id={`${id}-saludo`} rows={2} value={draft.greeting} onChange={e => setField('greeting', e.target.value)} inputClassName="campo-form vap-textarea" />
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
          <Input id={`${id}-silencio`} type="number" min={1} max={120} value={draft.max_silence_seconds} onChange={e => setField('max_silence_seconds', Number(e.target.value))} inputClassName="campo-form" />
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
            <Input aria-label={t('voiceagent.etiqueta_de_tecla', { n: key })} type="text" value={val.label} onChange={e => setDraft(d => ({ ...(d as VoiceAgentConfig), dtmf_menu: { ...(d as VoiceAgentConfig).dtmf_menu, [key]: { ...val, label: e.target.value } } }))} className="vap-fila__campo" />
            <Select suelto placeholder={false} aria-label={t('voiceagent.motivo_de_tecla', { n: key })} value={val.intent}
              onChange={e => setDraft(d => ({ ...(d as VoiceAgentConfig), dtmf_menu: { ...(d as VoiceAgentConfig).dtmf_menu, [key]: { ...val, intent: e.target.value } } }))}
              className="vap-select">
              {opcionesIntent}
            </Select>
            <IconButton variante="caja" tono="peligro" ariaLabel={t('common.delete')} title={t('common.delete')} onClick={() => removeDtmf(key)}>
              <Trash2 size={14} aria-hidden="true" />
            </IconButton>
          </div>
        ))}
        <div className="vap-fila">
          <Input aria-label={t('voiceagent.tecla_ej_4')} type="text" placeholder={t('voiceagent.tecla_ej_4')} value={newKey} onChange={e => setNewKey(e.target.value)} maxLength={2} className="vap-tecla__nueva" />
          <Input aria-label={t('voiceagent.etiqueta_visible')} type="text" placeholder={t('voiceagent.etiqueta_visible')} value={newLabel} onChange={e => setNewLabel(e.target.value)} className="vap-fila__campo" />
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
                  <Input aria-label={t('voiceagent.nueva_keyword')} type="text" placeholder={t('voiceagent.nueva_keyword')} value={newKw} onChange={e => setNewKw(e.target.value)} onKeyDown={e => e.key === 'Enter' && addKeyword(intent)} className="vap-fila__campo" />
                  <Button size="sm" variant="secondary" icon={<Plus size={13} />} onClick={() => addKeyword(intent)} disabled={!newKw.trim()}>{t('voiceagent.anadir')}</Button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="u-actions-8">
        <Button variant="secondary" onClick={() => config && setDraft(desdeGuardado(config))}>{t('voiceagent.descartar_cambios')}</Button>
        <Button onClick={() => onSave(draft)} loading={saving}>{t('voiceagent.guardar_configuracion')}</Button>
      </div>
    </div>
  )
}
