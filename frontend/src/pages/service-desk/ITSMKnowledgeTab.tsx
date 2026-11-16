import { useAppT } from "../../hooks/useAppT";
import DocumentosDeFicha from '../../components/conectores/DocumentosDeFicha'
import { useId, useState } from 'react'
import { useAppT as useAppTSimple } from '../../i18n/AppLangContext'
import type { ChangeEvent, CSSProperties } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import RcaWizardModal from '../../components/servicedesk/RcaWizardModal'
import GestionDelProblema from '../../components/servicedesk/GestionDelProblema'
import PlantillasRca from '../../components/servicedesk/PlantillasRca'

import { extractErr, fmtDateTime } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { sdKbApi, problemsApi } from '../../services/api'
import type { SdArticuloKb, SdArticuloKbDetalle, SdCalidadKb, SdErrorConocido, SdTicketDeErrorConocido } from '../../services/api/tipos-sd'
import { Button, Spinner, EmptyState, Modal } from '../../components/ui'
import MarkdownText from '../../components/ui/MarkdownText'
import { COLOR } from '../../constants/theme'
import { etiquetaSd, PBadge, PRIORITY_LABEL, SBadge } from './sdUtils'
import { DELAYED_REFETCH_MS, STALE_SHORT_MS } from '../../constants/timings'
import './ITSMKnowledgeTab.css'

type Priority = 'p1_critical' | 'p2_high' | 'p3_medium' | 'p4_low' | string
type ProblemStatus = 'open' | 'investigating' | 'known_error' | 'resolved' | 'closed' | string
type KbStatus = 'draft' | 'published' | 'archived' | string

/** Lo comun a un problema (SdProblema) y a un error conocido (SdErrorConocido) en los formularios. */
type ProblemRecord = {
  id: string | number
  /** Solo en el error conocido: el problema del que sale (lo que se edita). */
  problem_id?: string
  number?: string
  title: string
  description?: string
  root_cause?: string
  workaround?: string
  fix_description?: string
  priority?: Priority
  status?: ProblemStatus
  related_ticket_count?: number
  affected_tickets?: number
  ci?: string
}

type KbArticle = SdArticuloKb

type LinkedTicket = SdTicketDeErrorConocido

const PRIORIDADES = ['p1_critical', 'p2_high', 'p3_medium', 'p4_low']

/** Color del dato (estado) para las clases `.itk-*` que lo leen. */
const colorVar = (c: string) => ({ '--itk-c': c } as CSSProperties)

/** `MarkdownText` solo acepta `style`: el estilo de lectura va como objeto. */
const LECTURA_STYLE: CSSProperties = { fontSize: 'var(--text-base)', lineHeight: 1.65, color: 'var(--text-1)' }

function KELinkedTickets({ kedbId }: { kedbId: string | number }) {
  const { t } = useAppT()
  const { data: tickets, isLoading } = useQuery<LinkedTicket[]>({
    queryKey: ['sd-ke-tickets', kedbId],
    queryFn: () => sdKbApi.knownErrorTickets(kedbId).then(r => r.data).catch(() => []),
    staleTime: STALE_SHORT_MS,
  })
  if (isLoading) return <div className="itk-linked-loading"><Spinner /></div>
  if (!tickets?.length) return (
    <div className="itk-linked-empty">
      {t('itsmknowledge.no_hay_tickets_vinculados_a_este_error')}
    </div>
  )
  return (
    <div className="itk-linked">
      <div className="itk-linked__title">{t('itsmknowledge.tickets_vinculados')}</div>
      <div className="u-stack-6">
        {tickets.map((tk) => (
          <div key={tk.id} className="itk-linked__row">
            <span className="itk-linked__number">{tk.number}</span>
            <span className="itk-linked__text">{tk.title}</span>
            <SBadge v={String(tk.status ?? '')} />
          </div>
        ))}
      </div>
    </div>
  )
}

