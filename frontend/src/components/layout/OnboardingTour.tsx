/**
 * OnboardingTour — Tours interactivos por módulo
 * Sistema propio sin dependencias externas.
 * Muestra tooltips contextuales con resaltado del elemento objetivo.
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'

// ── Definición de tours por ruta ──────────────────────────────────────────────
interface TourStep {
  title: string
  text: string
  target: string | null
  position: 'center' | 'top' | 'bottom' | 'left' | 'right'
}

interface HighlightRect {
  top: number
  left: number
  width: number
  height: number
}

interface TooltipPos {
  top: string
  left: string
  transform: string
  position?: 'fixed'
}

const TOURS: Record<string, TourStep[]> = {
  '/projects': [
    { title: '⬡ Proyectos', text: 'Aquí gestionas todos tus proyectos. Puedes crear proyectos desde cero o instanciar una plantilla predefinida.', target: null, position: 'center' },
    { title: '+ Nuevo proyecto', text: 'Crea un nuevo proyecto con nombre, tipo, fechas y presupuesto. Asigna un PM y vincula al cliente.', target: '[data-tour="btn-new-project"]', position: 'bottom' },
    { title: '📋 Plantillas', text: 'Usa plantillas predefinidas para crear proyectos con fases, tareas y riesgos ya configurados. Ahorra horas de setup.', target: '[data-tour="btn-templates"]', position: 'bottom' },
  ],
  '/clients': [
    { title: '🏢 Gestión de Clientes', text: 'Los clientes son el hub central del sistema. Desde aquí accedes a proyectos, contratos, facturas, tickets y el portal del cliente.', target: null, position: 'center' },
    { title: '+ Nuevo cliente', text: 'Crea un cliente con sus datos fiscales, contacto y sector. Después podrás vincularle proyectos, contratos y licencias.', target: '[data-tour="btn-new-client"]', position: 'bottom' },
    { title: '📅 Timeline del cliente', text: 'La pestaña Timeline muestra un Gantt con todos los proyectos del cliente en los próximos 12 meses.', target: null, position: 'center' },
    { title: '🌐 Portal del cliente', text: 'La pestaña Portal permite crear accesos para que el cliente vea el estado del proyecto, apruebe entregables y abra tickets.', target: null, position: 'center' },
  ],
  '/service-desk': [
    { title: '🎫 Service Desk', text: 'Gestiona tickets de soporte internos y del portal de clientes. Organiza por colas, SLAs y agentes.', target: null, position: 'center' },
    { title: 'SLA y prioridades', text: 'Cada ticket tiene una prioridad (crítico, alto, medio, bajo) que determina el tiempo de respuesta según la política SLA.', target: null, position: 'center' },
  ],
  '/reports': [
    { title: '📊 Reportes y Analytics', text: 'Genera informes de más de 20 métricas: horas, margen, tickets, velocidad de sprint, pipeline y más.', target: null, position: 'center' },
    { title: '📅 Informes programados', text: 'Programa el envío automático de informes por email con adjunto PDF. Frecuencia diaria, semanal o mensual.', target: null, position: 'center' },
  ],
}

const STORAGE_KEY = 'contecflow-tour-completed'

function getCompleted(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') }
  catch { return {} }
}

function markCompleted(route: string) {
  const c = getCompleted()
  c[route] = true
  localStorage.setItem(STORAGE_KEY, JSON.stringify(c))
}

interface OnboardingTourProps {
  route: string
}

// ── Componente principal ───────────────────────────────────────────────────────
export default function OnboardingTour({ route }: OnboardingTourProps) {
  const [step, setStep]     = useState<number>(0)
  const [active, setActive] = useState<boolean>(false)
  const [pos, setPos]       = useState<TooltipPos>({ top: '50%', left: '50%', transform: 'translate(-50%,-50%)' })
  const [highlight, setHighlight] = useState<HighlightRect | null>(null)
  const tourRef = useRef<HTMLDivElement | null>(null)

  const steps = useMemo(() => TOURS[route] || [], [route])

  // Activar automáticamente si la ruta no se completó
  useEffect(() => {
    if (!steps.length) return
    const completed = getCompleted()
    if (!completed[route]) {
      const timer = setTimeout(() => setActive(true), 800)
      return () => clearTimeout(timer)
    }
  }, [steps.length, route])

  // Calcular posición del tooltip en cada step
  useEffect(() => {
    if (!active || !steps[step]) return
    const target = steps[step].target
    if (!target) {
      setPos({ top: '50%', left: '50%', transform: 'translate(-50%,-50%)', position: 'fixed' })
      setHighlight(null)
      return
    }
    const el = document.querySelector(target)
    if (!el) {
      setPos({ top: '50%', left: '50%', transform: 'translate(-50%,-50%)', position: 'fixed' })
      setHighlight(null)
      return
    }
    const rect = el.getBoundingClientRect()
    setHighlight({ top: rect.top, left: rect.left, width: rect.width, height: rect.height })

    const tooltipW = 320
    const tooltipH = 180
    const spaceBelow = window.innerHeight - rect.bottom
    const spaceAbove = rect.top

    let top: number
    let left: number
    if (spaceBelow > tooltipH + 20 || spaceBelow > spaceAbove) {
      top  = rect.bottom + 12
    } else {
      top  = rect.top - tooltipH - 12
    }
    left = Math.max(12, Math.min(rect.left, window.innerWidth - tooltipW - 12))
    setPos({ top: `${top}px`, left: `${left}px`, transform: 'none', position: 'fixed' })
  }, [active, step, steps])

  const next = useCallback(() => {
    if (step < steps.length - 1) {
      setStep(s => s + 1)
    } else {
      markCompleted(route)
      setActive(false)
      setStep(0)
      setHighlight(null)
    }
  }, [step, steps.length, route])

  const skip = useCallback(() => {
    markCompleted(route)
    setActive(false)
    setStep(0)
    setHighlight(null)
  }, [route])

  if (!active || !steps.length) return null

  const current = steps[step]

  return (
    <>
      {/* Overlay semitransparente */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 'var(--z-tour)',
        background: 'rgba(0,0,0,0.55)', pointerEvents: 'none',
      }} />

      {/* Highlight del elemento objetivo */}
      {highlight && (
        <div style={{
          position: 'fixed', zIndex: 'var(--z-tour-spotlight)', pointerEvents: 'none',
          top:    highlight.top    - 6,
          left:   highlight.left   - 6,
          width:  highlight.width  + 12,
          height: highlight.height + 12,
          borderRadius: 10,
          boxShadow: '0 0 0 4px var(--accent), 0 0 0 9999px rgba(0,0,0,0.55)',
          border: '2px solid var(--accent)',
        }} />
      )}

      {/* Tooltip */}
      <div ref={tourRef} style={{
        ...pos, zIndex: 'var(--z-tour-tooltip)', position: 'fixed',
        width: 320, background: 'var(--surface-1)',
        border: '1px solid var(--accent-border-strong)', borderRadius: 14,
        boxShadow: '0 16px 48px rgba(0,0,0,0.8)',
        padding: '20px 22px',
        animation: 'tour-in 0.2s ease',
      }}>
        {/* Progreso */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 14 }}>
          {steps.map((_, i) => (
            <div key={i} style={{
              flex: 1, height: 3, borderRadius: 2,
              background: i <= step ? 'var(--accent)' : 'var(--surface-4)',
              transition: 'background 0.2s',
            }} />
          ))}
        </div>

        <div style={{ fontSize: "var(--text-md-em)", fontWeight: 800, marginBottom: 8, color: 'var(--text-1)' }}>
          {current.title}
        </div>
        <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', lineHeight: 1.6, marginBottom: 18 }}>
          {current.text}
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <button onClick={skip} style={{
            background: 'none', border: 'none', color: 'var(--text-2)',
            cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit',
          }}>
            Saltar tour
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            {step > 0 && (
              <button onClick={() => setStep(s => s - 1)} style={{
                background: 'transparent', border: '1px solid var(--surface-4)',
                borderRadius: 8, padding: '6px 14px', color: 'var(--text-2)',
                cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit',
              }}>‹ Atrás</button>
            )}
            <button onClick={next} style={{
              background: step === steps.length - 1
                ? 'linear-gradient(135deg, var(--success), var(--success))'
                : 'linear-gradient(135deg, var(--accent), var(--accent-dim))',
              border: 'none', borderRadius: 8, padding: '7px 18px',
              color: 'var(--surface-0)', cursor: 'pointer', fontSize: "var(--text-base)",
              fontWeight: 700, fontFamily: 'inherit',
            }}>
              {step === steps.length - 1 ? '✓ Entendido' : 'Siguiente ›'}
            </button>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes tour-in {
          from { opacity: 0; transform: ${pos.transform === 'none' ? 'translateY(8px)' : `${pos.transform} translateY(8px)`}; }
          to   { opacity: 1; transform: ${pos.transform === 'none' ? 'translateY(0)' : pos.transform}; }
        }
      `}</style>
    </>
  )
}

// ── Hook para reiniciar un tour ───────────────────────────────────────────────
export function useRestartTour() {
  return (route: string) => {
    const c = getCompleted()
    delete c[route]
    localStorage.setItem(STORAGE_KEY, JSON.stringify(c))
    window.location.reload()
  }
}

// ── Botón de ayuda flotante ───────────────────────────────────────────────────
export function TourHelpButton({ route }: { route: string }) {
  const restart = useRestartTour()
  if (!TOURS[route]) return null
  return (
    <button
      onClick={() => restart(route)}
      title="Ver tour de este módulo"
      style={{
        position: 'fixed', bottom: 80, right: 24,
        width: 38, height: 38, borderRadius: '50%',
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
        color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-lg)",
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 9990, boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
        transition: 'all 0.15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--accent)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.color = 'var(--text-2)' }}
    >?</button>
  )
}
