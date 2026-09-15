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
 */
import { useState, useMemo, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  smartScheduleApi, taskDependenciesApi, tasksApi,
} from '../services/api'
import { useToast } from '../context/ToastContext'
import { Sparkles, X, RefreshCw } from 'lucide-react'

interface Suggestion {
  task_id: string | number
  suggested_start?: string | null
  suggested_due?: string | null
  rationale?: string | null
  _selected?: boolean
  _title?: string
  [key: string]: unknown
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
    onSuccess: async (data: { scheduled?: Suggestion[]; unscheduled_count?: number; message?: string } | undefined) => {
      const arr: Suggestion[] = Array.isArray(data?.scheduled) ? data!.scheduled! : []
      setUnscheduledCount(data?.unscheduled_count || 0)

      // Buscar títulos de cada task para mostrar al user. Hacemos una llamada
      // ligera por proyecto si está disponible; si no, una a una.
      const title_map: Record<string, string> = {}
      try {
        if (projectId) {
          const res = await tasksApi.list({ project_id: String(projectId), page_size: 300 })
          const items: Array<{ id: string | number; title: string }> = res.data ?? []
          for (const t of items) title_map[String(t.id)] = t.title
        }
      } catch { /* noop, falls back below */ }
      setTasksById(title_map)

      setSuggestions(arr.map((s) => ({
        ...s,
        _selected: true,           // por defecto, todas seleccionadas
        _title: title_map[String(s.task_id)] || `Tarea #${String(s.task_id).slice(0, 8)}`,
      })))
      if (arr.length === 0) {
        toast.info(data?.message || 'No hay tareas sin fecha para planificar.')
      }
    },
    onError: (e: ErrLike) => {
      setError(e?.response?.data?.detail || e?.message || 'Error al generar sugerencias')
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
          id: s.task_id,
          start_date: s.suggested_start,
          due_date: s.suggested_due,
        }))
      if (updates.length === 0) {
        return Promise.reject(new Error('No hay tareas seleccionadas'))
      }
      return taskDependenciesApi.bulkDates(updates as unknown as Record<string, unknown>).then(r => r.data)
    },
    onSuccess: (_data) => {
      const n = suggestions.filter(s => s._selected).length
      toast.success(`Aplicadas ${n} tareas. Las fechas se han guardado.`)
      qc.invalidateQueries({ queryKey: ['gantt-tasks'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['tasks-my'] })
      onClose()
    },
    onError: (e: ErrLike) => {
      const detail = e?.response?.data?.detail || e?.message || 'Error al aplicar fechas'
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

  if (!open) return null

  return (
    <div role="presentation" onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
      zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div role="dialog" aria-modal="true" tabIndex={-1}
        onClick={e => e.stopPropagation()}
        onKeyDown={e => { if (e.key === 'Escape') onClose() }}
        style={{
        width: 720, maxWidth: '95vw', maxHeight: '88vh',
        background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
        borderRadius: 12, padding: '22px 26px',
        boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 'var(--text-md)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Sparkles size={18} color="var(--accent)" /> Auto-planificar tareas sin fecha
            </h3>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', marginTop: 4 }}>
              {projectName ? <>Proyecto: <strong>{projectName}</strong></> : 'Todas las tareas sin fecha visibles'}
              {unscheduledCount > 0 && <> · {unscheduledCount} sin planificar</>}
            </div>
          </div>
          <button onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: 'var(--text-2)', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        {/* Controls */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}>
          <label style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>
            Máx. tareas a planificar:
          </label>
          <input
            type="number" min={1} max={100} value={maxTasks}
            onChange={e => setMaxTasks(parseInt(e.target.value, 10) || 20)}
            disabled={isLoading || isApplying}
            style={{
              width: 70, padding: '6px 8px',
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              borderRadius: 6, color: 'var(--text-1)', fontSize: 'var(--text-sm)',
            }}
          />
          <button
            onClick={() => requestSuggestions()}
            disabled={isLoading || isApplying}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 12px',
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              color: 'var(--text-2)', borderRadius: 6, cursor: isLoading ? 'wait' : 'pointer',
              fontSize: 'var(--text-sm)',
            }}
          >
            <RefreshCw size={13} /> Regenerar
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 200 }}>
          {error && (
            <div style={{
              background: 'rgba(239,68,68,0.12)', border: '1px solid var(--danger)',
              color: 'var(--danger)', padding: '10px 14px', borderRadius: 8,
              fontSize: 'var(--text-sm)', marginBottom: 12,
            }}>⚠ {error}</div>
          )}
          {isLoading ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>
              ⏳ Generando sugerencias con IA…
            </div>
          ) : suggestions.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>
              {error ? 'Reintenta cuando el error se resuelva.'
                    : 'No hay tareas sin fecha para planificar. Todo está al día. 🎉'}
            </div>
          ) : (
            <>
              {/* Header row */}
              <div style={{
                display: 'grid', gridTemplateColumns: '24px 1fr 120px 120px',
                gap: 10, alignItems: 'center',
                padding: '8px 4px', borderBottom: '1px solid var(--surface-4)',
                fontSize: 'var(--text-xs)', textTransform: 'uppercase',
                color: 'var(--text-3)', fontWeight: 600,
              }}>
                <input
                  type="checkbox" checked={allSelected}
                  onChange={_toggleAll}
                  title="Seleccionar/Deseleccionar todas"
                />
                <div>Tarea / Razón IA</div>
                <div>Start</div>
                <div>Due</div>
              </div>

              {suggestions.map((s, idx) => (
                <div key={s.task_id || idx} style={{
                  display: 'grid', gridTemplateColumns: '24px 1fr 120px 120px',
                  gap: 10, alignItems: 'center',
                  padding: '10px 4px', borderBottom: '1px solid var(--surface-4)',
                }}>
                  <input
                    type="checkbox" checked={!!s._selected}
                    onChange={() => _toggle(idx)}
                    disabled={isApplying}
                  />
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' }}>
                      {s._title}
                    </div>
                    {s.rationale && (
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2, fontStyle: 'italic' }}>
                        💡 {s.rationale}
                      </div>
                    )}
                  </div>
                  <input
                    type="date" value={s.suggested_start || ''}
                    onChange={e => _updateDate(idx, 'suggested_start', e.target.value)}
                    disabled={isApplying}
                    style={{
                      padding: '6px 8px', background: 'var(--surface-3)',
                      border: '1px solid var(--surface-4)', borderRadius: 6,
                      color: 'var(--text-1)', fontSize: 'var(--text-xs)',
                    }}
                  />
                  <input
                    type="date" value={s.suggested_due || ''}
                    onChange={e => _updateDate(idx, 'suggested_due', e.target.value)}
                    disabled={isApplying}
                    style={{
                      padding: '6px 8px', background: 'var(--surface-3)',
                      border: '1px solid var(--surface-4)', borderRadius: 6,
                      color: 'var(--text-1)', fontSize: 'var(--text-xs)',
                    }}
                  />
                </div>
              ))}
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          paddingTop: 14, borderTop: '1px solid var(--surface-4)', marginTop: 12,
        }}>
          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>
            {selectedCount} de {suggestions.length} seleccionadas
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={onClose} disabled={isApplying}
              style={{
                padding: '8px 16px',
                background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                color: 'var(--text-2)', borderRadius: 8, cursor: 'pointer',
                fontSize: 'var(--text-sm)',
              }}>
              Cancelar
            </button>
            <button
              onClick={() => applySelected()}
              disabled={!someSelected || isApplying || isLoading}
              style={{
                padding: '8px 18px',
                background: someSelected ? 'var(--accent)' : 'var(--surface-3)',
                color: someSelected ? '#fff' : 'var(--text-3)',
                border: 'none', borderRadius: 8,
                cursor: someSelected && !isApplying ? 'pointer' : 'not-allowed',
                fontWeight: 600, fontSize: 'var(--text-sm)',
                opacity: isApplying ? 0.6 : 1,
              }}
            >
              {isApplying ? '⏳ Aplicando…' : `✓ Aplicar ${selectedCount} seleccionadas`}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
