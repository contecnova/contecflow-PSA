/**
 * PerformanceReviewsPage — Evaluaciones de rendimiento 360°
 *
 * Flujo completo:
 *   1) HR/Admin crea un ciclo (Q1 2025, Annual…) → status `draft`
 *      ↳ El ciclo nace con una plantilla de preguntas por defecto (5 ratings + 3 textos)
 *      ↳ HR/Admin puede personalizar la plantilla mientras el ciclo siga en borrador
 *   2) HR/Admin activa el ciclo                  → status `active`
 *   3) HR/Admin asigna evaluaciones (quién evalúa a quién)
 *      ↳ Al elegir un tipo (manager/par/upward) la UI restringe el evaluador
 *        al pool elegible según organigrama (manager_id) y equipo/departamento.
 *      ↳ Si un tipo no aplica para esa persona se deshabilita con explicación.
 *   4) Cada evaluador rellena su evaluación según las preguntas de la plantilla
 *   5) Evaluador envía → status `submitted`
 *   6) HR/Admin cierra el ciclo                  → status `closed` (read-only)
 */
import { useState, useEffect, useMemo } from 'react'
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import { performanceApi, usersApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, Page } from '../components/ui'
import {
  Star, Plus, ChevronRight, ChevronDown, Clock, CheckCircle2,
  User, Users as UsersIcon, Crown, ArrowUp, UserPlus, Save, Send,
  Pencil, Trash2, AlertCircle, ListChecks, Target, BarChart3,
  Eye, EyeOff, Lock, X, TrendingUp, History,
  Activity, Bell, AlertTriangle, Zap, Map as MapIcon, Flag, FileDown,
} from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'

const NO_PERMISSION_TIP = 'Solo admin / RR.HH.'

// ── Estilos compartidos ────────────────────────────────────────────────────
// Se extraen aquí los patrones inline más repetidos para reducir ruido en JSX
// y unificar el look. NO cambian el comportamiento visible.
const styles = {
  flexEndRow:        { display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' },
  flexBetweenRow:    { display: 'flex', justifyContent: 'space-between', gap: 'var(--space-2)' },
  inlineIcon:        { display: 'inline-flex', alignItems: 'center', gap: 8 },
  inlineIconSm:      { display: 'inline-flex', alignItems: 'center', gap: 6 },
  warningInlineXs:   { display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--warning)', fontSize: 'var(--text-xs)' },
  mutedTextXs:       { fontSize: 'var(--text-xs)', color: 'var(--text-3)' },
  titleSmBold:       { fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' },
  titleSmBolder:     { fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-1)' },
  titleMdBold:       { fontSize: 'var(--text-md-em)', fontWeight: 700, color: 'var(--text-1)' },
  hintXs:            { fontSize: 'var(--text-xs)' },
  flex1MinW0:        { minWidth: 0, flex: 1 },
  redAsterisk:       { color: 'var(--danger)' },
  twoColGrid:        { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)' },
  rowItemTile:       {
    gap: 'var(--space-2)', padding: '8px 10px',
    background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--surface-4)',
  },
  rowItemTilePadded: {
    gap: 'var(--space-2)', padding: '10px 12px',
    background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--surface-4)',
  },
}

// Genera estilo de chip toggle activo/inactivo (botones de selección de tipo,
// pares, upward, plantilla, etc.). El tamaño se pasa explícitamente para no
// alterar la apariencia.
const chipStyle = ({ active, disabled = false, padding = '8px 12px', fontSize = 'var(--text-sm)' }) => ({
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding, borderRadius: 'var(--radius-md)',
  background: active ? 'var(--accent-muted)' : 'var(--surface-3)',
  border: `1px solid ${active ? 'var(--accent)' : 'var(--surface-4)'}`,
  color: disabled ? 'var(--text-4)' : (active ? 'var(--accent)' : 'var(--text-2)'),
  cursor: disabled ? 'not-allowed' : 'pointer',
  opacity: disabled ? 0.55 : 1,
  fontFamily: 'inherit',
  fontSize, fontWeight: 600,
})

// ── Catálogos ──────────────────────────────────────────────────────────────
const STATUS_CFG = {
  draft:  { kind: 'neutral', label: 'Borrador' },
  active: { kind: 'accent',  label: 'Activo' },
  closed: { kind: 'success', label: 'Cerrado' },
}

const REVIEW_TYPES = [
  { id: 'self',    Icon: User,      label: 'Autoevaluación', help: 'El propio empleado se evalúa' },
  { id: 'peer',    Icon: UsersIcon, label: 'Par',            help: 'Compañeros del mismo equipo o departamento' },
  { id: 'manager', Icon: Crown,     label: 'Manager',        help: 'El responsable directo según organigrama' },
  { id: 'upward',  Icon: ArrowUp,   label: 'Upward',         help: 'Reportes directos evalúan a su responsable' },
]
const TYPE_BY_ID = Object.fromEntries(REVIEW_TYPES.map(t => [t.id, t]))

const QUESTION_KINDS = [
  { id: 'rating_5',     label: 'Puntuación 1-5' },
  { id: 'rating_10',    label: 'Puntuación 1-10' },
  { id: 'scale_likert', label: 'Likert (1-5)' },
  { id: 'yes_no',       label: 'Sí / No' },
  { id: 'text_short',   label: 'Texto corto' },
  { id: 'text_long',    label: 'Texto largo' },
]
const KIND_LABEL = Object.fromEntries(QUESTION_KINDS.map(k => [k.id, k.label]))

const isRatingKind = k => k === 'rating_5' || k === 'rating_10' || k === 'scale_likert'
const ratingMax = q => q.scale_max ?? (q.kind === 'rating_10' ? 10 : 5)
const ratingMin = q => q.scale_min ?? 1

// ── ScoreBar ────────────────────────────────────────────────────────────────
function ScoreBar({ value, max = 5 }) {
  const pct = value ? (value / max) * 100 : 0
  const color = pct >= 80 ? 'var(--success)'
              : pct >= 60 ? 'var(--accent)'
              : pct >= 40 ? 'var(--warning)'
              : 'var(--danger)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: 'var(--surface-4)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, transition: 'width 0.4s var(--easing)' }} />
      </div>
      <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color, minWidth: 28, textAlign: 'right',
        fontFamily: 'var(--font-mono)' }}>{value ? Number(value).toFixed(1) : '—'}</span>
    </div>
  )
}

