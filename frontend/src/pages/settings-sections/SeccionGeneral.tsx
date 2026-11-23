/**
 * Secciones General (moneda, zona horaria, idioma, jornada) y Seguridad de sesión.
 * Troceado de SettingsPageSections.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState, type ChangeEvent } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi } from '../../services/settingsApi'
import { Button, IconButton, Input, Select, Spinner, Switch } from '../../components/ui'
import { Check, Settings, Lock } from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import SeccionDeAjustes from './SeccionDeAjustes'
import { useOrgSettings } from '../../hooks/useOrgSettings'
import { timezoneOptions } from '../../constants/timezones'

// ── General: moneda, zona horaria, idioma y jornada de la empresa ───────────────
/**
 * 18-11-2026 (reorganización de Configuración): una sola fuente. Estos cuatro
 * valores son las claves de ejecución `DEFAULT_CURRENCY`, `DEFAULT_TIMEZONE`,
 * `DEFAULT_LANGUAGE` y `DEFAULT_WORKING_HOURS_PER_DAY` (las que lee
 * `/settings/org-defaults`); `PATCH /settings/general/{alias}` las escribe
 * (ALIAS_DE_EJECUCION en app/services/settings_service/generales.py). Antes se
 * guardaban en filas propias que no leía nadie, y Config. dinámica → Locale
 * editaba las de verdad: ahora Config. dinámica las oculta.
 * El nombre visible de la empresa y del producto se edita en Marca.
 * Guardado como el resto de secciones: borrador + «Guardar»; el refresco tras
 * escritura (services/api/refrescoTrasEscritura.ts) actualiza las pantallas.
 */
const CAMPOS_GENERALES = ['currency', 'timezone', 'language', 'work_hours_per_day'] as const

type CampoGeneral = typeof CAMPOS_GENERALES[number]

const IDIOMAS_OPERADOR = ['es', 'en', 'zh'] as const

export function GeneralSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const { currencies } = useOrgSettings()
  const { data: settings = [], isLoading } = useQuery({ queryKey: ['settings-general'], queryFn: () => settingsApi.getGeneral().then(r => r.data) })
  const guardados = Object.fromEntries(CAMPOS_GENERALES.map(k => [k, settings.find(s => s.key === k)?.value ?? ''])) as Record<CampoGeneral, string>
  const [borrador, setBorrador] = useState<Partial<Record<CampoGeneral, string>>>({})
  const valor = (k: CampoGeneral) => borrador[k] ?? guardados[k]
  const cambiados = CAMPOS_GENERALES.filter(k => borrador[k] !== undefined && borrador[k] !== guardados[k])
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: async () => { for (const k of cambiados) await settingsApi.updateSetting(k, String(borrador[k])) },
    onSuccess: () => { setBorrador({}); toast.success(t('i18n.saved')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const poner = (k: CampoGeneral) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setBorrador(b => ({ ...b, [k]: e.target.value }))
  const monedas = Array.from(new Set([...(currencies || []), guardados.currency].filter(Boolean)))

  if (isLoading) return <Spinner />
  return (
    <SeccionDeAjustes icon={<Settings size={18} />} title={t('settings.configuracion_general')} description={t('ajustes.general_desc')}>
      <div className="set-grid-fields">
        <Select label={t('settings.currency')} value={valor('currency')} onChange={poner('currency')}
          options={monedas.map(m => ({ value: m, label: m }))} />
        <Select label={t('settings.timezone')} value={valor('timezone')} onChange={poner('timezone')}
          options={timezoneOptions(valor('timezone')).map(tz => ({ value: tz, label: tz }))} />
        <Select label={t('settings_sections.idioma')} value={valor('language')} onChange={poner('language')}
          options={IDIOMAS_OPERADOR.map(l => ({ value: l, label: t(`ajustes.idioma_${l}`) }))} />
        <Input label={t('settings.work_hours')} type="number" min={1} max={24} step={0.5}
          value={valor('work_hours_per_day')} onChange={poner('work_hours_per_day')} />
      </div>
      <div className="set-acciones">
        <span className="u-text2-sm">{t('ajustes.general_nombre_en_marca')} <Link to="/settings/branding" className="set-enlace">{t('settings_page.tab_branding')}</Link></span>
        <Button icon={<Check size={14} />} disabled={cambiados.length === 0} loading={isPending} onClick={() => guardar()}>{t('common.save')}</Button>
      </div>
    </SeccionDeAjustes>
  )
}

// ── Session security ──────────────────────────────────────────────────────────
const IDLE_TIMEOUT_OPTIONS = [5, 10, 15, 30, 60, 120, 240]

export function SessionSecuritySection() {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()

  const { data: settings = [] } = useQuery({
    queryKey: ['settings-general'],
    queryFn: () => settingsApi.getGeneral().then(r => r.data),
  })
  const { mutate: update } = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => settingsApi.updateSetting(key, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings-general'] }),
    onError: e => toast.error(extractErr(e, t('settings_sections.err_guardar'))),
  })

  const find = (k: string) => settings.find(s => s.key === k)?.value
  const idleEnabled = find('idle_timeout_enabled') === 'true'
  const idleMinutes = parseInt(find('idle_timeout_minutes') || '30', 10)

  return (
    <SeccionDeAjustes icon={<Lock size={18} />} title={t('settings.seguridad_de_sesion')} description={t('settings_sections.sesion_desc')}>
      <div className="set-session">

        {/* Toggle idle timeout */}
        <div className="set-panel set-panel--row">
          <div>
            <div className="set-panel-title">
              {t('settings.cierre_de_sesion_por_inactividad')}
            </div>
            <div className="u-text3-xs-mt2">
              {t('settings.cierra_la_sesion_automaticamente_si_el_usuario')}
            </div>
          </div>
          <Switch aria-label={t('settings.cierre_de_sesion_por_inactividad')} checked={idleEnabled}
            onChange={m => update({ key: 'idle_timeout_enabled', value: m ? 'true' : 'false' })} />
        </div>

        {/* Timeout duration selector */}
        <div className={`set-panel${idleEnabled ? '' : ' set-panel--off'}`} role="group" aria-labelledby="set-idle-minutes" aria-disabled={!idleEnabled || undefined}>
          <span id="set-idle-minutes" className="set-label">{t('settings.minutos_de_inactividad_antes_de_cerrar_sesion')}</span>
          <div className="set-options">
            {IDLE_TIMEOUT_OPTIONS.map(m => (
              <IconButton
                key={m}
                ariaLabel={m < 60 ? t('settings_sections.n_min', { n: m }) : t('settings_sections.n_h', { n: m / 60 })}
                aria-pressed={m === idleMinutes}
                tabIndex={idleEnabled ? undefined : -1}
                onClick={() => update({ key: 'idle_timeout_minutes', value: String(m) })}
                className={`set-option${m === idleMinutes ? ' set-option--on' : ''}`}
              >
                {m < 60 ? t('settings_sections.n_min', { n: m }) : t('settings_sections.n_h', { n: m / 60 })}
              </IconButton>
            ))}
          </div>
          <div className="set-hint-mt10">
            {t('settings.se_mostrara_un_aviso_60_segundos_antes')}
          </div>
        </div>

      </div>
    </SeccionDeAjustes>
  )
}
