import { useAppT } from "../../hooks/useAppT";
import DocumentosDeFicha from '../../components/conectores/DocumentosDeFicha'
import { useId, useState } from 'react'
import { useAppT as useAppTSimple } from '../../i18n/AppLangContext'
import type { ChangeEvent, CSSProperties } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import RcaWizardModal from '../../components/servicedesk/RcaWizardModal'

import { extractErr, fmtDateTime } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { sdKbApi, problemsApi } from '../../services/api'
import { Button, Spinner, EmptyState, Modal } from '../../components/ui'
import MarkdownText from '../../components/ui/MarkdownText'
import { COLOR, alpha } from '../../constants/theme'
import { etiquetaSd, SBadge } from './sdUtils'
import StatusBadge from '../../components/ui/StatusBadge'
import { DELAYED_REFETCH_MS, STALE_SHORT_MS } from '../../constants/timings'

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
    <StatusBadge color={color} caps={false}>{PRIORITY_LABEL[v ?? ''] || v}</StatusBadge>
  )
}

function KELinkedTickets({ kedbId }: { kedbId: string | number }) {
  const { t } = useAppT()
  const { data: tickets, isLoading } = useQuery<LinkedTicket[]>({
    queryKey: ['sd-ke-tickets', kedbId],
    queryFn: () => sdKbApi.knownErrorTickets(kedbId).then(r => r.data as LinkedTicket[]).catch(() => []),
    staleTime: STALE_SHORT_MS,
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
      <div className="u-stack-6">
        {tickets.map((tk) => (
          <div key={tk.id} style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '6px 10px' }}>
            <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)' }}>#{tk.id}</span>
            <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', flex: 1 }}>{tk.title}</span>
            <SBadge v={String(tk.status ?? '')} />
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
      <div className="u-row-between-mb16">
        <div className="u-text3-sm">
          {t('itsmknowledge.base_de_errores_conocidos_problemas_con_causa')}
        </div>
        <Button onClick={() => { setEditing(null); setShowNew(true) }}>{t('itsmknowledge.nuevo_error_conocido')}</Button>
      </div>
      {isLoading ? <Spinner /> :
       kedb.length === 0 ? <EmptyState icon="📚" title={t('itsmknowledge.sin_errores_conocidos')} description="Crea el primer error conocido para documentar workaround y causa raíz." /> :
      <div className="u-stack-12">
        {kedb.map((ke) => (
          <div key={ke.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
              <div className="u-flex1">
                <span style={{ fontSize: "var(--text-xs)", color: COLOR.warning, fontWeight: 700, marginRight: 10 }}>{ke.number}</span>
                <span style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-1)' }}>{ke.title}</span>
              </div>
              <div className="u-row-center-8">
                <button
                  onClick={() => setExpandedKE(expandedKE === ke.id ? null : ke.id)}
                  style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', background: 'var(--surface-4)', padding: '2px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
                >
                  {ke.affected_tickets || 0} tickets {expandedKE === ke.id ? '▲' : '▼'}
                </button>
                <button onClick={() => setEditing(ke)} style={{ padding: '3px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>✏ Editar</button>
              </div>
            </div>
            {ke.ci && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginBottom: 8 }}>CI afectado: {ke.ci}</div>}
            {ke.root_cause && (
              <div className="u-mb-10">
                <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 4 }}>CAUSA RAIZ</div>
                <div className="u-text2-base">{ke.root_cause}</div>
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
      <div className="u-stack-14">
        <div><label id={`${idPrefix}-title-et`} htmlFor={`${idPrefix}-title`} style={LS}>Titulo *</label><input id={`${idPrefix}-title`} aria-labelledby={`${idPrefix}-title-et`} value={form.title} onChange={set('title')} style={IS} placeholder={t('itsmknowledge.titulo_del_error_conocido')} /></div>
        <div><label id={`${idPrefix}-description-et`} htmlFor={`${idPrefix}-description`} style={LS}>Descripcion</label><textarea id={`${idPrefix}-description`} aria-labelledby={`${idPrefix}-description-et`} value={form.description} onChange={set('description')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.describe_el_error_conocido')} /></div>
        <div><label id={`${idPrefix}-root-cause-et`} htmlFor={`${idPrefix}-root-cause`} style={LS}>Causa raiz</label><textarea id={`${idPrefix}-root-cause`} aria-labelledby={`${idPrefix}-root-cause-et`} value={form.root_cause} onChange={set('root_cause')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.causa_raiz_identificada')} /></div>
        <div><label id={`${idPrefix}-workaround-et`} htmlFor={`${idPrefix}-workaround`} style={LS}>{t('itsmknowledge.workaround_solucion_temporal')}</label><textarea id={`${idPrefix}-workaround`} aria-labelledby={`${idPrefix}-workaround-et`} value={form.workaround} onChange={set('workaround')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.solucion_temporal_disponible')} /></div>
        <div><label id={`${idPrefix}-fix-description-et`} htmlFor={`${idPrefix}-fix-description`} style={LS}>{t('itsmknowledge.solucion_definitiva_2')}</label><textarea id={`${idPrefix}-fix-description`} aria-labelledby={`${idPrefix}-fix-description-et`} value={form.fix_description} onChange={set('fix_description')} rows={2} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.solucion_definitiva_aplicada')} /></div>
        <div className="u-grid2-12">
          <div><label htmlFor={`${idPrefix}-priority`} style={LS}>Prioridad</label><select id={`${idPrefix}-priority`} value={form.priority} onChange={set('priority')} style={IS}>{['p1_critical', 'p2_high', 'p3_medium', 'p4_low'].map(p => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}</select></div>
          <div><label htmlFor={`${idPrefix}-status`} style={LS}>Estado</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} style={IS}>{[['open', 'Abierto'], ['investigating', 'Investigando'], ['known_error', 'Error conocido'], ['resolved', 'Resuelto']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        </div>
        <div className="u-actions-10">
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
      <div className="u-row-between-mb16">
        <div className="u-text3-sm">
          {t('itsmknowledge.registro_de_problemas_causas_raiz_de_incidentes')}
        </div>
        <Button onClick={() => { setEditing(null); setShowModal(true) }}>{t('itsmknowledge.nuevo_problema')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       problems.length === 0
        ? <EmptyState icon="🔍" title={t('itsmknowledge.sin_problemas_registrados')} description="Crea el primer problema para investigar incidentes recurrentes." />
        : <div className="u-stack-10">
            {problems.map((p) => {
              const sc = statusColors[p.status ?? ''] || COLOR.text2
              return (
                <div key={p.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '16px 20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div className="u-flex1">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                        <span style={{ fontSize: "var(--text-xs)", color: COLOR.warning, fontWeight: 700 }}>{p.number}</span>
                        <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: sc, background: alpha(sc, '15'), padding: '2px 8px', borderRadius: 4 }}>
                          {etiquetaSd('prb_st', p.status)}
                        </span>
                        <PBadge v={p.priority} />
                        {(p.related_tickets ?? []).length > 0 && (
                          <span className="u-text3-xs">
                            {(p.related_tickets ?? []).length} ticket{(p.related_tickets ?? []).length !== 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-1)' }}>{p.title}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                      <button onClick={() => setRcaWizardProblem(p)} style={{ padding: '4px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--info)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>🔍 RCA</button>
                      {p.status !== 'known_error' && (
                        <button
                          onClick={() => openConfirmGlobal({ message: `¿Promover "${p.title}" a Error Conocido (KEDB)?`, onConfirm: () => promoteToKE(p.id), danger: false })}
                          disabled={promotingId === p.id}
                          style={{ padding: '4px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(251,146,60,0.4)', background: 'transparent', color: 'var(--orange)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}
                        >
                          📋 Promover a KE
                        </button>
                      )}
                      <button onClick={() => { setEditing(p); setShowModal(true) }} style={{ padding: '4px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>✏ Editar</button>
                      <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar "${p.title}"? Esta acción no se puede deshacer.`, onConfirm: () => deleteProblem(p.id), danger: true }) }} style={{ padding: '4px 8px', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(255,71,87,0.3)', background: 'transparent', color: COLOR.danger, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>🗑</button>
                    </div>
                  </div>
                  {p.root_cause && (
                    <div style={{ marginBottom: 8 }}>
                      <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', marginRight: 8 }}>Causa raiz</span>
                      <span className="u-text2-sm">{p.root_cause}</span>
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
      <div className="u-stack-14">
        <div><label id={`${idPrefix}-title-et`} htmlFor={`${idPrefix}-title`} style={LS}>Titulo *</label><input id={`${idPrefix}-title`} aria-labelledby={`${idPrefix}-title-et`} value={form.title} onChange={set('title')} style={IS} placeholder={t('itsmknowledge.titulo_del_problema')} /></div>
        <div><label id={`${idPrefix}-description-et`} htmlFor={`${idPrefix}-description`} style={LS}>Descripcion</label><textarea id={`${idPrefix}-description`} aria-labelledby={`${idPrefix}-description-et`} value={form.description} onChange={set('description')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.describe_el_problema')} /></div>
        <div><label id={`${idPrefix}-root-cause-et`} htmlFor={`${idPrefix}-root-cause`} style={LS}>Causa raiz</label><textarea id={`${idPrefix}-root-cause`} aria-labelledby={`${idPrefix}-root-cause-et`} value={form.root_cause} onChange={set('root_cause')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.causa_raiz_identificada')} /></div>
        <div><label id={`${idPrefix}-workaround-et`} htmlFor={`${idPrefix}-workaround`} style={LS}>Workaround (solucion temporal)</label><textarea id={`${idPrefix}-workaround`} aria-labelledby={`${idPrefix}-workaround-et`} value={form.workaround} onChange={set('workaround')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.solucion_temporal')} /></div>
        <div><label id={`${idPrefix}-fix-description-et`} htmlFor={`${idPrefix}-fix-description`} style={LS}>Solucion definitiva (opcional)</label><textarea id={`${idPrefix}-fix-description`} aria-labelledby={`${idPrefix}-fix-description-et`} value={form.fix_description} onChange={set('fix_description')} rows={2} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.solucion_definitiva_2')} /></div>
        <div className="u-grid2-12">
          <div><label htmlFor={`${idPrefix}-priority`} style={LS}>Prioridad</label><select id={`${idPrefix}-priority`} value={form.priority} onChange={set('priority')} style={IS}>{[['p1_critical', 'P1 Critico'], ['p2_high', 'P2 Alto'], ['p3_medium', 'P3 Medio'], ['p4_low', 'P4 Bajo']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
          <div><label htmlFor={`${idPrefix}-status`} style={LS}>Estado</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} style={IS}>{[['open', 'Abierto'], ['investigating', 'Investigando'], ['known_error', 'Error conocido'], ['resolved', 'Resuelto'], ['closed', 'Cerrado']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        </div>
        <div className="u-actions-10">
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
  // Revisión 2026-11: un artículo sólo se podía abrir editándolo.
  const [leyendo, setLeyendo] = useState<string | number | null>(null)
  const [devolviendo, setDevolviendo] = useState<KbArticle | null>(null)
  const [nota, setNota] = useState('')
  const [vista, setVista] = useState<'articulos' | 'calidad'>('articulos')
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
    staleTime: STALE_SHORT_MS,
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

  if (vista === 'calidad') return <div><SelectorDeVista vista={vista} setVista={setVista} /><CalidadKB /></div>

  return (
    <div>
      <SelectorDeVista vista={vista} setVista={setVista} />
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
            <div className="u-row-6">
              <button onClick={() => setLeyendo(a.id)} style={{ flex: 1, padding: '5px 0', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-1)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>📖 {ts('itsmknowledge.leer')}</button>
              <button onClick={() => { setEditing(a); setShowNew(true) }} style={{ flex: 1, padding: '5px 0', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>✏ Editar</button>
              {a.status === 'in_review' ? <>
                <button onClick={() => revisar({ id: a.id, publish: true })} style={{ flex: 1, padding: '5px 0', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: COLOR.success, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>▶ {ts('sd_cfg.kb_publish')}</button>
                <button onClick={() => setDevolviendo(a)} style={{ flex: 1, padding: '5px 0', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: COLOR.warning, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>↩ {ts('sd_cfg.kb_return')}</button>
              </> : <>
                <button onClick={() => toggleStatus({ id: a.id, status: a.status === 'published' ? 'draft' : 'published' })} style={{ flex: 1, padding: '5px 0', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>{a.status === 'published' ? `⏸ ${ts('sd_cfg.kb_unpublish')}` : `▶ ${ts('sd_cfg.kb_publish')}`}</button>
                {a.status === 'draft' && <button onClick={() => enviarARevision(a.id)} style={{ flex: 1, padding: '5px 0', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>{ts('sd_cfg.kb_submit')}</button>}
              </>}
              <button onClick={() => { openConfirmGlobal({ message: 'Eliminar articulo?', onConfirm: () => deleteArticle(a.id), danger: true }) }} style={{ padding: '5px 8px', borderRadius: 'var(--radius-sm)', border: `1px solid ${alpha(COLOR.danger, '30')}`, background: 'transparent', color: COLOR.danger, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>🗑</button>
            </div>
          </div>
        ))}
      </div>}

      {devolviendo && (
        <Modal open title={`${ts('sd_cfg.kb_return')} · ${devolviendo.title}`} onClose={() => setDevolviendo(null)}>
          <div className="u-stack-10">
            <textarea aria-label={ts('sd_cfg.kb_return_note')} placeholder={ts('sd_cfg.kb_return_note')} rows={4} value={nota} onChange={e => setNota(e.target.value)} style={{ ...IS, resize: 'vertical' }} />
            <div className="u-actions-8">
              <Button variant="secondary" onClick={() => setDevolviendo(null)}>{ts('common.cancel')}</Button>
              <Button disabled={!nota.trim()} onClick={() => revisar({ id: devolviendo.id, publish: false, comment: nota.trim() })}>{ts('sd_cfg.kb_return')}</Button>
            </div>
          </div>
        </Modal>
      )}
      {leyendo !== null && <LecturaDeArticulo id={leyendo} onClose={() => setLeyendo(null)} />}
      {showNew && <KBArticleModal article={editing} onClose={() => { setShowNew(false); setEditing(null) }} onSaved={() => { qc.invalidateQueries({ queryKey: ['sd-kb'] }); setShowNew(false); setEditing(null) }} />}
    </div>
  )
}

type KBArticleModalProps = {
  article: KbArticle | null
  onClose: () => void
  onSaved: () => void
  /** Para un alta: lo que ya se sabe (p. ej. el título desde una pregunta sin respuesta). */
  inicial?: { title?: string }
}

function KBArticleModal({ article, onClose, onSaved, inicial }: KBArticleModalProps) {
  const idCampo = useId()
  const { t } = useAppT()
  const idPrefix = useId()
  const toast = useToast()
  const isEdit = !!article
  const [form, setForm] = useState({
    title: article?.title || inicial?.title || '',
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
      <div className="u-stack-14">
        <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={LS}>Titulo *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={set('title')} style={IS} /></div>
        <div><label id={`${idPrefix}-summary-et`} htmlFor={`${idPrefix}-summary`} style={LS}>Resumen</label><input id={`${idPrefix}-summary`} aria-labelledby={`${idPrefix}-summary-et`} value={form.summary} onChange={set('summary')} style={IS} placeholder={t('itsmknowledge.resumen_del_articulo')} /></div>
        <div><label id={`${idPrefix}-body-et`} htmlFor={`${idPrefix}-body`} style={LS}>Contenido *</label><textarea id={`${idPrefix}-body`} aria-labelledby={`${idPrefix}-body-et`} value={form.body} onChange={set('body')} rows={8} style={{ ...IS, resize: 'vertical' }} placeholder={t('itsmknowledge.contenido_del_articulo')} /></div>
        <div className="u-grid2-12">
          <div><label id={`${idPrefix}-tags-et`} htmlFor={`${idPrefix}-tags`} style={LS}>{t('itsmknowledge.etiquetas_separadas_por_coma')}</label><input id={`${idPrefix}-tags`} aria-labelledby={`${idPrefix}-tags-et`} value={form.tags} onChange={set('tags')} style={IS} placeholder="etiqueta1, etiqueta2" /></div>
          <div><label htmlFor={`${idPrefix}-status`} style={LS}>Estado</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} style={IS}><option value="draft">Borrador</option><option value="published">Publicado</option><option value="archived">Archivado</option></select></div>
        </div>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: "var(--text-base)", color: 'var(--text-1)', cursor: 'pointer' }}><input type="checkbox" aria-label={t('itsmknowledge.visible_en_el_portal_cliente')} checked={form.is_public} onChange={set('is_public')} />{t('itsmknowledge.visible_en_el_portal_cliente')}</label>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title || !form.body} loading={isPending}>{isEdit ? 'Guardar cambios' : 'Crear articulo'}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Calidad de la base (revisión 2026-11) ───────────────────────────────────

type Hueco = { id: string; question: string; times_asked: number; source: string; last_asked_at: string | null }
type Correccion = { id: string; question: string; answer: string; is_public: boolean; usage_count: number; last_used_at: string | null }
type Aviso = { id: string; kind: 'stale' | 'contradiction'; article_number?: string; other_article_number?: string; detail?: string; first_seen_at?: string }
type Calidad = { gaps: Hueco[]; corrections: Correccion[]; findings: Aviso[]; counts: { gaps: number; corrections: number; findings: number } }

function useCalidad() {
  return useQuery<Calidad>({ queryKey: ['sd-kb-quality'], queryFn: () => sdKbApi.quality().then(r => r.data as Calidad), staleTime: STALE_SHORT_MS })
}

function SelectorDeVista({ vista, setVista }: { vista: string; setVista: (v: 'articulos' | 'calidad') => void }) {
  const { t } = useAppT()
  const { data } = useCalidad()
  const pendientes = (data?.counts.gaps ?? 0) + (data?.counts.findings ?? 0)
  return (
    <div role="tablist" style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
      {(['articulos', 'calidad'] as const).map(v => (
        <button key={v} role="tab" aria-selected={vista === v} type="button" onClick={() => setVista(v)}
          style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${vista === v ? 'var(--accent)' : 'var(--surface-4)'}`, background: vista === v ? 'var(--accent-muted)' : 'transparent', color: vista === v ? 'var(--accent)' : 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-sm)' }}>
          {t('itsmknowledge.vista_' + v)}{v === 'calidad' && pendientes > 0 ? ` (${pendientes})` : ''}
        </button>
      ))}
    </div>
  )
}

function CalidadKB() {
  const { t } = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading } = useCalidad()
  const { hasRole } = useAuth()
  const esAdmin = hasRole('admin')
  const [respondiendo, setRespondiendo] = useState<Hueco | null>(null)
  const [respuesta, setRespuesta] = useState('')
  const [publica, setPublica] = useState(true)
  const [articuloDe, setArticuloDe] = useState<Hueco | null>(null)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sd-kb-quality'] })
  const alFallar = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const { mutate: responder, isPending } = useMutation({
    mutationFn: (h: Hueco) => sdKbApi.createCorrection({ question: h.question, answer: respuesta.trim(), is_public: publica, gap_id: h.id }),
    onSuccess: () => { refrescar(); setRespondiendo(null); setRespuesta(''); toast.success(t('itsmknowledge.correccion_guardada')) },
    onError: alFallar,
  })
  const { mutate: estado } = useMutation({
    mutationFn: ({ tipo, id, status }: { tipo: 'gap' | 'finding' | 'correction'; id: string; status: string }) =>
      tipo === 'gap' ? sdKbApi.setGapStatus(id, status) : tipo === 'finding' ? sdKbApi.setFindingStatus(id, status) : sdKbApi.setCorrectionStatus(id, status),
    onSuccess: refrescar, onError: alFallar,
  })
  const { mutate: pasar, isPending: pasando } = useMutation({
    mutationFn: () => sdKbApi.runQuality(),
    // Con cola la revision va al worker (202 `{status: 'queued'}`): aviso y refresco diferido.
    onSuccess: (r: { data?: { status?: string } }) => {
      if (r?.data?.status === 'queued') {
        toast.success('Revisión de calidad en curso: los resultados aparecerán en unos minutos.')
        setTimeout(refrescar, DELAYED_REFETCH_MS)
        return
      }
      refrescar()
    },
    onError: alFallar,
  })
  if (isLoading || !data) return <Spinner />
  const tarjeta: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '12px 14px', display: 'flex', gap: 12, alignItems: 'flex-start', justifyContent: 'space-between' }
  const boton: CSSProperties = { padding: '4px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', fontSize: 'var(--text-xs)', cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }
  const titulo: CSSProperties = { fontSize: 'var(--text-md)', fontWeight: 700, margin: '18px 0 8px' }
  const vacio = (texto: string) => <div className="u-text3-sm">{texto}</div>
  return (
    <div>
      <div className="u-row-between">
        <div className="u-text2-sm">{t('itsmknowledge.calidad_intro')}</div>
        {esAdmin && <button type="button" style={boton} disabled={pasando} onClick={() => pasar()}>{pasando ? '…' : t('itsmknowledge.revisar_ahora')}</button>}
      </div>

      <div style={titulo}>❓ {t('itsmknowledge.sin_respuesta')} ({data.gaps.length})</div>
      {data.gaps.length === 0 ? vacio(t('itsmknowledge.sin_respuesta_vacio')) : (
        <div className="u-stack-8">
          {data.gaps.map(h => (
            <div key={h.id} style={tarjeta}>
              <div className="u-flex1">
                <div style={{ fontSize: 'var(--text-base)', color: 'var(--text-1)' }}>{h.question}</div>
                <div className="u-hint">
                  {t('itsmknowledge.veces', { n: h.times_asked })} · {t('itsmknowledge.origen_' + h.source)}{h.last_asked_at ? ` · ${fmtDateTime(h.last_asked_at)}` : ''}
                </div>
              </div>
              <div className="u-row-6">
                <button type="button" style={{ ...boton, color: 'var(--accent)' }} onClick={() => { setRespondiendo(h); setRespuesta('') }}>{t('itsmknowledge.responder')}</button>
                <button type="button" style={boton} onClick={() => setArticuloDe(h)}>{t('itsmknowledge.crear_articulo')}</button>
                <button type="button" style={boton} onClick={() => estado({ tipo: 'gap', id: h.id, status: 'dismissed' })}>{t('itsmknowledge.descartar')}</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={titulo}>⚠ {t('itsmknowledge.avisos')} ({data.findings.length})</div>
      {data.findings.length === 0 ? vacio(t('itsmknowledge.avisos_vacio')) : (
        <div className="u-stack-8">
          {data.findings.map(f => (
            <div key={f.id} style={tarjeta}>
              <div className="u-flex1">
                <div style={{ fontSize: 'var(--text-base)', color: 'var(--text-1)' }}>
                  {f.kind === 'stale' ? `🕰 ${t('itsmknowledge.caducado', { kb: f.article_number ?? '' })}` : `⇄ ${t('itsmknowledge.contradiccion', { a: f.article_number ?? '', b: f.other_article_number ?? '' })}`}
                </div>
                {f.detail && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', marginTop: 4 }}>{f.detail}</div>}
              </div>
              <div className="u-row-6">
                <button type="button" style={{ ...boton, color: COLOR.success }} onClick={() => estado({ tipo: 'finding', id: f.id, status: 'resolved' })}>{t('itsmknowledge.resuelto')}</button>
                <button type="button" style={boton} onClick={() => estado({ tipo: 'finding', id: f.id, status: 'dismissed' })}>{t('itsmknowledge.descartar')}</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={titulo}>✓ {t('itsmknowledge.correcciones')} ({data.corrections.length})</div>
      {data.corrections.length === 0 ? vacio(t('itsmknowledge.correcciones_vacio')) : (
        <div className="u-stack-8">
          {data.corrections.map(c => (
            <div key={c.id} style={tarjeta}>
              <div className="u-flex1">
                <div className="u-text3-sm">{c.question}</div>
                <div style={{ fontSize: 'var(--text-base)', color: 'var(--text-1)', marginTop: 4, whiteSpace: 'pre-wrap' }}>{c.answer}</div>
                <div className="u-hint">
                  {c.is_public ? t('itsmknowledge.tambien_clientes') : t('itsmknowledge.solo_interna')} · {t('itsmknowledge.usada', { n: c.usage_count })}
                </div>
              </div>
              <button type="button" style={boton} onClick={() => estado({ tipo: 'correction', id: c.id, status: 'archived' })}>{t('itsmknowledge.archivar')}</button>
            </div>
          ))}
        </div>
      )}

      {respondiendo && (
        <Modal open title={t('itsmknowledge.responder')} onClose={() => setRespondiendo(null)}>
          <div className="u-stack-10">
            <div className="u-text2-sm">{respondiendo.question}</div>
            <textarea aria-label={t('itsmknowledge.respuesta')} placeholder={t('itsmknowledge.respuesta')} rows={6} value={respuesta} onChange={e => setRespuesta(e.target.value)}
              style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontFamily: 'inherit', resize: 'vertical' }} />
            <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 'var(--text-sm)' }}>
              <input type="checkbox" aria-label={t('itsmknowledge.tambien_clientes')} checked={publica} onChange={e => setPublica(e.target.checked)} />{t('itsmknowledge.tambien_clientes')}
            </label>
            <div className="u-text3-xs">{t('itsmknowledge.responder_ayuda')}</div>
            <div className="u-actions-8">
              <Button variant="secondary" onClick={() => setRespondiendo(null)}>{t('common.cancel')}</Button>
              <Button disabled={isPending || !respuesta.trim()} onClick={() => responder(respondiendo)}>{t('itsmknowledge.guardar_respuesta')}</Button>
            </div>
          </div>
        </Modal>
      )}
      {articuloDe && (
        <KBArticleModal article={null} inicial={{ title: articuloDe.question }} onClose={() => setArticuloDe(null)}
          onSaved={() => { estado({ tipo: 'gap', id: articuloDe.id, status: 'answered' }); qc.invalidateQueries({ queryKey: ['sd-kb'] }); setArticuloDe(null) }} />
      )}
    </div>
  )
}

export default function ITSMKnowledgeTab({ mode }: { mode: 'problems' | 'kedb' | 'kb' | string }) {
  if (mode === 'problems') return <Problems />
  if (mode === 'kedb') return <KnownErrors />
  return <KB />
}


/** Lectura de un artículo sin entrar en el formulario (revisión 2026-11). */
export function LecturaDeArticulo({ id, onClose }: { id: string | number; onClose: () => void }) {
  const ts = useAppTSimple()
  const { data } = useQuery<KbArticle>({ queryKey: ['sd-kb-articulo', id], queryFn: () => sdKbApi.get(id).then(r => r.data as KbArticle) })
  return (
    <Modal open onClose={onClose} title={data?.title || '…'} size="lg">
      {data ? (
        <div>
          <MarkdownText text={data.body || data.summary || ''} style={{ fontSize: 'var(--text-base)', lineHeight: 1.65, color: 'var(--text-1)' }} />
          <div style={{ display: 'flex', gap: 14, marginTop: 16, fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
            <span>👍 {data.helpful_count || 0}</span><span>👁 {data.view_count || 0}</span>
            {data.tags && <span>🏷 {data.tags}</span>}
            <span>{data.is_public ? ts('itsmknowledge.publico') : ts('itsmknowledge.interno')}</span>
          </div>
          {/* Revisión 2026-11: los documentos de origen del artículo, en contecmind. El portal no los ve. */}
          <div style={{ marginTop: 18 }}><DocumentosDeFicha ficha="kb_article" id={String(id)} /></div>
        </div>
      ) : <Spinner />}
    </Modal>
  )
}
