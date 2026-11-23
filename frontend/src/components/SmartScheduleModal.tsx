/**
 * SmartScheduleModal — Item I27 (UI de Smart Schedule).
 *
 * Modal compartido para todos los entry points (Gantt, Tasks, Project Detail,
 * QuickCreate). Flow:
 *   1. Abre modal con ``projectId`` opcional.
 *   2. POST /ai-modules/smart-schedule con {project_id, max_tasks} → motor de
 *      planificación (19-11-2026: ya no IA; horario, festivos, ausencias, carga
 *      y dependencias de cada responsable) devuelve [{task_id, title,
 *      suggested_start, suggested_due, assignee_name, motivo}].
 *   3. Muestra preview con checkbox por tarea, fechas editables, rationale.
 *   4. User selecciona las tareas a aplicar y pulsa "Aplicar seleccionadas".
 *   5. POST /tasks/bulk-dates con los updates → fechas escritas.
 *   6. Invalidate queries de tasks/gantt para refrescar.
 *
 * Pattern consistente con voice (#25) y contracts (H22): preview → confirmar.
 *
 * 16-11-2026: textos que estaban fijos en castellano (o en inglés: "Start",
 * "Due") pasan a i18n en es/en/zh; emojis (⚠🎉💡⏳✓) cambiados por iconos
 * lucide; botones del pie con Button del kit.
 */
import { useState, useMemo, useEffect, useId } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { smartScheduleApi, taskDependenciesApi } from '../services/api'
import { extractErr } from '../utils/helpers'
import type { FechaSugerida, MotivoDePlanificacion } from '../services/api/tipos-analitica'
import { useToast } from '../context/ToastContext'
import { AlertTriangle, Check, CheckCircle2, Lightbulb, Sparkles, X, RefreshCw } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { Button, Checkbox, IconButton, useDialogoEditable } from './ui'
import DateInput from './ui/DateInput'
import './SmartScheduleModal.css'
import { Input } from './ui'

/** Una sugerencia del modelo con lo que el usuario edita en el modal. */
type Suggestion = Omit<FechaSugerida, 'suggested_start' | 'suggested_due'> & {
  suggested_start?: string | null
  suggested_due?: string | null
  _selected?: boolean
  _title?: string
}

interface SmartScheduleModalProps {
  open: boolean
  onClose: () => void
  projectId?: string | number | null
  projectName?: string
}

interface ErrLike {
  response?: { data?: { detail?: string } }
  message?: string
}

type Traducir = (clave: string, params?: Record<string, string | number>) => string

/** El motivo de la propuesta, en el idioma del usuario. */
function textoDelMotivo(m: MotivoDePlanificacion | undefined, traducir: Traducir): string {
  if (!m) return ''
  if (m.codigo === 'sin_hueco') return traducir('smartschedulemodal.motivo_sin_hueco', { horas: m.horas })
  const partes = [traducir(`smartschedulemodal.motivo_horas_${m.origen_horas ?? 'estimacion'}`, { horas: m.horas })]
  partes.push(m.sin_responsable
    ? traducir('smartschedulemodal.motivo_sin_responsable', { dias: m.dias ?? 0 })
    : traducir('smartschedulemodal.motivo_persona', { persona: m.persona ?? '', dias: m.dias ?? 0 }))
  if (m.espera_predecesora) partes.push(traducir('smartschedulemodal.motivo_espera'))
  return partes.join(' · ')
}

