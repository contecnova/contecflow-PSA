/**
 * RcaWizardModal — Multi-step AI-assisted RCA wizard for a Problem record.
 *
 * Steps come from the server (five_whys / fishbone / itil_standard templates).
 * Each step has a text answer + optional AI hint via the ai-assist endpoint.
 *
 * Backend endpoints:
 *   POST /sd/problems/{id}/rca-wizard/start    { template: 'five_whys'|... }
 *   GET  /sd/problems/{id}/rca-wizard
 *   POST /sd/problems/{id}/rca-wizard/step     { step, answer }
 *   POST /sd/problems/{id}/rca-wizard/ai-assist{ step }
 *   POST /sd/problems/{id}/rca-wizard/complete
 *
 * 16-11-2026 (pasada de diseño): título traducido y sin «🔍 Wizard»; iconos
 * lucide en lugar de «💡 ✅ 🤖 ▶ →»; la pista del paso sin --info; campo con
 * `ds-input`; «Paso N» y «Sin sugerencia» traducidos.
 */
import React, { type CSSProperties, useState } from 'react'
import { CheckCircle2, ChevronRight, Lightbulb, Sparkles } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { problemsApi } from '../../services/api'
import { problemasApi } from '../../services/api/serviceDeskMercado'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import type { SdAsistenteRca, SdRcaCompletado } from '../../services/api/tipos-sd'
import { Button, Radio, Spinner, Modal, Textarea } from '../ui'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { STALE_ALWAYS } from '../../constants/timings'
import './RcaWizardModal.css'

type WizardState = SdAsistenteRca


/** Plantillas del servidor (las de serie y las propias de la empresa, mejoras
 *  de mercado 16-11-2026): antes eran tres fijas aquí, en castellano, y una
 *  plantilla creada por la empresa no se podía elegir. */

