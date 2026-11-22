/**
 * Configuración → IA e idiomas → Asistente de reuniones (`/settings/reuniones`,
 * 19-11-2026). Capacidad `reuniones.config` (admin).
 *
 * Bloques: consentimiento, retención, traducción y vinculación, transcripción
 * (STT externo con contrato), Microsoft Teams, Zoom, Google Meet, bot invitado
 * y RGPD por persona. Patrón de ConfigBiO365: borrador local y un botón
 * Guardar. Los secretos nunca llegan del servidor (solo `*_set`); se escriben
 * en claro y vacío = no cambia. Cada conector nace apagado. El bot no se
 * puede activar sin la referencia del contrato de encargo de tratamiento
 * (art. 28 RGPD); el servidor también lo exige (`reuniones_proveedor_sin_contrato`).
 * Guardar queda auditado en el servidor (antes/después, sin secretos).
 */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Copy, Download, FileLock2, Languages, PlugZap, ShieldCheck, Timer, Trash2, Video } from 'lucide-react'
import {
  Button, Confirm, FormField, Input, Section, Segmentado, Select, Spinner, StatusBadge, Switch, UserSelect, Textarea,
} from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { downloadBlob, extractErr, fmtDateTime } from '../../utils/helpers'
import { reunionesApi } from '../../services/api/reuniones'
import type { ConectorReuniones, ConfigReuniones as Config, ConfigReunionesIn } from '../../services/api/reuniones'
import { CLAVES } from './comun'
import './Reuniones.css'

/** Secretos que se escriben (nunca se leen). */
interface Secretos {
  teams_client_secret: string
  teams_client_state: string
  zoom_client_secret: string
  zoom_webhook_secret: string
  meet_service_account_key: string
  bots_api_key: string
  bots_webhook_secret: string
}
const SIN_SECRETOS: Secretos = {
  teams_client_secret: '', teams_client_state: '', zoom_client_secret: '', zoom_webhook_secret: '',
  meet_service_account_key: '', bots_api_key: '', bots_webhook_secret: '',
}

/** Solo los secretos escritos (vacío = no cambia). */
const si = (v: string) => (v.trim() ? v : undefined)

function cuerpoDeGuardado(b: Config, s: Secretos): ConfigReunionesIn {
  return {
    consent: { ...b.consent },
    retention: { ...b.retention },
    translation: { ...b.translation },
    linking: { ...b.linking },
    transcription: { allow_external_stt: b.transcription.allow_external_stt, external_stt_contract: b.transcription.external_stt_contract },
    teams: {
      enabled: b.teams.enabled, tenant_id: b.teams.tenant_id, client_id: b.teams.client_id, mode: b.teams.mode,
      client_secret: si(s.teams_client_secret), client_state: si(s.teams_client_state),
    },
    zoom: {
      enabled: b.zoom.enabled, account_id: b.zoom.account_id, client_id: b.zoom.client_id,
      client_secret: si(s.zoom_client_secret), webhook_secret: si(s.zoom_webhook_secret),
    },
    meet: { enabled: b.meet.enabled, service_account_email: b.meet.service_account_email, service_account_key: si(s.meet_service_account_key) },
    bots: {
      enabled: b.bots.enabled, provider: b.bots.provider, region: b.bots.region, bot_name: b.bots.bot_name,
      contract_reference: b.bots.contract_reference, api_key: si(s.bots_api_key), webhook_secret: si(s.bots_webhook_secret),
    },
  }
}

function Bloque({ icono, titulo, descripcion, children, acciones }: { icono: ReactNode; titulo: string; descripcion?: string; children: ReactNode; acciones?: ReactNode }) {
  return (
    <div className="reu-config__bloque">
      <Section title={<span className="reu-seccion">{icono}{titulo}</span>} subtitle={descripcion} actions={acciones}>
        {children}
      </Section>
    </div>
  )
}

