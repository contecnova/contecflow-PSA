// Pestañas de peticiones, mensajes, documentos, wiki y estadisticas del portal de cliente. 23-11-2026: troceado de ClientPortalPage sin cambio de comportamiento.
import React, { useState } from 'react'
import type { CSSProperties } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { portalApi, wikiApi } from '../services/api'
import type { VisibilidadDeWiki } from '../services/api/tipos-alm'
import { Button, Checkbox, Modal, Pulsable, Select, Spinner, EmptyState, KpiCard, Input, Textarea } from '../components/ui'
import { Users, FlaskConical, Lightbulb, FileText, BookOpen, Plus, Check, CheckCircle2, XCircle, Zap, ClipboardList, User, Wallet, CalendarDays, MessageSquare, Rocket, Package, NotebookPen, BarChart3, Hourglass, Download, Info, MessageCircle, Star, Gauge, FileSignature } from 'lucide-react'
import { fmtDate, extractErr } from '../utils/helpers'
import { FR_STATUS_CFG } from '../constants/sharedStatus'
import { useAppT } from '../i18n/AppLangContext'
import { NOTIFICATIONS_POLL_MS } from '../constants/timings'
import { ConversationPoliciesPanel, TeamGovernedConversationInbox } from '../components/portal/GovernedConversations'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { isSafeUrl, sanitizeUrl } from '../utils/security'
import { type FormDocumento, type PeticionDeCambio, type RespuestaPeticion, StatusBadge, aplanarPaginas, colorVar } from './ClientPortalComun'

