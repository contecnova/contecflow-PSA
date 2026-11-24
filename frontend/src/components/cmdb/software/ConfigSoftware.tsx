/**
 * Configuración → Software y vulnerabilidades (`/settings/cmdb-software`,
 * 19-11-2026). Fuentes de avisos (OSV, NVD, GitHub, EPSS, KEV y
 * endoflife.date) con su dirección y credenciales, sincronización automática,
 * plazos de remediación por severidad, caducidad de las excepciones, aviso de
 * fin de vida, licencias permitidas y prohibidas, y ticket automático.
 *
 * Credenciales: la clave de NVD y el token de GitHub se guardan cifrados; el
 * campo vacío no las cambia y «Quitar» envía `'__borrar__'`. Sin ninguna
 * fuente activa el módulo funciona igual importando ficheros.
 *
 * Pide `software.config` (catalogoDeAjustes.tsx). Diseño:
 * docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Lock, PlugZap } from 'lucide-react'
import { useAppT } from '../../../i18n/AppLangContext'
import { useToast } from '../../../context/ToastContext'
import { fmtDateTime } from '../../../utils/helpers'
import { cmdbSoftwareApi } from '../../../services/api/cmdbSoftware'
import type { ConfigSoftware as Config, ConfigSoftwareIn, Severidad } from '../../../services/api/cmdbSoftware'
import { Button, Section, Select, Spinner, StatusBadge, Switch, Input } from '../../ui'
import { useErr, useEtiquetaSw } from './comun'
import { ConexionesDeEscaneo } from './Escaneos'
import ConfigRiesgo from './riesgo/ConfigRiesgo'
import '../../servicedesk/sdMercado.css'
import './software.css'

type Fuente = 'osv' | 'nvd' | 'ghsa' | 'epss' | 'kev' | 'eol'
const FUENTES: Fuente[] = ['osv', 'nvd', 'ghsa', 'epss', 'kev', 'eol']
const NUMEROS = ['max_queries', 'timeout_seconds', 'sla_days_critical', 'sla_days_high', 'sla_days_medium', 'sla_days_low', 'sla_days_kev', 'exception_max_days', 'eol_warning_days'] as const
const BORRAR = '__borrar__'

type Borrador = ConfigSoftwareIn & { nvd_api_key: string; ghsa_token: string }

const desde = (c: Config): Borrador => ({
  osv_enabled: c.osv_enabled, osv_url: c.osv_url, nvd_enabled: c.nvd_enabled, nvd_url: c.nvd_url,
  ghsa_enabled: c.ghsa_enabled, ghsa_url: c.ghsa_url, epss_enabled: c.epss_enabled, epss_url: c.epss_url,
  kev_enabled: c.kev_enabled, kev_url: c.kev_url, eol_enabled: c.eol_enabled, eol_url: c.eol_url, auto_sync: c.auto_sync,
  max_queries: c.max_queries, timeout_seconds: c.timeout_seconds, sla_days_critical: c.sla_days_critical, sla_days_high: c.sla_days_high,
  sla_days_medium: c.sla_days_medium, sla_days_low: c.sla_days_low, sla_days_kev: c.sla_days_kev, exception_max_days: c.exception_max_days,
  eol_warning_days: c.eol_warning_days, licenses_allowed: c.licenses_allowed, licenses_denied: c.licenses_denied,
  auto_ticket_min_severity: c.auto_ticket_min_severity, nvd_api_key: '', ghsa_token: '',
})

export default function ConfigSoftware() {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { data: config, isLoading } = useQuery({ queryKey: ['sw', 'config'], queryFn: cmdbSoftwareApi.config })
  const [b, setB] = useState<Borrador | null>(null)
  useEffect(() => { if (config && !b) setB(desde(config)) }, [config, b])
  const guardar = useMutation({
    mutationFn: (d: Borrador) => {
      const { nvd_api_key, ghsa_token, ...resto } = d
      return cmdbSoftwareApi.guardarConfig({ ...resto, ...(nvd_api_key ? { nvd_api_key } : {}), ...(ghsa_token ? { ghsa_token } : {}) })
    },
    onSuccess: c => { setB(desde(c)); toast.success(t('sw.cfg_guardada')); qc.invalidateQueries({ queryKey: ['sw', 'config'] }) },
    onError: err,
  })
  const probar = useMutation({
    mutationFn: (f: Fuente) => cmdbSoftwareApi.probarFuente(f),
    onSuccess: (r, f) => r.ok ? toast.success(t('sw.cfg_prueba_ok', { fuente: e('fuente', f) })) : toast.error(t('sw.cfg_prueba_mal', { fuente: e('fuente', f), detalle: r.error ?? '' })),
    onError: err,
  })
  if (isLoading || !config || !b) return <Spinner />
  const set = <K extends keyof Borrador>(k: K, v: Borrador[K]) => setB({ ...b, [k]: v })
  const quitarSecreto = (k: 'nvd_api_key' | 'ghsa_token') => guardar.mutate({ ...b, [k]: BORRAR })

  return (
    <div className="u-stack-20">
      <div className="sw-aviso"><Lock size={14} /> {t('sw.cfg_aviso')}</div>

      <Section title={t('sw.cfg_fuentes')} subtitle={t('sw.cfg_fuentes_desc')}>
        <ul className="sdm-list">
          {FUENTES.map(f => {
            const activa = b[`${f}_enabled` as keyof Borrador] as boolean
            const url = (b[`${f}_url` as keyof Borrador] as string | null) ?? ''
            return (
              <li key={f} className="sdm-list__item">
                <div className="u-flex1-min0 u-stack-6">
                  <div className="u-wrap-8">
                    <Switch checked={activa} onChange={v => set(`${f}_enabled` as keyof Borrador, v as never)} label={e('fuente', f)} />
                    {f === 'nvd' && config.nvd_api_key_set && <StatusBadge kind="success" caps={false}>{t('sw.cfg_clave_puesta')}</StatusBadge>}
                    {f === 'ghsa' && config.ghsa_token_set && <StatusBadge kind="success" caps={false}>{t('sw.cfg_token_puesto')}</StatusBadge>}
                  </div>
                  <div className="u-text3-xs">{t(`sw.cfg_fuente_${f}_d`)}</div>
                  <div className="sdm-form">
                    <Input label={t('sw.cfg_direccion')} value={url} placeholder={config[`${f}_url_effective` as keyof Config] as string} onChange={ev => set(`${f}_url` as keyof Borrador, (ev.target.value || null) as never)} inputClassName="u-mono" />
                    {f === 'nvd' && (
                      <Input label={t('sw.cfg_clave_nvd')} type="password" autoComplete="off" value={b.nvd_api_key} placeholder={config.nvd_api_key_set ? t('sw.cfg_puesta_no_cambia') : t('sw.cfg_opcional')} onChange={ev => set('nvd_api_key', ev.target.value)} />
                    )}
                    {f === 'ghsa' && (
                      <Input label={t('sw.cfg_token_github')} type="password" autoComplete="off" value={b.ghsa_token} placeholder={config.ghsa_token_set ? t('sw.cfg_puesta_no_cambia') : t('sw.cfg_obligatorio_github')} onChange={ev => set('ghsa_token', ev.target.value)} />
                    )}
                  </div>
                </div>
                <div className="u-actions-8">
                  {f === 'nvd' && config.nvd_api_key_set && <Button size="xs" variant="ghost" onClick={() => quitarSecreto('nvd_api_key')}>{t('sw.cfg_quitar')}</Button>}
                  {f === 'ghsa' && config.ghsa_token_set && <Button size="xs" variant="ghost" onClick={() => quitarSecreto('ghsa_token')}>{t('sw.cfg_quitar')}</Button>}
                  <Button size="xs" variant="secondary" icon={<PlugZap size={12} />} disabled={!activa} loading={probar.isPending && probar.variables === f} onClick={() => probar.mutate(f)}>{t('sw.cfg_probar')}</Button>
                </div>
              </li>
            )
          })}
        </ul>
      </Section>

      {/* Se guardan aparte (cada conexión con su botón); no forman parte del borrador. */}
      <ConexionesDeEscaneo />

      <Section title={t('sw.cfg_sincronizacion')} subtitle={t('sw.cfg_sincronizacion_desc')}>
        <div className="u-stack-12">
          <Switch checked={!!b.auto_sync} onChange={v => set('auto_sync', v)} label={t('sw.cfg_auto_sync')} />
          <div className="sdm-form">
            {(['max_queries', 'timeout_seconds'] as const).map(k => (
              <Input key={k} label={t(`sw.cfg_${k}`)} type="number" min={1} value={b[k] ?? ''} onChange={ev => set(k, Number(ev.target.value) || 0)} />
            ))}
          </div>
          <div className="u-text3-xs">{t('sw.ultima_sync')}: {config.last_sync_at ? fmtDateTime(config.last_sync_at) : t('sw.nunca')}{config.last_sync_status ? ` · ${e('ejec', config.last_sync_status)}` : ''}</div>
        </div>
      </Section>

      <Section title={t('sw.cfg_plazos')} subtitle={t('sw.cfg_plazos_desc')}>
        <div className="sdm-form">
          {NUMEROS.filter(k => k.startsWith('sla_') || k === 'exception_max_days' || k === 'eol_warning_days').map(k => (
            <Input key={k} label={t(`sw.cfg_${k}`)} type="number" min={1} value={b[k] ?? ''} onChange={ev => set(k, Number(ev.target.value) || 0)} />
          ))}
        </div>
      </Section>

      <Section title={t('sw.cfg_licencias')} subtitle={t('sw.cfg_licencias_desc')}>
        <div className="sdm-form">
          <Input label={t('sw.cfg_licencias_permitidas')} value={b.licenses_allowed ?? ''} placeholder="MIT, Apache-2.0, BSD-3-Clause" onChange={ev => set('licenses_allowed', ev.target.value || null)} inputClassName="u-mono" />
          <Input label={t('sw.cfg_licencias_prohibidas')} value={b.licenses_denied ?? ''} placeholder="AGPL-3.0-only, SSPL-1.0" onChange={ev => set('licenses_denied', ev.target.value || null)} inputClassName="u-mono" />
        </div>
      </Section>

      <Section title={t('sw.cfg_ticket')} subtitle={t('sw.cfg_ticket_desc')}>
        <Select label={t('sw.cfg_ticket_desde')} placeholder={false} value={b.auto_ticket_min_severity ?? ''} onChange={ev => set('auto_ticket_min_severity', (ev.target.value || null) as Severidad | null)}>
            <option value="">{t('sw.cfg_ticket_nunca')}</option>
            {(['critical', 'high', 'medium', 'low'] as Severidad[]).map(s => <option key={s} value={s}>{t('sw.cfg_ticket_o_mas', { sev: e('sev', s) })}</option>)}
          </Select>
      </Section>

      <div className="u-actions-10">
        <Button variant="secondary" disabled={guardar.isPending} onClick={() => setB(desde(config))}>{t('sw.cfg_descartar')}</Button>
        <Button loading={guardar.isPending} onClick={() => guardar.mutate(b)}>{t('common.save')}</Button>
      </div>

      {/* Índice de riesgo (22-11-2026): se guarda aparte, con su propio botón. */}
      <ConfigRiesgo />
    </div>
  )
}
