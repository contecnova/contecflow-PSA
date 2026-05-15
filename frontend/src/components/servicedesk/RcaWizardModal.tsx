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
import { Button, Spinner, Modal } from '../ui'
import { useToast } from '../../context/ToastContext'
import { COLOR } from '../../constants/theme'

// TODO type: problemsApi RCA wizard payloads — needs shared types
interface WizardStepDef {
  prompt?: string
  hint?: string
  answer?: string
  [k: string]: unknown
}

interface WizardState {
  steps?: WizardStepDef[]
  current_step?: number
  template?: string
  [k: string]: unknown
}

const IS: React.CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const LS: React.CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

const TEMPLATES = [
  { value: 'five_whys',     label: '5 Porqués',       desc: 'Iteración de causas encadenadas' },
  { value: 'fishbone',      label: 'Diagrama Ishikawa', desc: 'Causas por categoría (6M)' },
  { value: 'itil_standard', label: 'ITIL estándar',    desc: 'Flujo ITIL Problem Management' },
]

function TemplateSelector({ onStart, isPending }: { onStart: (template: string) => void; isPending: boolean }) {
  const [tpl, setTpl] = useState<string>('five_whys')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>
        Selecciona la metodología de análisis de causa raíz:
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {TEMPLATES.map(t => (
          <label key={t.value} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, background: tpl === t.value ? 'var(--accent-muted)' : 'var(--surface-3)', border: `1px solid ${tpl === t.value ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 10, padding: '12px 16px', cursor: 'pointer' }}>
            <input type="radio" name="tpl" value={t.value} checked={tpl === t.value} onChange={() => setTpl(t.value)} style={{ marginTop: 3, accentColor: 'var(--accent)', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: tpl === t.value ? 'var(--accent)' : 'var(--text-1)' }}>{t.label}</div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginTop: 2 }}>{t.desc}</div>
            </div>
          </label>
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button onClick={() => onStart(tpl)} loading={isPending}>
          Iniciar wizard ▶
        </Button>
      </div>
    </div>
  )
}

interface WizardStepProps {
  problemId: string | number
  state: WizardState | null | undefined
  onRefresh: () => void
  onComplete: (result: unknown) => void
}

function WizardStep({ problemId, state, onRefresh, onComplete }: WizardStepProps) {
  const toast = useToast()
  const steps: WizardStepDef[] = state?.steps ?? []
  const currentStep = state?.current_step ?? 0
  const totalSteps = steps.length
  const isLast = currentStep >= totalSteps - 1
  const stepDef: WizardStepDef = steps[currentStep] ?? {}

  const [answer, setAnswer] = useState<string>('')
  const [aiHint, setAiHint] = useState<string | null>(null)
  const [aiLoading, setAiLoading] = useState<boolean>(false)

  const { mutate: submitStep, isPending: submitting } = useMutation({
    mutationFn: () => problemsApi.rcaWizardStep(problemId, { step: currentStep, answer }),
    onSuccess: () => { setAnswer(''); setAiHint(null); onRefresh() },
    onError: () => toast.error('Error al guardar respuesta'),
  })

  const { mutate: completeWizard, isPending: completing } = useMutation({
    mutationFn: () => problemsApi.rcaWizardComplete(problemId),
    onSuccess: (res) => { toast.success('RCA completado y aplicado al problema'); onComplete(res.data) },
    onError: () => toast.error('Error al completar el wizard'),
  })

  const getAiHint = async () => {
    setAiLoading(true)
    try {
      const res = await problemsApi.rcaWizardAiAssist(problemId, { step: currentStep })
      setAiHint(res.data?.suggestion ?? res.data?.hint ?? 'Sin sugerencia disponible')
    } catch {
      toast.error('Error al obtener sugerencia IA')
    } finally {
      setAiLoading(false)
    }
  }

  // Progress bar
  const progress = totalSteps > 0 ? Math.round(((currentStep) / totalSteps) * 100) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Progress */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 6 }}>
          <span>Paso {currentStep + 1} de {totalSteps}</span>
          <span>{progress}% completado</span>
        </div>
        <div style={{ height: 4, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${progress}%`, background: 'var(--accent)', borderRadius: 4, transition: 'width 0.3s ease' }} />
        </div>
      </div>

      {/* Previous steps summary */}
      {state?.answers && Object.entries(state.answers).length > 0 && (
        <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '12px 14px', maxHeight: 120, overflowY: 'auto' }}>
          <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 8 }}>Respuestas anteriores</div>
          {Object.entries(state.answers).map(([idx, ans]) => (
            <div key={idx} style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 4 }}>
              <span style={{ fontWeight: 600 }}>P{Number(idx) + 1}:</span> {ans}
            </div>
          ))}
        </div>
      )}

      {/* Current step */}
      <div>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 8 }}>
          {stepDef.prompt || stepDef.title || `Paso ${currentStep + 1}`}
        </div>
        {stepDef.hint && (
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', background: `${COLOR.info ?? 'var(--info)'}10`, border: `1px solid ${COLOR.info ?? 'var(--info)'}25`, borderRadius: 6, padding: '8px 12px', marginBottom: 10 }}>
            💡 {stepDef.hint}
          </div>
        )}

        <label style={LS}>Tu respuesta</label>
        <textarea
          value={answer}
          onChange={e => setAnswer(e.target.value)}
          rows={4}
          style={{ ...IS, resize: 'vertical' }}
          placeholder="Describe la causa o responde a la pregunta…"
        />

        {/* AI hint */}
        {aiHint && (
          <div style={{ marginTop: 10, background: `${COLOR.success}10`, border: `1px solid ${COLOR.success}25`, borderRadius: 8, padding: '10px 14px' }}>
            <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: COLOR.success, textTransform: 'uppercase', marginBottom: 4 }}>🤖 Sugerencia IA</div>
            <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)' }}>{aiHint}</div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 10, justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <Button variant="secondary" onClick={getAiHint} loading={aiLoading} disabled={aiLoading}>
          🤖 Sugerencia IA
        </Button>
        <div style={{ display: 'flex', gap: 10 }}>
          {isLast ? (
            <Button onClick={() => completeWizard()} loading={completing} disabled={!answer.trim() || submitting}>
              ✅ Finalizar RCA
            </Button>
          ) : (
            <Button onClick={() => submitStep()} loading={submitting} disabled={!answer.trim()}>
              Siguiente →
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
  onCompleted: (result?: unknown) => void
}

export default function RcaWizardModal({ problem, onClose, onCompleted }: RcaWizardModalProps) {
  const qc = useQueryClient()
  const toast = useToast()

  const { data: wizardState, isLoading, refetch } = useQuery({
    queryKey: ['rca-wizard', problem.id],
    queryFn: () => problemsApi.rcaWizardGet(problem.id).then(r => r.data).catch(() => ({ wizard: null })),
    staleTime: 0,
    retry: false,
  })

  const { mutate: startWizard, isPending: starting } = useMutation({
    mutationFn: (template) => problemsApi.rcaWizardStart(problem.id, { template }),
    onSuccess: () => refetch(),
    onError: () => toast.error('Error al iniciar el wizard'),
  })

  const handleComplete = (result) => {
    qc.invalidateQueries({ queryKey: ['sd-problems'] })
    onCompleted?.(result)
    onClose()
  }

  const hasActiveWizard = wizardState && wizardState.status !== 'completed' && wizardState.steps?.length > 0

  return (
    <Modal open title={`🔍 Wizard RCA — ${problem.number}: ${problem.title}`} onClose={onClose} size="lg">
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spinner /></div>
      ) : hasActiveWizard ? (
        <WizardStep
          problemId={problem.id}
          state={wizardState}
          onRefresh={refetch}
          onComplete={handleComplete}
        />
      ) : wizardState?.status === 'completed' ? (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <div style={{ fontSize: "var(--text-5xl)", marginBottom: 12 }}>✅</div>
          <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: COLOR.success, marginBottom: 8 }}>RCA completado</div>
          <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 20 }}>
            Los campos del problema han sido actualizados con el análisis de causa raíz.
          </div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
            <Button variant="secondary" onClick={() => startWizard(wizardState.template || 'five_whys')} loading={starting}>
              Reiniciar wizard
            </Button>
            <Button onClick={onClose}>Cerrar</Button>
          </div>
        </div>
      ) : (
        <TemplateSelector onStart={startWizard} isPending={starting} />
      )}
    </Modal>
  )
}
