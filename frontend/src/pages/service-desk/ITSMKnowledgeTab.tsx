/**
 * Problemas, errores conocidos y base de conocimiento del service desk.
 *
 * 16-11-2026 (pasada de diseño): fuera los emojis (📚🔍📖📋✏🗑👍👁🏷▶↩⏸❓⚠✓🕰⇄▲▼)
 * en favor de iconos lucide; botones con <Button>/<IconButton> del kit (antes
 * botones teñidos a mano, uno con --info); estados con <StatusBadge>; selector
 * Artículos/Calidad con <Tabs>; campos con `ds-input`; vacíos con <EmptyState>
 * e icono (antes texto gris suelto); textos sin anglicismos («solución
 * temporal», «error conocido»). Sin estilos en línea con valores fijos.
 */
import DocumentosDeFicha from '../../components/conectores/DocumentosDeFicha'
import SeguimientoDeHueco from '../../components/servicedesk/SeguimientoDeHueco'
import { useId, useState } from 'react'
import { useAppLang, useAppT as useAppTSimple } from '../../i18n/AppLangContext'
import type { ChangeEvent } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, ArrowLeftRight, BookOpen, CheckCircle2, ChevronDown, ChevronUp, Clock, Eye, HelpCircle,
  ListChecks, Pause, Pencil, Play, Plus, RefreshCw, Search, Send, ShieldCheck, Tag, ThumbsUp, Trash2, Undo2, Wrench,
} from 'lucide-react'
import RcaWizardModal from '../../components/servicedesk/RcaWizardModal'
import GestionDelProblema from '../../components/servicedesk/GestionDelProblema'
import PlantillasRca from '../../components/servicedesk/PlantillasRca'
import VersionesKbPanel from '../../components/traduccion/VersionesKbPanel'

import { extractErr, fmtDateTime } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { sdKbApi, problemsApi } from '../../services/api'
import type { SdArticuloKb, SdArticuloKbDetalle, SdCalidadKb, SdErrorConocido, SdTicketDeErrorConocido } from '../../services/api/tipos-sd'
import { Buscador, Button, Checkbox, Spinner, EmptyState, Modal, Select, StatusBadge, Tabs, IconButton, useErroresDeCampo, Input, Textarea } from '../../components/ui'
import type { StatusBadgeKind } from '../../components/ui/StatusBadge'
import MarkdownText from '../../components/ui/MarkdownText'
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

const KIND_PROBLEMA: Record<string, StatusBadgeKind> = {
  open: 'danger', investigating: 'warning', known_error: 'orange', resolved: 'success', closed: 'neutral',
}
const KIND_KB: Record<string, StatusBadgeKind> = { published: 'success', draft: 'warning', in_review: 'accent', archived: 'neutral' }

