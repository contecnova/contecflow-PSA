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
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { problemsApi } from '../../services/api'
import type { SdAsistenteRca, SdRcaCompletado } from '../../services/api/tipos-sd'
import { Button, Spinner, Modal } from '../ui'
import { useToast } from '../../context/ToastContext'
import { COLOR, alpha } from '../../constants/theme'
import { useAppLang } from '../../i18n/AppLangContext'
import { STALE_ALWAYS } from '../../constants/timings'
import './RcaWizardModal.css'

type WizardState = SdAsistenteRca


const TEMPLATES = [
  { value: 'five_whys',     label: '5 Porqués',       desc: 'Iteración de causas encadenadas' },
  { value: 'fishbone',      label: 'Diagrama Ishikawa', desc: 'Causas por categoría (6M)' },
  { value: 'itil_standard', label: 'ITIL estándar',    desc: 'Flujo ITIL Problem Management' },
]

function TemplateSelector({ onStart, isPending }: { onStart: (template: string) => void; isPending: boolean }) {
  const { t: traducir } = useAppLang()
  const [tpl, setTpl] = useState<string>('five_whys')
  return (
    <div className="u-stack-16">
      <div className="u-text2-base">
        {traducir('rcawizardmodal.selecciona_la_metodologia_de_analisis_de_causa')}
      </div>
      <div className="u-stack-10">
        {TEMPLATES.map(t => (
          <label className="rcwimo-row-4 rcawizar-sx1" key={t.value} style={{ background: tpl === t.value ? 'var(--accent-muted)' : 'var(--surface-3)', border: `1px solid ${tpl === t.value ? 'var(--accent)' : 'var(--surface-4)'}` }}>
            <input type="radio" name="tpl" value={t.value} aria-label={t.label} checked={tpl === t.value} onChange={() => setTpl(t.value)} className="rcwimo-box-1" />
            <div>
              <div className="rcwimo-txt-2" style={{ color: tpl === t.value ? 'var(--accent)' : 'var(--text-1)' }}>{t.label}</div>
              <div className="rcwimo-box-2">{t.desc}</div>
            </div>
          </label>
        ))}
      </div>
      <div className="u-row-end">
        <Button onClick={() => onStart(tpl)} loading={isPending}>
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
      setAiHint(res.data.hint || 'Sin sugerencia disponible')
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
          <div className="rcwimo-box-11" style={{ width: `${progress}%` }} />
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
          {stepDef?.label || `Paso ${currentStep}`}
        </div>
        {stepDef?.prompt && (
          <div className="rcwimo-box-12 rcawizar-sx2" style={{ background: alpha(COLOR.info ?? 'var(--info)', '10'), border: `1px solid ${alpha(COLOR.info ?? 'var(--info)', '25')}` }}>
            💡 {stepDef.prompt}
          </div>
        )}

        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="rcwimo-ls">{traducir('portalsupportdesk.tu_respuesta')}</label>
        <textarea id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`}
          value={answer}
          onChange={e => setAnswer(e.target.value)}
          rows={4}
          className="rcwimo-is"
          placeholder={traducir('rcawizardmodal.describe_la_causa_o_responde_a_la')}
        />

        {/* AI hint */}
        {(aiHint ?? stepDef?.ai_hint) && (
          <div className="rcwimo-sp-1 rcawizar-sx3" style={{ background: alpha(COLOR.success, '10'), border: `1px solid ${alpha(COLOR.success, '25')}` }}>
            <div className="rcwimo-box-13" style={{ color: COLOR.success }}>{traducir('rcawizard.sugerencia_ia')}</div>
            <div className="rcwimo-txt-1">{aiHint ?? stepDef?.ai_hint}</div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="rcwimo-row-2">
        <Button variant="secondary" onClick={getAiHint} loading={aiLoading} disabled={aiLoading}>
          {traducir('rcawizard.sugerencia_ia')}
        </Button>
        <div className="u-row-10">
          {isLast ? (
            <Button onClick={() => completeWizard()} loading={completing} disabled={!answer.trim() || submitting}>
              {traducir('rcawizard.finalizar_rca')}
            </Button>
          ) : (
            <Button onClick={() => submitStep()} loading={submitting} disabled={!answer.trim()}>
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
    <Modal open title={`🔍 Wizard RCA — ${problem.number}: ${problem.title}`} onClose={onClose} size="lg">
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
          <div className="rcwimo-box-10">✅</div>
          <div className="rcwimo-box-14" style={{ color: COLOR.success }}>{traducir('rcawizard.rca_completado')}</div>
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
