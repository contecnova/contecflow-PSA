/**
 * SmartScheduleModal — Item I27 (UI de Smart Schedule).
 *
 * Modal compartido para todos los entry points (Gantt, Tasks, Project Detail,
 * QuickCreate). Flow:
 *   1. Abre modal con ``projectId`` opcional.
 *   2. POST /ai-modules/smart-schedule con {project_id, max_tasks} → LLM
 *      devuelve [{task_id, suggested_start, suggested_due, rationale}].
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
import {
  smartScheduleApi, taskDependenciesApi, tasksApi,
} from '../services/api'
import type { FechaSugerida } from '../services/api/tipos-analitica'
import { useToast } from '../context/ToastContext'
import { AlertTriangle, Check, CheckCircle2, Lightbulb, Sparkles, X, RefreshCw } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { Button, Checkbox, IconButton, useDialogo } from './ui'
import DateInput from './ui/DateInput'
import { SCHEDULE_TASKS_LIST_SIZE } from '../constants/pagination'
import './SmartScheduleModal.css'

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

export default function SmartScheduleModal({ open, onClose, projectId, projectName }: SmartScheduleModalProps) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])  // mutable: [{task_id, suggested_start, suggested_due, rationale, _selected, _title}]
  const [unscheduledCount, setUnscheduledCount] = useState(0)
  const [maxTasks, setMaxTasks] = useState(20)
  const [error, setError] = useState<string | null>(null)
  // `tasksById` no se lee en ninguna parte: se conserva solo el setter para no
  // alterar el comportamiento existente. Estado de solo escritura, candidato a
  // retirar cuando se revise este modal.
  const [, setTasksById] = useState<Record<string, string>>({})

  // ── Suggest mutation ─────────────────────────────────────────────────────
  const { mutate: requestSuggestions, isPending: isLoading, reset: resetSuggest } = useMutation({
    mutationFn: () => smartScheduleApi.suggest({
      project_id: projectId || null,
      max_tasks: maxTasks,
    }).then(r => r.data),
    onSuccess: async (data) => {
      const arr: Suggestion[] = data.scheduled
      setUnscheduledCount(data.unscheduled_count || 0)

      // Buscar títulos de cada task para mostrar al user. Hacemos una llamada
      // ligera por proyecto si está disponible; si no, una a una.
      const title_map: Record<string, string> = {}
      try {
        if (projectId) {
          const res = await tasksApi.list({ project_id: String(projectId), page_size: SCHEDULE_TASKS_LIST_SIZE })
          const items: Array<{ id: string | number; title: string }> = res.data ?? []
          for (const t of items) title_map[String(t.id)] = t.title
        }
      } catch { /* noop, falls back below */ }
      setTasksById(title_map)

      setSuggestions(arr.map((s) => ({
        ...s,
        _selected: true,           // por defecto, todas seleccionadas
        _title: title_map[String(s.task_id)] || traducir('smartschedulemodal.tarea_n', { id: String(s.task_id).slice(0, 8) }),
      })))
      if (arr.length === 0) {
        toast.info(data.message || traducir('smartschedulemodal.nada_que_planificar'))
      }
    },
    onError: (e: ErrLike) => {
      setError(e?.response?.data?.detail || e?.message || traducir('smartschedulemodal.error_sugerencias'))
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
      const detail = e?.response?.data?.detail || e?.message || traducir('smartschedulemodal.error_aplicar')
      toast.error(detail)
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
  const dialogRef = useDialogo<HTMLDivElement>(open, onClose)

  if (!open) return null

  return (
    <div role="presentation" onClick={onClose} className="smartsch-sx1">
      <div ref={dialogRef} role="dialog" aria-modal="true" tabIndex={-1}
        onClick={e => e.stopPropagation()}
        onKeyDown={e => { if (e.key === 'Escape') onClose() }} className="smartsch-sx2">
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
          <IconButton onClick={onClose} ariaLabel={traducir('common.close')} title={traducir('common.close')}
            className="smscmo-box-2">
            <X size={18} aria-hidden />
          </IconButton>
        </div>

        {/* Controls */}
        <div className="smscmo-row-3">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="u-text3-sm">
            {traducir('smartschedulemodal.max_tareas_a_planificar')}
          </label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`}
            type="number" min={1} max={100} value={maxTasks}
            onChange={e => setMaxTasks(parseInt(e.target.value, 10) || 20)}
            disabled={isLoading || isApplying}
            className="smscmo-box-3"
          />
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
              {traducir('smartschedulemodal.generando_sugerencias_con_ia')}
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
                <div>{traducir('smartschedulemodal.tarea_razon_ia')}</div>
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
                    {s.rationale && (
                      <div className="smscmo-box-6">
                        <Lightbulb size={12} aria-hidden /> {s.rationale}
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
