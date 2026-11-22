/**
 * Configuración → Software y vulnerabilidades → Índice de riesgo (22-11-2026):
 * pesos por factor (suman 1), saturaciones, multiplicadores de exposición y de
 * criticidad, explotación (KEV, EPSS, intentos y umbral de EPSS), edad, rangos
 * de impacto, objetivo de la empresa, días de histórico y avisos (KEV nuevo,
 * índice por encima de un umbral, SLA a punto de vencer; a quién y si va por
 * correo). «Restaurar valores por defecto» rellena con los del servidor.
 *
 * Pide `software.config` (la sección entera). Cada cambio se audita en el
 * servidor (`sw_risk_settings`). Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11.3 y §11.10.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RotateCcw, X } from 'lucide-react'
import { useAppT } from '../../../../i18n/AppLangContext'
import { useToast } from '../../../../context/ToastContext'
import { etiquetaCodigo } from '../../../../i18n/etiquetaCodigo'
import { STALE_REFERENCE_DATA_MS } from '../../../../constants/timings'
import { usersApi } from '../../../../services/api'
import { cmdbRiesgoApi } from '../../../../services/api/cmdbRiesgo'
import type { AjustesDeRiesgoBase, Factor } from '../../../../services/api/cmdbRiesgo'
import { Button, Checkbox, IconButton, Input, Section, Spinner, StatusBadge, UserSelect, useErroresDeCampo } from '../../../ui'
import { useErr } from '../comun'
import { useEtiquetaSwr } from './comunRiesgo'
import '../../../servicedesk/sdMercado.css'
import '../software.css'
import './riesgo.css'

const FACTORES: Factor[] = ['vulnerabilities', 'exploitation', 'exposure', 'configuration', 'eol', 'signals']
const ROLES = ['admin', 'pm', 'team_lead', 'hr', 'employee']
const TOLERANCIA = 0.001

/** Sin `defaults`: lo que se edita y se manda. */
const borrador = (a: AjustesDeRiesgoBase): AjustesDeRiesgoBase => JSON.parse(JSON.stringify({
  weights: a.weights, saturation: a.saturation, exposure: a.exposure, criticality: a.criticality, exploit: a.exploit,
  age: a.age, impact_ranges: a.impact_ranges, target: a.target, history_days: a.history_days, alerts: a.alerts,
}))

const num = (v: string) => (v === '' ? 0 : Number(v))
const numONulo = (v: string) => (v === '' ? null : Number(v))