function KnownErrors() {
  const { t } = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)
  const [editing, setEditing] = useState<ProblemRecord | null>(null)
  const [expandedKE, setExpandedKE] = useState<string | number | null>(null)

  const { data: kedb = [], isLoading } = useQuery<SdErrorConocido[]>({
    queryKey: ['sd-kedb'],
    queryFn: () => sdKbApi.knownErrors().then(r => r.data),
  })
  const { mutate: updateProblem } = useMutation({
    mutationFn: ({ id, ...data }: { id: string | number } & Partial<ProblemRecord>) => problemsApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-kedb'] }); setEditing(null); toast.success(t('itsmknowledge.ke_actualizado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div className="u-row-between-mb16">
        <div className="u-text3-sm">
          {t('itsmknowledge.base_de_errores_conocidos_problemas_con_causa')}
        </div>
        <Button onClick={() => { setEditing(null); setShowNew(true) }}>{t('itsmknowledge.nuevo_error_conocido')}</Button>
      </div>
      {isLoading ? <Spinner /> :
       kedb.length === 0 ? <EmptyState icon="📚" title={t('itsmknowledge.sin_errores_conocidos')} description={t('itsmknowledge.sin_errores_desc')} /> :
      <div className="u-stack-12">
        {kedb.map((ke) => (
          <div key={ke.id} className="itk-card">
            <div className="itk-card__head">
              <div className="u-flex1">
                <span className="itk-number itk-number--spaced">{ke.number}</span>
                <span className="itk-card__title">{ke.title}</span>
              </div>
              <div className="u-row-center-8">
                <button
                  type="button"
                  aria-expanded={expandedKE === ke.id}
                  onClick={() => setExpandedKE(expandedKE === ke.id ? null : ke.id)}
                  className="itk-count-btn"
                >
                  {t('itsmknowledge.n_tickets', { n: ke.affected_tickets || 0 })} <span aria-hidden="true">{expandedKE === ke.id ? '▲' : '▼'}</span>
                </button>
                <button type="button" onClick={() => setEditing(ke)} className="itk-btn itk-btn--sm itk-btn--accent"><span aria-hidden="true">✏</span> {t('itsmknowledge.editar')}</button>
              </div>
            </div>
            {ke.ci && <div className="itk-ci">{t('itsmknowledge.ci_afectado', { ci: ke.ci })}</div>}
            {ke.root_cause && (
              <div className="u-mb-10">
                <div className="itk-ke-heading">{t('itsmknowledge.causa_raiz')}</div>
                <div className="u-text2-base">{ke.root_cause}</div>
              </div>
            )}
            {ke.workaround ? (
              <div>
                <div className="itk-ke-heading itk-ke-heading--ok">{t('itsmknowledge.workaround')}</div>
                <div className="itk-workaround">
                  {ke.workaround}
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
              // El id del Known Error no es el del problema: se edita el problema.
              updateProblem({ id: editing.problem_id ?? editing.id, ...data })
            } else {
              problemsApi.create(data).then(() => {
                qc.invalidateQueries({ queryKey: ['sd-kedb'] })
                setShowNew(false)
                toast.success(t('itsmknowledge.ke_creado'))
              }).catch(e => toast.error(e?.response?.data?.detail || t('itsmknowledge.error')))
            }
          }}
        />
      )}
    </div>
  )
}

type KEDBModalProps = {
  item: ProblemRecord | null
  onClose: () => void
  onSaved: (data: Partial<ProblemRecord>) => void
}

function KEDBModal({ item, onClose, onSaved }: KEDBModalProps) {
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
    <Modal open title={isEdit ? t('itsmknowledge.editar_ke') : t('itsmknowledge.nuevo_ke')} onClose={onClose} size="lg">
      <div className="u-stack-14">
        <div><label id={`${idPrefix}-title-et`} htmlFor={`${idPrefix}-title`} className="itk-label">{t('itsmknowledge.titulo_req')}</label><input id={`${idPrefix}-title`} aria-labelledby={`${idPrefix}-title-et`} value={form.title} onChange={set('title')} className="itk-input" placeholder={t('itsmknowledge.titulo_del_error_conocido')} /></div>
        <div><label id={`${idPrefix}-description-et`} htmlFor={`${idPrefix}-description`} className="itk-label">{t('itsmknowledge.descripcion')}</label><textarea id={`${idPrefix}-description`} aria-labelledby={`${idPrefix}-description-et`} value={form.description} onChange={set('description')} rows={3} className="itk-input" placeholder={t('itsmknowledge.describe_el_error_conocido')} /></div>
        <div><label id={`${idPrefix}-root-cause-et`} htmlFor={`${idPrefix}-root-cause`} className="itk-label">{t('itsmknowledge.causa_raiz')}</label><textarea id={`${idPrefix}-root-cause`} aria-labelledby={`${idPrefix}-root-cause-et`} value={form.root_cause} onChange={set('root_cause')} rows={3} className="itk-input" placeholder={t('itsmknowledge.causa_raiz_identificada')} /></div>
        <div><label id={`${idPrefix}-workaround-et`} htmlFor={`${idPrefix}-workaround`} className="itk-label">{t('itsmknowledge.workaround_solucion_temporal')}</label><textarea id={`${idPrefix}-workaround`} aria-labelledby={`${idPrefix}-workaround-et`} value={form.workaround} onChange={set('workaround')} rows={3} className="itk-input" placeholder={t('itsmknowledge.solucion_temporal_disponible')} /></div>
        <div><label id={`${idPrefix}-fix-description-et`} htmlFor={`${idPrefix}-fix-description`} className="itk-label">{t('itsmknowledge.solucion_definitiva_2')}</label><textarea id={`${idPrefix}-fix-description`} aria-labelledby={`${idPrefix}-fix-description-et`} value={form.fix_description} onChange={set('fix_description')} rows={2} className="itk-input" placeholder={t('itsmknowledge.solucion_definitiva_aplicada')} /></div>
        <div className="u-grid2-12">
          <div><label htmlFor={`${idPrefix}-priority`} className="itk-label">{t('itsmknowledge.prioridad')}</label><select id={`${idPrefix}-priority`} value={form.priority} onChange={set('priority')} className="itk-input">{PRIORIDADES.map(p => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}</select></div>
          <div><label htmlFor={`${idPrefix}-status`} className="itk-label">{t('itsmknowledge.estado')}</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} className="itk-input">{['open', 'investigating', 'known_error', 'resolved'].map(v => <option key={v} value={v}>{etiquetaSd('prb_st', v)}</option>)}</select></div>
        </div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('itsmknowledge.cancelar')}</Button>
          <Button onClick={() => onSaved(form)} disabled={!form.title.trim()}>{isEdit ? t('itsmknowledge.guardar_cambios') : t('itsmknowledge.crear_ke')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function Problems() {
  const { t } = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<ProblemRecord | null>(null)
  const [rcaWizardProblem, setRcaWizardProblem] = useState<ProblemRecord | null>(null)
  // Mejoras de mercado 16-11-2026: el ciclo completo del problema y las plantillas RCA.
  const [gestionando, setGestionando] = useState<ProblemRecord | null>(null)
  const [verPlantillas, setVerPlantillas] = useState(false)
  const { user: yo } = useAuth()
  const ts = useAppTSimple()

  const { data: problems = [], isLoading } = useQuery<ProblemRecord[]>({
    queryKey: ['sd-problems'],
    queryFn: () => problemsApi.list().then(r => r.data),
  })
  const { mutate: createProblem, isPending: creating } = useMutation({
    mutationFn: (data: Partial<ProblemRecord>) => problemsApi.create(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-problems'] }); setShowModal(false); toast.success(t('itsmknowledge.problema_creado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: updateProblem, isPending: updating } = useMutation({
    mutationFn: ({ id, ...data }: { id: string | number } & Partial<ProblemRecord>) => problemsApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-problems'] }); setEditing(null); toast.success(t('itsmknowledge.problema_actualizado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteProblem } = useMutation({
    mutationFn: (id: string | number) => problemsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-problems'] }); toast.success(t('itsmknowledge.problema_eliminado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: promoteToKE, variables: promotingId } = useMutation({
    mutationFn: (id: string | number) => problemsApi.promoteKnownError(id),
    onSuccess: () => {
      toast.success(t('itsmknowledge.problema_promovido'))
      qc.invalidateQueries({ queryKey: ['sd-problems'] })
      qc.invalidateQueries({ queryKey: ['sd-kedb'] })
    },
    onError: e => toast.error(extractErr(e, t('itsmknowledge.error_promover'))),
  })

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
        <div className="u-actions-8">
          {yo?.role === 'admin' && <Button variant="secondary" onClick={() => setVerPlantillas(true)}>{ts('sd_mercado.plantillas_rca')}</Button>}
          <Button onClick={() => { setEditing(null); setShowModal(true) }}>{t('itsmknowledge.nuevo_problema')}</Button>
        </div>
      </div>

      {isLoading ? <Spinner /> :
       problems.length === 0
        ? <EmptyState icon="🔍" title={t('itsmknowledge.sin_problemas_registrados')} description={t('itsmknowledge.sin_problemas_desc')} />
        : <div className="u-stack-10">
            {problems.map((p) => {
              const sc = statusColors[p.status ?? ''] || COLOR.text2
              return (
                <div key={p.id} className="itk-card itk-card--problem">
                  <div className="itk-card__head itk-card__head--tight">
                    <div className="u-flex1">
                      <div className="itk-card__meta">
                        <span className="itk-number">{p.number}</span>
                        <span className="itk-status" style={colorVar(sc)}>
                          {etiquetaSd('prb_st', p.status)}
                        </span>
                        <PBadge v={p.priority} />
                        {(p.related_ticket_count ?? 0) > 0 && (
                          <span className="u-text3-xs">
                            {t('itsmknowledge.n_tickets', { n: p.related_ticket_count ?? 0 })}
                          </span>
                        )}
                      </div>
                      <div className="itk-card__title">{p.title}</div>
                    </div>
                    <div className="itk-card__actions">
                      <button type="button" onClick={() => setGestionando(p)} className="itk-btn itk-btn--accent">{ts('sd_mercado.gestionar')}</button>
                      <button type="button" onClick={() => setRcaWizardProblem(p)} className="itk-btn itk-btn--info"><span aria-hidden="true">🔍</span> {t('itsmknowledge.rca')}</button>
                      {p.status !== 'known_error' && (
                        <button
                          type="button"
                          onClick={() => openConfirmGlobal({ message: t('itsmknowledge.confirmar_promover', { title: p.title }), onConfirm: () => promoteToKE(p.id), danger: false })}
                          disabled={promotingId === p.id}
                          className="itk-btn itk-btn--orange"
                        >
                          <span aria-hidden="true">📋</span> {t('itsmknowledge.promover_ke')}
                        </button>
                      )}
                      <button type="button" onClick={() => { setEditing(p); setShowModal(true) }} className="itk-btn itk-btn--accent"><span aria-hidden="true">✏</span> {t('itsmknowledge.editar')}</button>
                      <button type="button" aria-label={t('itsmknowledge.eliminar_x', { title: p.title })} onClick={() => { openConfirmGlobal({ message: t('itsmknowledge.confirmar_eliminar_problema', { title: p.title }), onConfirm: () => deleteProblem(p.id), danger: true }) }} className="itk-btn itk-btn--delete"><span aria-hidden="true">🗑</span></button>
                    </div>
                  </div>
                  {p.root_cause && (
                    <div className="itk-mb-8">
                      <span className="itk-inline-heading">{t('itsmknowledge.causa_raiz')}</span>
                      <span className="u-text2-sm">{p.root_cause}</span>
                    </div>
                  )}
                  {p.workaround && (
                    <div className="itk-workaround itk-workaround--inline">
                      <span className="itk-inline-heading itk-inline-heading--ok">{t('itsmknowledge.workaround')}</span>
                      <span className="u-text1 u-sm">{p.workaround}</span>
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
        />
      )}
      {rcaWizardProblem && (
        <RcaWizardModal
          problem={rcaWizardProblem}
          onClose={() => setRcaWizardProblem(null)}
          onCompleted={() => qc.invalidateQueries({ queryKey: ['sd-problems'] })}
        />
      )}
      {gestionando && <GestionDelProblema problema={gestionando} onClose={() => { setGestionando(null); qc.invalidateQueries({ queryKey: ['sd-problems'] }) }} />}
      {verPlantillas && <PlantillasRca onClose={() => setVerPlantillas(false)} />}
    </div>
  )
}

type ProblemModalProps = {
  item: ProblemRecord | null
  onClose: () => void
  onSaved: (data: Partial<ProblemRecord>) => void
  isPending: boolean
}

function ProblemModal({ item, onClose, onSaved, isPending }: ProblemModalProps) {
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
    <Modal open title={isEdit ? t('itsmknowledge.editar_problema_titulo', { number: item.number ?? '' }) : t('itsmknowledge.nuevo_problema_titulo')} onClose={onClose} size="lg">
      <div className="u-stack-14">
        <div><label id={`${idPrefix}-title-et`} htmlFor={`${idPrefix}-title`} className="itk-label">{t('itsmknowledge.titulo_req')}</label><input id={`${idPrefix}-title`} aria-labelledby={`${idPrefix}-title-et`} value={form.title} onChange={set('title')} className="itk-input" placeholder={t('itsmknowledge.titulo_del_problema')} /></div>
        <div><label id={`${idPrefix}-description-et`} htmlFor={`${idPrefix}-description`} className="itk-label">{t('itsmknowledge.descripcion')}</label><textarea id={`${idPrefix}-description`} aria-labelledby={`${idPrefix}-description-et`} value={form.description} onChange={set('description')} rows={3} className="itk-input" placeholder={t('itsmknowledge.describe_el_problema')} /></div>
        <div><label id={`${idPrefix}-root-cause-et`} htmlFor={`${idPrefix}-root-cause`} className="itk-label">{t('itsmknowledge.causa_raiz')}</label><textarea id={`${idPrefix}-root-cause`} aria-labelledby={`${idPrefix}-root-cause-et`} value={form.root_cause} onChange={set('root_cause')} rows={3} className="itk-input" placeholder={t('itsmknowledge.causa_raiz_identificada')} /></div>
        <div><label id={`${idPrefix}-workaround-et`} htmlFor={`${idPrefix}-workaround`} className="itk-label">{t('itsmknowledge.workaround_solucion_temporal')}</label><textarea id={`${idPrefix}-workaround`} aria-labelledby={`${idPrefix}-workaround-et`} value={form.workaround} onChange={set('workaround')} rows={3} className="itk-input" placeholder={t('itsmknowledge.solucion_temporal')} /></div>
        <div><label id={`${idPrefix}-fix-description-et`} htmlFor={`${idPrefix}-fix-description`} className="itk-label">{t('itsmknowledge.solucion_definitiva_opcional')}</label><textarea id={`${idPrefix}-fix-description`} aria-labelledby={`${idPrefix}-fix-description-et`} value={form.fix_description} onChange={set('fix_description')} rows={2} className="itk-input" placeholder={t('itsmknowledge.solucion_definitiva_2')} /></div>
        <div className="u-grid2-12">
          <div><label htmlFor={`${idPrefix}-priority`} className="itk-label">{t('itsmknowledge.prioridad')}</label><select id={`${idPrefix}-priority`} value={form.priority} onChange={set('priority')} className="itk-input">{PRIORIDADES.map(v => <option key={v} value={v}>{PRIORITY_LABEL[v]}</option>)}</select></div>
          <div><label htmlFor={`${idPrefix}-status`} className="itk-label">{t('itsmknowledge.estado')}</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} className="itk-input">{['open', 'investigating', 'known_error', 'resolved', 'closed'].map(v => <option key={v} value={v}>{etiquetaSd('prb_st', v)}</option>)}</select></div>
        </div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('itsmknowledge.cancelar')}</Button>
          <Button onClick={() => onSaved(form)} disabled={isPending || !form.title.trim()} loading={isPending}>{isEdit ? t('itsmknowledge.guardar_cambios') : t('itsmknowledge.crear_problema')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function KB() {
  const { t } = useAppT()
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
    queryFn: () => sdKbApi.list({ search: search || undefined }).then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })
  const { mutate: deleteArticle } = useMutation({
    mutationFn: (id: string | number) => sdKbApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-kb'] }); toast.success(t('itsmknowledge.articulo_eliminado')) },
    onError: () => toast.error(t('itsmknowledge.error_eliminar')),
  })
  const { mutate: toggleStatus } = useMutation({
    mutationFn: ({ id, status }: { id: string | number; status: KbStatus }) => sdKbApi.update(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-kb'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const STATUS_COLOR: Record<string, string> = { published: COLOR.success, draft: COLOR.warning, in_review: 'var(--accent)', archived: COLOR.text2 }

  if (vista === 'calidad') return <div><SelectorDeVista vista={vista} setVista={setVista} /><CalidadKB /></div>

  return (
    <div>
      <SelectorDeVista vista={vista} setVista={setVista} />
      <div className="itk-search-row">
        <input placeholder={t('itsmknowledge.buscar_articulos')} aria-label={t('itsmknowledge.buscar_articulos')} value={search} onChange={e => setSearch(e.target.value)} className="itk-input itk-input--search" />
        <Button onClick={() => { setEditing(null); setShowNew(true) }}>{t('itsmknowledge.nuevo_articulo')}</Button>
      </div>
      {isLoading ? <Spinner /> :
      articles.length === 0 ? <EmptyState icon="📖" title={t('itsmknowledge.sin_articulos')} description={t('itsmknowledge.sin_articulos_desc')} /> :
      <div className="itk-grid">
        {articles.map((a) => (
          <div key={a.id} className="itk-article">
            <div className="itk-article__head">
              <div className="itk-article__title">{a.title}</div>
              <span className="itk-kb-status" style={colorVar(STATUS_COLOR[a.status ?? ''] || COLOR.text2)}>
                {a.status ? ts(`sd_cfg.kb_status_${a.status}`) : ''}
              </span>
            </div>
            {a.summary && <div className="itk-article__summary">{a.summary}</div>}
            {a.review_comment && a.status === 'draft' && <div className="itk-article__note">{ts('sd_cfg.kb_review_note', { note: a.review_comment })}</div>}
            <div className="itk-article__stats">
              <span>👍 {a.helpful_count || 0}</span>
              <span>👁 {a.view_count || 0}</span>
              {(a.deflection_count ?? 0) > 0 && <span>{ts('sd_cfg.kb_deflections', { n: a.deflection_count ?? 0 })}</span>}
              {a.tags && <span>🏷 {a.tags.split(',').slice(0, 2).join(', ')}</span>}
            </div>
            <div className="u-row-6">
              <button type="button" onClick={() => setLeyendo(a.id)} className="itk-abtn itk-abtn--read"><span aria-hidden="true">📖</span> {ts('itsmknowledge.leer')}</button>
              <button type="button" onClick={() => { setEditing(a); setShowNew(true) }} className="itk-abtn itk-abtn--accent"><span aria-hidden="true">✏</span> {t('itsmknowledge.editar')}</button>
              {a.status === 'in_review' ? <>
                <button type="button" onClick={() => revisar({ id: a.id, publish: true })} className="itk-abtn itk-abtn--success">▶ {ts('sd_cfg.kb_publish')}</button>
                <button type="button" onClick={() => setDevolviendo(a)} className="itk-abtn itk-abtn--warning">↩ {ts('sd_cfg.kb_return')}</button>
              </> : <>
                <button type="button" onClick={() => toggleStatus({ id: a.id, status: a.status === 'published' ? 'draft' : 'published' })} className="itk-abtn">{a.status === 'published' ? `⏸ ${ts('sd_cfg.kb_unpublish')}` : `▶ ${ts('sd_cfg.kb_publish')}`}</button>
                {a.status === 'draft' && <button type="button" onClick={() => enviarARevision(a.id)} className="itk-abtn itk-abtn--accent">{ts('sd_cfg.kb_submit')}</button>}
              </>}
              <button type="button" aria-label={t('itsmknowledge.eliminar_x', { title: a.title })} onClick={() => { openConfirmGlobal({ message: t('itsmknowledge.confirmar_eliminar_articulo'), onConfirm: () => deleteArticle(a.id), danger: true }) }} className="itk-abtn itk-abtn--delete"><span aria-hidden="true">🗑</span></button>
            </div>
          </div>
        ))}
      </div>}

      {devolviendo && (
        <Modal open title={`${ts('sd_cfg.kb_return')} · ${devolviendo.title}`} onClose={() => setDevolviendo(null)}>
          <div className="u-stack-10">
            <textarea aria-label={ts('sd_cfg.kb_return_note')} placeholder={ts('sd_cfg.kb_return_note')} rows={4} value={nota} onChange={e => setNota(e.target.value)} className="itk-input" />
            <div className="u-actions-8">
              <Button variant="secondary" onClick={() => setDevolviendo(null)}>{ts('common.cancel')}</Button>
              <Button disabled={!nota.trim()} onClick={() => revisar({ id: devolviendo.id, publish: false, comment: nota.trim() })}>{ts('sd_cfg.kb_return')}</Button>
            </div>
          </div>
        </Modal>
      )}
      {leyendo !== null && <LecturaDeArticulo id={leyendo} publico={articles.find(x => x.id === leyendo)?.is_public} onClose={() => setLeyendo(null)} />}
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
    mutationFn: (data: typeof form): Promise<unknown> => isEdit && article ? sdKbApi.update(article.id, data) : sdKbApi.create(data),
    onSuccess: () => { toast.success(isEdit ? t('itsmknowledge.articulo_actualizado') : t('itsmknowledge.articulo_creado')); onSaved() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const set = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value }))

  return (
    <Modal open title={isEdit ? t('itsmknowledge.editar_articulo') : t('itsmknowledge.nuevo_articulo_titulo')} onClose={onClose} size="lg">
      <div className="u-stack-14">
        <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="itk-label">{t('itsmknowledge.titulo_req')}</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={set('title')} className="itk-input" /></div>
        <div><label id={`${idPrefix}-summary-et`} htmlFor={`${idPrefix}-summary`} className="itk-label">{t('itsmknowledge.resumen')}</label><input id={`${idPrefix}-summary`} aria-labelledby={`${idPrefix}-summary-et`} value={form.summary} onChange={set('summary')} className="itk-input" placeholder={t('itsmknowledge.resumen_del_articulo')} /></div>
        <div><label id={`${idPrefix}-body-et`} htmlFor={`${idPrefix}-body`} className="itk-label">{t('itsmknowledge.contenido_req')}</label><textarea id={`${idPrefix}-body`} aria-labelledby={`${idPrefix}-body-et`} value={form.body} onChange={set('body')} rows={8} className="itk-input" placeholder={t('itsmknowledge.contenido_del_articulo')} /></div>
        <div className="u-grid2-12">
          <div><label id={`${idPrefix}-tags-et`} htmlFor={`${idPrefix}-tags`} className="itk-label">{t('itsmknowledge.etiquetas_separadas_por_coma')}</label><input id={`${idPrefix}-tags`} aria-labelledby={`${idPrefix}-tags-et`} value={form.tags} onChange={set('tags')} className="itk-input" placeholder={t('itsmknowledge.ph_tags')} /></div>
          <div><label htmlFor={`${idPrefix}-status`} className="itk-label">{t('itsmknowledge.estado')}</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} className="itk-input">{['draft', 'published', 'archived'].map(v => <option key={v} value={v}>{t(`sd_cfg.kb_status_${v}`)}</option>)}</select></div>
        </div>
        <label className="itk-check"><input type="checkbox" aria-label={t('itsmknowledge.visible_en_el_portal_cliente')} checked={form.is_public} onChange={set('is_public')} />{t('itsmknowledge.visible_en_el_portal_cliente')}</label>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('itsmknowledge.cancelar')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title || !form.body} loading={isPending}>{isEdit ? t('itsmknowledge.guardar_cambios') : t('itsmknowledge.crear_articulo')}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Calidad de la base (revisión 2026-11) ───────────────────────────────────

type Calidad = SdCalidadKb
type Hueco = Calidad['gaps'][number]

function useCalidad() {
  return useQuery<Calidad>({ queryKey: ['sd-kb-quality'], queryFn: () => sdKbApi.quality().then(r => r.data), staleTime: STALE_SHORT_MS })
}

function SelectorDeVista({ vista, setVista }: { vista: string; setVista: (v: 'articulos' | 'calidad') => void }) {
  const { t } = useAppT()
  const { data } = useCalidad()
  const pendientes = (data?.counts.gaps ?? 0) + (data?.counts.findings ?? 0)
  return (
    <div role="tablist" aria-label={t('itsmknowledge.vistas')} className="itk-tabs">
      {(['articulos', 'calidad'] as const).map(v => (
        <button key={v} role="tab" aria-selected={vista === v} type="button" onClick={() => setVista(v)}
          className="itk-tab">
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
    onSuccess: r => {
      if (r.data.status === 'queued') {
        toast.success(t('itsmknowledge.revision_en_curso'))
        setTimeout(refrescar, DELAYED_REFETCH_MS)
        return
      }
      refrescar()
    },
    onError: alFallar,
  })
  if (isLoading || !data) return <Spinner />
  const boton = 'itk-btn itk-btn--nowrap'
  const vacio = (texto: string) => <div className="u-text3-sm">{texto}</div>
  return (
    <div>
      <div className="u-row-between">
        <div className="u-text2-sm">{t('itsmknowledge.calidad_intro')}</div>
        {esAdmin && <button type="button" className={boton} disabled={pasando} onClick={() => pasar()}>{pasando ? '…' : t('itsmknowledge.revisar_ahora')}</button>}
      </div>

      <div className="itk-q-title">❓ {t('itsmknowledge.sin_respuesta')} ({data.gaps.length})</div>
      {data.gaps.length === 0 ? vacio(t('itsmknowledge.sin_respuesta_vacio')) : (
        <div className="u-stack-8">
          {data.gaps.map(h => (
            <div key={h.id} className="itk-q-card">
              <div className="u-flex1">
                <div className="itk-q-text">{h.question}</div>
                <div className="u-hint">
                  {t('itsmknowledge.veces', { n: h.times_asked })} · {t('itsmknowledge.origen_' + h.source)}{h.last_asked_at ? ` · ${fmtDateTime(h.last_asked_at)}` : ''}
                </div>
              </div>
              <div className="u-row-6">
                <button type="button" className={`${boton} itk-btn--accent`} onClick={() => { setRespondiendo(h); setRespuesta('') }}>{t('itsmknowledge.responder')}</button>
                <button type="button" className={boton} onClick={() => setArticuloDe(h)}>{t('itsmknowledge.crear_articulo')}</button>
                <button type="button" className={boton} onClick={() => estado({ tipo: 'gap', id: h.id, status: 'dismissed' })}>{t('itsmknowledge.descartar')}</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="itk-q-title">⚠ {t('itsmknowledge.avisos')} ({data.findings.length})</div>
      {data.findings.length === 0 ? vacio(t('itsmknowledge.avisos_vacio')) : (
        <div className="u-stack-8">
          {data.findings.map(f => (
            <div key={f.id} className="itk-q-card">
              <div className="u-flex1">
                <div className="itk-q-text">
                  {f.kind === 'stale' ? `🕰 ${t('itsmknowledge.caducado', { kb: f.article_number ?? '' })}` : `⇄ ${t('itsmknowledge.contradiccion', { a: f.article_number ?? '', b: f.other_article_number ?? '' })}`}
                </div>
                {f.detail && <div className="itk-q-detail">{f.detail}</div>}
              </div>
              <div className="u-row-6">
                <button type="button" className={`${boton} itk-btn--success`} onClick={() => estado({ tipo: 'finding', id: f.id, status: 'resolved' })}>{t('itsmknowledge.resuelto')}</button>
                <button type="button" className={boton} onClick={() => estado({ tipo: 'finding', id: f.id, status: 'dismissed' })}>{t('itsmknowledge.descartar')}</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="itk-q-title">✓ {t('itsmknowledge.correcciones')} ({data.corrections.length})</div>
      {data.corrections.length === 0 ? vacio(t('itsmknowledge.correcciones_vacio')) : (
        <div className="u-stack-8">
          {data.corrections.map(c => (
            <div key={c.id} className="itk-q-card">
              <div className="u-flex1">
                <div className="u-text3-sm">{c.question}</div>
                <div className="itk-q-text itk-q-text--answer">{c.answer}</div>
                <div className="u-hint">
                  {c.is_public ? t('itsmknowledge.tambien_clientes') : t('itsmknowledge.solo_interna')} · {t('itsmknowledge.usada', { n: c.usage_count })}
                </div>
              </div>
              <button type="button" className={boton} onClick={() => estado({ tipo: 'correction', id: c.id, status: 'archived' })}>{t('itsmknowledge.archivar')}</button>
            </div>
          ))}
        </div>
      )}

      {respondiendo && (
        <Modal open title={t('itsmknowledge.responder')} onClose={() => setRespondiendo(null)}>
          <div className="u-stack-10">
            <div className="u-text2-sm">{respondiendo.question}</div>
            <textarea aria-label={t('itsmknowledge.respuesta')} placeholder={t('itsmknowledge.respuesta')} rows={6} value={respuesta} onChange={e => setRespuesta(e.target.value)}
              className="itk-answer" />
            <label className="itk-check-sm">
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
/** `publico` viene de la lista: el detalle (`GET /sd/kb/{id}`) no trae `is_public`. */
export function LecturaDeArticulo({ id, publico, onClose }: { id: string | number; publico?: boolean; onClose: () => void }) {
  const ts = useAppTSimple()
  const { data } = useQuery<SdArticuloKbDetalle>({ queryKey: ['sd-kb-articulo', id], queryFn: () => sdKbApi.get(id).then(r => r.data) })
  return (
    <Modal open onClose={onClose} title={data?.title || '…'} size="lg">
      {data ? (
        <div>
          <MarkdownText text={data.body || data.summary || ''} style={LECTURA_STYLE} />
          <div className="itk-read-stats">
            <span>👍 {data.helpful_count || 0}</span><span>👁 {data.view_count || 0}</span>
            {data.tags && <span>🏷 {data.tags}</span>}
            {publico !== undefined && <span>{publico ? ts('itsmknowledge.publico') : ts('itsmknowledge.interno')}</span>}
          </div>
          {/* Revisión 2026-11: los documentos de origen del artículo, en contecmind. El portal no los ve. */}
          <div className="itk-read-docs"><DocumentosDeFicha ficha="kb_article" id={String(id)} /></div>
        </div>
      ) : <Spinner />}
    </Modal>
  )
}
