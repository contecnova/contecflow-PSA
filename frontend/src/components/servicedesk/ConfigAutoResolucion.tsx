/**
 * Sección «Autorresolución» de Configuración (`/settings/sd-autorresolucion`, 19-11-2026).
 *
 * Antes era la tarjeta «Configuración» de Service desk → Herramientas →
 * Autorresolución (AutoResolutionPanel). Umbrales de resolver y de sugerir,
 * horas hasta el cierre automático, ventana de validación y lote por ejecución
 * manual. Las cifras, las ejecuciones y la valoración siguen en el módulo.
 *
 * Lectura y escritura: GET/PATCH /sd/auto-resolution/config, solo admin; la
 * sección pide `sd.administrar`. Auditado desde el 19-11-2026
 * (`sd_auto_resolution_config`, antes y después; antes no quedaba rastro).
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { autoResolutionApi } from '../../services/api'
import type { ConfigDeAutoResolucion } from '../../services/api/tipos-analitica'
import { Button, Input, Spinner } from '../ui'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import './AutoResolutionPanel.css'

type AutoResolutionConfig = Partial<ConfigDeAutoResolucion>

export default function ConfigAutoResolucion() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [cfgDraft, setCfgDraft] = useState<AutoResolutionConfig | null>(null)

  const { data: config, isLoading } = useQuery<AutoResolutionConfig>({
    queryKey: ['sd-auto-resolution-config'],
    queryFn: () => autoResolutionApi.getConfig().then(r => r.data),
  })
  useEffect(() => {
    if (config) setCfgDraft(config)
  }, [config])

  const { mutate: saveConfig, isPending: savingConfig } = useMutation({
    mutationFn: () => autoResolutionApi.patchConfig({
      threshold_auto: Number(cfgDraft?.threshold_auto ?? 0.85),
      threshold_suggest: Number(cfgDraft?.threshold_suggest ?? 0.65),
      auto_close_hours_after_resolution: Number(cfgDraft?.auto_close_hours_after_resolution ?? 72),
      validation_window_hours: Number(cfgDraft?.validation_window_hours ?? 48),
      default_job_limit: Number(cfgDraft?.default_job_limit ?? 25),
    }),
    onSuccess: () => {
      toast.success(t('autoresolution.configuracion_de_auto_resolucion_guardada'))
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-config'] })
    },
    onError: (e) => toast.error(extractErr(e, t('autoresolution.error_guardar'))),
  })

  const setNum = (k: keyof ConfigDeAutoResolucion) => (e: { target: { value: string } }) =>
    setCfgDraft(prev => ({ ...prev, [k]: Number(e.target.value) }))

  if (isLoading || !cfgDraft) return <Spinner />
  return (
    <div className="u-stack-16">
      <div className="arp-config">
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor="arp-umbral-auto">{t('autoresolution.umbral_auto_resolver')}</label>
          <div className="arp-rango">
            <input id="arp-umbral-auto" type="range" min="0" max="1" step="0.01" className="arp-rango__input"
              value={cfgDraft.threshold_auto ?? 0.85} onChange={setNum('threshold_auto')} />
            <span className="arp-rango__valor">{Math.round((cfgDraft.threshold_auto ?? 0.85) * 100)} %</span>
          </div>
        </div>
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor="arp-umbral-sug">{t('autoresolution.umbral_sugerencia')}</label>
          <div className="arp-rango">
            <input id="arp-umbral-sug" type="range" min="0" max="1" step="0.01" className="arp-rango__input"
              value={cfgDraft.threshold_suggest ?? 0.65} onChange={setNum('threshold_suggest')} />
            <span className="arp-rango__valor">{Math.round((cfgDraft.threshold_suggest ?? 0.65) * 100)} %</span>
          </div>
        </div>
        <Input label={t('autoresolution.horas_para_auto_cierre')} type="number"
          value={cfgDraft.auto_close_hours_after_resolution ?? 72} onChange={setNum('auto_close_hours_after_resolution')} />
        <Input label={t('autoresolution.ventana_validacion_horas')} type="number"
          value={cfgDraft.validation_window_hours ?? 48} onChange={setNum('validation_window_hours')} />
        <Input label={t('autoresolution.lote_por_ejecucion_manual')} type="number"
          value={cfgDraft.default_job_limit ?? 25} onChange={setNum('default_job_limit')} />
      </div>
      <div className="u-actions-8">
        <Button onClick={() => saveConfig()} loading={savingConfig}>{t('autoresolution.guardar_configuracion')}</Button>
      </div>
    </div>
  )
}
