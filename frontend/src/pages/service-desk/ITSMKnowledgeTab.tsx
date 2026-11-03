import { useAppT } from "../../hooks/useAppT";
import { useId, useState } from 'react'
import { useAppT as useAppTSimple } from '../../i18n/AppLangContext'
import type { ChangeEvent, CSSProperties } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import RcaWizardModal from '../../components/servicedesk/RcaWizardModal'

import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { sdKbApi, problemsApi } from '../../services/api'
import { Button, Spinner, EmptyState, Modal } from '../../components/ui'
import { COLOR, alpha } from '../../constants/theme'

type Priority = 'p1_critical' | 'p2_high' | 'p3_medium' | 'p4_low' | string
type ProblemStatus = 'open' | 'investigating' | 'known_error' | 'resolved' | 'closed' | string
type KbStatus = 'draft' | 'published' | 'archived' | string

type ProblemRecord = {
  id: string | number
  number?: string
  title: string
  description?: string
  root_cause?: string
  workaround?: string
  fix_description?: string
  priority?: Priority
  status?: ProblemStatus
  related_tickets?: Array<unknown>
  affected_tickets?: number
  ci?: string
}

type KbArticle = {
  id: string | number
  title: string
  summary?: string
  body?: string
  tags?: string
  status?: KbStatus
  is_public?: boolean
  helpful_count?: number
  view_count?: number
  deflection_count?: number
  review_comment?: string | null
}

type LinkedTicket = {
  id: string | number
  title?: string
  status?: string
}

type InputStyles = CSSProperties

const PRIORITY_COLOR: Record<string, string> = {
  p1_critical: COLOR.danger,
  p2_high: COLOR.orange,
  p3_medium: COLOR.warning,
  p4_low: COLOR.text2,
}

const PRIORITY_LABEL: Record<string, string> = {
  p1_critical: 'P1 Critico',
  p2_high: 'P2 Alto',
  p3_medium: 'P3 Medio',
  p4_low: 'P4 Bajo',
}

function PBadge({ v }: { v?: Priority }) {
  const color = PRIORITY_COLOR[v ?? ''] || COLOR.text2
  return (
    <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color, padding: '2px 7px', borderRadius: 4, border: `1px solid ${alpha(color, '30')}`, background: alpha(color, '12'), whiteSpace: 'nowrap' }}>
      {PRIORITY_LABEL[v ?? ''] || v}
    </span>
  )
}