// ── ReviewForm: rellenar una evaluación dinámica según preguntas del ciclo ─
function ReviewForm({ review, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()

  const { data: questions = [], isLoading: loadingQs } = useQuery({
    queryKey: ['perf-cycle-questions', review.cycle_id],
    queryFn: () => performanceApi.listQuestions(review.cycle_id).then(r => r.data),
  })

  const [answers, setAnswers] = useState({})
  // Hidratamos respuestas con lo que venga del review (answers + legacy).
  // Solo re-hidratamos cuando cambia la review seleccionada (review.id):
  // depender de review.answers haría que cualquier re-render del padre con
  // una nueva referencia del objeto pisara las ediciones locales del usuario.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intencional: solo on review.id change
  useEffect(() => {
    setAnswers(review.answers || {})
  }, [review.id])

  const cleanAnswers = () => {
    const out = {}
    for (const [k, v] of Object.entries(answers)) {
      out[k] = v === '' ? null : v
    }
    return out
  }

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: () => performanceApi.updateReview(review.id, { answers: cleanAnswers() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['perf-my-reviews'] })
      qc.invalidateQueries({ queryKey: ['perf-cycle-reviews', review.cycle_id] })
      toast.success('Borrador guardado')
    },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })
  const { mutate: submit, isPending: submitting } = useMutation({
    mutationFn: async () => {
      // Encadenado: guarda primero los cambios, luego envía
      await performanceApi.updateReview(review.id, { answers: cleanAnswers() })
      return performanceApi.submitReview(review.id)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['perf-my-reviews'] })
      qc.invalidateQueries({ queryKey: ['perf-cycle-reviews', review.cycle_id] })
      toast.success('Evaluación enviada')
      onClose()
    },
    onError: e => toast.error(extractErr(e, 'Error al enviar')),
  })

  const typeCfg = TYPE_BY_ID[review.review_type] || TYPE_BY_ID.peer
  const TypeIcon = typeCfg.Icon
  const ratingQs = questions.filter(q => isRatingKind(q.kind))
  const otherQs  = questions.filter(q => !isRatingKind(q.kind))
  const filledRatings = ratingQs.filter(q => answers[q.key] != null && answers[q.key] !== '').length
  const missingRequired = questions.filter(q => q.required && (answers[q.key] == null || answers[q.key] === ''))

  return (
    <Modal open onClose={onClose}
      title={<span style={styles.inlineIcon}>
        <TypeIcon size={16} /> Evaluar a {review.reviewee_name}
      </span>}
      subtitle={`${typeCfg.label} · ${filledRatings} de ${ratingQs.length || '—'} puntuaciones rellenas`}
      width={620}>
      {loadingQs ? <Spinner /> : (
        <div className="ds-stack" style={{ gap: 'var(--space-4)' }}>
          {/* Ratings agrupadas */}
          {ratingQs.length > 0 && (
            <div className="ds-card--inset" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div className="ds-eyebrow">Puntuaciones</div>
              {ratingQs.map(q => {
                const min = ratingMin(q)
                const max = ratingMax(q)
                const buttons = []
                for (let n = min; n <= max; n++) buttons.push(n)
                return (
                  <div key={q.id} className="ds-row-between" style={{ gap: 'var(--space-3)' }}>
                    <div style={styles.flex1MinW0}>
                      <div style={styles.titleSmBold}>
                        {q.label}{q.required && <span style={styles.redAsterisk}> *</span>}
                      </div>
                      {q.hint && <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>{q.hint}</div>}
                    </div>
                    <div style={{ display: 'flex', gap: 4, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                      {buttons.map(n => {
                        const active = Number(answers[q.key]) >= n
                        return (
                          <button key={n} type="button"
                            onClick={() => setAnswers(s => ({ ...s, [q.key]: n }))}
                            aria-label={`${q.label}: ${n} de ${max}`}
                            style={{
                              width: 30, height: 30, borderRadius: 'var(--radius-sm)',
                              background: active ? 'var(--accent)' : 'var(--surface-4)',
                              border: `1px solid ${active ? 'var(--accent)' : 'var(--surface-4)'}`,
                              color: active ? '#fff' : 'var(--text-3)',
                              cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 700,
                              fontFamily: 'inherit',
                              transition: 'background 0.15s var(--easing)',
                            }}>
                            {n}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Preguntas no-rating: yes_no + text_short + text_long */}
          {otherQs.map(q => {
            if (q.kind === 'yes_no') {
              const v = answers[q.key]
              return (
                <div key={q.id} className="ds-field">
                  <label className="ds-field__label">
                    {q.label}{q.required && <span style={styles.redAsterisk}> *</span>}
                  </label>
                  {q.hint && <div className="ds-field__hint">{q.hint}</div>}
                  <div className="ds-row-wrap" style={{ marginTop: 4 }}>
                    {[{ k: 'yes', l: 'Sí' }, { k: 'no', l: 'No' }].map(({ k, l }) => (
                      <button key={k} type="button"
                        onClick={() => setAnswers(s => ({ ...s, [q.key]: k }))}
                        style={{
                          padding: '6px 14px', borderRadius: 'var(--radius-md)',
                          background: v === k ? 'var(--accent-muted)' : 'var(--surface-3)',
                          border: `1px solid ${v === k ? 'var(--accent)' : 'var(--surface-4)'}`,
                          color: v === k ? 'var(--accent)' : 'var(--text-2)',
                          cursor: 'pointer', fontFamily: 'inherit',
                          fontSize: 'var(--text-sm)', fontWeight: 600,
                        }}>
                        {l}
                      </button>
                    ))}
                  </div>
                </div>
              )
            }
            const isLong = q.kind === 'text_long'
            return (
              <div key={q.id} className="ds-field">
                <label className="ds-field__label">
                  {q.label}{q.required && <span style={styles.redAsterisk}> *</span>}
                </label>
                {q.hint && <div className="ds-field__hint">{q.hint}</div>}
                {isLong ? (
                  <textarea value={answers[q.key] || ''}
                    onChange={e => setAnswers(s => ({ ...s, [q.key]: e.target.value }))}
                    rows={3} className="ds-input" style={{ resize: 'vertical' }} />
                ) : (
                  <input type="text" value={answers[q.key] || ''}
                    onChange={e => setAnswers(s => ({ ...s, [q.key]: e.target.value }))}
                    className="ds-input" />
                )}
              </div>
            )
          })}

          {questions.length === 0 && (
            <div className="ds-card--inset" style={{ display: 'block', textAlign: 'center' }}>
              <div className="ds-muted">Este ciclo aún no tiene preguntas configuradas.</div>
            </div>
          )}

          {missingRequired.length > 0 && (
            <div style={styles.warningInlineXs}>
              <AlertCircle size={12} /> Faltan {missingRequired.length} respuesta(s) obligatoria(s)
            </div>
          )}

          <div style={styles.flexEndRow}>
            <Button variant="secondary" onClick={() => save()} disabled={saving || submitting} loading={saving}>
              <Save size={13} /> Guardar borrador
            </Button>
            <Button onClick={() => submit()}
              disabled={saving || submitting || missingRequired.length > 0}
              loading={submitting}>
              <Send size={13} /> Enviar evaluación
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

// ── AssignReviewModal: HR/Admin asigna quién evalúa a quién (smart 360°) ───
function AssignReviewModal({ cycle, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({ reviewer_id: '', reviewee_id: '', review_type: 'manager' })

  const { data: users = [] } = useQuery({
    queryKey: ['users-for-review-assign'],
    queryFn: () => usersApi.list({ page_size: 200 }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
  })

  // Cuando hay reviewee, consultamos backend para conocer la elegibilidad por
  // tipo. Mostramos en paralelo los 4 tipos para activar/desactivar chips.
  const eligibilityQueries = useQueries({
    queries: REVIEW_TYPES.map(t => ({
      queryKey: ['perf-eligible', cycle.id, form.reviewee_id, t.id],
      queryFn: () => performanceApi.eligibleReviewers(cycle.id, form.reviewee_id, t.id).then(r => r.data),
      enabled: !!form.reviewee_id,
    })),
  })

  const elByType = Object.fromEntries(REVIEW_TYPES.map((t, i) => [t.id, eligibilityQueries[i].data]))

  const currentTypePool = elByType[form.review_type]
  const eligibleUsers = currentTypePool?.users || []
  const blockedReason = currentTypePool?.reason_blocked

  // Si cambia el reviewee, reseteamos el reviewer_id por seguridad
  useEffect(() => {
    if (!form.reviewee_id) return
    if (form.review_type === 'self') {
      setForm(f => ({ ...f, reviewer_id: f.reviewee_id }))
    } else {
      setForm(f => ({ ...f, reviewer_id: '' }))
    }
  }, [form.reviewee_id, form.review_type])

  const { mutate: assign, isPending } = useMutation({
    mutationFn: () => performanceApi.createReview(cycle.id, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['perf-cycle-reviews', cycle.id] })
      qc.invalidateQueries({ queryKey: ['perf-cycles'] })
      toast.success('Evaluación asignada')
      onClose()
    },
    onError: e => toast.error(extractErr(e, 'Error al asignar')),
  })

  const isSelfType = form.review_type === 'self'
  const canSubmit = !!form.reviewee_id && !!form.reviewer_id && !!form.review_type && !blockedReason

  return (
    <Modal open onClose={onClose}
      title="Asignar evaluación"
      subtitle={`Ciclo: ${cycle.name}`}
      width={560}>
      <div className="ds-stack" style={{ gap: 'var(--space-4)' }}>
        {/* Persona evaluada (primero, para poder calcular elegibilidad) */}
        <div className="ds-field">
          <label className="ds-field__label">Persona evaluada *</label>
          <select value={form.reviewee_id}
            onChange={e => setForm(f => ({ ...f, reviewee_id: e.target.value }))}
            className="ds-input">
            <option value="">Selecciona…</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name || u.username}</option>)}
          </select>
        </div>

        {/* Tipo de evaluación */}
        <div className="ds-field">
          <label className="ds-field__label">Tipo</label>
          <div className="ds-row-wrap">
            {REVIEW_TYPES.map(({ id, Icon, label }) => {
              const active = form.review_type === id
              const pool = elByType[id]
              const disabled = !!form.reviewee_id && !!pool && (pool.users?.length || 0) === 0 && id !== 'self'
              const tip = disabled ? (pool?.reason_blocked || 'No hay evaluadores elegibles') : undefined
              return (
                <span key={id} title={tip} style={{ display: 'inline-flex' }}>
                  <button type="button"
                    onClick={() => !disabled && setForm(f => ({
                      ...f, review_type: id,
                      reviewer_id: id === 'self' ? f.reviewee_id : '',
                    }))}
                    disabled={disabled}
                    style={chipStyle({ active, disabled })}>
                    <Icon size={13} /> {label}
                  </button>
                </span>
              )
            })}
          </div>
          <div className="ds-field__hint">{TYPE_BY_ID[form.review_type]?.help}</div>
          {blockedReason && (
            <div style={{ ...styles.warningInlineXs, marginTop: 4 }}>
              <AlertCircle size={12} /> {blockedReason}
            </div>
          )}
        </div>

        {/* Evaluador (oculto si es 'self') — restringido al pool elegible */}
        {!isSelfType && (
          <div className="ds-field">
            <label className="ds-field__label">Evaluador *</label>
            <select value={form.reviewer_id}
              onChange={e => setForm(f => ({ ...f, reviewer_id: e.target.value }))}
              className="ds-input"
              disabled={!form.reviewee_id || !!blockedReason}>
              <option value="">{form.reviewee_id ? 'Selecciona…' : 'Elige primero la persona evaluada'}</option>
              {eligibleUsers.map(u => (
                <option key={u.id} value={u.id}>
                  {u.full_name}{u.team ? ` · ${u.team}` : (u.department ? ` · ${u.department}` : '')}
                </option>
              ))}
            </select>
            {form.reviewee_id && !blockedReason && eligibleUsers.length > 0 && (
              <div className="ds-field__hint">
                {eligibleUsers.length} evaluador(es) elegible(s) según organigrama y equipo
              </div>
            )}
          </div>
        )}

        <div style={styles.flexEndRow}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => assign()} disabled={!canSubmit || isPending} loading={isPending}>
            <UserPlus size={13} /> Asignar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── QuestionsEditor: edita la plantilla de preguntas de un ciclo en draft ───
function QuestionsEditor({ cycleId, cycleStatus }) {
  const toast = useToast()
  const qc = useQueryClient()
  const editable = cycleStatus === 'draft'

  const { data: questions = [], isLoading } = useQuery({
    queryKey: ['perf-cycle-questions', cycleId],
    queryFn: () => performanceApi.listQuestions(cycleId).then(r => r.data),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['perf-cycle-questions', cycleId] })

  const { mutate: addQ } = useMutation({
    mutationFn: data => performanceApi.addQuestion(cycleId, data),
    onSuccess: () => { invalidate(); toast.success('Pregunta añadida') },
    onError: e => toast.error(extractErr(e, 'Error al añadir')),
  })
  const { mutate: updateQ } = useMutation({
    mutationFn: ({ id, data }) => performanceApi.updateQuestion(id, data),
    onSuccess: () => { invalidate(); toast.success('Pregunta actualizada') },
    onError: e => toast.error(extractErr(e, 'Error al actualizar')),
  })
  const { mutate: removeQ } = useMutation({
    mutationFn: id => performanceApi.deleteQuestion(id),
    onSuccess: () => { invalidate(); toast.success('Pregunta eliminada') },
    onError: e => toast.error(extractErr(e, 'Error al eliminar')),
  })

  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState(null)

  if (isLoading) return <Spinner />

  return (
    <div className="ds-card--inset" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      <div className="ds-row-between">
        <div className="ds-eyebrow" style={styles.inlineIconSm}>
          <ListChecks size={12} /> Plantilla de preguntas ({questions.length})
        </div>
        {editable && (
          <Button size="sm" variant="secondary" onClick={() => setAdding(true)}>
            <Plus size={11} /> Añadir
          </Button>
        )}
      </div>
      {questions.length === 0 ? (
        <div className="ds-muted" style={{ fontSize: 'var(--text-sm)' }}>
          Sin preguntas. {editable && 'Añade alguna o siembra las predeterminadas.'}
        </div>
      ) : (
        <div className="ds-stack-sm">
          {questions.map(q => (
            <div key={q.id} className="ds-row-between" style={styles.rowItemTile}>
              <div style={styles.flex1MinW0}>
                <div style={styles.titleSmBold}>
                  {q.label}{q.required && <span style={styles.redAsterisk}> *</span>}
                </div>
                <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                  {KIND_LABEL[q.kind] || q.kind} · key={q.key}
                </div>
              </div>
              {editable && (
                <div style={{ display: 'flex', gap: 4 }}>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(q)} aria-label="Editar">
                    <Pencil size={11} />
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => {
                    if (confirm(`¿Eliminar pregunta "${q.label}"?`)) removeQ(q.id)
                  }} aria-label="Eliminar">
                    <Trash2 size={11} />
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {!editable && (
        <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
          La plantilla solo es editable mientras el ciclo está en borrador.
        </div>
      )}
      {adding && (
        <QuestionEditModal
          onClose={() => setAdding(false)}
          onSave={data => { addQ(data); setAdding(false) }}
        />
      )}
      {editing && (
        <QuestionEditModal
          question={editing}
          onClose={() => setEditing(null)}
          onSave={data => { updateQ({ id: editing.id, data }); setEditing(null) }}
        />
      )}
    </div>
  )
}

function QuestionEditModal({ question, onClose, onSave }) {
  const isEdit = !!question
  const [form, setForm] = useState(() => ({
    key:       question?.key       || '',
    label:     question?.label     || '',
    hint:      question?.hint      || '',
    kind:      question?.kind      || 'rating_5',
    required:  question?.required  || false,
    scale_min: question?.scale_min ?? '',
    scale_max: question?.scale_max ?? '',
  }))

  const submit = () => {
    const data = {
      label: form.label.trim(),
      hint:  form.hint.trim() || null,
      kind:  form.kind,
      required: !!form.required,
      scale_min: form.scale_min === '' ? null : Number(form.scale_min),
      scale_max: form.scale_max === '' ? null : Number(form.scale_max),
    }
    if (!isEdit) {
      data.key = form.key.trim() || form.label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 60)
    }
    onSave(data)
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar pregunta' : 'Nueva pregunta'} width={520}>
      <div className="ds-stack">
        {!isEdit && (
          <div className="ds-field">
            <label className="ds-field__label">Identificador (opcional)</label>
            <input value={form.key} onChange={e => setForm(f => ({ ...f, key: e.target.value }))}
              className="ds-input" placeholder="se genera del título si lo dejas vacío" />
          </div>
        )}
        <div className="ds-field">
          <label className="ds-field__label">Pregunta *</label>
          <input value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
            className="ds-input" placeholder="Ej: Calidad del trabajo" autoFocus />
        </div>
        <div className="ds-field">
          <label className="ds-field__label">Ayuda (opcional)</label>
          <input value={form.hint} onChange={e => setForm(f => ({ ...f, hint: e.target.value }))}
            className="ds-input" placeholder="Texto pequeño de apoyo bajo la pregunta" />
        </div>
        <div style={styles.twoColGrid}>
          <div className="ds-field">
            <label className="ds-field__label">Tipo</label>
            <select value={form.kind} onChange={e => setForm(f => ({ ...f, kind: e.target.value }))}
              className="ds-input">
              {QUESTION_KINDS.map(k => <option key={k.id} value={k.id}>{k.label}</option>)}
            </select>
          </div>
          <div className="ds-field" style={{ alignSelf: 'end' }}>
            <label style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 'var(--text-sm)' }}>
              <input type="checkbox" checked={form.required}
                onChange={e => setForm(f => ({ ...f, required: e.target.checked }))} />
              Obligatoria
            </label>
          </div>
        </div>
        {isRatingKind(form.kind) && (
          <div style={styles.twoColGrid}>
            <div className="ds-field">
              <label className="ds-field__label">Escala mín</label>
              <input type="number" value={form.scale_min}
                onChange={e => setForm(f => ({ ...f, scale_min: e.target.value }))}
                className="ds-input" placeholder="1" />
            </div>
            <div className="ds-field">
              <label className="ds-field__label">Escala máx</label>
              <input type="number" value={form.scale_max}
                onChange={e => setForm(f => ({ ...f, scale_max: e.target.value }))}
                className="ds-input" placeholder={form.kind === 'rating_10' ? '10' : '5'} />
            </div>
          </div>
        )}
        <div style={styles.flexEndRow}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={submit} disabled={!form.label.trim()}>
            <Save size={13} /> Guardar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── New360CampaignModal: wizard que crea una campaña con todos sus evaluadores
function New360CampaignModal({ cycle, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()

  // Estado de la campaña agrupado en un único objeto. Se exponen setters
  // específicos para preservar la legibilidad de los handlers existentes.
  const [campaign, setCampaign] = useState({
    subjectId: '',
    selfReview: true,
    managerId: '',
    peerIds: [],
    upwardIds: [],
    threshold: 3,
  })
  const { subjectId, selfReview, managerId, peerIds, upwardIds, threshold } = campaign
  const setSubjectId  = v => setCampaign(s => ({ ...s, subjectId: v }))
  const setSelfReview = v => setCampaign(s => ({ ...s, selfReview: v }))
  const setManagerId  = v => setCampaign(s => ({ ...s, managerId: v }))
  const setPeerIds    = updater => setCampaign(s => ({
    ...s, peerIds: typeof updater === 'function' ? updater(s.peerIds) : updater,
  }))
  const setUpwardIds  = updater => setCampaign(s => ({
    ...s, upwardIds: typeof updater === 'function' ? updater(s.upwardIds) : updater,
  }))
  const setThreshold  = v => setCampaign(s => ({ ...s, threshold: v }))

  const { data: users = [] } = useQuery({
    queryKey: ['users-for-360-campaign'],
    queryFn: () => usersApi.list({ page_size: 200 }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
  })

  // Para cada tipo (excepto self) calculamos elegibilidad cuando hay subject
  const elQueries = useQueries({
    queries: ['manager', 'peer', 'upward'].map(t => ({
      queryKey: ['perf-eligible', cycle.id, subjectId, t],
      queryFn: () => performanceApi.eligibleReviewers(cycle.id, subjectId, t).then(r => r.data),
      enabled: !!subjectId,
    })),
  })
  const [managerData, peerData, upwardData] = elQueries.map(q => q.data)
  const managerOptions = managerData?.users || []
  const peerOptions    = peerData?.users    || []
  const upwardOptions  = upwardData?.users  || []

  // Si hay un único manager elegible, lo preseleccionamos.
  // Omitimos managerId y setManagerId a propósito: managerId solo se usa para
  // evitar pisar una selección manual (la guard `!managerId` ya lo cubre);
  // incluirlo dispararía el efecto cuando el usuario eligiese, y setManagerId
  // es una función creada en cada render que provocaría re-ejecuciones inútiles.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intencional: solo on managerOptions change
  useEffect(() => {
    if (managerOptions.length === 1 && !managerId) setManagerId(managerOptions[0].id)
  }, [managerOptions])

  // Cuando cambia el subject reseteamos selecciones derivadas
  useEffect(() => {
    setManagerId('')
    setPeerIds([])
    setUpwardIds([])
  }, [subjectId])

  const togglePeer   = id => setPeerIds  (s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])
  const toggleUpward = id => setUpwardIds(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])

  const totalReviewers = (selfReview ? 1 : 0) + (managerId ? 1 : 0) + peerIds.length + upwardIds.length

  const { mutate: create, isPending } = useMutation({
    mutationFn: () => performanceApi.createCampaign(cycle.id, {
      subject_id: subjectId,
      self_review: selfReview,
      manager_reviewer_id: managerId || null,
      peer_reviewer_ids: peerIds,
      upward_reviewer_ids: upwardIds,
      anonymity_threshold: Number(threshold) || 3,
      auto_activate: true,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['perf-campaigns', cycle.id] })
      qc.invalidateQueries({ queryKey: ['perf-cycle-reviews', cycle.id] })
      toast.success(`Campaña 360° creada con ${totalReviewers} evaluador(es)`)
      onClose()
    },
    onError: e => toast.error(extractErr(e, 'Error al crear campaña')),
  })

  const canCreate = !!subjectId && totalReviewers > 0 && !isPending

  return (
    <Modal open onClose={onClose}
      title={<span style={styles.inlineIcon}>
        <Target size={16} /> Nueva campaña 360°
      </span>}
      subtitle={`Ciclo: ${cycle.name}`}
      width={680}>
      <div className="ds-stack" style={{ gap: 'var(--space-4)' }}>
        {/* Subject */}
        <div className="ds-field">
          <label className="ds-field__label">Persona evaluada *</label>
          <select value={subjectId}
            onChange={e => setSubjectId(e.target.value)}
            className="ds-input">
            <option value="">Selecciona…</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name || u.username}</option>)}
          </select>
        </div>

        {!subjectId ? (
          <div className="ds-card--inset" style={{ display: 'block', textAlign: 'center' }}>
            <div className="ds-muted">Selecciona primero la persona a evaluar para ver sus evaluadores elegibles.</div>
          </div>
        ) : (
          <>
            {/* Self */}
            <div className="ds-card--inset" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
              <input type="checkbox" id="self-review-cb"
                checked={selfReview} onChange={e => setSelfReview(e.target.checked)} />
              <label htmlFor="self-review-cb" style={{ cursor: 'pointer', flex: 1 }}>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                  <User size={12} style={{ verticalAlign: 'middle' }} /> Autoevaluación
                </div>
                <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                  La propia persona se evalúa (recomendado en 360°)
                </div>
              </label>
            </div>

            {/* Manager */}
            <div className="ds-field">
              <label className="ds-field__label">
                <Crown size={11} style={{ verticalAlign: 'middle' }} /> Manager
              </label>
              {managerData?.reason_blocked ? (
                <div style={styles.warningInlineXs}>
                  <AlertCircle size={12} /> {managerData.reason_blocked}
                </div>
              ) : (
                <select value={managerId} onChange={e => setManagerId(e.target.value)}
                  className="ds-input">
                  <option value="">— Sin manager —</option>
                  {managerOptions.map(u => (
                    <option key={u.id} value={u.id}>{u.full_name}</option>
                  ))}
                </select>
              )}
            </div>

            {/* Peers */}
            <div className="ds-field">
              <label className="ds-field__label">
                <UsersIcon size={11} style={{ verticalAlign: 'middle' }} /> Pares
                <span className="ds-muted" style={{ fontWeight: 400, marginLeft: 6 }}>
                  ({peerIds.length} seleccionados de {peerOptions.length} elegibles)
                </span>
              </label>
              {peerData?.reason_blocked ? (
                <div style={styles.warningInlineXs}>
                  <AlertCircle size={12} /> {peerData.reason_blocked}
                </div>
              ) : peerOptions.length === 0 ? (
                <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                  Sin pares elegibles
                </div>
              ) : (
                <div className="ds-row-wrap" style={{ gap: 6 }}>
                  {peerOptions.map(u => {
                    const sel = peerIds.includes(u.id)
                    return (
                      <button key={u.id} type="button" onClick={() => togglePeer(u.id)}
                        style={{
                          padding: '6px 10px', borderRadius: 'var(--radius-md)',
                          background: sel ? 'var(--accent-muted)' : 'var(--surface-3)',
                          border: `1px solid ${sel ? 'var(--accent)' : 'var(--surface-4)'}`,
                          color: sel ? 'var(--accent)' : 'var(--text-2)',
                          cursor: 'pointer', fontFamily: 'inherit',
                          fontSize: 'var(--text-xs)', fontWeight: 600,
                        }}>
                        {u.full_name}
                        {u.team && <span style={{ opacity: 0.6, marginLeft: 4 }}>· {u.team}</span>}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Upward */}
            <div className="ds-field">
              <label className="ds-field__label">
                <ArrowUp size={11} style={{ verticalAlign: 'middle' }} /> Reportes directos (upward)
                <span className="ds-muted" style={{ fontWeight: 400, marginLeft: 6 }}>
                  ({upwardIds.length}/{upwardOptions.length})
                </span>
              </label>
              {upwardData?.reason_blocked ? (
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
                  color: 'var(--text-3)', fontSize: 'var(--text-xs)' }}>
                  <AlertCircle size={12} /> {upwardData.reason_blocked}
                </div>
              ) : upwardOptions.length === 0 ? (
                <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                  Sin reportes directos
                </div>
              ) : (
                <div className="ds-row-wrap" style={{ gap: 6 }}>
                  {upwardOptions.map(u => {
                    const sel = upwardIds.includes(u.id)
                    return (
                      <button key={u.id} type="button" onClick={() => toggleUpward(u.id)}
                        style={{
                          padding: '6px 10px', borderRadius: 'var(--radius-md)',
                          background: sel ? 'var(--accent-muted)' : 'var(--surface-3)',
                          border: `1px solid ${sel ? 'var(--accent)' : 'var(--surface-4)'}`,
                          color: sel ? 'var(--accent)' : 'var(--text-2)',
                          cursor: 'pointer', fontFamily: 'inherit',
                          fontSize: 'var(--text-xs)', fontWeight: 600,
                        }}>
                        {u.full_name}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Anonimización */}
            <div className="ds-field">
              <label className="ds-field__label">
                <Lock size={11} style={{ verticalAlign: 'middle' }} /> Umbral de anonimización
              </label>
              <input type="number" min={1} max={20} value={threshold}
                onChange={e => setThreshold(e.target.value)}
                className="ds-input" style={{ width: 100 }} />
              <div className="ds-field__hint">
                Cuando un grupo (pares, upward) tenga menos respuestas que este umbral,
                los comentarios individuales se ocultan en el dashboard.
              </div>
            </div>
          </>
        )}

        <div className="ds-row-between" style={{ alignItems: 'center' }}>
          <div className="ds-muted" style={{ fontSize: 'var(--text-sm)' }}>
            Total: <strong style={{ color: 'var(--text-1)' }}>{totalReviewers}</strong> evaluador(es)
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <Button variant="secondary" onClick={onClose}>Cancelar</Button>
            <Button onClick={() => create()} disabled={!canCreate} loading={isPending}>
              <Target size={13} /> Crear campaña 360°
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

// ── Campaign360Dashboard: panel agregado y anonimizado por subject ─────────
function Campaign360Dashboard({ campaignId, onClose, onOpenHistory }) {
  const toast = useToast()
  const { data, isLoading } = useQuery({
    queryKey: ['perf-campaign-dashboard', campaignId],
    queryFn: () => performanceApi.campaignDashboard(campaignId).then(r => r.data),
  })

  const downloadPdf = async () => {
    try {
      const res = await performanceApi.campaignDashboardPdf(campaignId)
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const name = data?.campaign?.subject_name?.replace(/\s+/g, '_') || 'subject'
      a.download = `360_${name}_${campaignId.slice(0, 8)}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (e) {
      toast.error(extractErr(e, 'Error al descargar PDF'))
    }
  }

  if (isLoading || !data) {
    return (
      <Modal open onClose={onClose} title="Dashboard 360°" width={760}>
        <Spinner />
      </Modal>
    )
  }

  const c = data.campaign
  const groups = data.groups || {}
  const ratingQs = (data.questions || []).filter(q => isRatingKind(q.kind))
  const textQs   = (data.questions || []).filter(q => !isRatingKind(q.kind))

  const GROUP_META = [
    { id: 'self',    label: 'Self',    Icon: User },
    { id: 'manager', label: 'Manager', Icon: Crown },
    { id: 'peer',    label: 'Pares',   Icon: UsersIcon },
    { id: 'upward',  label: 'Upward',  Icon: ArrowUp },
  ]

  return (
    <Modal open onClose={onClose}
      title={<span style={styles.inlineIcon}>
        <BarChart3 size={16} /> Dashboard 360° — {c.subject_name}
      </span>}
      subtitle={`${data.total_submitted}/${data.total_assigned} respuestas · umbral anonimización: ${data.anonymity_threshold}`}
      width={760}>
      <div className="ds-stack" style={{ gap: 'var(--space-4)' }}>
        {/* Resumen por grupo */}
        <div className="ds-grid-cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }}>
          {GROUP_META.map(({ id, label, Icon }) => {
            const g = groups[id] || { count: 0, anonymized: false }
            return (
              <div key={id} className="ds-card--inset" style={{ display: 'block', textAlign: 'center' }}>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
                  color: 'var(--text-3)', fontSize: 'var(--text-xs)' }}>
                  <Icon size={11} /> {label}
                </div>
                <div style={{ fontSize: 'var(--text-lg)', fontWeight: 800, color: 'var(--text-1)' }}>
                  {g.count}
                </div>
                {g.anonymized && (
                  <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--warning)',
                    display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                    <Lock size={9} /> Anonimizado
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Comparación por pregunta tipo rating */}
        {ratingQs.length > 0 && (
          <div className="ds-card--inset" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <div className="ds-eyebrow">Comparación por pregunta</div>
            {ratingQs.map(q => {
              const max = ratingMax(q)
              const cmp = data.comparison?.[q.key] || {}
              const selfVal = cmp.self
              const peersVal = cmp.peers
              const managerVal = cmp.manager
              const upwardVal = cmp.upward
              // Detectar gap self vs others (blind spot / hidden strength)
              const others = [peersVal, managerVal, upwardVal].filter(v => v != null)
              const othersAvg = others.length ? others.reduce((s, v) => s + v, 0) / others.length : null
              let gapBadge = null
              if (selfVal != null && othersAvg != null) {
                const diff = selfVal - othersAvg
                if (Math.abs(diff) >= 1) {
                  gapBadge = diff > 0
                    ? { text: 'Punto ciego', color: 'var(--warning)' }
                    : { text: 'Fortaleza no percibida', color: 'var(--success)' }
                }
              }
              return (
                <div key={q.id}>
                  <div className="ds-row-between" style={{ marginBottom: 4 }}>
                    <div style={styles.titleSmBold}>
                      {q.label}
                    </div>
                    {gapBadge && (
                      <span style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: gapBadge.color }}>
                        {gapBadge.text}
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'grid', gap: 4 }}>
                    {GROUP_META.map(({ id, label }) => {
                      const key = id === 'peer' ? 'peers' : id
                      const v = cmp[key]
                      if (v == null) {
                        return (
                          <div key={id} className="ds-row" style={{ gap: 8, alignItems: 'center' }}>
                            <span style={{ width: 80, fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{label}</span>
                            <span className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>—</span>
                          </div>
                        )
                      }
                      return (
                        <div key={id} className="ds-row" style={{ gap: 8, alignItems: 'center' }}>
                          <span style={{ width: 80, fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{label}</span>
                          <div style={{ flex: 1 }}>
                            <ScoreBar value={v} max={max} />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Comentarios de texto, agrupados y anonimizados si procede */}
        {textQs.length > 0 && (
          <div className="ds-stack-sm">
            <div className="ds-eyebrow">Comentarios cualitativos</div>
            {textQs.map(q => (
              <div key={q.id} className="ds-card--inset" style={{ display: 'block' }}>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>
                  {q.label}
                </div>
                {GROUP_META.map(({ id, label, Icon }) => {
                  const g = groups[id]
                  if (!g) return null
                  const items = g.text_by_question?.[q.key] || []
                  return (
                    <div key={id} style={{ marginTop: 6 }}>
                      <div className="ds-row" style={{ gap: 6, color: 'var(--text-3)',
                        fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: 4 }}>
                        <Icon size={11} /> {label}
                        {g.anonymized && (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3,
                            color: 'var(--warning)' }}>
                            <Lock size={9} /> oculto (n={g.count}, umbral={data.anonymity_threshold})
                          </span>
                        )}
                      </div>
                      {!g.anonymized && items.length === 0 && (
                        <div className="ds-muted" style={{ fontSize: 'var(--text-xs)', paddingLeft: 18 }}>
                          Sin respuestas
                        </div>
                      )}
                      {!g.anonymized && items.map((it, idx) => (
                        <div key={idx} style={{ paddingLeft: 18, fontSize: 'var(--text-xs)',
                          color: 'var(--text-2)', borderLeft: '2px solid var(--surface-4)',
                          marginLeft: 6, marginBottom: 4 }}>
                          {String(it.text)}
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-2)' }}>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <Button variant="secondary"
              onClick={() => onOpenHistory?.(c.subject_id, c.subject_name)}>
              <TrendingUp size={13} /> Ver evolución histórica
            </Button>
            <Button variant="secondary" onClick={downloadPdf}>
              <FileDown size={13} /> Descargar PDF
            </Button>
          </div>
          <Button variant="secondary" onClick={onClose}>
            <X size={13} /> Cerrar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── History360Modal: evolución del subject a lo largo de varios ciclos ────
function History360Modal({ subjectId, subjectName, onClose }) {
  const { data, isLoading } = useQuery({
    queryKey: ['perf-360-history', subjectId],
    queryFn: () => performanceApi.history360(subjectId).then(r => r.data),
  })

  const series = data?.series || []
  // Recopilamos todas las question keys que aparecen al menos una vez
  const allQs = useMemo(() => {
    const map = new Map()
    for (const s of series) {
      for (const [k, v] of Object.entries(s.ratings || {})) {
        if (!map.has(k)) map.set(k, { key: k, label: v.label, max: v.scale_max })
      }
    }
    return [...map.values()]
  }, [series])

  return (
    <Modal open onClose={onClose}
      title={<span style={styles.inlineIcon}>
        <TrendingUp size={16} /> Evolución 360° — {subjectName || data?.subject_name}
      </span>}
      subtitle={`${series.length} campañas con respuestas`}
      width={780}>
      {isLoading ? <Spinner /> : series.length === 0 ? (
        <EmptyState svgIcon={<History size={36} />}
          title="Sin histórico aún"
          description="Cuando se cierren campañas con respuestas, aparecerán aquí ordenadas cronológicamente." />
      ) : (
        <div className="ds-stack" style={{ gap: 'var(--space-3)' }}>
          {/* Cabecera con cycles */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: `220px repeat(${series.length}, 1fr)`,
            gap: 6, alignItems: 'center',
            fontSize: 'var(--text-xs)', color: 'var(--text-3)',
          }}>
            <div className="ds-eyebrow" style={{ paddingLeft: 0 }}>Pregunta</div>
            {series.map(s => (
              <div key={s.campaign_id} style={{ textAlign: 'center', minWidth: 0 }}>
                <div style={{ fontWeight: 700, color: 'var(--text-1)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {s.cycle_name}
                </div>
                <div className="ds-muted" style={{ fontSize: 'var(--text-2xs)' }}>
                  {s.created_at}
                </div>
              </div>
            ))}
          </div>

          {/* Filas: una por pregunta de rating */}
          {allQs.map(q => (
            <div key={q.key} style={{
              display: 'grid',
              gridTemplateColumns: `220px repeat(${series.length}, 1fr)`,
              gap: 6, alignItems: 'center',
              padding: '8px 0', borderTop: '1px solid var(--surface-4)',
            }}>
              <div style={styles.titleSmBold}>
                {q.label}
              </div>
              {series.map(s => {
                const r = s.ratings?.[q.key]
                if (!r) {
                  return <div key={s.campaign_id} className="ds-muted"
                    style={{ textAlign: 'center', fontSize: 'var(--text-xs)' }}>—</div>
                }
                const others = r.others
                const self   = r.self
                return (
                  <div key={s.campaign_id} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {others != null && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', minWidth: 36 }}>others</span>
                        <div style={{ flex: 1 }}>
                          <ScoreBar value={others} max={q.max} />
                        </div>
                      </div>
                    )}
                    {self != null && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', minWidth: 36 }}>self</span>
                        <div style={{ flex: 1 }}>
                          <ScoreBar value={self} max={q.max} />
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--space-3)' }}>
        <Button variant="secondary" onClick={onClose}>
          <X size={13} /> Cerrar
        </Button>
      </div>
    </Modal>
  )
}

// ── CampaignsList: campañas 360° dentro de un ciclo ───────────────────────
function CampaignsList({ cycle, isManager, onCreate, onOpenDashboard }) {
  const { data: campaigns = [], isLoading } = useQuery({
    queryKey: ['perf-campaigns', cycle.id],
    queryFn: () => performanceApi.listCampaigns(cycle.id).then(r => r.data).catch(() => []),
  })

  return (
    <div className="ds-card--inset" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      <div className="ds-row-between">
        <div className="ds-eyebrow" style={styles.inlineIconSm}>
          <Target size={12} /> Campañas 360° ({campaigns.length})
        </div>
        {cycle.status !== 'closed' && (
          <span title={!isManager ? NO_PERMISSION_TIP : undefined} style={{ display: 'inline-flex' }}>
            <Button size="sm" onClick={() => onCreate(cycle)} disabled={!isManager}>
              <Plus size={11} /> Nueva campaña
            </Button>
          </span>
        )}
      </div>
      {isLoading ? <Spinner /> : campaigns.length === 0 ? (
        <div className="ds-muted" style={{ fontSize: 'var(--text-sm)' }}>
          Sin campañas. Una campaña agrupa autoevaluación + manager + pares + upward para una persona,
          y produce un dashboard agregado y anonimizado.
        </div>
      ) : (
        <div className="ds-stack-sm">
          {campaigns.map(camp => {
            const total = camp.total_reviewers || 0
            const submitted = camp.submitted || 0
            const pct = total ? Math.round((submitted / total) * 100) : 0
            return (
              <div key={camp.id} className="ds-row-between"
                style={{ ...styles.rowItemTilePadded, cursor: 'pointer' }}
                onClick={() => onOpenDashboard(camp.id)}>
                <div style={styles.flex1MinW0}>
                  <div style={styles.titleSmBolder}>
                    {camp.subject_name}
                  </div>
                  <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                    {submitted}/{total} respuestas ({pct}%) · {camp.status}
                    {' · '}
                    {Object.entries(camp.by_type || {})
                      .filter(([, n]) => n > 0)
                      .map(([t, n]) => `${t}:${n}`).join(' ')}
                  </div>
                </div>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--accent)' }}>
                  <BarChart3 size={13} />
                  <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600 }}>Dashboard</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── CycleCard: tarjeta de un ciclo con sus evaluaciones ────────────────────
function CycleCard({ cycle, isManager, onActivate, onCloseCycle, onAssign, onCreateCampaign, onOpenDashboard }) {
  const [expanded, setExpanded] = useState(false)
  const { data: reviews = [], isLoading } = useQuery({
    queryKey: ['perf-cycle-reviews', cycle.id],
    queryFn: () => performanceApi.cycleReviews(cycle.id).then(r => r.data).catch(() => []),
    enabled: expanded && (cycle.status === 'active' || cycle.status === 'closed'),
  })

  const statusCfg = STATUS_CFG[cycle.status] || STATUS_CFG.draft
  const submittedReviews = reviews.filter(r => r.score_overall != null)
  const avgScore = submittedReviews.length > 0
    ? (submittedReviews.reduce((s, r) => s + (r.score_overall || 0), 0) / submittedReviews.length).toFixed(1)
    : null

  const ChevronIcon = expanded ? ChevronDown : ChevronRight

  return (
    <div className="ds-card" style={{ gap: 'var(--space-3)' }}>
      <div className="ds-row" style={{ gap: 'var(--space-3)' }}>
        <button type="button" onClick={() => setExpanded(s => !s)}
          aria-label={expanded ? 'Contraer' : 'Expandir'}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-3)', display: 'inline-flex', alignItems: 'center', padding: 0,
          }}>
          <ChevronIcon size={16} />
        </button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={styles.titleMdBold}>{cycle.name}</div>
          <div className="ds-row-wrap" style={{ marginTop: 4 }}>
            <span className={`ds-pill ds-pill--${statusCfg.kind === 'neutral' ? '' : statusCfg.kind}`}>
              {statusCfg.label}
            </span>
            {cycle.start_date && (
              <span className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                {fmtDate(cycle.start_date)} – {cycle.end_date ? fmtDate(cycle.end_date) : '?'}
              </span>
            )}
            <span className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
              {cycle.total_reviews || 0} evaluaciones · {cycle.pending} pendientes · {cycle.submitted} enviadas
            </span>
            {avgScore && (
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)', fontWeight: 700 }}>
                Media: {avgScore}/5
              </span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          {cycle.status === 'draft' && (
            <span title={!isManager ? NO_PERMISSION_TIP : undefined} style={{ display: 'inline-flex' }}>
              <Button size="sm" onClick={() => onActivate(cycle.id)} disabled={!isManager}>
                Activar
              </Button>
            </span>
          )}
          {cycle.status === 'active' && (
            <>
              <span title={!isManager ? NO_PERMISSION_TIP : undefined} style={{ display: 'inline-flex' }}>
                <Button size="sm" onClick={() => onAssign(cycle)} disabled={!isManager}>
                  <UserPlus size={12} /> Asignar
                </Button>
              </span>
              <span title={!isManager ? NO_PERMISSION_TIP : undefined} style={{ display: 'inline-flex' }}>
                <Button size="sm" variant="secondary" onClick={() => onCloseCycle(cycle.id)} disabled={!isManager}>
                  Cerrar ciclo
                </Button>
              </span>
            </>
          )}
        </div>
      </div>

      {expanded && (
        <div className="ds-stack-sm">
          {/* Plantilla de preguntas (siempre visible cuando expandido) */}
          <QuestionsEditor cycleId={cycle.id} cycleStatus={cycle.status} />

          {/* Campañas 360° — solo en ciclos activos o cerrados */}
          {(cycle.status === 'active' || cycle.status === 'closed') && (
            <CampaignsList cycle={cycle} isManager={isManager}
              onCreate={onCreateCampaign}
              onOpenDashboard={onOpenDashboard} />
          )}

          {/* Evaluaciones — solo en ciclos activos/cerrados */}
          {(cycle.status === 'active' || cycle.status === 'closed') && (
            isLoading ? <Spinner /> : reviews.length === 0 ? (
              <div className="ds-card--inset" style={{ display: 'block' }}>
                <div className="ds-muted" style={{ fontSize: 'var(--text-sm)' }}>
                  Sin evaluaciones aún. {cycle.status === 'active' && isManager && 'Pulsa "Asignar" para crear la primera.'}
                  {cycle.status === 'active' && !isManager && 'RR.HH. asignará las evaluaciones cuando estén listas.'}
                </div>
              </div>
            ) : (
              <div className="ds-grid-cards" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 'var(--space-2)' }}>
                {reviews.map(r => {
                  const t = TYPE_BY_ID[r.review_type] || TYPE_BY_ID.peer
                  const TypeIcon = t.Icon
                  const submitted = r.status === 'submitted'
                  return (
                    <div key={r.id} className="ds-card--inset" style={{ display: 'block' }}>
                      <div className="ds-row-between" style={{ marginBottom: 6 }}>
                        <div style={styles.flex1MinW0}>
                          <div style={styles.titleSmBolder}>
                            {r.reviewee_name}
                          </div>
                          <div className="ds-muted" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 'var(--text-xs)' }}>
                            <TypeIcon size={11} /> {t.label}
                          </div>
                        </div>
                        <span style={{
                          fontSize: 'var(--text-2xs)', fontWeight: 700,
                          color: submitted ? 'var(--success)' : 'var(--warning)',
                          display: 'inline-flex', alignItems: 'center', gap: 3,
                        }}>
                          {submitted
                            ? <><CheckCircle2 size={10} /> Enviado</>
                            : <><Clock size={10} /> Pendiente</>}
                        </span>
                      </div>
                      {r.score_overall != null && <ScoreBar value={r.score_overall} />}
                      <div className="ds-muted" style={{ fontSize: 'var(--text-xs)', marginTop: 4 }}>
                        por {r.reviewer_name}
                      </div>
                    </div>
                  )
                })}
              </div>
            )
          )}
        </div>
      )}
    </div>
  )
}

// ── NewCycleModal ──────────────────────────────────────────────────────────
function NewCycleModal({ existingCycles, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    name: '', start_date: '', end_date: '',
    template_mode: 'default',  // 'default' | 'clone' | 'empty'
    clone_from: '',
  })

  const cloneable = useMemo(
    () => (existingCycles || []).filter(c => c.id),
    [existingCycles],
  )

  const { mutate, isPending } = useMutation({
    mutationFn: () => {
      const payload = {
        name: form.name,
        start_date: form.start_date || null,
        end_date:   form.end_date   || null,
        seed_default_questions: form.template_mode === 'default',
        clone_questions_from_cycle_id: form.template_mode === 'clone' ? form.clone_from : null,
      }
      return performanceApi.createCycle(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['perf-cycles'] })
      toast.success('Ciclo creado')
      onClose()
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const canCreate = !!form.name.trim() &&
    (form.template_mode !== 'clone' || !!form.clone_from)

  return (
    <Modal open onClose={onClose} title="Nuevo ciclo de evaluación" width={520}>
      <div className="ds-stack">
        <div className="ds-field">
          <label className="ds-field__label">Nombre *</label>
          <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            className="ds-input" placeholder="Ej: Evaluación Q1 2026" autoFocus />
        </div>
        <div style={styles.twoColGrid}>
          <div className="ds-field">
            <label className="ds-field__label">Inicio</label>
            <input type="date" value={form.start_date}
              onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
              className="ds-input" />
          </div>
          <div className="ds-field">
            <label className="ds-field__label">Fin</label>
            <input type="date" value={form.end_date}
              onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
              className="ds-input" />
          </div>
        </div>
        <div className="ds-field">
          <label className="ds-field__label">Plantilla de preguntas</label>
          <div className="ds-row-wrap">
            {[
              { id: 'default', label: 'Por defecto (5 ratings + 3 textos)' },
              { id: 'clone',   label: 'Clonar de otro ciclo', disabled: cloneable.length === 0 },
              { id: 'empty',   label: 'Vacía (la rellenaré yo)' },
            ].map(opt => {
              const active = form.template_mode === opt.id
              return (
                <button key={opt.id} type="button"
                  disabled={opt.disabled}
                  onClick={() => setForm(f => ({ ...f, template_mode: opt.id }))}
                  style={{
                    padding: '6px 12px', borderRadius: 'var(--radius-md)',
                    background: active ? 'var(--accent-muted)' : 'var(--surface-3)',
                    border: `1px solid ${active ? 'var(--accent)' : 'var(--surface-4)'}`,
                    color: active ? 'var(--accent)' : 'var(--text-2)',
                    cursor: opt.disabled ? 'not-allowed' : 'pointer',
                    opacity: opt.disabled ? 0.55 : 1,
                    fontFamily: 'inherit',
                    fontSize: 'var(--text-sm)', fontWeight: 600,
                  }}>
                  {opt.label}
                </button>
              )
            })}
          </div>
          {form.template_mode === 'clone' && (
            <div style={{ marginTop: 8 }}>
              <select value={form.clone_from}
                onChange={e => setForm(f => ({ ...f, clone_from: e.target.value }))}
                className="ds-input">
                <option value="">Selecciona ciclo origen…</option>
                {cloneable.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          )}
        </div>
        <div style={styles.flexEndRow}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate()} disabled={isPending || !canCreate} loading={isPending}>
            <Plus size={13} /> Crear ciclo
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── KPIDashboardTab: panel operativo de HR ─────────────────────────────────
function KPIDashboardTab({ cycles }) {
  const toast = useToast()
  const qc = useQueryClient()

  const { data: kpis, isLoading } = useQuery({
    queryKey: ['perf-kpis-org'],
    queryFn: () => performanceApi.orgKpis().then(r => r.data),
  })

  const { mutate: runReminders, isPending: running } = useMutation({
    mutationFn: () => performanceApi.runReminders(),
    onSuccess: res => {
      const d = res.data
      toast.success(
        `Recordatorios: ${d.reminders_sent} enviados, ${d.reminders_skipped_dedup} omitidos.`,
      )
      qc.invalidateQueries({ queryKey: ['perf-kpis-org'] })
    },
    onError: e => toast.error(extractErr(e, 'Error al disparar recordatorios')),
  })

  if (isLoading || !kpis) return <Spinner />

  const stat = (label, value, hint, color) => (
    <div className="ds-card--inset" style={{ display: 'block' }}>
      <div className="ds-eyebrow">{label}</div>
      <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, color: color || 'var(--text-1)',
        fontFamily: 'var(--font-mono)' }}>
        {value}
      </div>
      {hint && <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>{hint}</div>}
    </div>
  )

  return (
    <div className="ds-stack" style={{ gap: 'var(--space-4)' }}>
      <div className="ds-row-between">
        <div className="ds-eyebrow" style={styles.inlineIconSm}>
          <Activity size={12} /> Panel operativo
        </div>
        <Button size="sm" variant="secondary" onClick={() => runReminders()}
          disabled={running} loading={running}>
          <Bell size={11} /> Disparar recordatorios ahora
        </Button>
      </div>

      <div className="ds-grid-cards" style={{
        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8,
      }}>
        {stat('Ciclos activos', kpis.active_cycles)}
        {stat('Ciclos cerrados', kpis.closed_cycles)}
        {stat('Reviews pendientes', kpis.pending_reviews_active,
          `de ${kpis.total_reviews_active} en ciclos activos`,
          kpis.pending_reviews_active > 0 ? 'var(--warning)' : 'var(--success)')}
        {stat('Completion rate global',
          `${kpis.global_completion_rate}%`,
          'sobre todos los ciclos activos',
          kpis.global_completion_rate >= 70 ? 'var(--success)'
          : kpis.global_completion_rate >= 40 ? 'var(--accent)' : 'var(--warning)')}
        {stat('Tiempo medio de envío',
          kpis.avg_days_to_submit_closed != null ? `${kpis.avg_days_to_submit_closed} d` : '—',
          'en ciclos ya cerrados')}
      </div>

      {/* Ciclos atascados */}
      {kpis.stalled_cycles?.length > 0 && (
        <div className="ds-card--inset" style={{ display: 'block' }}>
          <div className="ds-row" style={{ gap: 6, color: 'var(--warning)',
            fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: 6 }}>
            <AlertTriangle size={14} />
            {kpis.stalled_cycles.length} ciclo(s) atascado(s)
          </div>
          <div className="ds-stack-sm">
            {kpis.stalled_cycles.map(s => (
              <div key={s.cycle_id} className="ds-row-between" style={styles.rowItemTile}>
                <div style={styles.flex1MinW0}>
                  <div style={styles.titleSmBolder}>
                    {s.cycle_name}
                  </div>
                  <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                    {s.completion_rate}% completado
                    {s.overdue && ' · vencido'}
                    {s.end_date && ` · cerraba ${s.end_date}`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Drill-down por ciclo */}
      {cycles?.filter(c => c.status === 'active').length > 0 && (
        <div className="ds-card--inset" style={{ display: 'block' }}>
          <div className="ds-eyebrow" style={{ marginBottom: 6 }}>Ciclos activos en detalle</div>
          <div className="ds-stack-sm">
            {cycles.filter(c => c.status === 'active').map(c => (
              <CycleKpiRow key={c.id} cycle={c} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function CycleKpiRow({ cycle }) {
  const { data: k, isLoading } = useQuery({
    queryKey: ['perf-cycle-kpi', cycle.id],
    queryFn: () => performanceApi.cycleKpis(cycle.id).then(r => r.data),
  })
  if (isLoading || !k) return <Spinner />

  const rate = k.completion_rate
  const color = rate >= 70 ? 'var(--success)' : rate >= 40 ? 'var(--accent)' : 'var(--warning)'

  return (
    <div className="ds-row-between" style={styles.rowItemTile}>
      <div style={styles.flex1MinW0}>
        <div style={styles.titleSmBolder}>
          {k.cycle_name}
        </div>
        <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
          {k.submitted}/{k.total_reviews} enviadas
          {k.days_to_close != null && ` · cierra en ${k.days_to_close} días`}
          {k.avg_days_to_submit != null && ` · media ${k.avg_days_to_submit} d`}
        </div>
        {k.top_stalled_reviewers?.length > 0 && (
          <div className="ds-row-wrap" style={{ marginTop: 6 }}>
            {k.top_stalled_reviewers.slice(0, 5).map(s => (
              <span key={s.user_id} style={{
                fontSize: 'var(--text-2xs)', padding: '2px 6px',
                background: 'var(--surface-4)', borderRadius: 'var(--radius-sm)',
                color: 'var(--text-2)',
              }}>
                {s.user_name} · {s.pending}
              </span>
            ))}
          </div>
        )}
      </div>
      <div style={{ width: 140 }}>
        <ScoreBar value={rate / 20} max={5} />
        <div style={{ textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 700, color }}>
          {rate}%
        </div>
      </div>
    </div>
  )
}

// ── DevPlansTab: planes de desarrollo del usuario actual ───────────────────
const PLAN_STATUS_CFG = {
  draft:     { label: 'Borrador', color: 'var(--text-3)' },
  active:    { label: 'Activo',   color: 'var(--accent)' },
  completed: { label: 'Completado', color: 'var(--success)' },
  archived:  { label: 'Archivado', color: 'var(--text-4)' },
}
const GOAL_STATUS_CFG = {
  pending:     { label: 'Pendiente',   color: 'var(--text-3)' },
  in_progress: { label: 'En curso',    color: 'var(--accent)' },
  done:        { label: 'Completado',  color: 'var(--success)' },
  blocked:     { label: 'Bloqueado',   color: 'var(--warning)' },
  cancelled:   { label: 'Cancelado',   color: 'var(--text-4)' },
}

function DevPlansTab({ subjectId, subjectName }) {
  const [openPlanId, setOpenPlanId] = useState(null)
  const [creating, setCreating] = useState(false)

  const { data: plans = [], isLoading } = useQuery({
    queryKey: ['dev-plans', subjectId],
    queryFn: () => performanceApi.listUserPlans(subjectId).then(r => r.data),
    enabled: !!subjectId,
  })

  return (
    <div className="ds-stack" style={{ gap: 'var(--space-3)' }}>
      <div className="ds-row-between">
        <div className="ds-eyebrow" style={styles.inlineIconSm}>
          <MapIcon size={12} /> Planes de desarrollo de {subjectName}
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus size={11} /> Nuevo plan
        </Button>
      </div>

      {isLoading ? <Spinner /> : plans.length === 0 ? (
        <EmptyState svgIcon={<MapIcon size={36} />}
          title="Sin planes aún"
          description="Tras una campaña 360° crea un plan con objetivos concretos, fechas y revisiones." />
      ) : (
        <div className="ds-stack-sm">
          {plans.map(p => {
            const cfg = PLAN_STATUS_CFG[p.status] || PLAN_STATUS_CFG.draft
            return (
              <div key={p.id} className="ds-card" onClick={() => setOpenPlanId(p.id)}
                style={{ cursor: 'pointer' }}>
                <div className="ds-row-between">
                  <div style={styles.flex1MinW0}>
                    <div style={styles.titleMdBold}>
                      {p.title}
                    </div>
                    <div className="ds-row-wrap" style={{ marginTop: 4 }}>
                      <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: cfg.color }}>
                        {cfg.label}
                      </span>
                      <span className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                        {(p.goals || []).length} objetivos
                      </span>
                      {p.target_date && (
                        <span className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                          Objetivo: {p.target_date}
                        </span>
                      )}
                      {p.next_review_at && (
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)' }}>
                          Próxima revisión: {p.next_review_at}
                        </span>
                      )}
                    </div>
                  </div>
                  <div style={{ width: 100 }}>
                    <ScoreBar value={p.progress_pct / 20} max={5} />
                    <div style={{ textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 700,
                      color: p.progress_pct >= 70 ? 'var(--success)' : 'var(--text-2)' }}>
                      {p.progress_pct}%
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {creating && (
        <NewDevPlanModal subjectId={subjectId} onClose={() => setCreating(false)} />
      )}
      {openPlanId && (
        <DevPlanModal planId={openPlanId} onClose={() => setOpenPlanId(null)} />
      )}
    </div>
  )
}

function NewDevPlanModal({ subjectId, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    title: '', summary: '', target_date: '', next_review_at: '',
    goals: [{ title: '', due_date: '' }],
  })

  const setGoal = (idx, key, value) => setForm(f => ({
    ...f, goals: f.goals.map((g, i) => i === idx ? { ...g, [key]: value } : g),
  }))
  const addRow = () => setForm(f => ({ ...f, goals: [...f.goals, { title: '', due_date: '' }] }))
  const removeRow = idx => setForm(f => ({ ...f, goals: f.goals.filter((_, i) => i !== idx) }))

  const { mutate, isPending } = useMutation({
    mutationFn: () => performanceApi.createPlan({
      subject_id: subjectId,
      title: form.title.trim(),
      summary: form.summary.trim() || null,
      target_date: form.target_date || null,
      next_review_at: form.next_review_at || null,
      goals: form.goals.filter(g => g.title.trim()).map(g => ({
        title: g.title.trim(), due_date: g.due_date || null,
      })),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dev-plans', subjectId] })
      toast.success('Plan creado')
      onClose()
    },
    onError: e => toast.error(extractErr(e, 'Error al crear plan')),
  })

  return (
    <Modal open onClose={onClose}
      title={<span style={styles.inlineIcon}>
        <MapIcon size={16} /> Nuevo plan de desarrollo
      </span>}
      width={560}>
      <div className="ds-stack">
        <div className="ds-field">
          <label className="ds-field__label">Título *</label>
          <input value={form.title}
            onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            className="ds-input" placeholder="Ej: Mejora comunicación 2026" autoFocus />
        </div>
        <div className="ds-field">
          <label className="ds-field__label">Resumen / contexto</label>
          <textarea value={form.summary}
            onChange={e => setForm(f => ({ ...f, summary: e.target.value }))}
            rows={3} className="ds-input" style={{ resize: 'vertical' }}
            placeholder="Resumen del 360° y áreas de mejora identificadas" />
        </div>
        <div style={styles.twoColGrid}>
          <div className="ds-field">
            <label className="ds-field__label">Fecha objetivo</label>
            <input type="date" value={form.target_date}
              onChange={e => setForm(f => ({ ...f, target_date: e.target.value }))}
              className="ds-input" />
          </div>
          <div className="ds-field">
            <label className="ds-field__label">Próxima revisión</label>
            <input type="date" value={form.next_review_at}
              onChange={e => setForm(f => ({ ...f, next_review_at: e.target.value }))}
              className="ds-input" />
          </div>
        </div>
        <div className="ds-field">
          <label className="ds-field__label">
            <Flag size={11} style={{ verticalAlign: 'middle' }} /> Objetivos iniciales
          </label>
          {form.goals.map((g, idx) => (
            <div key={idx} style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
              <input value={g.title}
                onChange={e => setGoal(idx, 'title', e.target.value)}
                className="ds-input" placeholder={`Objetivo ${idx + 1}`}
                style={{ flex: 1 }} />
              <input type="date" value={g.due_date}
                onChange={e => setGoal(idx, 'due_date', e.target.value)}
                className="ds-input" style={{ width: 150 }} />
              {form.goals.length > 1 && (
                <Button size="sm" variant="ghost" onClick={() => removeRow(idx)}
                  aria-label="Quitar">
                  <X size={12} />
                </Button>
              )}
            </div>
          ))}
          <Button size="sm" variant="ghost" onClick={addRow}>
            <Plus size={11} /> Añadir objetivo
          </Button>
        </div>
        <div style={styles.flexEndRow}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate()} disabled={!form.title.trim() || isPending}
            loading={isPending}>
            <Save size={13} /> Crear plan
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function DevPlanModal({ planId, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [newGoal, setNewGoal] = useState('')

  const { data: plan, isLoading } = useQuery({
    queryKey: ['dev-plan', planId],
    queryFn: () => performanceApi.getPlan(planId).then(r => r.data),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['dev-plan', planId] })
    if (plan?.subject_id) qc.invalidateQueries({ queryKey: ['dev-plans', plan.subject_id] })
  }

  const { mutate: setStatus } = useMutation({
    mutationFn: status => performanceApi.updatePlan(planId, { status }),
    onSuccess: () => { invalidate(); toast.success('Estado actualizado') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: setGoalStatus } = useMutation({
    mutationFn: ({ id, status }) => performanceApi.updateGoal(id, { status }),
    onSuccess: invalidate,
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: addG } = useMutation({
    mutationFn: title => performanceApi.addGoal(planId, { title }),
    onSuccess: () => { invalidate(); setNewGoal('') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: removeG } = useMutation({
    mutationFn: id => performanceApi.deleteGoal(id),
    onSuccess: invalidate,
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (isLoading || !plan) return (
    <Modal open onClose={onClose} title="Plan" width={640}><Spinner /></Modal>
  )

  const cfg = PLAN_STATUS_CFG[plan.status] || PLAN_STATUS_CFG.draft

  return (
    <Modal open onClose={onClose}
      title={<span style={styles.inlineIcon}>
        <MapIcon size={16} /> {plan.title}
      </span>}
      subtitle={`${plan.subject_name} · ${plan.progress_pct}% completado`}
      width={680}>
      <div className="ds-stack" style={{ gap: 'var(--space-3)' }}>
        <div className="ds-row-wrap">
          {Object.entries(PLAN_STATUS_CFG).map(([k, v]) => (
            <button key={k} type="button" onClick={() => setStatus(k)}
              style={{
                padding: '6px 10px', borderRadius: 'var(--radius-md)',
                background: plan.status === k ? 'var(--accent-muted)' : 'var(--surface-3)',
                border: `1px solid ${plan.status === k ? 'var(--accent)' : 'var(--surface-4)'}`,
                color: plan.status === k ? 'var(--accent)' : 'var(--text-2)',
                cursor: 'pointer', fontFamily: 'inherit',
                fontSize: 'var(--text-xs)', fontWeight: 600,
              }}>
              {v.label}
            </button>
          ))}
        </div>

        {plan.summary && (
          <div className="ds-card--inset" style={{ display: 'block' }}>
            <div className="ds-eyebrow">Contexto</div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
              {plan.summary}
            </div>
          </div>
        )}

        <div className="ds-card--inset" style={{ display: 'block' }}>
          <div className="ds-eyebrow">Objetivos</div>
          {plan.goals.length === 0 ? (
            <div className="ds-muted" style={{ fontSize: 'var(--text-sm)' }}>Sin objetivos aún.</div>
          ) : (
            <div className="ds-stack-sm">
              {plan.goals.map(g => {
                const gcfg = GOAL_STATUS_CFG[g.status] || GOAL_STATUS_CFG.pending
                return (
                  <div key={g.id} className="ds-row-between" style={{
                    gap: 8, padding: '8px 10px',
                    background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--surface-4)',
                  }}>
                    <div style={styles.flex1MinW0}>
                      <div style={styles.titleSmBold}>
                        {g.title}
                      </div>
                      <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                        {g.due_date && `Vence ${g.due_date} · `}
                        {g.completed_at && `Completado ${g.completed_at}`}
                      </div>
                    </div>
                    <select value={g.status}
                      onChange={e => setGoalStatus({ id: g.id, status: e.target.value })}
                      className="ds-input" style={{ width: 130, fontSize: 'var(--text-xs)' }}>
                      {Object.entries(GOAL_STATUS_CFG).map(([k, v]) => (
                        <option key={k} value={k}>{v.label}</option>
                      ))}
                    </select>
                    <Button size="sm" variant="ghost"
                      onClick={() => { if (confirm('¿Eliminar objetivo?')) removeG(g.id) }}
                      aria-label="Eliminar">
                      <Trash2 size={11} />
                    </Button>
                  </div>
                )
              })}
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <input value={newGoal}
              onChange={e => setNewGoal(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && newGoal.trim() && addG(newGoal.trim())}
              className="ds-input" style={{ flex: 1 }}
              placeholder="Añadir nuevo objetivo y pulsar Enter" />
            <Button size="sm" onClick={() => newGoal.trim() && addG(newGoal.trim())}
              disabled={!newGoal.trim()}>
              <Plus size={11} /> Añadir
            </Button>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button variant="secondary" onClick={onClose}>
            <X size={13} /> Cerrar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────
export default function PerformanceReviewsPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { user } = useAuth()
  const isManager = ['admin', 'hr'].includes(user?.role)

  const [tab, setTab] = useState('cycles')

  // Estado de modales agrupado. Cada propiedad es independiente y se asigna
  // mediante helpers locales para mantener una API similar a setState.
  const [modals, setModals] = useState({
    showNewCycle:     false,
    editingReview:    null,
    assigningCycle:   null,
    campaigningCycle: null,
    openDashboardId:  null,
    historySubject:   null,  // {id, name}
  })
  const setModal = (key, value) => setModals(m => ({ ...m, [key]: value }))
  const setShowNewCycle     = v => setModal('showNewCycle', v)
  const setEditingReview    = v => setModal('editingReview', v)
  const setAssigningCycle   = v => setModal('assigningCycle', v)
  const setCampaigningCycle = v => setModal('campaigningCycle', v)
  const setOpenDashboardId  = v => setModal('openDashboardId', v)
  const setHistorySubject   = v => setModal('historySubject', v)
  const {
    showNewCycle, editingReview, assigningCycle,
    campaigningCycle, openDashboardId, historySubject,
  } = modals

  const { data: cycles = [], isLoading: loadingCycles } = useQuery({
    queryKey: ['perf-cycles'],
    queryFn: () => performanceApi.cycles().then(r => r.data).catch(() => []),
  })
  const { data: myReviews = [], isLoading: loadingMine } = useQuery({
    queryKey: ['perf-my-reviews'],
    queryFn: () => performanceApi.myReviews().then(r => r.data).catch(() => []),
  })

  const { mutate: activate } = useMutation({
    mutationFn: id => performanceApi.activateCycle(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['perf-cycles'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: closeCycle } = useMutation({
    mutationFn: id => performanceApi.closeCycle(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['perf-cycles'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Page
      icon={<Star size={18} />}
      title={t('performance.title') || 'Evaluaciones de rendimiento'}
      subtitle={t('performance.subtitle') || 'Ciclos de evaluación 360° (autoevaluación, par, manager y upward)'}
      rightActions={
        tab === 'cycles' && (
          <span title={!isManager ? NO_PERMISSION_TIP : undefined} style={{ display: 'inline-flex' }}>
            <Button onClick={() => setShowNewCycle(true)} disabled={!isManager}>
              <Plus size={13} /> Nuevo ciclo
            </Button>
          </span>
        )
      }
    >
      {/* Tabs */}
      <div className="ds-segmented" role="tablist" style={{ alignSelf: 'flex-start' }}>
        <button type="button" role="tab" aria-pressed={tab === 'cycles'} onClick={() => setTab('cycles')}>
          Ciclos
        </button>
        <button type="button" role="tab" aria-pressed={tab === 'pending'} onClick={() => setTab('pending')}>
          <Clock size={11} /> Mis evaluaciones
          {myReviews.length > 0 && ` (${myReviews.length})`}
        </button>
        <button type="button" role="tab" aria-pressed={tab === 'plans'} onClick={() => setTab('plans')}>
          <MapIcon size={11} /> Mi plan
        </button>
        {isManager && (
          <button type="button" role="tab" aria-pressed={tab === 'kpis'} onClick={() => setTab('kpis')}>
            <Activity size={11} /> Panel HR
          </button>
        )}
      </div>

      {/* Panel KPIs (solo admin/HR) */}
      {tab === 'kpis' && isManager && <KPIDashboardTab cycles={cycles} />}

      {/* Plan de desarrollo (todos los usuarios ven el suyo) */}
      {tab === 'plans' && user && (
        <DevPlansTab subjectId={user.id} subjectName={user.full_name || 'Mi plan'} />
      )}

      {/* Ciclos */}
      {tab === 'cycles' && (
        loadingCycles ? <Spinner /> : cycles.length === 0 ? (
          <EmptyState svgIcon={<Star size={36} />}
            title="Sin ciclos de evaluación"
            description={isManager
              ? 'Crea el primer ciclo para iniciar evaluaciones.'
              : 'Cuando RR.HH. inicie un ciclo, aparecerá aquí.'} />
        ) : (
          <div data-export-table="performance-cycles-list" className="ds-stack">
            {cycles.map(c => (
              <CycleCard key={c.id} cycle={c} isManager={isManager}
                onActivate={activate}
                onCloseCycle={closeCycle}
                onAssign={setAssigningCycle}
                onCreateCampaign={setCampaigningCycle}
                onOpenDashboard={setOpenDashboardId}
              />
            ))}
          </div>
        )
      )}

      {/* Mis evaluaciones pendientes */}
      {tab === 'pending' && (
        <>
          {/* Acceso a mi evolución 360° (siempre visible en la pestaña) */}
          <div className="ds-card--inset" style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 'var(--space-3)',
          }}>
            <div>
              <div style={styles.titleSmBolder}>
                Mi evolución 360°
              </div>
              <div className="ds-muted" style={{ fontSize: 'var(--text-xs)' }}>
                Compara tus puntuaciones (others vs self) a lo largo de los ciclos cerrados.
              </div>
            </div>
            <Button variant="secondary" size="sm"
              onClick={() => setHistorySubject({ id: user?.id, name: user?.full_name })}>
              <TrendingUp size={12} /> Ver evolución
            </Button>
          </div>

          {loadingMine ? <Spinner /> : myReviews.length === 0 ? (
            <EmptyState svgIcon={<CheckCircle2 size={36} />}
              title="Sin evaluaciones pendientes"
              description="Cuando alguien te asigne una evaluación, aparecerá aquí." />
          ) : (
          <div data-export-table="performance-pending-list" className="ds-stack-sm">
            {myReviews.map(r => {
              const t = TYPE_BY_ID[r.review_type] || TYPE_BY_ID.peer
              const TypeIcon = t.Icon
              return (
                <div key={r.id} className="ds-card" style={{ flexDirection: 'row', alignItems: 'center', gap: 'var(--space-3)', padding: '14px 16px' }}>
                  <div style={{ width: 32, height: 32, borderRadius: 'var(--radius-md)',
                    background: 'var(--accent-muted)', color: 'var(--accent)',
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <TypeIcon size={16} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)' }}>
                      Evaluar a {r.reviewee_name}
                    </div>
                    <div className="ds-muted">{t.label} · {t.help}</div>
                  </div>
                  <Button onClick={() => setEditingReview(r)}>Rellenar evaluación</Button>
                </div>
              )
            })}
          </div>
          )}
        </>
      )}

      {showNewCycle && <NewCycleModal existingCycles={cycles} onClose={() => setShowNewCycle(false)} />}
      {editingReview && <ReviewForm review={editingReview} onClose={() => setEditingReview(null)} />}
      {assigningCycle && <AssignReviewModal cycle={assigningCycle} onClose={() => setAssigningCycle(null)} />}
      {campaigningCycle && (
        <New360CampaignModal cycle={campaigningCycle}
          onClose={() => setCampaigningCycle(null)} />
      )}
      {openDashboardId && (
        <Campaign360Dashboard campaignId={openDashboardId}
          onClose={() => setOpenDashboardId(null)}
          onOpenHistory={(id, name) => setHistorySubject({ id, name })} />
      )}
      {historySubject && (
        <History360Modal subjectId={historySubject.id}
          subjectName={historySubject.name}
          onClose={() => setHistorySubject(null)} />
      )}
    </Page>
  )
}