export default function ConfigReuniones() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: config, isLoading } = useQuery({ queryKey: CLAVES.config, queryFn: reunionesApi.config })
  const [b, setB] = useState<Config | null>(null)
  const [s, setS] = useState<Secretos>(SIN_SECRETOS)

  useEffect(() => { if (config && !b) setB(structuredClone(config)) }, [config, b])

  const guardar = useMutation({
    mutationFn: (c: ConfigReunionesIn) => reunionesApi.guardarConfig(c),
    onSuccess: nueva => {
      setS(SIN_SECRETOS)
      setB(structuredClone(nueva))
      qc.setQueryData(CLAVES.config, nueva)
      toast.success(t('reuniones.config.guardada'))
    },
    onError: e => toast.error(extractErr(e)),
  })
  const probar = useMutation({
    mutationFn: (c: ConectorReuniones) => reunionesApi.probar(c),
    onSuccess: r => (r.ok ? toast.success(r.detail || t('reuniones.config.prueba_ok')) : toast.error(r.detail || t('reuniones.config.prueba_mal'))),
    onError: e => toast.error(extractErr(e)),
  })
  const suscripcion = useMutation({
    mutationFn: () => reunionesApi.suscripcionTeams(),
    onSuccess: r => {
      toast.success(t('reuniones.config.teams_suscripcion_hecha', { fecha: fmtDateTime(r.expires_at) }))
      qc.invalidateQueries({ queryKey: CLAVES.config })
      setB(x => (x ? { ...x, teams: { ...x.teams, subscription_id: r.id, subscription_expires_at: r.expires_at } } : x))
    },
    onError: e => toast.error(extractErr(e)),
  })

  if (isLoading || !b) return <Spinner />

  /** Cambia un campo de un bloque del borrador. */
  const set = <K extends keyof Config>(bloque: K, cambios: Partial<Config[K]>) =>
    setB(x => (x ? { ...x, [bloque]: { ...x[bloque], ...cambios } } : x))
  const setSecreto = (k: keyof Secretos, v: string) => setS(x => ({ ...x, [k]: v }))
  const copiar = async (texto: string) => {
    try { await navigator.clipboard.writeText(texto); toast.success(t('reuniones.config.copiado')) } catch { toast.error(t('reuniones.config.no_copiado')) }
  }
  const puesto = (set_: boolean) => (set_ ? t('reuniones.config.secreto_puesto') : '')
  const sinContrato = !b.bots.contract_reference.trim()
  const sttSinContrato = b.transcription.allow_external_stt && !b.transcription.external_stt_contract.trim()

  const urlWebhook = (url: string) => (
    <div className="reu-config__copiar">
      <Input label={t('reuniones.config.webhook_url')} value={url} onChange={() => undefined} disabled />
      <Button variant="secondary" size="sm" icon={<Copy size={14} />} onClick={() => { void copiar(url) }} disabled={!url}>{t('reuniones.config.copiar')}</Button>
    </div>
  )
  const botonProbar = (c: ConectorReuniones, activo: boolean) => (
    <Button size="sm" variant="secondary" icon={<PlugZap size={14} />} disabled={!activo}
      loading={probar.isPending && probar.variables === c} onClick={() => probar.mutate(c)}>
      {t('reuniones.config.probar')}
    </Button>
  )

  return (
    <div className="reu-config" data-testid="config-reuniones">
      <Bloque icono={<ShieldCheck size={16} aria-hidden />} titulo={t('reuniones.config.consentimiento')} descripcion={t('reuniones.config.consentimiento_d')}>
        <div className="reu-config__campos">
          <Switch checked={b.consent.notice_required} onChange={v => set('consent', { notice_required: v })}
            label={t('reuniones.config.aviso_obligatorio')} ayuda={t('reuniones.config.aviso_obligatorio_d')} />
          <Switch checked={b.consent.require_consent} onChange={v => set('consent', { require_consent: v })}
            label={t('reuniones.config.exigir_consentimiento')} ayuda={t('reuniones.config.exigir_consentimiento_d')} />
          <div className="u-col-full">
            <FormField label={t('reuniones.config.texto_aviso')} hint={t('reuniones.config.texto_aviso_d')}>
              <Textarea rows={3} value={b.consent.notice_text} onChange={e => set('consent', { notice_text: e.target.value })} inputClassName="reu-textarea" />
            </FormField>
          </div>
          <div className="u-col-full">
            <FormField label={t('reuniones.config.mensaje_bot')} hint={t('reuniones.config.mensaje_bot_d')}>
              <Textarea rows={3} value={b.consent.bot_message} onChange={e => set('consent', { bot_message: e.target.value })} inputClassName="reu-textarea" />
            </FormField>
          </div>
        </div>
      </Bloque>

      <Bloque icono={<Timer size={16} aria-hidden />} titulo={t('reuniones.config.retencion')} descripcion={t('reuniones.config.retencion_d')}>
        <div className="reu-config__campos">
          <Input type="number" min={1} label={t('reuniones.config.dias_audio')} value={b.retention.audio_days}
            onChange={e => set('retention', { audio_days: Number(e.target.value) || 1 })} hint={t('reuniones.config.dias_audio_d')} />
          <Input type="number" min={1} label={t('reuniones.config.dias_transcripcion')} value={b.retention.transcript_days}
            onChange={e => set('retention', { transcript_days: Number(e.target.value) || 1 })} hint={t('reuniones.config.dias_transcripcion_d')} />
        </div>
      </Bloque>

      <Bloque icono={<Languages size={16} aria-hidden />} titulo={t('reuniones.config.traduccion')} descripcion={t('reuniones.config.traduccion_d')}>
        <div className="reu-config__campos">
          <Switch checked={b.translation.per_person} onChange={v => set('translation', { per_person: v })}
            label={t('reuniones.config.traduccion_por_persona')} ayuda={t('reuniones.config.traduccion_por_persona_d')} />
          <Switch checked={b.linking.auto} onChange={v => set('linking', { auto: v })}
            label={t('reuniones.config.vinculacion_auto')} ayuda={t('reuniones.config.vinculacion_auto_d')} />
        </div>
      </Bloque>

      <Bloque icono={<FileLock2 size={16} aria-hidden />} titulo={t('reuniones.config.transcripcion')} descripcion={t('reuniones.config.transcripcion_d')}>
        <div className="reu-config__campos">
          <Switch checked={b.transcription.allow_external_stt} onChange={v => set('transcription', { allow_external_stt: v })}
            label={t('reuniones.config.stt_externo')} ayuda={t('reuniones.config.stt_externo_d')} />
          <Input label={t('reuniones.config.stt_contrato')} value={b.transcription.external_stt_contract}
            onChange={e => set('transcription', { external_stt_contract: e.target.value })}
            error={sttSinContrato ? t('reuniones.config.stt_contrato_falta') : undefined} />
          <div className="u-col-full u-text3-xs">
            {t('reuniones.config.stt_proveedores', { lista: b.transcription.stt_providers.join(', ') || '—' })}
            {' · '}
            {t('reuniones.config.stt_efectivo', { proveedor: b.transcription.stt_effective ?? t('reuniones.config.stt_ninguno') })}
          </div>
        </div>
      </Bloque>

      <Bloque icono={<Video size={16} aria-hidden />} titulo={t('reuniones.plataforma.teams')} descripcion={t('reuniones.config.teams_d')}
        acciones={botonProbar('teams', b.teams.enabled)}>
        <div className="reu-config__campos">
          <Switch checked={b.teams.enabled} onChange={v => set('teams', { enabled: v })} label={t('reuniones.config.activo')} />
          <Input label={t('reuniones.config.tenant_id')} value={b.teams.tenant_id} onChange={e => set('teams', { tenant_id: e.target.value })} />
          <Input label={t('reuniones.config.client_id')} value={b.teams.client_id} onChange={e => set('teams', { client_id: e.target.value })} />
          <Input type="password" label={t('reuniones.config.client_secret')} value={s.teams_client_secret}
            onChange={e => setSecreto('teams_client_secret', e.target.value)} placeholder={puesto(b.teams.secret_set)} hint={t('reuniones.config.secreto_ayuda')} />
          <div className="u-col-full reu-campo">
            <span className="reu-campo__etiqueta">{t('reuniones.config.teams_modo')}</span>
            <Segmentado aria-label={t('reuniones.config.teams_modo')} valor={b.teams.mode} onChange={v => set('teams', { mode: v as Config['teams']['mode'] })}
              opciones={[
                { valor: 'polling', etiqueta: t('reuniones.config.teams_sondeo') },
                { valor: 'subscription', etiqueta: t('reuniones.config.teams_suscripcion') },
              ]} />
            <span className="u-text3-xs">{b.teams.mode === 'polling' ? t('reuniones.config.teams_sondeo_d') : t('reuniones.config.teams_suscripcion_d')}</span>
          </div>
          {b.teams.mode === 'subscription' && (
            <>
              <Input type="password" label={t('reuniones.config.client_state')} value={s.teams_client_state}
                onChange={e => setSecreto('teams_client_state', e.target.value)} placeholder={puesto(b.teams.client_state_set)} hint={t('reuniones.config.secreto_ayuda')} />
              <div className="u-col-full">{urlWebhook(b.teams.webhook_url)}</div>
              <div className="u-col-full reu-botonera">
                <span className="u-text3-xs">
                  {b.teams.subscription_id
                    ? t('reuniones.config.teams_suscripcion_vence', { fecha: fmtDateTime(b.teams.subscription_expires_at) })
                    : t('reuniones.config.teams_sin_suscripcion')}
                </span>
                <Button size="sm" variant="secondary" loading={suscripcion.isPending} disabled={!b.teams.enabled} onClick={() => suscripcion.mutate()}>
                  {t('reuniones.config.teams_crear_suscripcion')}
                </Button>
              </div>
            </>
          )}
        </div>
      </Bloque>

      <Bloque icono={<Video size={16} aria-hidden />} titulo={t('reuniones.plataforma.zoom')} descripcion={t('reuniones.config.zoom_d')}
        acciones={botonProbar('zoom', b.zoom.enabled)}>
        <div className="reu-config__campos">
          <Switch checked={b.zoom.enabled} onChange={v => set('zoom', { enabled: v })} label={t('reuniones.config.activo')} />
          <Input label={t('reuniones.config.account_id')} value={b.zoom.account_id} onChange={e => set('zoom', { account_id: e.target.value })} />
          <Input label={t('reuniones.config.client_id')} value={b.zoom.client_id} onChange={e => set('zoom', { client_id: e.target.value })} />
          <Input type="password" label={t('reuniones.config.client_secret')} value={s.zoom_client_secret}
            onChange={e => setSecreto('zoom_client_secret', e.target.value)} placeholder={puesto(b.zoom.secret_set)} hint={t('reuniones.config.secreto_ayuda')} />
          <Input type="password" label={t('reuniones.config.webhook_secret')} value={s.zoom_webhook_secret}
            onChange={e => setSecreto('zoom_webhook_secret', e.target.value)} placeholder={puesto(b.zoom.webhook_secret_set)} hint={t('reuniones.config.secreto_ayuda')} />
          <div className="u-col-full">{urlWebhook(b.zoom.webhook_url)}</div>
        </div>
      </Bloque>

      <Bloque icono={<Video size={16} aria-hidden />} titulo={t('reuniones.plataforma.meet')} descripcion={t('reuniones.config.meet_d')}
        acciones={botonProbar('meet', b.meet.enabled)}>
        <div className="reu-config__campos">
          <Switch checked={b.meet.enabled} onChange={v => set('meet', { enabled: v })} label={t('reuniones.config.activo')} />
          <Input type="email" label={t('reuniones.config.cuenta_servicio')} value={b.meet.service_account_email}
            onChange={e => set('meet', { service_account_email: e.target.value })} />
          <div className="u-col-full">
            <FormField label={t('reuniones.config.clave_json')} hint={b.meet.key_set ? t('reuniones.config.secreto_puesto') : t('reuniones.config.clave_json_d')}>
              <Textarea rows={4} autoComplete="off" spellCheck={false} value={s.meet_service_account_key} onChange={e => setSecreto('meet_service_account_key', e.target.value)} inputClassName="reu-textarea reu-secreto" />
            </FormField>
          </div>
        </div>
      </Bloque>

      <Bloque icono={<Bot size={16} aria-hidden />} titulo={t('reuniones.config.bot')} descripcion={t('reuniones.config.bot_d')}
        acciones={botonProbar('bots', b.bots.enabled)}>
        <div className="reu-config__campos">
          <Input className="u-col-full" label={t('reuniones.config.contrato')} value={b.bots.contract_reference}
            onChange={e => set('bots', { contract_reference: e.target.value, ...(e.target.value.trim() ? {} : { enabled: false }) })}
            hint={t('reuniones.config.contrato_d')} />
          {b.bots.contract_accepted_at && (
            <div className="u-col-full u-text3-xs">
              {t('reuniones.config.contrato_aceptado', { quien: b.bots.contract_accepted_by ?? '—', fecha: fmtDateTime(b.bots.contract_accepted_at) })}
            </div>
          )}
          <Switch checked={b.bots.enabled} disabled={sinContrato} onChange={v => set('bots', { enabled: v })}
            label={t('reuniones.config.activo')} ayuda={sinContrato ? t('reuniones.config.bot_sin_contrato') : undefined} />
          <Select label={t('reuniones.config.proveedor')} value={b.bots.provider} placeholder={false}
            onChange={e => set('bots', { provider: e.target.value })}
            options={(b.bots.providers.length ? b.bots.providers : [b.bots.provider]).filter(Boolean).map(p => ({ value: p, label: p }))} />
          <Input label={t('reuniones.config.region')} value={b.bots.region} onChange={e => set('bots', { region: e.target.value })} />
          <Input label={t('reuniones.config.nombre_bot')} value={b.bots.bot_name} onChange={e => set('bots', { bot_name: e.target.value })} />
          <Input type="password" label={t('reuniones.config.api_key')} value={s.bots_api_key}
            onChange={e => setSecreto('bots_api_key', e.target.value)} placeholder={puesto(b.bots.api_key_set)} hint={t('reuniones.config.secreto_ayuda')} />
          <Input type="password" label={t('reuniones.config.webhook_secret')} value={s.bots_webhook_secret}
            onChange={e => setSecreto('bots_webhook_secret', e.target.value)} placeholder={puesto(b.bots.webhook_secret_set)} hint={t('reuniones.config.secreto_ayuda')} />
          <div className="u-col-full">{urlWebhook(b.bots.webhook_url)}</div>
        </div>
      </Bloque>

      <div className="reu-config__pie">
        <Button variant="secondary" onClick={() => { setB(config ? structuredClone(config) : null); setS(SIN_SECRETOS) }}>{t('reuniones.config.descartar')}</Button>
        <Button loading={guardar.isPending} disabled={sttSinContrato} onClick={() => guardar.mutate(cuerpoDeGuardado(b, s))}>{t('common.save')}</Button>
      </div>

      <RgpdPorPersona />
    </div>
  )
}