function KELinkedTickets({ kedbId }: { kedbId: string | number }) {
  const { t } = useAppT()
  const { data: tickets, isLoading } = useQuery<LinkedTicket[]>({
    queryKey: ['sd-ke-tickets', kedbId],
    queryFn: () => sdKbApi.knownErrorTickets(kedbId).then(r => r.data as LinkedTicket[]).catch(() => []),
    staleTime: 30000,
  })
  if (isLoading) return <div style={{ padding: '8px 0' }}><Spinner /></div>
  if (!tickets?.length) return (
    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', padding: '8px 0', borderTop: '1px solid var(--surface-4)', marginTop: 10 }}>
      {t('itsmknowledge.no_hay_tickets_vinculados_a_este_error')}
    </div>
  )
  return (
    <div style={{ marginTop: 10, borderTop: '1px solid var(--surface-4)', paddingTop: 10 }}>
      <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 8 }}>Tickets vinculados</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {tickets.map((tk) => (
          <div key={tk.id} style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'var(--surface-4)', borderRadius: 6, padding: '6px 10px' }}>
            <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)' }}>#{tk.id}</span>
            <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', flex: 1 }}>{tk.title}</span>
            <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{tk.status}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function KnownErrors() {
  const { t } = useAppT()
  useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)
  const [editing, setEditing] = useState<ProblemRecord | null>(null)
  const [expandedKE, setExpandedKE] = useState<string | number | null>(null)

  const { data: kedb = [], isLoading } = useQuery<ProblemRecord[]>({
    queryKey: ['sd-kedb'],
    queryFn: () => sdKbApi.knownErrors().then(r => r.data as ProblemRecord[]),
  })
  const { mutate: updateProblem } = useMutation({
    mutationFn: ({ id, ...data }: { id: string | number } & Partial<ProblemRecord>) => problemsApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-kedb'] }); setEditing(null); toast.success('Error conocido actualizado') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const IS: InputStyles = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
          {t('itsmknowledge.base_de_errores_conocidos_problemas_con_causa')}
        </div>
        <Button onClick={() => { setEditing(null); setShowNew(true) }}>{t('itsmknowledge.nuevo_error_conocido')}</Button>
      </div>
      {isLoading ? <Spinner /> :
       kedb.length === 0 ? <EmptyState icon="📚" title={t('itsmknowledge.sin_errores_conocidos')} description="Crea el primer error conocido para documentar workaround y causa raíz." /> :
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {kedb.map((ke) => (
          <div key={ke.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
              <div style={{ flex: 1 }}>
                <span style={{ fontSize: "var(--text-xs)", color: COLOR.warning, fontWeight: 700, marginRight: 10 }}>{ke.number}</span>
                <span style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-1)' }}>{ke.title}</span>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <button
                  onClick={() => setExpandedKE(expandedKE === ke.id ? null : ke.id)}
                  style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', background: 'var(--surface-4)', padding: '2px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
                >
                  {ke.affected_tickets || 0} tickets {expandedKE === ke.id ? '▲' : '▼'}
                </button>
                <button onClick={() => setEditing(ke)} style={{ padding: '3px 10px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>✏ Editar</button>
              </div>
            </div>
            {ke.ci && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginBottom: 8 }}>CI afectado: {ke.ci}</div>}
            {ke.root_cause && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 4 }}>CAUSA RAIZ</div>
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{ke.root_cause}</div>
              </div>
            )}
            {ke.workaround ? (
              <div>
                <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: COLOR.success, marginBottom: 4 }}>WORKAROUND</div>
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', background: alpha(COLOR.success, '08'), border: `1px solid ${alpha(COLOR.success, '20')}`, borderRadius: 8, padding: '10px 14px' }}>
                  {ke.workaround}
                </div>
              </div>
            ) : ke.fix_description ? (
              <div>
                <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: COLOR.info, marginBottom: 4 }}>{t('itsmknowledge.solucion_definitiva')}</div>
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', background: alpha(COLOR.info, '08'), border: `1px solid ${alpha(COLOR.info, '20')}`, borderRadius: 8, padding: '10px 14px' }}>
                  {ke.fix_description}
                </div>
              </div>
            ) : null}
            {/* Linked tickets */}
            {expandedKE === ke.id && (
              <KELinkedTickets kedbId={ke.id} />
            )}
          </div>
        ))}
      </div>}

      {(showNew || editing) && (
        <KEDBModal
          item={editing}
          onClose={() => { setShowNew(false); setEditing(null) }}
          onSaved={(data: Partial<ProblemRecord>) => {
            if (editing) {
              updateProblem({ id: editing.id, ...data })
            } else {
              problemsApi.create(data).then(() => {
                qc.invalidateQueries({ queryKey: ['sd-kedb'] })
                setShowNew(false)
                toast.success('Error conocido creado')
              }).catch(e => toast.error(e?.response?.data?.detail || 'Error'))
            }
          }}
          IS={IS} LS={LS}
        />
      )}
    </div>
  )
}

type KEDBModalProps = {
  item: ProblemRecord | null
  onClose: () => void
  onSaved: (data: Partial<ProblemRecord>) => void
  IS: InputStyles
  LS: CSSProperties
}