// ── Feature Requests Tab ──────────────────────────────────────────────────────
export function FeatureRequestsTab({ projectId }: { projectId: string }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = React.useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [responding, setResponding] = useState<PeticionDeCambio | null>(null)
  const [responseForm, setResponseForm] = useState<RespuestaPeticion>({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' })

  const { data: frs = [], isLoading } = useQuery({
    queryKey: ['portal-frs', projectId],
    queryFn: () => portalApi.featureRequests({ project_id: projectId }).then(r => r.data),
    enabled: !!projectId,
  })

  const { mutate: respond, isPending } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: RespuestaPeticion }) => portalApi.respondFeatureRequest(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs', projectId] }); setResponding(null) },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => portalApi.respondFeatureRequest(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-frs', projectId] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  return (
    <div>
      {isLoading ? <Spinner /> : frs.length === 0 ? (
        <EmptyState svgIcon={<Lightbulb size={36} />} title={t('client_portal.fr_empty_title')} description={t('client_portal.fr_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {frs.map(fr => (
            <div key={fr.id} className="cpp-fr" style={colorVar(fr.priority_color)}>
              <div className="cpp-row-top cpp-row-top--mb">
                <div className="u-flex1">
                  <div className="cpp-title-row cpp-title-row--sm">
                    <span className="u-text2-mono-xs">{fr.code}</span>
                    <span className="u-md-700">{fr.title}</span>
                  </div>
                  <p className="cpp-fr__desc">{fr.description}</p>
                  <div className="cpp-fr__meta">
                    <span className="cpp-fr__prio cpp-con-icono"><Zap size={12} aria-hidden="true" />{fr.priority_label}</span>
                    {fr.affected_area && <span className="u-text2 cpp-con-icono"><ClipboardList size={12} aria-hidden="true" />{fr.affected_area}</span>}
                    {fr.client_name && <span className="u-text2 cpp-con-icono"><User size={12} aria-hidden="true" />{fr.client_name}</span>}
                    <span className="u-text2">{fmtDate(fr.submitted_at)}</span>
                  </div>
                  {fr.pm_response && (
                    <div className="cpp-fr__response">
                      <span className="u-text2">{`${t('client_portal.fr_pm_response')}: `}</span>{fr.pm_response}
                      {fr.estimated_cost && <span className="cpp-fr__cost cpp-con-icono"><Wallet size={12} aria-hidden="true" />{fmtMoneda(fr.estimated_cost, { decimales: 0 })}</span>}
                      {fr.estimated_delivery_weeks && <span className="cpp-fr__weeks cpp-con-icono"><CalendarDays size={12} aria-hidden="true" />{t('clientportalpage.n_semanas', { count: fr.estimated_delivery_weeks })}</span>}
                    </div>
                  )}
                  {fr.client_approved === true && <div className="cpp-fr__approved cpp-con-icono"><CheckCircle2 size={13} aria-hidden="true" />{`${t('client_portal.fr_client_approved')} ${fmtDate(fr.client_approved_at)}`}</div>}
                  {fr.client_approved === false && <div className="cpp-fr__rejected cpp-con-icono"><XCircle size={13} aria-hidden="true" />{t('client_portal.fr_client_rejected')}</div>}
                </div>
                <div className="cpp-fr__side">
                  <StatusBadge status={fr.status} cfg={FR_STATUS_CFG} />
                  {['new', 'reviewing'].includes(fr.status) && (
                    <Button size="sm" icon={<MessageSquare size={13} />} onClick={() => { setResponding(fr); setResponseForm({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' }) }}>
                      {t('client_portal.fr_respond')}
                    </Button>
                  )}
                  {fr.status === 'approved' && (
                    <Button size="sm" variant="secondary" icon={<Rocket size={13} />} onClick={() => updateStatus({ id: fr.id, status: 'in_development' })}>
                      {t('client_portal.fr_start_dev')}
                    </Button>
                  )}
                  {fr.status === 'in_development' && (
                    <Button size="sm" variant="secondary" icon={<CheckCircle2 size={13} />} onClick={() => updateStatus({ id: fr.id, status: 'done' })}>
                      {t('client_portal.fr_completed')}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {responding && (
        <Modal open title={`${t('client_portal.fr_modal_title')}: ${responding.title}`} onClose={() => setResponding(null)} width={520}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cpp-label">{t('client_portal.fr_label_response')} *</label><Textarea id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={responseForm.pm_response} onChange={e => setResponseForm(f => ({ ...f, pm_response: e.target.value }))} rows={3} placeholder={t('client_portal.fr_response_placeholder')} inputClassName="cpp-input" /></div>
            <div className="cpp-grid-3">
              <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cpp-label">{t('client_portal.fr_label_hours')}</label><Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" value={responseForm.estimated_hours} onChange={e => setResponseForm(f => ({ ...f, estimated_hours: e.target.value }))} placeholder={t('clientportalpage.ejemplo', { valor: 8 })} inputClassName="cpp-input" /></div>
              <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="cpp-label">{t('client_portal.fr_label_cost')} ({fmtMoneda.simbolo})</label><Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={responseForm.estimated_cost} onChange={e => setResponseForm(f => ({ ...f, estimated_cost: e.target.value }))} placeholder={t('clientportalpage.ejemplo', { valor: 1200 })} inputClassName="cpp-input" /></div>
              <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="cpp-label">{t('client_portal.fr_label_weeks')}</label><Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={responseForm.estimated_delivery_weeks} onChange={e => setResponseForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} placeholder={t('clientportalpage.ejemplo', { valor: 4 })} inputClassName="cpp-input" /></div>
            </div>
            <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="cpp-label">{t('client_portal.fr_label_status')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-5`} value={responseForm.status} onChange={e => setResponseForm(f => ({ ...f, status: e.target.value }))} className="cpp-input">
                <option value="estimated">{t('client_portal.fr_status_estimated')}</option>
                <option value="reviewing">{t('client_portal.fr_status_reviewing')}</option>
                <option value="rejected">{t('client_portal.fr_status_rejected')}</option>
              </Select>
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setResponding(null)}>{t('common.cancel')}</Button>
              <Button onClick={() => respond({ id: responding.id, data: responseForm })} disabled={isPending || !responseForm.pm_response}>{t('client_portal.fr_send_response')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Messages Tab ──────────────────────────────────────────────────────────────
export function MessagesTab({ projectId }: { projectId: string }) {
  const traducir = useAppT()
  return (
    <div className="u-stack-16">
      <TeamGovernedConversationInbox
        title={traducir('clientportal.conversaciones_del_portal')}
        emptyTitle={traducir('clientportalpage.sin_conversaciones')}
        emptyDescription={traducir('clientportalpage.sin_conversaciones_desc')}
        projectOptions={projectId ? [{ id: projectId, name: projectId, code: '' }] : []}
        initialProjectId={projectId || ''}
      />
      <ConversationPoliciesPanel />
    </div>
  )
}

// ── Documents Tab ─────────────────────────────────────────────────────────────
export function DocumentsTab({ projectId }: { projectId: string }) {
  const idCampo = React.useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [docForm, setDocForm] = useState<FormDocumento>({ title: '', description: '', category: 'deliverable', file_url: '', file_name: '', requires_signature: false })

  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['portal-docs', projectId],
    queryFn: () => portalApi.documents({ project_id: projectId }).then(r => r.data),
    enabled: !!projectId,
  })
  const { mutate: addDoc } = useMutation({
    mutationFn: (data: FormDocumento) => portalApi.createDocument(projectId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-docs', projectId] }); setShowAdd(false) },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const CAT_LABELS: Record<string, string> = {
    contract: t('client_portal.docs_contract'),
    deliverable: t('client_portal.docs_deliverable'),
    meeting_notes: t('client_portal.docs_meeting_notes'),
    report: t('client_portal.docs_report'),
    other: t('client_portal.docs_other'),
  }
  const CAT_ICONS: Record<string, React.ReactNode> = {
    contract: <FileSignature size={16} />, deliverable: <Package size={16} />, meeting_notes: <NotebookPen size={16} />,
    report: <BarChart3 size={16} />, other: <FileText size={16} />,
  }
  const CAT_COLORS: Record<string, string> = { contract: 'var(--purple)', deliverable: 'var(--success)', meeting_notes: 'var(--accent)', report: 'var(--warning)', other: 'var(--text-2)' }

  return (
    <div>
      <div className="cpp-tab-head">
        <div className="u-text2-base">{docs.length} {t('client_portal.docs_count')}</div>
        <Button onClick={() => setShowAdd(true)} icon={<Plus size={14} />}>{t('client_portal.docs_add')}</Button>
      </div>
      {isLoading ? <Spinner /> : docs.length === 0 ? (
        <EmptyState svgIcon={<FileText size={36} />} title={t('client_portal.docs_empty_title')} description={t('client_portal.docs_empty_desc')} />
      ) : (
        <div className="ds-card ds-card--plano">
          {docs.map(doc => {
            const color = CAT_COLORS[doc.category] || 'var(--text-2)'
            return (
              <div key={doc.id} className="cpp-row">
                <span className="cpp-doc__icon" aria-hidden="true">{CAT_ICONS[doc.category] || <FileText size={16} />}</span>
                <div className="u-flex1">
                  <div className="u-base-700">{doc.title}</div>
                  <div className="u-text2-xs">
                    <span className="cpp-doc__cat" style={colorVar(color)}>{CAT_LABELS[doc.category] || t('client_portal.docs_other')}</span>
                    {doc.file_name && ` · ${doc.file_name}`}
                    {doc.created_at && ` · ${fmtDate(doc.created_at)}`}
                  </div>
                </div>
                {doc.requires_signature && (
                  <span className={doc.signed_by_client ? 'cpp-sign is-signed cpp-con-icono' : 'cpp-sign cpp-con-icono'}>
                    {doc.signed_by_client ? <Check size={12} aria-hidden="true" /> : <Hourglass size={12} aria-hidden="true" />}
                    {doc.signed_by_client ? t('client_portal.docs_signed') : t('client_portal.docs_pending_signature')}
                  </span>
                )}
                {doc.file_url && isSafeUrl(doc.file_url) && (
                  <a href={sanitizeUrl(doc.file_url)} target="_blank" rel="noopener noreferrer" className="cpp-btn cpp-con-icono">
                    <Download size={13} aria-hidden="true" />{t('client_portal.docs_download')}
                  </a>
                )}
              </div>
            )
          })}
        </div>
      )}

      {showAdd && (
        <Modal open title={t('client_portal.docs_modal_title')} onClose={() => setShowAdd(false)} width={480}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cpp-label">{t('client_portal.docs_label_title')} *</label><Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={docForm.title} onChange={e => setDocForm(f => ({ ...f, title: e.target.value }))} inputClassName="cpp-input" /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cpp-label">{t('client_portal.docs_label_category')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-2`} value={docForm.category} onChange={e => setDocForm(f => ({ ...f, category: e.target.value }))} className="cpp-input">
                {Object.entries(CAT_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="cpp-label">{t('client_portal.docs_label_file_url')}</label><Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="url" value={docForm.file_url} onChange={e => setDocForm(f => ({ ...f, file_url: e.target.value }))} placeholder="https://..." inputClassName="cpp-input" /></div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="cpp-label">{t('client_portal.docs_label_file_name')}</label><Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={docForm.file_name} onChange={e => setDocForm(f => ({ ...f, file_name: e.target.value }))} placeholder={t('client_portal.docs_placeholder_file_name')} inputClassName="cpp-input" /></div>
            <Checkbox label={t('client_portal.docs_requires_signature')} checked={docForm.requires_signature} onChange={marcado => setDocForm(f => ({ ...f, requires_signature: marcado }))} />
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowAdd(false)}>{t('common.cancel')}</Button>
              <Button onClick={() => addDoc(docForm)} disabled={!docForm.title}>{t('client_portal.docs_share')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Wiki Portal Tab (operador: controla qué páginas wiki ve el cliente) ───────
export function WikiPortalTab({ projectId }: { projectId: string }) {
  const t = useAppT()
  const { data: spaces = [] } = useQuery({
    queryKey: ['wiki-spaces-portal', projectId],
    queryFn: () => wikiApi.portalSpaces().then(r => r.data.filter(s => !projectId || s.project_id === projectId || !s.project_id)),
  })
  const [selectedSpace, setSelectedSpace] = React.useState('')
  const { data: pages = [], isLoading } = useQuery({
    queryKey: ['wiki-pages-portal-op', selectedSpace],
    // Antes solo salían las páginas raíz: las subpáginas no se podían publicar.
    queryFn: () => wikiApi.portalPages(selectedSpace).then(r => aplanarPaginas(r.data)),
    enabled: !!selectedSpace,
  })
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: setVis } = useMutation({
    mutationFn: ({ id, visibility }: { id: string; visibility: VisibilidadDeWiki }) => wikiApi.portalUpdatePage(id, { visibility }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wiki-pages-portal-op', selectedSpace] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const VIS: Record<VisibilidadDeWiki, { label: string; color: string }> = {
    team:   { label: `${t('client_portal.wiki_vis_team')}`, color: 'var(--text-2)' },
    portal: { label: `${t('client_portal.wiki_vis_portal')}`, color: 'var(--accent)' },
    public: { label: `${t('client_portal.wiki_vis_public')}`, color: 'var(--success)' },
  }

  return (
    <div>
      <div className="cpp-info">
        <strong className="u-accent cpp-con-icono"><Info size={14} aria-hidden="true" />{t('client_portal.wiki_info_title')}</strong>
        {' '}— {t('client_portal.wiki_info_desc')}
      </div>
      <div className="cpp-wiki-filter">
        <Select suelto value={selectedSpace} onChange={e => setSelectedSpace(e.target.value)}
          aria-label={t('client_portal.wiki_select_space')} placeholder={t('client_portal.wiki_select_space')}
          className="cpp-input cpp-input--roomy u-flex1">
          {spaces.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </Select>
      </div>
      {isLoading && <Spinner />}
      {selectedSpace && !isLoading && pages.length === 0 && (
        <EmptyState svgIcon={<BookOpen size={36} />} title={t('client_portal.wiki_empty_title')} description={t('client_portal.wiki_empty_desc')} />
      )}
      {pages.length > 0 && (
        <div className="ds-card ds-card--plano">
          {pages.map(page => (
            <div key={page.id} className="cpp-row cpp-row--wiki">
              <span className="cpp-wiki-icon" aria-hidden="true" style={{ '--cpp-nivel': page.nivel } as CSSProperties}><FileText size={14} /></span>
              <div className="u-flex1">
                <div className="u-base-600">{page.title}</div>
                <div className="u-text2-xs">{page.slug}</div>
              </div>
              <div className="u-row-6" role="group" aria-label={t('clientportalpage.visibilidad_de', { title: page.title })}>
                {(Object.entries(VIS) as Array<[VisibilidadDeWiki, { label: string; color: string }]>).map(([val, cfg]) => (
                  <Pulsable key={val} onClick={() => setVis({ id: page.id, visibility: val })}
                    aria-pressed={page.visibility === val}
                    className="cpp-vis" style={colorVar(cfg.color)}>
                    {cfg.label}
                  </Pulsable>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Stats panel ───────────────────────────────────────────────────────────────
export function StatsPanel({ projectId }: { projectId: string }) {
  const t = useAppT()
  const { data: stats } = useQuery({
    queryKey: ['portal-stats', projectId],
    queryFn: () => portalApi.stats(projectId).then(r => r.data),
    enabled: !!projectId,
    refetchInterval: NOTIFICATIONS_POLL_MS,
  })
  if (!stats) return null
  return (
    <div className="ds-grid-stats cpp-stats-kpi">
      <KpiCard icon={<Users size={16} />} label={t('client_portal.stat_contacts')} value={stats.client_count} />
      <KpiCard icon={<MessageCircle size={16} />} label={t('client_portal.stat_unread_messages')} value={stats.unread_messages} warning={stats.unread_messages > 0} />
      <KpiCard icon={<Lightbulb size={16} />} label={t('client_portal.stat_pending_requests')} value={stats.fr_pending_review} danger={stats.fr_pending_review > 0} />
      <KpiCard icon={<FlaskConical size={16} />} label={t('client_portal.stat_pending_uat')} value={stats.uat_pending} accent={stats.uat_pending > 0} />
      <KpiCard icon={<Star size={16} />} label={t('client_portal.stat_avg_satisfaction')} value={stats.avg_satisfaction ? `${stats.avg_satisfaction}/5` : '—'} />
      <KpiCard icon={<Gauge size={16} />} label={t('client_portal.stat_avg_nps')} value={stats.avg_nps ?? '—'}
        danger={stats.avg_nps != null && stats.avg_nps < 6} warning={stats.avg_nps != null && stats.avg_nps >= 6 && stats.avg_nps < 8} />
    </div>
  )
}