export default function SmartScheduleModal({ open, onClose, projectId, projectName }: SmartScheduleModalProps) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])  // mutable: [{task_id, suggested_start, suggested_due, rationale, _selected, _title}]
  const [unscheduledCount, setUnscheduledCount] = useState(0)
  const [maxTasks, setMaxTasks] = useState(20)
  const [error, setError] = useState<string | null>(null)

  // ── Suggest mutation ─────────────────────────────────────────────────────
  const { mutate: requestSuggestions, isPending: isLoading, reset: resetSuggest } = useMutation({
    mutationFn: () => smartScheduleApi.suggest({
      project_id: projectId || null,
      max_tasks: maxTasks,
    }).then(r => r.data),
    onSuccess: (data) => {
      const arr: Suggestion[] = data.scheduled ?? []
      setUnscheduledCount(data.unscheduled_count || 0)
      setSuggestions(arr.map((s) => ({
        ...s,
        // Sin hueco en el horizonte no hay fechas que aplicar: llega desmarcada.
        _selected: Boolean(s.suggested_start && s.suggested_due),
        _title: s.title || traducir('smartschedulemodal.tarea_n', { id: String(s.task_id).slice(0, 8) }),
      })))
      if (arr.length === 0) toast.info(traducir('smartschedulemodal.nada_que_planificar'))
    },
    onError: (e: ErrLike) => {
      setError(extractErr(e, traducir('smartschedulemodal.error_sugerencias')))
    },
  })

  // ── Auto-run cuando se abre el modal ─────────────────────────────────────
  useEffect(() => {
    if (open) {
      setSuggestions([])
      setError(null)
      setUnscheduledCount(0)
      requestSuggestions()
    } else {
      resetSuggest()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId])

  // ── Apply mutation ────────────────────────────────────────────────────────
  const { mutate: applySelected, isPending: isApplying } = useMutation({
    mutationFn: () => {
      const updates = suggestions
        .filter(s => s._selected && s.suggested_start && s.suggested_due)
        .map(s => ({
          id: String(s.task_id),
          start_date: s.suggested_start,
          due_date: s.suggested_due,
        }))
      if (updates.length === 0) {
        return Promise.reject(new Error(traducir('smartschedulemodal.ninguna_seleccionada')))
      }
      return taskDependenciesApi.bulkDates(updates).then(r => r.data)
    },
    onSuccess: (_data) => {
      const n = suggestions.filter(s => s._selected).length
      toast.success(traducir('smartschedule.aplicadas_n_tareas_las_fechas_se_han', { n }))
      qc.invalidateQueries({ queryKey: ['gantt-tasks'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['tasks-my'] })
      onClose()
    },
    onError: (e: ErrLike) => {
      toast.error(extractErr(e, traducir('smartschedulemodal.error_aplicar')))
    },
  })

  // ── Helpers UI ───────────────────────────────────────────────────────────
  const allSelected = suggestions.length > 0 && suggestions.every(s => s._selected)
  const someSelected = suggestions.some(s => s._selected)

  function _toggleAll() {
    const newVal = !allSelected
    setSuggestions(prev => prev.map(s => ({ ...s, _selected: newVal })))
  }
  function _toggle(idx: number) {
    setSuggestions(prev => prev.map((s, i) => i === idx ? { ...s, _selected: !s._selected } : s))
  }
  function _updateDate(idx: number, field: string, value: string) {
    setSuggestions(prev => prev.map((s, i) => i === idx ? { ...s, [field]: value } : s))
  }

  const selectedCount = useMemo(() => suggestions.filter(s => s._selected).length, [suggestions])
  // Fondo, Esc y X preguntan si hay cambios sin guardar (kit, 23-11-2026).
  const { ref: dialogRef, pedirCierre } = useDialogoEditable<HTMLDivElement>(open, onClose)

  if (!open) return null

  return (
    <div role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) pedirCierre() }} className="smartsch-sx1">
      <div ref={dialogRef} role="dialog" aria-modal="true" tabIndex={-1}
        className="smartsch-sx2">
        {/* Header */}
        <div className="smscmo-row-1">
          <div>
            <h3 className="smscmo-row-2">
              <Sparkles size={18} color="var(--accent)" /> {traducir('smartschedulemodal.auto_planificar_tareas_sin_fecha')}
            </h3>
            <div className="smscmo-box-1">
              {projectName ? <>{traducir('smartschedule.proyecto')} <strong>{projectName}</strong></> : traducir('smartschedulemodal.todas_las_visibles')}
              {unscheduledCount > 0 && <> · {unscheduledCount} {traducir('smartschedulemodal.sin_planificar')}</>}
            </div>
          </div>
          <IconButton onClick={pedirCierre} ariaLabel={traducir('common.close')} title={traducir('common.close')}
            className="smscmo-box-2">
            <X size={18} aria-hidden />
          </IconButton>
        </div>

        {/* Controls */}
        <div className="smscmo-row-3">
          <Input label={traducir('smartschedulemodal.max_tareas_a_planificar')} id={`${idCampo}-1`} type="number" min={1} max={100} value={maxTasks} onChange={e => setMaxTasks(parseInt(e.target.value, 10) || 20)} disabled={isLoading || isApplying} />
          <Button size="sm" variant="secondary" icon={<RefreshCw size={13} />}
            onClick={() => requestSuggestions()}
            disabled={isLoading || isApplying}
          >
            {traducir('smartschedule.regenerar')}
          </Button>
        </div>

        {/* Body */}
        <div className="smscmo-box-4">
          {error && (
            <div className="smartsch-sx3"><AlertTriangle size={14} aria-hidden /> {error}</div>
          )}
          {isLoading ? (
            <div className="smscmo-box-5">
              {traducir('smartschedulemodal.calculando_plan')}
            </div>
          ) : suggestions.length === 0 ? (
            <div className="smscmo-box-5">
              {error ? traducir('smartschedulemodal.reintenta')
                    : <><CheckCircle2 size={16} aria-hidden /> {traducir('smartschedulemodal.todo_al_dia')}</>}
            </div>
          ) : (
            <>
              {/* Header row */}
              <div className="smscmo-grid-1">
                <Checkbox checked={allSelected}
                  aria-label={traducir('smartschedulemodal.seleccionar_deseleccionar_todas')}
                  onChange={() => _toggleAll()}
                />
                <div>{traducir('smartschedulemodal.tarea_y_motivo')}</div>
                <div>{traducir('smartschedulemodal.inicio')}</div>
                <div>{traducir('smartschedulemodal.vencimiento')}</div>
              </div>

              {suggestions.map((s, idx) => (
                <div key={s.task_id || idx} className="smscmo-grid-2">
                  <Checkbox checked={!!s._selected}
                    aria-label={s._title}
                    onChange={() => _toggle(idx)}
                    disabled={isApplying}
                  />
                  <div>
                    <div className="u-text1-sm-600">
                      {s._title}
                    </div>
                    {(s.motivo || s.rationale) && (
                      <div className="smscmo-box-6">
                        <Lightbulb size={12} aria-hidden /> {s.motivo ? textoDelMotivo(s.motivo, traducir) : s.rationale}
                      </div>
                    )}
                  </div>
                  <DateInput
                    value={s.suggested_start || ''}
                    onChange={e => _updateDate(idx, 'suggested_start', e.target.value)}
                    disabled={isApplying}
                    className="smart-schedule-modal-e3"
                  />
                  <DateInput
                    value={s.suggested_due || ''}
                    onChange={e => _updateDate(idx, 'suggested_due', e.target.value)}
                    disabled={isApplying}
                    className="smart-schedule-modal-e3"
                  />
                </div>
              ))}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="smscmo-row-4">
          <div className="u-text3-sm">
            {traducir('smartschedulemodal.n_de_total_seleccionadas', { n: selectedCount, total: suggestions.length })}
          </div>
          <div className="u-row-8">
            <Button variant="secondary" onClick={onClose} disabled={isApplying}>
              {traducir('common.cancel')}
            </Button>
            <Button icon={<Check size={14} />}
              onClick={() => applySelected()}
              disabled={!someSelected || isLoading}
              loading={isApplying}
            >
              {isApplying ? traducir('smartschedulemodal.aplicando') : traducir('smartschedulemodal.aplicar_n', { n: selectedCount })}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
