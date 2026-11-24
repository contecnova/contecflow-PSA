/**
 * Editor de preguntas de un ciclo y su modal de edición.
 * Troceado de PerformanceReviewsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useAppLang, useAppT } from '../../i18n/AppLangContext'
import { useState, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { performanceApi } from '../../services/api'
import { Button, Checkbox, Modal, Select, Spinner, Input, IconButton } from '../../components/ui'
import { Plus, Save, Pencil, Trash2, ListChecks } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { isRatingKind, KIND_LABEL, type Question, QUESTION_KINDS, type QuestionPayload } from './compartido'

// ── QuestionsEditor: edita la plantilla de preguntas de un ciclo en draft ───
export function QuestionsEditor({ cycleId, cycleStatus }: { cycleId: string; cycleStatus: string }) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const editable = cycleStatus === 'draft'

  const { data: questions = [], isLoading } = useQuery<Question[]>({
    queryKey: ['perf-cycle-questions', cycleId],
    queryFn: () => performanceApi.listQuestions(cycleId).then(r => r.data),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['perf-cycle-questions', cycleId] })

  const { mutate: addQ } = useMutation({
    mutationFn: (data: QuestionPayload) => performanceApi.addQuestion(cycleId, data),
    onSuccess: () => { invalidate(); toast.success(t('pagina_perf.pregunta_anadida')) },
    onError: e => toast.error(extractErr(e, t('pagina_perf.error_al_anadir'))),
  })
  const { mutate: updateQ } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: QuestionPayload }) => performanceApi.updateQuestion(id, data),
    onSuccess: () => { invalidate(); toast.success(t('pagina_perf.pregunta_actualizada')) },
    onError: e => toast.error(extractErr(e, t('pagina_perf.error_al_actualizar'))),
  })
  const { mutate: removeQ } = useMutation({
    mutationFn: (id: string) => performanceApi.deleteQuestion(id),
    onSuccess: () => { invalidate(); toast.success(t('pagina_perf.pregunta_eliminada')) },
    onError: e => toast.error(extractErr(e, t('pagina_perf.error_al_eliminar'))),
  })

  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Question | null>(null)

  if (isLoading) return <Spinner />

  return (
    <div className="ds-card--inset perf-stack-2">
      <div className="ds-row-between">
        <div className="ds-eyebrow performance-reviews-page-e13">
          <ListChecks size={12} /> {traducir('performancereviews.plantilla_de_preguntas')}{questions.length})
        </div>
        {editable && (
          <Button size="sm" variant="secondary" onClick={() => setAdding(true)}>
            <Plus size={11} /> {traducir('performancereviews.anadir')}
          </Button>
        )}
      </div>
      {questions.length === 0 ? (
        <div className="ds-muted u-sm">
          {traducir('performancereviews.sin_preguntas')} {editable && t('pagina_perf.anade_alguna_o_siembra_las_predeterminadas')}
        </div>
      ) : (
        <div className="ds-stack-sm">
          {questions.map(q => (
            <div key={q.id} className="ds-row-between performance-reviews-page-e14">
              <div className="performance-reviews-page-e8">
                <div className="performance-reviews-page-e9">
                  {q.label}{q.required && <span className="performance-reviews-page-e10"> *</span>}
                </div>
                <div className="ds-muted u-xs">
                  {KIND_LABEL[q.kind] ? t(KIND_LABEL[q.kind]) : q.kind}{' '}{t('pagina_perf.key')}{q.key}
                </div>
              </div>
              {editable && (
                <div className="ui-acciones">
                  <IconButton variante="caja" onClick={() => setEditing(q)} ariaLabel={t('pagina_perf.editar')}>
                    <Pencil size={11} />
                  </IconButton>
                  <IconButton variante="caja" tono="peligro" onClick={async () => {
                    if (await confirmar({ message: t('pagina_perf.eliminar_pregunta', { label: q.label }), danger: true, confirmLabel: t('pagina_perf.eliminar') })) removeQ(q.id)
                  }} ariaLabel={t('pagina_perf.eliminar')}>
                    <Trash2 size={11} />
                  </IconButton>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {!editable && (
        <div className="ds-muted u-xs">
          {traducir('performancereviews.la_plantilla_solo_es_editable_mientras_el')}
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

function QuestionEditModal({ question, onClose, onSave }: {
  question?: Question; onClose: () => void; onSave: (data: QuestionPayload) => void
}) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
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
    const data: QuestionPayload = {
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
    <Modal open onClose={onClose} title={isEdit ? t('pagina_perf.editar_pregunta') : t('pagina_perf.nueva_pregunta')} width={520}>
      <div className="ds-stack">
        {!isEdit && (
          <Input label={t('pagina_perf.identificador_opcional')} id={`${idCampo}-1`} value={form.key} onChange={e => setForm(f => ({ ...f, key: e.target.value }))} placeholder={traducir('performancereviews.se_genera_del_titulo_si_lo_dejas')} />
        )}
        <Input label={t('pagina_perf.pregunta')} id={`${idCampo}-2`} value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))} placeholder={traducir('performancereviews.ej_calidad_del_trabajo')} autoFocus />
        <Input label={t('pagina_perf.ayuda_opcional')} id={`${idCampo}-3`} value={form.hint} onChange={e => setForm(f => ({ ...f, hint: e.target.value }))} placeholder={traducir('performancereviews.texto_pequeno_de_apoyo_bajo_la_pregunta')} />
        <div className="performance-reviews-page-e15">
          <Select label={t('pagina_perf.tipo')} placeholder={false} id={`${idCampo}-4`} value={form.kind} onChange={e => setForm(f => ({ ...f, kind: e.target.value }))}>
              {QUESTION_KINDS.map(k => <option key={k.id} value={k.id}>{t(k.label)}</option>)}
            </Select>
          <div className="ds-field perf-box-6">
            <Checkbox className="perf-label-2" checked={!!form.required}
              onChange={v => setForm(f => ({ ...f, required: v }))} label={t('pagina_perf.obligatoria')} />
          </div>
        </div>
        {isRatingKind(form.kind) && (
          <div className="performance-reviews-page-e15">
            <Input label={traducir('performancereviews.escala_min')} id={`${idCampo}-5`} type="number" value={form.scale_min} onChange={e => setForm(f => ({ ...f, scale_min: e.target.value }))} placeholder="1" />
            <Input label={traducir('performancereviews.escala_max')} id={`${idCampo}-6`} type="number" value={form.scale_max} onChange={e => setForm(f => ({ ...f, scale_max: e.target.value }))} placeholder={form.kind === 'rating_10' ? '10' : '5'} />
          </div>
        )}
        <div className="performance-reviews-page-e12">
          <Button variant="secondary" onClick={onClose}>{t('pagina_perf.cancelar')}</Button>
          <Button onClick={submit} disabled={!form.label.trim()}>
            <Save size={13} />{' '}{t('pagina_perf.guardar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
