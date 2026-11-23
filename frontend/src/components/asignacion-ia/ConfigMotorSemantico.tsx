/**
 * Sección «Asignación por IA» de Configuración (`/settings/ia-asignacion`, 19-11-2026).
 *
 * Antes era la pestaña «Configuración» de Asignación IA (/semantic-engine):
 * modo del motor, embeddings y modelo, umbrales de confianza y auto-asignación
 * de tickets y tareas. En el módulo quedan perfiles, prueba y estadísticas, y
 * las acciones «Reconstruir embeddings» y «Auto-generar perfiles».
 *
 * Escritura: PUT /semantic/config (admin y RRHH en el servidor); la sección
 * pide `ia.asignacion_config`. pm, que entra al módulo a probar sugerencias,
 * ya no ve la configuración (antes la veía y le daba 403 al guardar).
 */
import type { ReactNode } from 'react'
import { useEffect, useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Bot, Brain, Check, ListChecks, Loader2, Zap } from 'lucide-react'
import { semanticApi } from '../../services/api'
import type { ConfigDelMotorSemantico } from '../../services/api/tipos-analitica'
import { Button, Pulsable, Select } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import '../../pages/SemanticEnginePage.css'
import { Input } from '../ui'

const fs = 'ds-input sem-input'
const ls = 'sem-label'

// Textos: claves de i18n del bloque `semanticengine`.
export const ENGINE_MODES: Record<string, { label: string; icon: ReactNode; desc: string }> = {
  hybrid:     { label: 'semanticengine.modo_hybrid',     icon: <Zap size={16} />,        desc: 'semanticengine.modo_hybrid_desc' },
  semantic:   { label: 'semanticengine.modo_semantic',   icon: <Brain size={16} />,      desc: 'semanticengine.modo_semantic_desc' },
  llm:        { label: 'semanticengine.modo_llm',        icon: <Bot size={16} />,        desc: 'semanticengine.modo_llm_desc' },
  rules_only: { label: 'semanticengine.modo_rules_only', icon: <ListChecks size={16} />, desc: 'semanticengine.modo_rules_only_desc' },
}

export const EMBEDDINGS_BACKENDS: Record<string, { label: string; desc: string }> = {
  tfidf:       { label: 'semanticengine.backend_tfidf',       desc: 'semanticengine.backend_tfidf_desc' },
  transformer: { label: 'semanticengine.backend_transformer', desc: 'semanticengine.backend_transformer_desc' },
}

type SemConfig = ConfigDelMotorSemantico