function TemplateSelector({ onStart, isPending }: { onStart: (template: string) => void; isPending: boolean }) {
  const { t: traducir } = useAppLang()
  const t = traducir
  const { data: plantillas = [], isLoading } = useQuery({ queryKey: ['sd-rca-templates'], queryFn: problemasApi.plantillas })
  const activas = plantillas.filter(p => p.is_active)
  const [tpl, setTpl] = useState<string>('')
  const elegida = tpl || activas[0]?.id || ''
  if (isLoading) return <Spinner />
  return (
    <div className="u-stack-16">
      <div className="u-text2-base">
        {traducir('rcawizardmodal.selecciona_la_metodologia_de_analisis_de_causa')}
      </div>
      <div className="u-stack-10">
        {activas.map(p => {
          const nombre = p.is_system ? etiquetaCodigo(t, 'sd_mercado.rca_tipo', p.template_type, p.name) : p.name
          return (
            <label htmlFor={`tpl-${p.id}`} className={`rcwimo-row-4 rcawizar-sx1 rca-wizard-modal-e1 ${elegida === p.id ? 'rca-wizard-modal-m2' : 'rca-wizard-modal-m3'}`} key={p.id} style={{ '--rca-wizard-modal-border': `1px solid ${elegida === p.id ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
              <Radio id={`tpl-${p.id}`} name="tpl" value={p.id} aria-label={nombre} checked={elegida === p.id} onChange={() => setTpl(p.id)} className="rcwimo-box-1" />
              <div>
                <div className={`rcwimo-txt-2 ${elegida === p.id ? 'rca-wizard-modal-m4' : 'rca-wizard-modal-m5'}`}>{nombre}</div>
                <div className="rcwimo-box-2">{p.is_system ? t(`sd_mercado.rca_tipo_desc.${p.template_type}`, p.description || '') : (p.description || '')} · {t('sd_mercado.n_pasos', { n: p.total_steps })}</div>
              </div>
            </label>
          )
        })}
      </div>
      <div className="u-row-end">
        <Button onClick={() => onStart(elegida)} loading={isPending} disabled={!elegida} icon={<ChevronRight size={14} />}>
          {traducir('rcawizard.iniciar_wizard')}
        </Button>
      </div>
    </div>
  )
}

interface WizardStepProps {
  problemId: string | number
  state: WizardState | null | undefined
  onRefresh: () => void
  onComplete: (result: SdRcaCompletado['rca']) => void
}

function WizardStep({ problemId, state, onRefresh, onComplete }: WizardStepProps) {
  const idCampo = React.useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const steps = state?.steps ?? []
  // Auditoría 2026-11: el servidor numera los pasos desde 1 (y así los espera
  // en /step y /ai-assist); la pantalla los usaba como índice desde 0: pregunta
  // equivocada, «Paso 6 de 5» y el último paso detectado uno antes.
  const currentStep = state?.current_step ?? 1
  const totalSteps = steps.length
  const isLast = currentStep >= totalSteps
  const stepDef = steps.find(s => s.step === currentStep)
  // Auditoría 2026-11: el resumen leía `state.answers`, el enunciado `title` y
  // la pista `hint`, y nada de eso existe: las respuestas y la pista de la IA
  // viven en cada paso (`answer`, `ai_hint`).
  const anteriores = steps.filter(s => s.answer && s.step !== currentStep)

  const [answer, setAnswer] = useState<string>('')
  const [aiHint, setAiHint] = useState<string | null>(null)
  const [aiLoading, setAiLoading] = useState<boolean>(false)

  const { mutate: submitStep, isPending: submitting } = useMutation({
    mutationFn: () => problemsApi.rcaWizardStep(problemId, { step: currentStep, answer }),
    onSuccess: () => { setAnswer(''); setAiHint(null); onRefresh() },
    onError: () => toast.error(traducir('rcawizard.error_al_guardar_respuesta')),
  })

  // El cierre exige todos los pasos respondidos: la respuesta del último se
  // guarda antes (sin eso el servidor respondía 400 «Steps not yet answered»).
  const { mutate: completeWizard, isPending: completing } = useMutation({
    mutationFn: async () => {
      await problemsApi.rcaWizardStep(problemId, { step: currentStep, answer })
      return problemsApi.rcaWizardComplete(problemId)
    },
    onSuccess: (res) => { toast.success(traducir('rcawizard.rca_completado_y_aplicado_al_problema')); onComplete(res.data.rca) },
    onError: () => toast.error(traducir('rcawizard.error_al_completar_el_wizard')),
  })

  const getAiHint = async () => {
    setAiLoading(true)
    try {
      const res = await problemsApi.rcaWizardAiAssist(problemId, { step: currentStep })
      setAiHint(res.data.hint || traducir('rcawizard.sin_sugerencia'))
    } catch {
      toast.error(traducir('rcawizard.error_al_obtener_sugerencia_ia'))
    } finally {
      setAiLoading(false)
    }
  }

  // Progress bar
  const progress = totalSteps > 0 ? Math.round(((currentStep - 1) / totalSteps) * 100) : 0

  return (
    <div className="rcwimo-stack-1">
      {/* Progress */}
      <div>
        <div className="rcwimo-row-1">
          <span>{traducir('rcawizardmodal.paso_x_de_y', { actual: currentStep, total: totalSteps })}</span>
          <span>{progress}{traducir('pagina_perf.completado')}</span>
        </div>
        <div className="rcwimo-box-3">
          <div className="rcwimo-box-11 rca-wizard-modal-e6" style={{ '--rca-wizard-modal-width': `${progress}%` } as CSSProperties} />
        </div>
      </div>

      {/* Previous steps summary */}
      {anteriores.length > 0 && (
        <div className="rcwimo-box-4">
          <div className="rcwimo-box-5">{traducir('rcawizard.respuestas_anteriores')}</div>
          {anteriores.map(s => (
            <div key={s.step} className="rcwimo-box-6">
              <span className="u-600">P{s.step} · {s.label}:</span> {s.answer}
            </div>
          ))}
        </div>
      )}

      {/* Current step */}
      <div>
        <div className="rcwimo-box-7">
          {stepDef?.label || traducir('rcawizard.paso_n', { n: currentStep })}
        </div>
        {stepDef?.prompt && (
          <div className="rcwimo-pista">
            <Lightbulb size={14} aria-hidden className="rcwimo-pista__icono" />
            <span>{stepDef.prompt}</span>
          </div>
        )}

        <Textarea label={traducir('portalsupportdesk.tu_respuesta')} id={`${idCampo}-1`} value={answer} onChange={e => setAnswer(e.target.value)} rows={4} placeholder={traducir('rcawizardmodal.describe_la_causa_o_responde_a_la')} />

        {/* AI hint */}
        {(aiHint ?? stepDef?.ai_hint) && (
          <div className="rcwimo-sugerencia">
            <div className="rcwimo-box-13"><Sparkles size={12} aria-hidden /> {traducir('rcawizard.sugerencia_ia')}</div>
            <div className="rcwimo-txt-1">{aiHint ?? stepDef?.ai_hint}</div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="rcwimo-row-2">
        <Button variant="secondary" onClick={getAiHint} loading={aiLoading} disabled={aiLoading} icon={<Sparkles size={14} />}>
          {traducir('rcawizard.sugerencia_ia')}
        </Button>
        <div className="u-row-10">
          {isLast ? (
            <Button onClick={() => completeWizard()} loading={completing} disabled={!answer.trim() || submitting} icon={<CheckCircle2 size={14} />}>
              {traducir('rcawizard.finalizar_rca')}
            </Button>
          ) : (
            <Button onClick={() => submitStep()} loading={submitting} disabled={!answer.trim()} icon={<ChevronRight size={14} />}>
              {traducir('rcawizard.siguiente')}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

interface RcaWizardModalProps {
  problem: { id: string | number; number?: string; title?: string }
  onClose: () => void
  onCompleted: (result?: SdRcaCompletado['rca']) => void
}

export default function RcaWizardModal({ problem, onClose, onCompleted }: RcaWizardModalProps) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()

  const { data: wizardState, isLoading, refetch } = useQuery<WizardState | null>({
    queryKey: ['rca-wizard', problem.id],
    queryFn: async () => {
      const response = await problemsApi.rcaWizardGet(problem.id)
      return response.data.wizard
    },
    staleTime: STALE_ALWAYS,
    retry: false,
  })

  const { mutate: startWizard, isPending: starting } = useMutation({
    mutationFn: (template: string) => problemsApi.rcaWizardStart(problem.id, { template }),
    onSuccess: () => refetch(),
    onError: () => toast.error(traducir('rcawizard.error_al_iniciar_el_wizard')),
  })

  const handleComplete = (result: SdRcaCompletado['rca']) => {
    qc.invalidateQueries({ queryKey: ['sd-problems'] })
    onCompleted?.(result)
    onClose()
  }

  // El servidor marca el cierre con `completed` (no hay `status`).
  const hasActiveWizard = !!wizardState && !wizardState.completed && wizardState.steps.length > 0

  return (
    <Modal open title={traducir('rcawizardmodal.titulo', { numero: problem.number ?? '', titulo: problem.title ?? '' })} onClose={onClose} size="lg">
      {isLoading ? (
        <div className="rcwimo-box-8"><Spinner /></div>
      ) : hasActiveWizard ? (
        <WizardStep
          problemId={problem.id}
          state={wizardState}
          onRefresh={refetch}
          onComplete={handleComplete}
        />
      ) : wizardState?.completed ? (
        <div className="rcwimo-box-9">
          <div className="rcwimo-box-10"><CheckCircle2 size={40} aria-hidden /></div>
          <div className="rcwimo-box-14">{traducir('rcawizard.rca_completado')}</div>
          <div className="u-text2-base-mb20">
            {traducir('rcawizardmodal.los_campos_del_problema_han_sido_actualizados')}
          </div>
          <div className="rcwimo-row-3">
            <Button variant="secondary" onClick={() => startWizard(wizardState.template || 'five_whys')} loading={starting}>
              {traducir('rcawizard.reiniciar_wizard')}
            </Button>
            <Button onClick={onClose}>{traducir('common.close')}</Button>
          </div>
        </div>
      ) : (
        <TemplateSelector onStart={startWizard} isPending={starting} />
      )}
    </Modal>
  )
}