export default function ConfigRiesgo() {
  const t = useAppT()
  const e = useEtiquetaSwr()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const campos = useErroresDeCampo()
  const { data: ajustes, isLoading } = useQuery({ queryKey: ['swr', 'ajustes'], queryFn: cmdbRiesgoApi.ajustes })
  const usuarios = useQuery({ queryKey: ['users', 'directory'], queryFn: () => usersApi.directory().then(r => r.data as { id: string; full_name?: string }[]), staleTime: STALE_REFERENCE_DATA_MS })
  const [b, setB] = useState<AjustesDeRiesgoBase | null>(null)
  useEffect(() => { if (ajustes && !b) setB(borrador(ajustes)) }, [ajustes, b])
  const guardar = useMutation({
    mutationFn: (d: AjustesDeRiesgoBase) => cmdbRiesgoApi.guardarAjustes(d),
    onMutate: () => campos.limpiar(),
    onSuccess: a => { setB(borrador(a)); toast.success(t('swr.cfg_guardada')); qc.invalidateQueries({ queryKey: ['swr'] }) },
    onError: x => { if (!campos.recoger(x)) err(x) },
  })
  if (isLoading || !ajustes || !b) return <Spinner />

  const set = <K extends keyof AjustesDeRiesgoBase>(k: K, v: AjustesDeRiesgoBase[K]) => setB({ ...b, [k]: v })
  const setEn = <K extends 'weights' | 'saturation' | 'exposure' | 'criticality' | 'exploit' | 'age' | 'impact_ranges'>(k: K, sub: string, v: number) =>
    setB({ ...b, [k]: { ...(b[k] as Record<string, number>), [sub]: v } })
  const setAviso = <K extends keyof AjustesDeRiesgoBase['alerts']>(k: K, v: AjustesDeRiesgoBase['alerts'][K]) => setB({ ...b, alerts: { ...b.alerts, [k]: v } })

  const suma = FACTORES.reduce((s, f) => s + (Number(b.weights[f]) || 0), 0)
  const pesosBien = Math.abs(suma - 1) <= TOLERANCIA
  const pesoMal = FACTORES.some(f => b.weights[f] < 0 || b.weights[f] > 1)
  const saturacionMal = FACTORES.some(f => !(b.saturation[f] > 0))
  const rangosMal = !(b.impact_ranges.high_from > b.impact_ranges.medium_from)
  const objetivoMal = !(b.target >= 0 && b.target <= 100)
  const epssMal = !(b.exploit.epss_threshold >= 0 && b.exploit.epss_threshold <= 1)
  const hayError = !pesosBien || pesoMal || saturacionMal || rangosMal || objetivoMal || epssMal
  const nombre = (id: string) => usuarios.data?.find(u => u.id === id)?.full_name ?? id

  const numero = (etiqueta: string, valor: number | null, onChange: (v: string) => void, extra?: { min?: number; max?: number; step?: number | string; error?: string; hint?: string }) => (
    <Input key={etiqueta} label={etiqueta} type="number" value={valor == null ? '' : valor} min={extra?.min} max={extra?.max} step={extra?.step ?? 'any'}
      error={extra?.error} hint={extra?.hint} onChange={ev => onChange(ev.target.value)} />
  )

  return (
    <div className="u-stack-20">
      <Section title={t('swr.cfg_titulo')} subtitle={t('swr.cfg_desc')}
        actions={<Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} onClick={() => setB(borrador(ajustes.defaults))}>{t('swr.cfg_restaurar')}</Button>}>
        <div className="u-stack-20">
          <div className="u-stack-12">
            <div className="ds-eyebrow">{t('swr.cfg_pesos')}</div>
            <div className="u-text3-xs">{t('swr.cfg_pesos_ayuda')}</div>
            <div className="sdm-form">
              {FACTORES.map(f => numero(e('factor', f), b.weights[f], v => setEn('weights', f, num(v)), { min: 0, max: 1, step: 0.01 }))}
            </div>
            <div className={`swr-suma${pesosBien ? '' : ' swr-suma--mal'}`} role={pesosBien ? undefined : 'alert'}>
              {t(pesosBien ? 'swr.cfg_suma_ok' : 'swr.cfg_suma_mal', { suma: suma.toFixed(3) })}
            </div>
            {campos.de('weights') && <div className="u-field-error">{campos.de('weights')}</div>}
          </div>

          <div className="u-stack-12">
            <div className="ds-eyebrow">{t('swr.cfg_saturacion')}</div>
            <div className="u-text3-xs">{t('swr.cfg_saturacion_ayuda')}</div>
            <div className="sdm-form">
              {FACTORES.map(f => numero(e('factor', f), b.saturation[f], v => setEn('saturation', f, num(v)), { min: 0, step: 0.5, error: b.saturation[f] > 0 ? undefined : t('swr.cfg_mayor_que_cero') }))}
            </div>
          </div>

          <div className="u-stack-12">
            <div className="ds-eyebrow">{t('swr.cfg_multiplicadores')}</div>
            <div className="u-text3-xs">{t('swr.cfg_multiplicadores_ayuda')}</div>
            <div className="sdm-form">
              {(['internet', 'internal', 'isolated'] as const).map(k => numero(t('swr.cfg_expo', { valor: e('exposicion', k) }), b.exposure[k], v => setEn('exposure', k, num(v)), { min: 0, max: 1, step: 0.05 }))}
              {(['critical', 'high', 'medium', 'low'] as const).map(k => numero(t('swr.cfg_criticidad', { valor: e('nivel', k) }), b.criticality[k], v => setEn('criticality', k, num(v)), { min: 0, max: 1, step: 0.05 }))}
            </div>
          </div>

          <div className="u-stack-12">
            <div className="ds-eyebrow">{t('swr.cfg_explotacion')}</div>
            <div className="sdm-form">
              {numero(t('swr.cfg_w_kev'), b.exploit.w_kev, v => setEn('exploit', 'w_kev', num(v)), { min: 0, step: 0.1 })}
              {numero(t('swr.cfg_w_epss'), b.exploit.w_epss, v => setEn('exploit', 'w_epss', num(v)), { min: 0, step: 0.1 })}
              {numero(t('swr.cfg_w_attempts'), b.exploit.w_attempts, v => setEn('exploit', 'w_attempts', num(v)), { min: 0, step: 0.1 })}
              {numero(t('swr.cfg_epss_threshold'), b.exploit.epss_threshold, v => setEn('exploit', 'epss_threshold', num(v)), { min: 0, max: 1, step: 0.05, hint: t('swr.cfg_epss_threshold_ayuda'), error: epssMal ? t('swr.cfg_entre_0_y_1') : undefined })}
              {numero(t('swr.cfg_w_age'), b.age.w_age, v => setEn('age', 'w_age', num(v)), { min: 0, step: 0.05 })}
              {numero(t('swr.cfg_age_cap_days'), b.age.age_cap_days, v => setEn('age', 'age_cap_days', num(v)), { min: 1, step: 1 })}
            </div>
          </div>

          <div className="u-stack-12">
            <div className="ds-eyebrow">{t('swr.cfg_impacto_objetivo')}</div>
            <div className="sdm-form">
              {numero(t('swr.cfg_high_from'), b.impact_ranges.high_from, v => setEn('impact_ranges', 'high_from', num(v)), { min: 0, max: 100, step: 1, error: rangosMal ? t('err_srv.swr_rangos_de_impacto') : undefined })}
              {numero(t('swr.cfg_medium_from'), b.impact_ranges.medium_from, v => setEn('impact_ranges', 'medium_from', num(v)), { min: 0, max: 100, step: 1 })}
              {numero(t('swr.objetivo'), b.target, v => set('target', num(v)), { min: 0, max: 100, step: 1, hint: t('swr.cfg_objetivo_ayuda'), error: objetivoMal ? t('err_srv.swr_objetivo_no_valido') : campos.de('target') })}
              {numero(t('swr.cfg_history_days'), b.history_days, v => set('history_days', num(v)), { min: 30, step: 1, hint: t('swr.cfg_history_days_ayuda'), error: campos.de('history_days') })}
            </div>
          </div>
        </div>
      </Section>

      <Section title={t('swr.cfg_avisos')} subtitle={t('swr.cfg_avisos_desc')}>
        <div className="u-stack-12">
          <Checkbox checked={b.alerts.kev_new} onChange={v => setAviso('kev_new', v)} label={t('swr.cfg_kev_new')} ayuda={t('swr.cfg_kev_new_ayuda')} />
          <div className="sdm-form">
            {numero(t('swr.cfg_index_above'), b.alerts.index_above, v => setAviso('index_above', numONulo(v)), { min: 0, max: 100, step: 1, hint: t('swr.cfg_vacio_desactiva') })}
            {numero(t('swr.cfg_sla_due_days'), b.alerts.sla_due_days, v => setAviso('sla_due_days', numONulo(v)), { min: 1, step: 1, hint: t('swr.cfg_vacio_desactiva') })}
          </div>
          <div className="u-stack-6">
            <div className="ds-eyebrow">{t('swr.cfg_roles')}</div>
            <div className="u-wrap-10">
              {ROLES.map(r => <Checkbox key={r} checked={b.alerts.roles.includes(r)} label={etiquetaCodigo(t, 'rol_usuario', r)}
                onChange={si => setAviso('roles', si ? [...b.alerts.roles, r] : b.alerts.roles.filter(x => x !== r))} />)}
            </div>
          </div>
          <div className="u-stack-6">
            <div className="ds-eyebrow">{t('swr.cfg_usuarios')}</div>
            <div className="u-wrap-6">
              {b.alerts.user_ids.map(id => (
                <StatusBadge key={id} caps={false}>{nombre(id)} <IconButton ariaLabel={t('swr.quitar_usuario', { nombre: nombre(id) })} onClick={() => setAviso('user_ids', b.alerts.user_ids.filter(x => x !== id))}><X size={12} /></IconButton></StatusBadge>
              ))}
            </div>
            <div className="sw-campo-estrecho">
              <UserSelect value="" placeholder={t('swr.cfg_anadir_usuario')} filterFn={u => !b.alerts.user_ids.includes(u.id)}
                onChange={id => { if (id) setAviso('user_ids', [...b.alerts.user_ids, id]) }} />
            </div>
          </div>
          <Checkbox checked={b.alerts.email} onChange={v => setAviso('email', v)} label={t('swr.cfg_email')} ayuda={t('swr.cfg_email_ayuda')} />
          {campos.de('alerts') && <div className="u-field-error">{campos.de('alerts')}</div>}
        </div>
      </Section>

      <div className="u-actions-10">
        <Button variant="secondary" disabled={guardar.isPending} onClick={() => { campos.limpiar(); setB(borrador(ajustes)) }}>{t('swr.cfg_descartar')}</Button>
        <Button loading={guardar.isPending} disabled={hayError} onClick={() => guardar.mutate(b)}>{t('swr.cfg_guardar')}</Button>
      </div>
    </div>
  )
}