function KEDBModal({ item, onClose, onSaved, IS, LS }: KEDBModalProps) {
  const { t } = useAppT()
  const idPrefix = useId()
  const isEdit = !!item
  const [form, setForm] = useState({
    title: item?.title || '',
    description: item?.description || '',
    root_cause: item?.root_cause || '',
    workaround: item?.workaround || '',
    fix_description: item?.fix_description || '',
    priority: item?.priority || 'p3_medium',
    status: item?.status || 'known_error',
  })
  const set = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <Modal open title={isEdit ? 'Editar error conocido' : 'Nuevo error conocido (KEDB)'} onClose={onClose} size="lg">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div><label htmlFor={`${idPrefix}-title`} style={LS}>Titulo *</label><input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} style={IS} placeholder={t('itsmknowledge.titulo_del_error_conocido')} /></div>
        <div><label htmlFor={`${idPrefix}-description`} style={LS}>Descripcion</label><textarea id={`${idPrefix}-description`} value={form.description} onChange={set('description')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.describe_el_error_conocido')} /></div>
        <div><label htmlFor={`${idPrefix}-root-cause`} style={LS}>Causa raiz</label><textarea id={`${idPrefix}-root-cause`} value={form.root_cause} onChange={set('root_cause')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.causa_raiz_identificada')} /></div>
        <div><label htmlFor={`${idPrefix}-workaround`} style={LS}>{t('itsmknowledge.workaround_solucion_temporal')}</label><textarea id={`${idPrefix}-workaround`} value={form.workaround} onChange={set('workaround')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.solucion_temporal_disponible')} /></div>
        <div><label htmlFor={`${idPrefix}-fix-description`} style={LS}>{t('itsmknowledge.solucion_definitiva_2')}</label><textarea id={`${idPrefix}-fix-description`} value={form.fix_description} onChange={set('fix_description')} rows={2} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.solucion_definitiva_aplicada')} /></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div><label htmlFor={`${idPrefix}-priority`} style={LS}>Prioridad</label><select id={`${idPrefix}-priority`} value={form.priority} onChange={set('priority')} style={IS}>{['p1_critical', 'p2_high', 'p3_medium', 'p4_low'].map(p => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}</select></div>
          <div><label htmlFor={`${idPrefix}-status`} style={LS}>Estado</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} style={IS}>{[['open', 'Abierto'], ['investigating', 'Investigando'], ['known_error', 'Error conocido'], ['resolved', 'Resuelto']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => onSaved(form)} disabled={!form.title.trim()}>{isEdit ? 'Guardar cambios' : 'Crear error conocido'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function Problems() {
  const { t } = useAppT()
  useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<ProblemRecord | null>(null)
  const [rcaWizardProblem, setRcaWizardProblem] = useState<ProblemRecord | null>(null)

  const { data: problems = [], isLoading } = useQuery<ProblemRecord[]>({
    queryKey: ['sd-problems'],
    queryFn: () => problemsApi.list().then(r => r.data as ProblemRecord[]),
  })
  const { mutate: createProblem, isPending: creating } = useMutation({
    mutationFn: (data: Partial<ProblemRecord>) => problemsApi.create(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-problems'] }); setShowModal(false); toast.success('Problema creado') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: updateProblem, isPending: updating } = useMutation({
    mutationFn: ({ id, ...data }: { id: string | number } & Partial<ProblemRecord>) => problemsApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-problems'] }); setEditing(null); toast.success('Problema actualizado') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteProblem } = useMutation({
    mutationFn: (id: string | number) => problemsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-problems'] }); toast.success('Problema eliminado') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: promoteToKE, variables: promotingId } = useMutation({
    mutationFn: (id: string | number) => problemsApi.promoteKnownError(id),
    onSuccess: () => {
      toast.success('Problema promovido a Error Conocido (KEDB)')
      qc.invalidateQueries({ queryKey: ['sd-problems'] })
      qc.invalidateQueries({ queryKey: ['sd-kedb'] })
    },
    onError: e => toast.error(extractErr(e, 'Error al promover')),
  })

  const IS: InputStyles = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  const statusColors: Record<string, string> = {
    open: COLOR.danger,
    investigating: COLOR.warning,
    known_error: 'var(--orange)',
    resolved: COLOR.success,
    closed: COLOR.text2,
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
          {t('itsmknowledge.registro_de_problemas_causas_raiz_de_incidentes')}
        </div>
        <Button onClick={() => { setEditing(null); setShowModal(true) }}>{t('itsmknowledge.nuevo_problema')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       problems.length === 0
        ? <EmptyState icon="🔍" title={t('itsmknowledge.sin_problemas_registrados')} description="Crea el primer problema para investigar incidentes recurrentes." />
        : <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {problems.map((p) => {
              const sc = statusColors[p.status ?? ''] || COLOR.text2
              return (
                <div key={p.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '16px 20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                        <span style={{ fontSize: "var(--text-xs)", color: COLOR.warning, fontWeight: 700 }}>{p.number}</span>
                        <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: sc, background: alpha(sc, '15'), padding: '2px 8px', borderRadius: 4 }}>
                          {p.status?.replace(/_/g, ' ')}
                        </span>
                        <PBadge v={p.priority} />
                        {(p.related_tickets ?? []).length > 0 && (
                          <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                            {(p.related_tickets ?? []).length} ticket{(p.related_tickets ?? []).length !== 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-1)' }}>{p.title}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                      <button onClick={() => setRcaWizardProblem(p)} style={{ padding: '4px 10px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--info)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>🔍 RCA</button>
                      {p.status !== 'known_error' && (
                        <button
                          onClick={() => openConfirmGlobal({ message: `¿Promover "${p.title}" a Error Conocido (KEDB)?`, onConfirm: () => promoteToKE(p.id), danger: false })}
                          disabled={promotingId === p.id}
                          style={{ padding: '4px 10px', borderRadius: 6, border: '1px solid rgba(251,146,60,0.4)', background: 'transparent', color: 'var(--orange)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}
                        >
                          📋 Promover a KE
                        </button>
                      )}
                      <button onClick={() => { setEditing(p); setShowModal(true) }} style={{ padding: '4px 10px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>✏ Editar</button>
                      <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar "${p.title}"? Esta acción no se puede deshacer.`, onConfirm: () => deleteProblem(p.id), danger: true }) }} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid rgba(255,71,87,0.3)', background: 'transparent', color: COLOR.danger, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>🗑</button>
                    </div>
                  </div>
                  {p.root_cause && (
                    <div style={{ marginBottom: 8 }}>
                      <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', marginRight: 8 }}>Causa raiz</span>
                      <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{p.root_cause}</span>
                    </div>
                  )}
                  {p.workaround && (
                    <div style={{ background: alpha(COLOR.success, '08'), border: `1px solid ${alpha(COLOR.success, '20')}`, borderRadius: 8, padding: '8px 12px' }}>
                      <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: COLOR.success, textTransform: 'uppercase', marginRight: 8 }}>Workaround</span>
                      <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>{p.workaround}</span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
      }

      {showModal && (
        <ProblemModal
          item={editing}
          onClose={() => { setShowModal(false); setEditing(null) }}
          onSaved={(data: Partial<ProblemRecord>) => editing
            ? updateProblem({ id: editing.id, ...data })
            : createProblem(data)
          }
          isPending={creating || updating}
          IS={IS} LS={LS}
        />
      )}
      {rcaWizardProblem && (
        <RcaWizardModal
          problem={rcaWizardProblem}
          onClose={() => setRcaWizardProblem(null)}
          onCompleted={() => qc.invalidateQueries({ queryKey: ['sd-problems'] })}
        />
      )}
    </div>
  )
}

type ProblemModalProps = {
  item: ProblemRecord | null
  onClose: () => void
  onSaved: (data: Partial<ProblemRecord>) => void
  isPending: boolean
  IS: InputStyles
  LS: CSSProperties
}

function ProblemModal({ item, onClose, onSaved, isPending, IS, LS }: ProblemModalProps) {
  const { t } = useAppT()
  const idPrefix = useId()
  const isEdit = !!item
  const [form, setForm] = useState({
    title: item?.title || '',
    description: item?.description || '',
    root_cause: item?.root_cause || '',
    workaround: item?.workaround || '',
    fix_description: item?.fix_description || '',
    priority: item?.priority || 'p3_medium',
    status: item?.status || 'open',
  })
  const set = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))
  return (
    <Modal open title={isEdit ? `Editar - ${item.number}` : 'Nuevo problema'} onClose={onClose} size="lg">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div><label htmlFor={`${idPrefix}-title`} style={LS}>Titulo *</label><input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} style={IS} placeholder={t('itsmknowledge.titulo_del_problema')} /></div>
        <div><label htmlFor={`${idPrefix}-description`} style={LS}>Descripcion</label><textarea id={`${idPrefix}-description`} value={form.description} onChange={set('description')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.describe_el_problema')} /></div>
        <div><label htmlFor={`${idPrefix}-root-cause`} style={LS}>Causa raiz</label><textarea id={`${idPrefix}-root-cause`} value={form.root_cause} onChange={set('root_cause')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.causa_raiz_identificada')} /></div>
        <div><label htmlFor={`${idPrefix}-workaround`} style={LS}>Workaround (solucion temporal)</label><textarea id={`${idPrefix}-workaround`} value={form.workaround} onChange={set('workaround')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.solucion_temporal')} /></div>
        <div><label htmlFor={`${idPrefix}-fix-description`} style={LS}>Solucion definitiva (opcional)</label><textarea id={`${idPrefix}-fix-description`} value={form.fix_description} onChange={set('fix_description')} rows={2} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.solucion_definitiva_2')} /></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div><label htmlFor={`${idPrefix}-priority`} style={LS}>Prioridad</label><select id={`${idPrefix}-priority`} value={form.priority} onChange={set('priority')} style={IS}>{[['p1_critical', 'P1 Critico'], ['p2_high', 'P2 Alto'], ['p3_medium', 'P3 Medio'], ['p4_low', 'P4 Bajo']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
          <div><label htmlFor={`${idPrefix}-status`} style={LS}>Estado</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} style={IS}>{[['open', 'Abierto'], ['investigating', 'Investigando'], ['known_error', 'Error conocido'], ['resolved', 'Resuelto'], ['closed', 'Cerrado']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => onSaved(form)} disabled={isPending || !form.title.trim()} loading={isPending}>{isEdit ? 'Guardar cambios' : 'Crear problema'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function KB() {
  const { t } = useAppT()
  useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [editing, setEditing] = useState<KbArticle | null>(null)
  const ts = useAppTSimple()
  const [devolviendo, setDevolviendo] = useState<KbArticle | null>(null)
  const [nota, setNota] = useState('')
  const refrescarKb = () => qc.invalidateQueries({ queryKey: ['sd-kb'] })
  const { mutate: enviarARevision } = useMutation({
    mutationFn: (id: string | number) => sdKbApi.submit(id),
    onSuccess: refrescarKb, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: revisar } = useMutation({
    mutationFn: ({ id, publish, comment }: { id: string | number; publish: boolean; comment?: string }) => sdKbApi.review(id, { publish, comment }),
    onSuccess: () => { refrescarKb(); setDevolviendo(null); setNota('') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { data: articles = [], isLoading } = useQuery<KbArticle[]>({
    queryKey: ['sd-kb', search],
    queryFn: () => sdKbApi.list({ search: search || undefined }).then(r => r.data as KbArticle[]),
    staleTime: 30000,
  })
  const { mutate: deleteArticle } = useMutation({
    mutationFn: (id: string | number) => sdKbApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-kb'] }); toast.success('Articulo eliminado') },
    onError: () => toast.error('Error al eliminar'),
  })
  const { mutate: toggleStatus } = useMutation({
    mutationFn: ({ id, status }: { id: string | number; status: KbStatus }) => sdKbApi.update(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-kb'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const IS: InputStyles = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }

  const STATUS_COLOR: Record<string, string> = { published: COLOR.success, draft: COLOR.warning, in_review: 'var(--accent)', archived: COLOR.text2 }

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        <input placeholder={t('itsmknowledge.buscar_articulos')} aria-label={t('itsmknowledge.buscar_articulos')} value={search} onChange={e => setSearch(e.target.value)} style={{ ...IS, flex: 1 }} />
        <Button onClick={() => { setEditing(null); setShowNew(true) }}>{t('itsmknowledge.nuevo_articulo')}</Button>
      </div>
      {isLoading ? <Spinner /> :
      articles.length === 0 ? <EmptyState icon="📖" title={t('itsmknowledge.sin_articulos')} description="Crea el primer artículo de conocimiento." /> :
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px,1fr))', gap: 14 }}>
        {articles.map((a) => (
          <div key={a.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-1)', flex: 1, marginRight: 8 }}>{a.title}</div>
              <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, whiteSpace: 'nowrap', background: alpha(STATUS_COLOR[a.status ?? ''] || COLOR.text2, '15'), color: STATUS_COLOR[a.status ?? ''] || COLOR.text2 }}>
                {a.status ? ts(`sd_cfg.kb_status_${a.status}`) : ''}
              </span>
            </div>
            {a.summary && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>{a.summary}</div>}
            {a.review_comment && a.status === 'draft' && <div style={{ fontSize: "var(--text-xs)", color: COLOR.warning, marginBottom: 10 }}>{ts('sd_cfg.kb_review_note', { note: a.review_comment })}</div>}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 12 }}>
              <span>👍 {a.helpful_count || 0}</span>
              <span>👁 {a.view_count || 0}</span>
              {(a.deflection_count ?? 0) > 0 && <span>{ts('sd_cfg.kb_deflections', { n: a.deflection_count ?? 0 })}</span>}
              {a.tags && <span>🏷 {a.tags.split(',').slice(0, 2).join(', ')}</span>}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button onClick={() => { setEditing(a); setShowNew(true) }} style={{ flex: 1, padding: '5px 0', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>✏ Editar</button>
              {a.status === 'in_review' ? <>
                <button onClick={() => revisar({ id: a.id, publish: true })} style={{ flex: 1, padding: '5px 0', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: COLOR.success, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>▶ {ts('sd_cfg.kb_publish')}</button>
                <button onClick={() => setDevolviendo(a)} style={{ flex: 1, padding: '5px 0', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: COLOR.warning, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>↩ {ts('sd_cfg.kb_return')}</button>
              </> : <>
                <button onClick={() => toggleStatus({ id: a.id, status: a.status === 'published' ? 'draft' : 'published' })} style={{ flex: 1, padding: '5px 0', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>{a.status === 'published' ? `⏸ ${ts('sd_cfg.kb_unpublish')}` : `▶ ${ts('sd_cfg.kb_publish')}`}</button>
                {a.status === 'draft' && <button onClick={() => enviarARevision(a.id)} style={{ flex: 1, padding: '5px 0', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>{ts('sd_cfg.kb_submit')}</button>}
              </>}
              <button onClick={() => { openConfirmGlobal({ message: 'Eliminar articulo?', onConfirm: () => deleteArticle(a.id), danger: true }) }} style={{ padding: '5px 8px', borderRadius: 6, border: `1px solid ${alpha(COLOR.danger, '30')}`, background: 'transparent', color: COLOR.danger, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>🗑</button>
            </div>
          </div>
        ))}
      </div>}

      {devolviendo && (
        <Modal open title={`${ts('sd_cfg.kb_return')} · ${devolviendo.title}`} onClose={() => setDevolviendo(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <textarea aria-label={ts('sd_cfg.kb_return_note')} placeholder={ts('sd_cfg.kb_return_note')} rows={4} value={nota} onChange={e => setNota(e.target.value)} style={{ ...IS, resize: 'vertical' }} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <Button variant="secondary" onClick={() => setDevolviendo(null)}>{ts('common.cancel')}</Button>
              <Button disabled={!nota.trim()} onClick={() => revisar({ id: devolviendo.id, publish: false, comment: nota.trim() })}>{ts('sd_cfg.kb_return')}</Button>
            </div>
          </div>
        </Modal>
      )}
      {showNew && <KBArticleModal article={editing} onClose={() => { setShowNew(false); setEditing(null) }} onSaved={() => { qc.invalidateQueries({ queryKey: ['sd-kb'] }); setShowNew(false); setEditing(null) }} />}
    </div>
  )
}

type KBArticleModalProps = {
  article: KbArticle | null
  onClose: () => void
  onSaved: () => void
}

function KBArticleModal({ article, onClose, onSaved }: KBArticleModalProps) {
  const { t } = useAppT()
  const idPrefix = useId()
  const toast = useToast()
  const isEdit = !!article
  const [form, setForm] = useState({
    title: article?.title || '',
    summary: article?.summary || '',
    body: article?.body || '',
    tags: article?.tags || '',
    status: article?.status || 'draft',
    is_public: article?.is_public ?? true,
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (data: typeof form) => isEdit && article ? sdKbApi.update(article.id, data) : sdKbApi.create(data),
    onSuccess: () => { toast.success(isEdit ? 'Articulo actualizado' : 'Articulo creado'); onSaved() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const set = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value }))
  const IS: InputStyles = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <Modal open title={isEdit ? 'Editar articulo KB' : 'Nuevo articulo KB'} onClose={onClose} size="lg">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div><label style={LS}>Titulo *</label><input value={form.title} onChange={set('title')} style={IS} /></div>
        <div><label htmlFor={`${idPrefix}-summary`} style={LS}>Resumen</label><input id={`${idPrefix}-summary`} value={form.summary} onChange={set('summary')} style={IS} placeholder={t('itsmknowledge.resumen_del_articulo')} /></div>
        <div><label htmlFor={`${idPrefix}-body`} style={LS}>Contenido *</label><textarea id={`${idPrefix}-body`} value={form.body} onChange={set('body')} rows={8} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.contenido_del_articulo')} /></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div><label htmlFor={`${idPrefix}-tags`} style={LS}>{t('itsmknowledge.etiquetas_separadas_por_coma')}</label><input id={`${idPrefix}-tags`} value={form.tags} onChange={set('tags')} style={IS} placeholder="etiqueta1, etiqueta2" /></div>
          <div><label htmlFor={`${idPrefix}-status`} style={LS}>Estado</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} style={IS}><option value="draft">Borrador</option><option value="published">Publicado</option><option value="archived">Archivado</option></select></div>
        </div>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: "var(--text-base)", color: 'var(--text-1)', cursor: 'pointer' }}><input type="checkbox" checked={form.is_public} onChange={set('is_public')} />{t('itsmknowledge.visible_en_el_portal_cliente')}</label>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title || !form.body} loading={isPending}>{isEdit ? 'Guardar cambios' : 'Crear articulo'}</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function ITSMKnowledgeTab({ mode }: { mode: 'problems' | 'kedb' | 'kb' | string }) {
  if (mode === 'problems') return <Problems />
  if (mode === 'kedb') return <KnownErrors />
  return <KB />
}