function KELinkedTickets({ kedbId }: { kedbId: string | number }) {
  const { t } = useAppLang()
  const { data: tickets, isLoading } = useQuery<LinkedTicket[]>({
    queryKey: ['sd-ke-tickets', kedbId],
    queryFn: () => sdKbApi.knownErrorTickets(kedbId).then(r => r.data),
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
  const { t } = useAppLang()
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
  const nuevo = <Button icon={<Plus size={14} />} onClick={() => { setEditing(null); setShowNew(true) }}>{t('itsmknowledge.nuevo_error_conocido')}</Button>

  return (
    <div>
      <div className="itk-toolbar">
        <div className="u-text2-sm">
          {t('itsmknowledge.base_de_errores_conocidos_problemas_con_causa')}
        </div>
        {nuevo}
      </div>
      {isLoading ? <Spinner /> :
       kedb.length === 0 ? <EmptyState icon={<ShieldCheck size={28} />} title={t('itsmknowledge.sin_errores_conocidos')} description={t('itsmknowledge.sin_errores_desc')} action={nuevo} /> :
      <div className="u-stack-12">
        {kedb.map((ke) => (
          <div key={ke.id} className="itk-card">
            <div className="itk-card__head">
              <div className="itk-card__titlebox">
                <span className="itk-number itk-number--spaced">{ke.number}</span>
                <span className="itk-card__title">{ke.title}</span>
              </div>
              <div className="itk-card__actions">
                <Button
                  size="xs"
                  variant="ghost"
                  onClick={() => setExpandedKE(expandedKE === ke.id ? null : ke.id)}
                  icon={expandedKE === ke.id ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                >
                  {t('itsmknowledge.n_tickets', { n: ke.affected_tickets || 0 })}
                </Button>
                <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditing(ke)}>{t('itsmknowledge.editar')}</Button>
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
              }).catch(e => toast.error(extractErr(e, t('itsmknowledge.error'))))
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
  const { t } = useAppLang()
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
        <Input label={t('itsmknowledge.titulo_req')} id={`${idPrefix}-title`} value={form.title} onChange={set('title')} placeholder={t('itsmknowledge.titulo_del_error_conocido')} />
        <Textarea label={t('itsmknowledge.descripcion')} id={`${idPrefix}-description`} value={form.description} onChange={set('description')} rows={3} placeholder={t('itsmknowledge.describe_el_error_conocido')} />
        <Textarea label={t('itsmknowledge.causa_raiz')} id={`${idPrefix}-root-cause`} value={form.root_cause} onChange={set('root_cause')} rows={3} placeholder={t('itsmknowledge.causa_raiz_identificada')} />
        <Textarea label={t('itsmknowledge.workaround_solucion_temporal')} id={`${idPrefix}-workaround`} value={form.workaround} onChange={set('workaround')} rows={3} placeholder={t('itsmknowledge.solucion_temporal_disponible')} />
        <Textarea label={t('itsmknowledge.solucion_definitiva_2')} id={`${idPrefix}-fix-description`} value={form.fix_description} onChange={set('fix_description')} rows={2} placeholder={t('itsmknowledge.solucion_definitiva_aplicada')} />
        <div className="u-grid2-12">
          <Select label={t('itsmknowledge.prioridad')} placeholder={false} id={`${idPrefix}-priority`} value={form.priority} onChange={set('priority')}>{PRIORIDADES.map(p => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}</Select>
          <Select label={t('itsmknowledge.estado')} placeholder={false} id={`${idPrefix}-status`} value={form.status} onChange={set('status')}>{['open', 'investigating', 'known_error', 'resolved'].map(v => <option key={v} value={v}>{etiquetaSd('prb_st', v)}</option>)}</Select>
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
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<ProblemRecord | null>(null)
  const [rcaWizardProblem, setRcaWizardProblem] = useState<ProblemRecord | null>(null)
  // Mejoras de mercado 16-11-2026: el ciclo completo del problema y las plantillas RCA.
  const [gestionando, setGestionando] = useState<ProblemRecord | null>(null)
  const [verPlantillas, setVerPlantillas] = useState(false)
  const { puede } = useAuth()
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

  const nuevo = <Button icon={<Plus size={14} />} onClick={() => { setEditing(null); setShowModal(true) }}>{t('itsmknowledge.nuevo_problema')}</Button>

  return (
    <div>
      <div className="itk-toolbar">
        <div className="u-text2-sm">
          {t('itsmknowledge.registro_de_problemas_causas_raiz_de_incidentes')}
        </div>
        <div className="u-actions-8">
          {puede('sd.administrar') && <Button variant="secondary" icon={<ListChecks size={14} />} onClick={() => setVerPlantillas(true)}>{ts('sd_mercado.plantillas_rca')}</Button>}
          {nuevo}
        </div>
      </div>

      {isLoading ? <Spinner /> :
       problems.length === 0
        ? <EmptyState icon={<Search size={28} />} title={t('itsmknowledge.sin_problemas_registrados')} description={t('itsmknowledge.sin_problemas_desc')} action={nuevo} />
        : <div className="u-stack-10">
            {problems.map((p) => (
                <div key={p.id} className="itk-card itk-card--problem">
                  <div className="itk-card__head itk-card__head--tight">
                    <div className="itk-card__titlebox">
                      <div className="itk-card__meta">
                        <span className="itk-number">{p.number}</span>
                        <StatusBadge kind={KIND_PROBLEMA[p.status ?? ''] ?? 'neutral'} caps={false}>{etiquetaSd('prb_st', p.status)}</StatusBadge>
                        <PBadge v={p.priority} />
                        {(p.related_ticket_count ?? 0) > 0 && (
                          <span className="u-text2-xs">
                            {t('itsmknowledge.n_tickets', { n: p.related_ticket_count ?? 0 })}
                          </span>
                        )}
                      </div>
                      <div className="itk-card__title">{p.title}</div>
                    </div>
                    <div className="itk-card__actions">
                      <Button size="xs" variant="secondary" icon={<Wrench size={12} />} onClick={() => setGestionando(p)}>{ts('sd_mercado.gestionar')}</Button>
                      <Button size="xs" variant="secondary" icon={<Search size={12} />} onClick={() => setRcaWizardProblem(p)}>{t('itsmknowledge.rca')}</Button>
                      {p.status !== 'known_error' && (
                        <Button
                          size="xs"
                          variant="secondary"
                          icon={<ShieldCheck size={12} />}
                          onClick={() => openConfirmGlobal({ message: t('itsmknowledge.confirmar_promover', { title: p.title }), onConfirm: () => promoteToKE(p.id), danger: false })}
                          disabled={promotingId === p.id}
                        >
                          {t('itsmknowledge.promover_ke')}
                        </Button>
                      )}
                      <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => { setEditing(p); setShowModal(true) }}>{t('itsmknowledge.editar')}</Button>
                      <IconButton variante="caja" tono="peligro" ariaLabel={t('itsmknowledge.eliminar_x', { title: p.title })} onClick={() => { openConfirmGlobal({ message: t('itsmknowledge.confirmar_eliminar_problema', { title: p.title }), onConfirm: () => deleteProblem(p.id), danger: true }) }}><Trash2 size={14} aria-hidden /></IconButton>
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
            ))}
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
  const { t } = useAppLang()
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
        <Input label={t('itsmknowledge.titulo_req')} id={`${idPrefix}-title`} value={form.title} onChange={set('title')} placeholder={t('itsmknowledge.titulo_del_problema')} />
        <Textarea label={t('itsmknowledge.descripcion')} id={`${idPrefix}-description`} value={form.description} onChange={set('description')} rows={3} placeholder={t('itsmknowledge.describe_el_problema')} />
        <Textarea label={t('itsmknowledge.causa_raiz')} id={`${idPrefix}-root-cause`} value={form.root_cause} onChange={set('root_cause')} rows={3} placeholder={t('itsmknowledge.causa_raiz_identificada')} />
        <Textarea label={t('itsmknowledge.workaround_solucion_temporal')} id={`${idPrefix}-workaround`} value={form.workaround} onChange={set('workaround')} rows={3} placeholder={t('itsmknowledge.solucion_temporal')} />
        <Textarea label={t('itsmknowledge.solucion_definitiva_opcional')} id={`${idPrefix}-fix-description`} value={form.fix_description} onChange={set('fix_description')} rows={2} placeholder={t('itsmknowledge.solucion_definitiva_2')} />
        <div className="u-grid2-12">
          <Select label={t('itsmknowledge.prioridad')} placeholder={false} id={`${idPrefix}-priority`} value={form.priority} onChange={set('priority')}>{PRIORIDADES.map(v => <option key={v} value={v}>{PRIORITY_LABEL[v]}</option>)}</Select>
          <Select label={t('itsmknowledge.estado')} placeholder={false} id={`${idPrefix}-status`} value={form.status} onChange={set('status')}>{['open', 'investigating', 'known_error', 'resolved', 'closed'].map(v => <option key={v} value={v}>{etiquetaSd('prb_st', v)}</option>)}</Select>
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
  const { t } = useAppLang()
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

  if (vista === 'calidad') return <div className="u-stack-16"><SelectorDeVista vista={vista} setVista={setVista} /><CalidadKB /></div>

  const nuevo = <Button icon={<Plus size={14} />} onClick={() => { setEditing(null); setShowNew(true) }}>{t('itsmknowledge.nuevo_articulo')}</Button>

  return (
    <div className="u-stack-16">
      <SelectorDeVista vista={vista} setVista={setVista} />
      <div className="itk-search-row">
        <Buscador placeholder={t('itsmknowledge.buscar_articulos')} aria-label={t('itsmknowledge.buscar_articulos')} value={search} onChange={setSearch} className="itk-input--search" />
        {nuevo}
      </div>
      {isLoading ? <Spinner /> :
      articles.length === 0 ? <EmptyState icon={<BookOpen size={28} />} title={t('itsmknowledge.sin_articulos')} description={t(search ? 'itsmknowledge.sin_articulos_busqueda' : 'itsmknowledge.sin_articulos_desc')} action={search ? undefined : nuevo} /> :
      <div className="itk-grid">
        {articles.map((a) => (
          <div key={a.id} className="itk-article">
            <div className="itk-article__head">
              <div className="itk-article__title">{a.title}</div>
              {a.status && <StatusBadge kind={KIND_KB[a.status] ?? 'neutral'} caps={false} className="itk-nowrap">{ts(`sd_cfg.kb_status_${a.status}`)}</StatusBadge>}
            </div>
            {a.summary && <div className="itk-article__summary">{a.summary}</div>}
            {a.review_comment && a.status === 'draft' && <div className="itk-article__note">{ts('sd_cfg.kb_review_note', { note: a.review_comment })}</div>}
            <div className="itk-article__stats">
              <span className="itk-stat" title={t('itsmknowledge.utiles')}><ThumbsUp size={12} aria-hidden /> {a.helpful_count || 0}</span>
              <span className="itk-stat" title={t('itsmknowledge.vistas_n')}><Eye size={12} aria-hidden /> {a.view_count || 0}</span>
              {(a.deflection_count ?? 0) > 0 && <span>{ts('sd_cfg.kb_deflections', { n: a.deflection_count ?? 0 })}</span>}
              {a.tags && <span className="itk-stat"><Tag size={12} aria-hidden /> {a.tags.split(',').slice(0, 2).join(', ')}</span>}
            </div>
            <div className="itk-article__actions">
              <Button size="xs" variant="secondary" icon={<BookOpen size={12} />} onClick={() => setLeyendo(a.id)}>{ts('itsmknowledge.leer')}</Button>
              <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => { setEditing(a); setShowNew(true) }}>{t('itsmknowledge.editar')}</Button>
              {a.status === 'in_review' ? <>
                <Button size="xs" variant="secondary" icon={<Play size={12} />} onClick={() => revisar({ id: a.id, publish: true })}>{ts('sd_cfg.kb_publish')}</Button>
                <Button size="xs" variant="secondary" icon={<Undo2 size={12} />} onClick={() => setDevolviendo(a)}>{ts('sd_cfg.kb_return')}</Button>
              </> : <>
                <Button size="xs" variant="secondary" icon={a.status === 'published' ? <Pause size={12} /> : <Play size={12} />} onClick={() => toggleStatus({ id: a.id, status: a.status === 'published' ? 'draft' : 'published' })}>{a.status === 'published' ? ts('sd_cfg.kb_unpublish') : ts('sd_cfg.kb_publish')}</Button>
                {a.status === 'draft' && <Button size="xs" variant="secondary" icon={<Send size={12} />} onClick={() => enviarARevision(a.id)}>{ts('sd_cfg.kb_submit')}</Button>}
              </>}
              <IconButton variante="caja" tono="peligro" ariaLabel={t('itsmknowledge.eliminar_x', { title: a.title })} onClick={() => { openConfirmGlobal({ message: t('itsmknowledge.confirmar_eliminar_articulo'), onConfirm: () => deleteArticle(a.id), danger: true }) }}><Trash2 size={14} aria-hidden /></IconButton>
            </div>
          </div>
        ))}
      </div>}

      {devolviendo && (
        <Modal open title={`${ts('sd_cfg.kb_return')} · ${devolviendo.title}`} onClose={() => setDevolviendo(null)}>
          <div className="u-stack-10">
            <Textarea aria-label={ts('sd_cfg.kb_return_note')} placeholder={ts('sd_cfg.kb_return_note')} rows={4} value={nota} onChange={e => setNota(e.target.value)} inputClassName="itk-textarea" />
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
  /** 23-11-2026: con el id del artículo creado (para enlazarlo a una pregunta sin respuesta). */
  onSaved: (creadoId?: string) => void
  /** Para un alta: lo que ya se sabe (p. ej. el título desde una pregunta sin respuesta). */
  inicial?: { title?: string }
}

function KBArticleModal({ article, onClose, onSaved, inicial }: KBArticleModalProps) {
  const idCampo = useId()
  const { t } = useAppLang()
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
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (data: typeof form): Promise<unknown> => isEdit && article ? sdKbApi.update(article.id, data) : sdKbApi.create(data),
    onSuccess: (r: unknown) => { toast.success(isEdit ? t('itsmknowledge.articulo_actualizado') : t('itsmknowledge.articulo_creado')); onSaved((r as { data?: { id?: string } } | undefined)?.data?.id) },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  const set = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value }))

  return (
    <Modal open title={isEdit ? t('itsmknowledge.editar_articulo') : t('itsmknowledge.nuevo_articulo_titulo')} onClose={onClose} size="lg">
      <div className="u-stack-14">
        <div><Input label={t('itsmknowledge.titulo_req')} id={`${idCampo}-1`} value={form.title} onChange={set('title')} />{msg('title')}</div>
        <div><Input label={t('itsmknowledge.resumen')} id={`${idPrefix}-summary`} value={form.summary} onChange={set('summary')} placeholder={t('itsmknowledge.resumen_del_articulo')} />{msg('summary')}</div>
        <div><Textarea label={t('itsmknowledge.contenido_req')} id={`${idPrefix}-body`} value={form.body} onChange={set('body')} rows={8} placeholder={t('itsmknowledge.contenido_del_articulo')} />{msg('body')}</div>
        <div className="u-grid2-12">
          <div><Input label={t('itsmknowledge.etiquetas_separadas_por_coma')} id={`${idPrefix}-tags`} value={form.tags} onChange={set('tags')} placeholder={t('itsmknowledge.ph_tags')} />{msg('tags')}</div>
          <div><Select label={t('itsmknowledge.estado')} placeholder={false} id={`${idPrefix}-status`} value={form.status} onChange={set('status')}>{['draft', 'published', 'archived'].map(v => <option key={v} value={v}>{t(`sd_cfg.kb_status_${v}`)}</option>)}</Select>{msg('status')}</div>
        </div>
        <Checkbox className="itk-check" aria-label={t('itsmknowledge.visible_en_el_portal_cliente')} checked={!!form.is_public} onChange={v => { campos.limpiar('is_public'); setForm(f => ({ ...f, is_public: v })) }} label={t('itsmknowledge.visible_en_el_portal_cliente')} />
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('itsmknowledge.cancelar')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title || !form.body} loading={isPending}>{isEdit ? t('itsmknowledge.guardar_cambios') : t('itsmknowledge.crear_articulo')}</Button>
        </div>
        {/* Traducción en tiempo real (16-11-2026): el artículo en otros idiomas. */}
        {isEdit && article && <VersionesKbPanel articleId={String(article.id)} />}
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
  const { t } = useAppLang()
  const { data } = useCalidad()
  const pendientes = (data?.counts.gaps ?? 0) + (data?.counts.findings ?? 0)
  return (
    <Tabs
      ariaLabel={t('itsmknowledge.vistas')}
      active={vista}
      onChange={id => setVista(id as 'articulos' | 'calidad')}
      items={[
        { id: 'articulos', label: t('itsmknowledge.vista_articulos'), icon: <BookOpen size={14} /> },
        { id: 'calidad', label: t('itsmknowledge.vista_calidad'), icon: <CheckCircle2 size={14} />, count: pendientes > 0 ? pendientes : undefined },
      ]}
    />
  )
}

function CalidadKB() {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading } = useCalidad()
  const { puede } = useAuth()
  const esAdmin = puede('sd.administrar')
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
  return (
    <div>
      <div className="itk-toolbar">
        <div className="u-text2-sm">{t('itsmknowledge.calidad_intro')}</div>
        {esAdmin && <Button variant="secondary" icon={<RefreshCw size={14} />} loading={pasando} disabled={pasando} onClick={() => pasar()}>{t('itsmknowledge.revisar_ahora')}</Button>}
      </div>

      <h3 className="itk-q-title"><HelpCircle size={16} aria-hidden className="itk-q-title__icon" />{t('itsmknowledge.sin_respuesta')} ({data.gaps.length})</h3>
      {data.gaps.length === 0 ? <EmptyState icon={<HelpCircle size={28} />} title={t('itsmknowledge.sin_respuesta_titulo')} description={t('itsmknowledge.sin_respuesta_vacio')} /> : (
        <div className="u-stack-8">
          {data.gaps.map(h => (
            <div key={h.id} className="itk-q-card">
              <div className="u-flex1-min0">
                <div className="itk-q-text">{h.question}</div>
                <div className="itk-q-meta">
                  {t('itsmknowledge.veces', { n: h.times_asked })} · {t('itsmknowledge.origen_' + h.source)}{h.last_asked_at ? ` · ${fmtDateTime(h.last_asked_at)}` : ''}
                </div>
                {/* 23-11-2026: responsable, plazo, seguimiento, tarea y artículo que la responde. */}
                <SeguimientoDeHueco h={h} onCambio={refrescar} />
              </div>
              <div className="itk-q-actions">
                <Button size="xs" onClick={() => { setRespondiendo(h); setRespuesta('') }}>{t('itsmknowledge.responder')}</Button>
                <Button size="xs" variant="secondary" icon={<Plus size={12} />} onClick={() => setArticuloDe(h)}>{t('itsmknowledge.crear_articulo')}</Button>
                <Button size="xs" variant="ghost" onClick={() => estado({ tipo: 'gap', id: h.id, status: 'dismissed' })}>{t('itsmknowledge.descartar')}</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <h3 className="itk-q-title"><AlertTriangle size={16} aria-hidden className="itk-q-title__icon" />{t('itsmknowledge.avisos')} ({data.findings.length})</h3>
      {data.findings.length === 0 ? <EmptyState icon={<AlertTriangle size={28} />} title={t('itsmknowledge.avisos_titulo')} description={t('itsmknowledge.avisos_vacio')} /> : (
        <div className="u-stack-8">
          {data.findings.map(f => (
            <div key={f.id} className="itk-q-card">
              <div className="u-flex1-min0">
                <div className="itk-q-text itk-q-text--icon">
                  {f.kind === 'stale'
                    ? <><Clock size={14} aria-hidden className="itk-q-title__icon" />{t('itsmknowledge.caducado', { kb: f.article_number ?? '' })}</>
                    : <><ArrowLeftRight size={14} aria-hidden className="itk-q-title__icon" />{t('itsmknowledge.contradiccion', { a: f.article_number ?? '', b: f.other_article_number ?? '' })}</>}
                </div>
                {f.detail && <div className="itk-q-detail">{f.detail}</div>}
              </div>
              <div className="itk-q-actions">
                <Button size="xs" variant="secondary" icon={<CheckCircle2 size={12} />} onClick={() => estado({ tipo: 'finding', id: f.id, status: 'resolved' })}>{t('itsmknowledge.resuelto')}</Button>
                <Button size="xs" variant="ghost" onClick={() => estado({ tipo: 'finding', id: f.id, status: 'dismissed' })}>{t('itsmknowledge.descartar')}</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <h3 className="itk-q-title"><CheckCircle2 size={16} aria-hidden className="itk-q-title__icon" />{t('itsmknowledge.correcciones')} ({data.corrections.length})</h3>
      {data.corrections.length === 0 ? <EmptyState icon={<CheckCircle2 size={28} />} title={t('itsmknowledge.correcciones_titulo')} description={t('itsmknowledge.correcciones_vacio')} /> : (
        <div className="u-stack-8">
          {data.corrections.map(c => (
            <div key={c.id} className="itk-q-card">
              <div className="u-flex1-min0">
                <div className="u-text2-sm">{c.question}</div>
                <div className="itk-q-text itk-q-text--answer">{c.answer}</div>
                <div className="itk-q-meta">
                  {c.is_public ? t('itsmknowledge.tambien_clientes') : t('itsmknowledge.solo_interna')} · {t('itsmknowledge.usada', { n: c.usage_count })}
                </div>
              </div>
              <Button size="xs" variant="ghost" onClick={() => estado({ tipo: 'correction', id: c.id, status: 'archived' })}>{t('itsmknowledge.archivar')}</Button>
            </div>
          ))}
        </div>
      )}

      {respondiendo && (
        <Modal open title={t('itsmknowledge.responder')} onClose={() => setRespondiendo(null)}>
          <div className="u-stack-10">
            <div className="u-text2-sm">{respondiendo.question}</div>
            <Textarea aria-label={t('itsmknowledge.respuesta')} placeholder={t('itsmknowledge.respuesta')} rows={6} value={respuesta} onChange={e => setRespuesta(e.target.value)} inputClassName="itk-textarea" />
            <Checkbox className="itk-check-sm" aria-label={t('itsmknowledge.tambien_clientes')} checked={!!publica} onChange={setPublica} label={t('itsmknowledge.tambien_clientes')} />
            <div className="u-text2-xs">{t('itsmknowledge.responder_ayuda')}</div>
            <div className="u-actions-8">
              <Button variant="secondary" onClick={() => setRespondiendo(null)}>{t('common.cancel')}</Button>
              <Button disabled={isPending || !respuesta.trim()} loading={isPending} onClick={() => responder(respondiendo)}>{t('itsmknowledge.guardar_respuesta')}</Button>
            </div>
          </div>
        </Modal>
      )}
      {articuloDe && (
        <KBArticleModal article={null} inicial={{ title: articuloDe.question }} onClose={() => setArticuloDe(null)}
          onSaved={creadoId => {
            // 23-11-2026: se enlaza; si se creó publicado la cierra ya, si no al publicarlo.
            const gap = articuloDe.id
            if (creadoId) sdKbApi.gapArticle(gap, creadoId).then(refrescar).catch(alFallar)
            else estado({ tipo: 'gap', id: gap, status: 'answered' })
            qc.invalidateQueries({ queryKey: ['sd-kb'] }); setArticuloDe(null)
          }} />
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
          <MarkdownText text={data.body || data.summary || ''} className="itk-read-body" />
          <div className="itk-read-stats">
            <span className="itk-stat" title={ts('itsmknowledge.utiles')}><ThumbsUp size={12} aria-hidden /> {data.helpful_count || 0}</span>
            <span className="itk-stat" title={ts('itsmknowledge.vistas_n')}><Eye size={12} aria-hidden /> {data.view_count || 0}</span>
            {data.tags && <span className="itk-stat"><Tag size={12} aria-hidden /> {data.tags}</span>}
            {publico !== undefined && <span>{publico ? ts('itsmknowledge.publico') : ts('itsmknowledge.interno')}</span>}
          </div>
          {/* Revisión 2026-11: los documentos de origen del artículo, en contecmind. El portal no los ve. */}
          <div className="itk-read-docs"><DocumentosDeFicha ficha="kb_article" id={String(id)} /></div>
        </div>
      ) : <Spinner />}
    </Modal>
  )
}