/** Copia (acceso/portabilidad) y supresión de lo que una persona dijo y consintió en reuniones. */
function RgpdPorPersona() {
  const t = useAppT()
  const toast = useToast()
  const [por, setPor] = useState<'email' | 'user'>('email')
  const [correo, setCorreo] = useState('')
  const [usuario, setUsuario] = useState('')
  const [confirmar, setConfirmar] = useState(false)
  const [informe, setInforme] = useState<unknown>(null)
  const quien = por === 'email' ? { email: correo.trim() } : { user_id: usuario }
  const hayQuien = por === 'email' ? !!correo.trim() : !!usuario

  const copia = useMutation({
    mutationFn: () => reunionesApi.copiaRgpd(quien),
    onSuccess: datos => {
      const nombre = (por === 'email' ? correo.trim() : usuario).replace(/[^\w.@-]+/g, '_')
      downloadBlob(new Blob([JSON.stringify(datos, null, 2)], { type: 'application/json' }), `rgpd-reuniones-${nombre}.json`)
    },
    onError: e => toast.error(extractErr(e)),
  })
  const suprimir = useMutation({
    mutationFn: () => reunionesApi.suprimirRgpd(quien),
    onSuccess: r => { setConfirmar(false); setInforme(r); toast.success(t('reuniones.rgpd.suprimido')) },
    onError: e => { setConfirmar(false); toast.error(extractErr(e)) },
  })

  return (
    <Bloque icono={<ShieldCheck size={16} aria-hidden />} titulo={t('reuniones.rgpd.titulo')} descripcion={t('reuniones.rgpd.descripcion')}>
      <div className="reu-config__campos">
        <div className="u-col-full">
          <Segmentado aria-label={t('reuniones.rgpd.buscar_por')} valor={por} onChange={v => setPor(v as 'email' | 'user')}
            opciones={[{ valor: 'email', etiqueta: t('reuniones.rgpd.por_correo') }, { valor: 'user', etiqueta: t('reuniones.rgpd.por_usuario') }]} />
        </div>
        {por === 'email'
          ? <Input type="email" label={t('reuniones.campo.correo')} value={correo} onChange={e => setCorreo(e.target.value)} />
          : <FormField label={t('reuniones.rgpd.persona')}><UserSelect value={usuario} onChange={id => setUsuario(id)} /></FormField>}
        <div className="u-col-full reu-botonera">
          <Button variant="secondary" icon={<Download size={14} />} disabled={!hayQuien} loading={copia.isPending} onClick={() => copia.mutate()}>
            {t('reuniones.rgpd.descargar_copia')}
          </Button>
          <Button variant="danger" icon={<Trash2 size={14} />} disabled={!hayQuien} onClick={() => setConfirmar(true)}>
            {t('reuniones.rgpd.suprimir')}
          </Button>
        </div>
        {informe != null && (
          <div className="u-col-full">
            <StatusBadge kind="success" caps={false}>{t('reuniones.rgpd.informe')}</StatusBadge>
            <pre className="reu-informe">{JSON.stringify(informe, null, 2)}</pre>
          </div>
        )}
      </div>
      <Confirm open={confirmar} title={t('reuniones.rgpd.suprimir_titulo')} description={t('reuniones.rgpd.suprimir_desc')}
        loading={suprimir.isPending} onCancel={() => setConfirmar(false)} onConfirm={() => suprimir.mutate()} />
    </Bloque>
  )
}
