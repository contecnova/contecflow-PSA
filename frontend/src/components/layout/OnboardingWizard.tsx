// @ts-nocheck
/**
 * OnboardingWizard — Interactive step-by-step setup guide for new admins
 * Features:
 *   - Auto-detection: verifies completion by querying backend data
 *   - Per-step rich content with checklist tips
 *   - Live progress + step-level completion badges
 *   - Navigate-and-verify: clicking the CTA navigates then auto-marks step done
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, ChevronRight, ChevronLeft, CheckCircle, ExternalLink, RefreshCw } from 'lucide-react'
import { projectsApi, usersApi, slaSchedulesApi, sprintsApi, imputationsApi, onboardingApi } from '../../services/api'

// ── Per-step rich metadata ────────────────────────────────────────────────────
interface StepMeta {
  action_label: string
  path: string
  tips: string[]
  verify: () => Promise<boolean>
}

const STEP_META: Record<string, StepMeta> = {
  create_project: {
    action_label: 'Ir a Proyectos',
    path: '/projects',
    tips: [
      'Elige un código único como "PRJ-001" o las siglas del cliente.',
      'Selecciona el tipo de facturación: tiempo y materiales, precio fijo, o retainer.',
      'Asigna un PM — puede ser tú mismo para empezar.',
    ],
    verify: async () => {
      const r = await projectsApi.list({ page_size: 1 })
      const data = r.data
      if (Array.isArray(data)) return data.length > 0
      const total = data?.meta?.total ?? data?.total ?? (Array.isArray(data?.items) ? data.items.length : 0)
      return (total || 0) > 0
    },
  },
  invite_team: {
    action_label: 'Gestionar usuarios',
    path: '/settings',
    tips: [
      'Ve a Configuración → Usuarios → Nuevo usuario.',
      'Los roles disponibles son: Admin, PM, Team Lead, HR, Employee.',
      'Los empleados sólo ven sus propias tareas e imputaciones.',
    ],
    verify: async () => {
      const r = await usersApi.list({ page_size: 5 })
      const data = r.data
      const count = Array.isArray(data) ? data.length : (data?.total || 0)
      return count > 1  // más de 1 usuario = equipo configurado
    },
  },
  configure_sla: {
    action_label: 'Configurar SLA',
    path: '/sla-calendars',
    tips: [
      'Define el horario laboral (p. ej. lunes–viernes 9:00–18:00).',
      'Añade los festivos oficiales para calcular correctamente los SLA.',
      'Puedes tener múltiples calendarios para equipos en distintas zonas horarias.',
    ],
    verify: async () => {
      try {
        const r = await slaSchedulesApi.list({ page_size: 1 })
        const data = r.data
        return Array.isArray(data) ? data.length > 0 : (data?.items?.length || 0) > 0
      } catch { return false }
    },
  },
  create_sprint: {
    action_label: 'Crear sprint',
    path: '/sprints',
    tips: [
      'Duración recomendada: 2 semanas (puedes usar 1 o 4).',
      'Añade al menos 3 tareas con estimación de horas.',
      'Usa el planning de IA para auto-distribuir la carga del equipo.',
    ],
    verify: async () => {
      try {
        const r = await sprintsApi.list(undefined, { page_size: 1 })
        const data = r.data
        const items = data?.items ?? (Array.isArray(data) ? data : [])
        return Array.isArray(items) ? items.length > 0 : (data?.meta?.total || data?.total || 0) > 0
      } catch { return false }
    },
  },
  first_timesheet: {
    action_label: 'Imputar horas',
    path: '/imputar',
    tips: [
      'Selecciona el proyecto y la tarea en la que trabajaste.',
      'Introduce las horas (puedes usar decimales: 1.5 = 1h 30min).',
      'Activa el Timer para registrar automáticamente la duración real.',
    ],
    verify: async () => {
      try {
        const r = await imputationsApi.list({ page_size: 1 })
        const data = r.data
        if (Array.isArray(data)) return data.length > 0
        const total = data?.meta?.total ?? data?.total ?? (Array.isArray(data?.items) ? data.items.length : 0)
        return (total || 0) > 0
      } catch { return false }
    },
  },
}

// TODO type: onboarding payload — needs shared type from onboardingApi
interface OnboardingStep {
  id: string
  title: string
  description: string
  icon: string
}

interface OnboardingState {
  steps?: OnboardingStep[]
  completed_steps?: string[]
  progress_pct?: number
  is_complete?: boolean
  is_dismissed?: boolean
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function OnboardingWizard() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [activeStep, setActiveStep] = useState<number>(0)
  const [verifying, setVerifying]   = useState<boolean>(false)

  const { data: state, refetch } = useQuery<OnboardingState>({
    queryKey: ['onboarding'],
    queryFn: () => onboardingApi.get().then(r => r.data),
    staleTime: 5000,
  })

  const { mutate: completeStep } = useMutation({
    mutationFn: (step_id: string) => onboardingApi.completeStep({ step_id }),
    onSuccess: () => qc.invalidateQueries(['onboarding']),
  })

  const { mutate: dismiss } = useMutation({
    mutationFn: () => onboardingApi.dismiss(),
    onSuccess: () => qc.invalidateQueries(['onboarding']),
  })

  // Auto-verify all steps on mount and after each navigation
  useEffect(() => {
    if (!state?.steps) return
    const verify = async () => {
      for (const step of state.steps) {
        if (state.completed_steps?.includes(step.id)) continue
        const meta = STEP_META[step.id]
        if (!meta?.verify) continue
        try {
          const done = await meta.verify()
          if (done) completeStep(step.id)
        } catch { /* ignore */ }
      }
    }
    verify()
  }, [state?.steps, state?.completed_steps, completeStep])

  if (!state || state.is_complete || state.is_dismissed) return null

  const steps     = state.steps || []
  const completed = state.completed_steps || []
  const progress  = state.progress_pct || 0
  const current   = steps[activeStep] || steps[0]
  if (!current) return null

  const isCompleted = completed.includes(current?.id)
  const meta        = STEP_META[current?.id] || {}

  const handleAction = async () => {
    if (!isCompleted) completeStep(current.id)
    if (meta.path) {
      navigate(meta.path)
      // after navigating, re-verify after 2 seconds
      setTimeout(async () => {
        setVerifying(true)
        try {
          if (meta.verify) {
            const done = await meta.verify()
            if (done) { completeStep(current.id); refetch() }
          }
        } finally { setVerifying(false) }
      }, 2000)
    }
  }

  const handleVerify = async () => {
    setVerifying(true)
    try {
      if (meta.verify) {
        const done = await meta.verify()
        if (done) { completeStep(current.id); refetch() }
      }
    } finally { setVerifying(false) }
  }

  return (
    <div role="presentation" style={{
      position: 'fixed', inset: 0, zIndex: 2000,
      background: 'rgba(0,0,0,0.6)', display: 'flex',
      alignItems: 'center', justifyContent: 'center',
    }} onMouseDown={e => e.target === e.currentTarget && dismiss()}>
      <div style={{
        background: 'var(--surface-1)', border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 18, width: 560, maxWidth: '96vw',
        boxShadow: '0 32px 80px rgba(0,0,0,0.65)',
        overflow: 'hidden', maxHeight: '90vh', display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{ padding: '20px 24px 0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <div>
            <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--accent)', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 3 }}>
              Configuración inicial
            </div>
            <div style={{ fontSize: "var(--text-lg)", fontWeight: 800, color: 'var(--text-1)', letterSpacing: '-0.01em' }}>
              Bienvenido a Contecflow 👋
            </div>
          </div>
          <button onClick={() => dismiss()} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', padding: 6, borderRadius: 6 }} aria-label="Cerrar">
            <X size={15} />
          </button>
        </div>

        {/* Progress bar */}
        <div style={{ padding: '14px 24px 0', flexShrink: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 6 }}>
            <span>{completed.length} de {steps.length} completados</span>
            <span style={{ fontWeight: 700, color: progress >= 100 ? 'var(--success)' : 'var(--text-2)' }}>{progress}%</span>
          </div>
          <div style={{ height: 5, background: 'var(--surface-3)', borderRadius: 4, overflow: 'hidden' }}>
            <div style={{ height: '100%', background: progress >= 100 ? 'var(--success)' : 'var(--accent)', width: `${progress}%`, transition: 'width .5s cubic-bezier(0.4,0,0.2,1)', borderRadius: 4 }} />
          </div>
        </div>

        {/* Step tabs */}
        <div style={{ display: 'flex', gap: 4, padding: '16px 24px 0', overflowX: 'auto', flexShrink: 0 }}>
          {steps.map((step, i) => {
            const done = completed.includes(step.id)
            return (
              <button key={step.id} onClick={() => setActiveStep(i)}
                style={{
                  flex: 1, minWidth: 80, padding: '8px 6px', borderRadius: 10, border: 'none',
                  background: i === activeStep
                    ? 'var(--accent-muted)'
                    : done ? 'rgba(0,229,160,.08)' : 'var(--surface-3)',
                  color: i === activeStep ? 'var(--accent)' : done ? 'var(--success)' : 'var(--text-3)',
                  cursor: 'pointer', fontSize: "var(--text-xs)", fontWeight: 700, fontFamily: 'inherit',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                  outline: i === activeStep ? '2px solid var(--accent)' : 'none',
                  outlineOffset: -1, transition: 'all .15s',
                }}>
                <span style={{ fontSize: "var(--text-xl)", lineHeight: 1 }}>{done ? '✓' : step.icon}</span>
                <span style={{ fontSize: "var(--text-3xs-h)", whiteSpace: 'nowrap' }}>{step.title.split(' ').slice(0, 3).join(' ')}</span>
              </button>
            )
          })}
        </div>

        {/* Step content */}
        <div style={{ padding: '20px 24px', overflowY: 'auto', flex: 1 }}>
          <div style={{
            background: 'var(--surface-2)',
            border: `1px solid ${isCompleted ? 'rgba(0,229,160,.35)' : 'rgba(255,255,255,.07)'}`,
            borderRadius: 14, padding: '20px 22px', marginBottom: 16,
            transition: 'border-color .3s',
          }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginBottom: 16 }}>
              <div style={{ fontSize: "var(--text-4xl)", lineHeight: 1, flexShrink: 0, marginTop: 2 }}>{current.icon}</div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <div style={{ fontSize: "var(--text-md-em)", fontWeight: 800, color: 'var(--text-1)', letterSpacing: '-0.01em' }}>{current.title}</div>
                  {isCompleted && <CheckCircle size={16} style={{ color: 'var(--success)', flexShrink: 0 }} />}
                </div>
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', lineHeight: 1.65 }}>{current.description}</div>
              </div>
            </div>

            {/* Checklist tips */}
            {meta.tips && (
              <div style={{ borderTop: '1px solid rgba(255,255,255,.06)', paddingTop: 14 }}>
                <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 8 }}>Cómo hacerlo</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {meta.tips.map((tip, idx) => (
                    <div key={idx} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                      <div style={{ width: 18, height: 18, borderRadius: '50%', background: 'var(--surface-4)', border: '1px solid var(--surface-5)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-3xs)", fontWeight: 700, color: 'var(--accent)', flexShrink: 0, marginTop: 1 }}>{idx + 1}</div>
                      <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.6 }}>{tip}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* CTAs */}
            <div style={{ display: 'flex', gap: 8, marginTop: 18, flexWrap: 'wrap' }}>
              {meta.action_label && (
                <button onClick={handleAction} style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  background: isCompleted ? 'rgba(0,229,160,.1)' : 'var(--accent-muted)',
                  border: `1px solid ${isCompleted ? 'rgba(0,229,160,.35)' : 'rgba(79,142,247,.4)'}`,
                  borderRadius: 9, padding: '9px 18px', fontSize: "var(--text-base)", fontWeight: 700,
                  color: isCompleted ? 'var(--success)' : 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit', transition: 'all .15s',
                }}>
                  <ExternalLink size={13} />
                  {meta.action_label}
                </button>
              )}
              {!isCompleted && meta.verify && (
                <button onClick={handleVerify} disabled={verifying} style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  background: 'var(--surface-3)', border: '1px solid var(--surface-5)',
                  borderRadius: 9, padding: '9px 14px', fontSize: "var(--text-sm)", fontWeight: 600,
                  color: 'var(--text-2)', cursor: verifying ? 'wait' : 'pointer', fontFamily: 'inherit',
                }}>
                  <RefreshCw size={12} style={{ animation: verifying ? 'spin 1s linear infinite' : 'none' }} />
                  {verifying ? 'Verificando…' : 'Ya lo hice ✓'}
                </button>
              )}
            </div>
          </div>

          {/* Navigation */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <button onClick={() => setActiveStep(i => Math.max(0, i - 1))} disabled={activeStep === 0}
              style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: 'none', color: activeStep === 0 ? 'var(--text-4)' : 'var(--text-2)', cursor: activeStep === 0 ? 'default' : 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
              <ChevronLeft size={14} /> Anterior
            </button>
            <button onClick={() => dismiss()}
              style={{ background: 'none', border: 'none', color: 'var(--text-4)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
              Saltar configuración
            </button>
            {activeStep < steps.length - 1 ? (
              <button onClick={() => setActiveStep(i => Math.min(steps.length - 1, i + 1))}
                style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'var(--accent-muted)', border: '1px solid rgba(79,142,247,.4)', borderRadius: 9, padding: '7px 16px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 700, fontFamily: 'inherit' }}>
                Siguiente <ChevronRight size={14} />
              </button>
            ) : (
              <button onClick={() => dismiss()}
                style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(0,229,160,.1)', border: '1px solid rgba(0,229,160,.35)', borderRadius: 9, padding: '7px 16px', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 700, fontFamily: 'inherit' }}>
                <CheckCircle size={13} /> Finalizar
              </button>
            )}
          </div>
        </div>
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}