export default function ConfigMotorSemantico() {
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [hfModelDraft, setHfModelDraft] = useState('')

  const { data: config = {} } = useQuery<Partial<SemConfig>>({
    queryKey: ['sem-config'],
    queryFn: () => semanticApi.config().then(r => r.data),
  })
  useEffect(() => {
    setHfModelDraft(config.local_model_name && config.local_model_name !== 'tfidf' ? config.local_model_name : 'all-MiniLM-L6-v2')
  }, [config.local_model_name])

  const { mutate: saveConfig, isPending: savingConfig } = useMutation({
    mutationFn: (d: Record<string, unknown>) => semanticApi.updateConfig(d).then(r => r.data),
    onMutate: async (patch) => {
      await qc.cancelQueries({ queryKey: ['sem-config'] })
      const previous = qc.getQueryData(['sem-config'])
      qc.setQueryData(['sem-config'], (current: Partial<SemConfig> | undefined) => ({ ...(current || {}), ...patch }))
      return { previous }
    },
    onSuccess: data => {
      if (data?.config) qc.setQueryData(['sem-config'], data.config)
      toast.success(traducir('semanticengine.config_actualizada'))
    },
    onError: (e, _patch, ctx) => {
      if (ctx?.previous) qc.setQueryData(['sem-config'], ctx.previous)
      toast.error(extractErr(e, traducir('semanticengine.error_actualizar')))
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['sem-config'] }),
  })

  const backendLabel = (b: string) => EMBEDDINGS_BACKENDS[b] ? traducir(EMBEDDINGS_BACKENDS[b].label) : b
  const backendActual = config.embeddings_backend || 'tfidf'

  return (
      <div className="sem-grid2">
        <div className="sem-card sem-card--pad">
          <div className="sem-h sem-h--600">{traducir('semanticengine.modo_del_motor')}</div>
          <div className="u-stack-10">
            {Object.entries(ENGINE_MODES).map(([key, meta]) => (
              <Pulsable key={key} type="button" onClick={() => saveConfig({ engine_mode: key })} disabled={savingConfig}
                aria-pressed={config.engine_mode === key}
                className={`sem-mode${savingConfig ? ' sem-mode--saving' : ''}`}>
                <div className="u-row-center-10">
                  <span className="sem-mode__icon" aria-hidden="true">{meta.icon}</span>
                  <div>
                    <div className="sem-mode__label">{traducir(meta.label)}</div>
                    <div className="u-text2-xs-mt2">{traducir(meta.desc)}</div>
                  </div>
                  {config.engine_mode === key && <span className="sem-mode__check" aria-hidden="true">{savingConfig ? <Loader2 size={16} className="sem-girar" /> : <Check size={16} />}</span>}
                </div>
              </Pulsable>
            ))}
          </div>
        </div>

        <div className="u-stack-16">
          <div className="sem-card sem-card--pad">
            <div className="sem-h">{traducir('semanticengine.embeddings_y_modelo')}</div>

            <div className="u-mb-14">
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={ls}>{traducir('semanticengine.backend_de_embeddings')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-1`}
                value={backendActual}
                onChange={e => {
                  const backend = e.target.value
                  if (backend === 'transformer') {
                    const modelName = (hfModelDraft || config.local_model_name || 'all-MiniLM-L6-v2').trim()
                    saveConfig({ embeddings_backend: 'transformer', local_model_name: modelName || 'all-MiniLM-L6-v2' })
                    return
                  }
                  saveConfig({ embeddings_backend: 'tfidf', local_model_name: 'tfidf' })
                }}
                className={fs}
                disabled={savingConfig}
              >
                {Object.entries(EMBEDDINGS_BACKENDS).map(([key, meta]) => (
                  <option key={key} value={key}>{traducir(meta.label)}</option>
                ))}
              </Select>
              <div className="sem-hint">
                {EMBEDDINGS_BACKENDS[backendActual] ? traducir(EMBEDDINGS_BACKENDS[backendActual].desc) : ''}
              </div>
              {config.backend_en_uso && config.backend_en_uso !== backendActual && (
                // Revisión 2026-11: el configurado no siempre es el que se usa.
                <div className="sem-hint sem-hint--warning">
                  {traducir('semanticengine.backend_en_uso_distinto')} {backendLabel(config.backend_en_uso)}
                </div>
              )}
            </div>

            <div className="u-mb-10">
              <label id={`${idCampo}-eta463`} htmlFor={`${idCampo}-a463`} className={ls}>{traducir('semanticengine.modelo_hf')}</label>
              <div className="u-row-8">
                <Input id={`${idCampo}-a463`} aria-labelledby={`${idCampo}-eta463`} value={hfModelDraft} onChange={e => setHfModelDraft(e.target.value)} placeholder={traducir('semanticengine.modelo_hf_placeholder')} disabled={backendActual !== 'transformer' || savingConfig} className="sem-input--min0" />
                <Button
                  variant="secondary"
                  disabled={backendActual !== 'transformer' || savingConfig || !hfModelDraft.trim()}
                  onClick={() => saveConfig({ embeddings_backend: 'transformer', local_model_name: hfModelDraft.trim() })}
                >
                  {traducir('common.save')}
                </Button>
              </div>
            </div>

            <div className="sem-box">
              <div>{traducir('semanticengine.backend_activo')} <strong className="u-text1">{backendLabel(backendActual)}</strong></div>
              <div>{traducir('semanticengine.modelo_efectivo')} <strong className="u-text1">{config.effective_model_name || (config.local_model_name || 'all-MiniLM-L6-v2')}</strong></div>
            </div>
          </div>

          <div className="sem-card sem-card--pad">
            <div className="sem-h">{traducir('semanticengine.umbrales_de_confianza')}</div>
            {[
              { key: 'threshold_ticket', label: traducir('semanticengine.umbral_tickets'), val: config.threshold_ticket },
              { key: 'threshold_task',   label: traducir('semanticengine.umbral_tareas'),  val: config.threshold_task },
              { key: 'threshold_expert_cache', label: traducir('semanticengine.umbral_cache'), val: config.threshold_expert_cache },
              { key: 'load_balance_weight', label: traducir('semanticengine.peso_balanceo'), val: config.load_balance_weight },
            ].map(f => (
              <div key={f.key} className="u-mb-12">
                <div className="sem-range-head">
                  <label htmlFor={`${idCampo}-${f.key}`} className={`${ls} sem-label--flush`}>{f.label}</label>
                  <span className="sem-range-val">{f.val}</span>
                </div>
                <input id={`${idCampo}-${f.key}`} aria-label={f.label} type="range" min={f.key === 'load_balance_weight' ? '0.0' : '0.3'} max="0.99" step="0.01"
                  value={f.val || 0.6}
                  onChange={e => saveConfig({ [f.key]: parseFloat(e.target.value) })}
                  className="sem-range" />
              </div>
            ))}
          </div>

          <div className="sem-card sem-card--pad">
            <div className="sem-h">{traducir('semanticengine.auto_asignacion')}</div>
            {[
              { key: 'auto_assign_tickets', label: traducir('semanticengine.auto_tickets'), val: config.auto_assign_tickets },
              { key: 'auto_assign_tasks',   label: traducir('semanticengine.auto_tareas'),  val: config.auto_assign_tasks },
            ].map(f => (
              <div key={f.key} className="sem-toggle-row">
                <span className="sem-base">{f.label}</span>
                <Pulsable type="button" aria-label={f.label} aria-pressed={!!f.val} onClick={() => saveConfig({ [f.key]: !f.val })} className="sem-switch">
                  <span className="sem-switch__knob" />
                </Pulsable>
              </div>
            ))}
            <div className="sem-box sem-box--warning sem-con-icono">
              <AlertTriangle size={14} aria-hidden />
              <span>{traducir('semanticengine.con_auto_asignacion_activada_los_items_se')}</span>
            </div>
          </div>
        </div>
      </div>
  )
}
