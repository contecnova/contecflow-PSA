// Pestañas del portal del cliente en la ficha de cliente (configuracion, UAT, solicitudes, mensajes, documentos). 23-11-2026: troceado de ClientsPageTabs sin cambio de comportamiento.
import { type CSSProperties, useState, useEffect, useId } from 'react'
import { Check, Download, FileText, FlaskConical, FolderOpen, Lightbulb, MessageSquare, PenLine, Rocket, TriangleAlert } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { portalApi, wsApi, apiWsUrl } from '../../services/api'
import { Button, Spinner, EmptyState, Modal, Tabs, Select, Input, Textarea, SelectorDeContexto } from '../../components/ui'
import { BadgeWithTooltip } from '../../components/ui/BadgeWithTooltip'
import { IconFR, IconCR } from '../../components/ui/FRCRIcons'
import { fmtDate, fmtDateTime, extractErr } from '../../utils/helpers'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { PortalUsersTab } from './PortalUsersTab'
import { ConversationPoliciesPanel, TeamGovernedConversationInbox } from '../../components/portal/GovernedConversations'
import { useAppLang } from '../../i18n/AppLangContext'
import { alpha } from '../../constants/theme'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { WS_RECONNECT_DELAY_MS } from '../../constants/timings'
import { isSafeUrl, sanitizeUrl } from '../../utils/security'
import { CR_FECHAS, type ClientDetail, type ClientProjectRef, DOC_ICON, type FeatureRequestResponseForm, type TeamFeatureRequest, type TeamPortalDocument, type TeamUatSession } from './ClientsTabsComun'
import { PortalSettingsTab } from './ClientsTabsAjustesYFacturas'

export function PortalConfigTab({ cid, clientDetail }: { cid: string; clientDetail?: ClientDetail | null }) {
  const { t: traducir } = useAppLang()
  const [sub, setSub] = useState('accesos')
  // Proyectos del detalle del cliente: aquí solo se usan id, código y nombre.
  const proyectos = (clientDetail?.projects || []) as ClientProjectRef[]

  const subTabs = [
    { id: 'accesos', label: traducir('clientstabs.sub_accesos') },
    { id: 'uat', label: traducir('clientstabs.sub_uat') },
    { id: 'solicitudes', label: traducir('clientstabs.sub_solicitudes') },
    { id: 'mensajes', label: traducir('clientstabs.sub_mensajes') },
    { id: 'documentos', label: traducir('clientstabs.sub_documentos') },
    { id: 'config', label: traducir('clientstabs.sub_config') },
  ]

  return (
    <div>
      <Tabs items={subTabs} active={sub} onChange={setSub} ariaLabel={traducir('clientstabs.secciones_portal')} className="clpata-subtabs" />

      {sub === 'accesos' && <PortalUsersTab cid={cid} clientName={clientDetail?.name} />}
      {sub === 'uat' && <PortalUATTab _cid={cid} projects={proyectos} />}
      {sub === 'solicitudes' && <PortalSolicitudesTab cid={cid} projects={proyectos} />}
      {sub === 'mensajes' && <PortalMensajesTab cid={cid} projects={proyectos} />}
      {sub === 'documentos' && <PortalDocumentosTab cid={cid} projects={proyectos} />}
      {sub === 'config' && <PortalSettingsTab cid={cid} />}
    </div>
  )
}

export function PortalUATTab({ _cid, projects }: { _cid?: string; projects: ClientProjectRef[] }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const [selectedProject, setSelectedProject] = useState(projects[0]?.id || '')

  const { data: sessions = [], isLoading } = useQuery<TeamUatSession[]>({
    queryKey: ['uat-team-client', selectedProject],
    queryFn: () => portalApi.uat({ project_id: selectedProject }).then(r => r.data),
    enabled: !!selectedProject,
  })

  const statusColor: Record<string, string> = {
    pending: 'var(--text-2)', in_progress: 'var(--accent)', passed: 'var(--success)',
    failed: 'var(--danger)', conditional: 'var(--warning)',
  }
  const statusLabel: Record<string, string> = {
    pending: traducir('clientstabs.uat_pendiente'), in_progress: traducir('clientstabs.uat_en_progreso'), passed: traducir('clientstabs.uat_aprobado'),
    failed: traducir('clientstabs.uat_rechazado'), conditional: traducir('clientstabs.uat_con_reservas'),
  }

  return (
    <div>
      {projects.length === 0 ? (
        <EmptyState icon={<FlaskConical size={28} />} title={traducir('clients.sin_proyectos_para_uat')} description={traducir('clientstabs.asocia_proyecto_uat')} />
      ) : (
        <>
          {projects.length > 1 && (
            <SelectorDeContexto>
              <Select label={traducir('clientstabs.proyecto')} placeholder={false} id={`${idCampo}-1`} value={selectedProject} onChange={e => setSelectedProject(e.target.value)}>
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </Select>
            </SelectorDeContexto>
          )}

          {!selectedProject ? (
            <EmptyState icon={<FolderOpen size={28} />} title={traducir('clients.selecciona_un_proyecto')} description={traducir('clientstabs.elige_proyecto_uat')} />
          ) : isLoading ? <Spinner /> : sessions.length === 0 ? (
            <EmptyState icon={<FlaskConical size={28} />} title={traducir('clients.sin_sesiones_uat')} description={traducir('clientstabs.sin_sesiones_uat_proyecto')} />
          ) : (
            sessions.map(s => (
              <div key={s.id} className="clpata-panel2">
                <div className="clpata-row-7">
                  <div>
                    <div className="clpata-row-8">
                      <span className="u-text2-mono-xs">{s.code}</span>
                      <span className="u-md-700">{s.title}</span>
                    </div>
                    {s.description && <div className="u-text2-sm">{s.description.slice(0, 120)}</div>}
                    <div className="u-hint">
                      {s.available_from && traducir('clientstabs.disponible_desde', { fecha: fmtDate(s.available_from) })}
                      {s.deadline && ` · ${traducir('clientstabs.limite', { fecha: fmtDate(s.deadline) })}`}
                    </div>
                  </div>
                  <span className="clpata-box-32 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((statusColor[s.status] || 'var(--text-2)'), '20'), '--clients-page-tabs-color': statusColor[s.status] || 'var(--text-2)' } as CSSProperties}>
                    {statusLabel[s.status] || s.status}
                  </span>
                </div>
                {s.test_environment && (
                  <div className="clpata-box-11">
                    {/* 23-11-2026 (A3 del 04b): enlace solo si es http(s); si no, el texto tal cual. */}
                    {isSafeUrl(s.test_environment) && /^https?:/i.test(s.test_environment.trim())
                      ? <a href={sanitizeUrl(s.test_environment)} target="_blank" rel="noopener noreferrer" className="clpata-txt-1">{traducir('clients.entorno_de_pruebas')}</a>
                      : <span className="clpata-txt-1">{s.test_environment}</span>}
                  </div>
                )}
                {s.issues_count > 0 && (
                  <div className="clpata-box-12 clpata-ico">
                    <TriangleAlert size={13} aria-hidden="true" />{traducir('clientstabs.n_incidencias', { n: s.issues_count })}
                  </div>
                )}
              </div>
            ))
          )}
        </>
      )}
    </div>
  )
}

export function PortalSolicitudesTab({ cid }: { cid: string; projects?: ClientProjectRef[] }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { user, loading } = useAuth()

  useEffect(() => {
    if (loading || !user) return undefined

    // Auditoría 22-11-2026 (A2 del 04b): el cierre de la limpieza disparaba `onclose`
    // y programaba otra reconexión; si el ticket llegaba tras desmontar se abría un socket
    // huérfano. Con `cerrado` nada se reconecta ni se abre después de desmontar, y los
    // fallos del ticket se reintentan con un límite.
    let ws: WebSocket | undefined
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let cerrado = false
    let intentos = 0
    const MAX_INTENTOS_SIN_TICKET = 5
    function programar() {
      if (cerrado) return
      reconnectTimer = setTimeout(connectWS, WS_RECONNECT_DELAY_MS)
    }
    function connectWS() {
      if (cerrado) return
      wsApi.ticket().then((res) => {
        if (cerrado) return
        intentos = 0
        const ticket = res.data.ticket
        ws = new window.WebSocket(apiWsUrl(`/ws/notifications?ticket=${ticket}`))
        ws.onclose = () => { programar() }
        ws.onerror = () => { ws?.close() }
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data)
            if (msg.type === 'cr_state_changed' && msg.feature_request_id) {
              toast.info(traducir('clientstabs.cr_cambio_estado', { titulo: msg.title, estado: msg.cr_status }))
              qc.invalidateQueries({ queryKey: ['portal-frs-client', cid] })
            }
          } catch {
            /* accesorio: un mensaje que no es JSON no es para esta pantalla */
          }
        }
      }).catch(() => {
        intentos += 1
        if (intentos < MAX_INTENTOS_SIN_TICKET) programar()
      })
    }
    connectWS()
    return () => {
      cerrado = true
      clearTimeout(reconnectTimer)
      if (ws) { ws.onclose = null; ws.close() }
    }
  }, [cid, loading, qc, toast, user, traducir])

  const [responding, setResponding] = useState<TeamFeatureRequest | null>(null)
  const [responseForm, setResponseForm] = useState<FeatureRequestResponseForm>({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' })
  const [crDetail, setCrDetail] = useState<TeamFeatureRequest | null>(null)
  const [crFilter, setCrFilter] = useState('all')

  const { data: frs = [], isLoading } = useQuery<TeamFeatureRequest[]>({
    queryKey: ['portal-frs-client', cid],
    queryFn: () => portalApi.featureRequests({ client_org_id: cid }).then(r => r.data),
    enabled: !!cid,
  })

  const { mutate: respond, isPending } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: FeatureRequestResponseForm }) => portalApi.respondFeatureRequest(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs-client', cid] }); setResponding(null) },
    onError: e => toast.error(extractErr(e, traducir('clientstabs.error_responder'))),
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => portalApi.respondFeatureRequest(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-frs-client', cid] }),
    onError: e => toast.error(extractErr(e, traducir('clientstabs.error_actualizar_estado'))),
  })

  const statusColor: Record<string, string> = { new: 'var(--text-2)', reviewing: 'var(--accent)', estimated: 'var(--warning)', approved: 'var(--success)', rejected: 'var(--danger)', in_development: 'var(--purple)', done: 'var(--success)' }
  const statusLabel: Record<string, string> = { new: traducir('clientstabs.fr_nueva'), reviewing: traducir('clientstabs.fr_en_revision'), estimated: traducir('clientstabs.fr_presupuestada'), approved: traducir('clientstabs.fr_aprobada'), rejected: traducir('clientstabs.fr_rechazada'), in_development: traducir('clientstabs.fr_en_desarrollo'), done: traducir('clientstabs.fr_completada') }
  const prioColor: Record<string, string> = { low: 'var(--text-2)', medium: 'var(--warning)', high: 'var(--warning)', critical: 'var(--danger)' }

  if (isLoading) return <Spinner />

  const crStates = [
    { value: 'all', label: traducir('clientstabs.cr_todas') },
    { value: 'none', label: traducir('clientstabs.sin_cr') },
    { value: 'submitted', label: traducir('clientstabs.cr_enviada') },
    { value: 'under_review', label: traducir('clientstabs.cr_en_revision') },
    { value: 'approved', label: traducir('clientstabs.cr_aprobada') },
    { value: 'rejected', label: traducir('clientstabs.cr_rechazada') },
    { value: 'implemented', label: traducir('clientstabs.cr_implementada') },
  ]
  const filteredFrs = frs.filter(fr => {
    if (crFilter === 'all') return true
    if (crFilter === 'none') return !fr.cr_status
    return fr.cr_status === crFilter
  })

  return (
    <div>
      <div className="clpata-row-9">
        <span className="u-text2-base">{filteredFrs.length} {traducir('clients.solicitud_es_del_cliente')}</span>
        <Select suelto placeholder={false} aria-label={traducir('clientstabs.filtrar_por_cr')} value={crFilter} onChange={e => setCrFilter(e.target.value)} className="clpata-inp2">
          {crStates.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
        </Select>
      </div>
      {filteredFrs.length === 0 ? (
        <EmptyState icon={<Lightbulb size={28} />} title={traducir('clients.sin_solicitudes')} description={traducir('clientstabs.sin_solicitudes_cliente')} />
      ) : filteredFrs.map(fr => (
        <div className={`clpata-panel4 clients-page-tabs-e5 ${fr.cr_status ? 'clients-page-tabs-m6' : ''}`} key={fr.id} style={{ '--clients-page-tabs-border-left': fr.cr_status_color ? `6px solid ${fr.cr_status_color}` : '6px solid var(--text-3)' } as CSSProperties}>
          <div className="clpata-row-7">
            <div className="u-flex1">
              <div className="clpata-row-8">
                <IconFR />
                <span className="u-text2-mono-xs">{fr.code}</span>
                <span className="u-md-700">{fr.title}</span>
              </div>
              {fr.project_name && <div className="clpata-box-13 clpata-ico"><FolderOpen size={13} aria-hidden="true" />{fr.project_name}</div>}
            </div>
            <div className="clpata-row-10">
              <span className="clpata-box-33 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((prioColor[fr.priority] || 'var(--text-2)'), '20'), '--clients-page-tabs-color': prioColor[fr.priority] || 'var(--text-2)' } as CSSProperties}>{etiquetaCodigo(traducir, 'estado', fr.priority)}</span>
              <span className="clpata-box-33 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((statusColor[fr.status] || 'var(--text-2)'), '20'), '--clients-page-tabs-color': statusColor[fr.status] || 'var(--text-2)' } as CSSProperties}>{statusLabel[fr.status] || fr.status}</span>
              {fr.cr_status ? (
                <BadgeWithTooltip
                  label={`CR: ${fr.cr_status_label || fr.cr_status}`}
                  color={fr.cr_status_color || 'var(--text-3)'}
                  tooltip={traducir('clientstabs.tooltip_cr')}
                  icon={<IconCR />}
                  onClick={() => setCrDetail(fr)}
                />
              ) : (
                <BadgeWithTooltip
                  label={traducir('clientstabs.sin_cr')}
                  color="var(--text-3)"
                  tooltip={traducir('clientstabs.tooltip_sin_cr')}
                  icon={<IconCR />}
                />
              )}
            </div>
          </div>
          <div className="clpata-txt-2">{fr.description?.slice(0, 200)}</div>
          {fr.pm_response && (
            <div className="clpata-box-14">
              <strong className="u-success">{traducir('clients.respuesta_del_equipo')}</strong> {fr.pm_response}
              {fr.estimated_cost && <span className="clpata-box-15">· {fmtMoneda(fr.estimated_cost)}</span>}
              {fr.estimated_delivery_weeks && <span className="clpata-box-16">· {traducir('clientstabs.n_semanas', { n: fr.estimated_delivery_weeks })}</span>}
            </div>
          )}
          {fr.client_approved === true && <div className="clpata-box-17">{traducir('clients.cliente_aprobo_el')} {fmtDate(fr.client_approved_at)}</div>}
          {fr.client_approved === false && <div className="clpata-box-18">{traducir('clients.cliente_rechazo')}</div>}
          <div className="clpata-row-11">
            {['new', 'reviewing'].includes(fr.status) && (
              <Button size="sm" icon={<MessageSquare size={14} />} onClick={() => { setResponding(fr); setResponseForm({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' }) }}>
                {traducir('clientstabs.responder')}
              </Button>
            )}
            {fr.status === 'approved' && (
              <Button size="sm" variant="secondary" icon={<Rocket size={14} />} onClick={() => updateStatus({ id: fr.id, status: 'in_development' })}>
                {traducir('clientstabs.iniciar_desarrollo')}
              </Button>
            )}
            {fr.status === 'in_development' && (
              <Button size="sm" variant="secondary" icon={<Check size={14} />} onClick={() => updateStatus({ id: fr.id, status: 'done' })}>
                {traducir('clientstabs.marcar_completada')}
              </Button>
            )}
          </div>
          <div className="clpata-box-19">{fmtDateTime(fr.submitted_at)}</div>
        </div>
      ))}

      {responding && (
        <Modal open title={traducir('clientstabs.responder_a', { titulo: responding.title })} onClose={() => setResponding(null)} width={520}>
          <div className="u-stack-14">
            <Textarea label={traducir('clients.respuesta_analisis')} value={responseForm.pm_response} onChange={e => setResponseForm(f => ({ ...f, pm_response: e.target.value }))} rows={3} placeholder={traducir('clients.respuesta_del_equipo_2')} aria-label={traducir('clients.respuesta_del_equipo_2')} />
            <div className="clpata-grid-2">
              <Input label={traducir('clientstabs.horas_estimadas')} id={`${idCampo}-horas`} type="number" value={responseForm.estimated_hours} onChange={e => setResponseForm(f => ({ ...f, estimated_hours: e.target.value }))} placeholder={traducir('clientstabs.horas')} />
              <Input label={<>{traducir('clientstabs.coste_estimado')}({fmtMoneda.simbolo})</>} id={`${idCampo}-coste`} type="number" value={responseForm.estimated_cost} onChange={e => setResponseForm(f => ({ ...f, estimated_cost: e.target.value }))} placeholder={traducir('clientstabs.coste')} />
              <Input label={traducir('clientstabs.semanas_entrega')} id={`${idCampo}-semanas`} type="number" value={responseForm.estimated_delivery_weeks} onChange={e => setResponseForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} placeholder={traducir('clientstabs.semanas')} />
            </div>
            <Select label={traducir('common.status')} placeholder={false} id={`${idCampo}-1`} value={responseForm.status} onChange={e => setResponseForm(f => ({ ...f, status: e.target.value }))}>
                <option value="estimated">{traducir('clients.presupuestada_pendiente_aprobacion_cliente')}</option>
                <option value="rejected">{traducir('clients.rechazada_no_factible')}</option>
              </Select>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setResponding(null)}>{traducir('common.cancel')}</Button>
              <Button onClick={() => respond({ id: responding.id, data: responseForm })} disabled={isPending || !responseForm.pm_response}>{traducir('clientstabs.enviar_respuesta')}</Button>
            </div>
          </div>
        </Modal>
      )}

      {crDetail && (
        <Modal open title={traducir('clientstabs.detalle_cr')} onClose={() => setCrDetail(null)} width={520}>
          {crDetail.cr_status ? (
            <div className="u-stack-12">
              <div className="clpata-txt-5 clients-page-tabs-e7" style={{ '--clients-page-tabs-color': crDetail.cr_status_color } as CSSProperties}>
                <IconCR /> {traducir('clientstabs.estado_valor', { estado: crDetail.cr_status_label || crDetail.cr_status })}
              </div>
              <div><b>{traducir('clients.titulo')}</b> {crDetail.title}</div>
              <div><b>{traducir('clients.descripcion')}</b> {crDetail.description}</div>
              <div><b>{traducir('clientstabs.impacto')}</b> {crDetail.impact_label || crDetail.impact || '—'}</div>
              <div><b>{traducir('clientstabs.coste_impacto')}</b> {crDetail.cost_impact != null ? fmtMoneda(crDetail.cost_impact) : '—'}</div>
              <div><b>{traducir('clientstabs.impacto_plazo')}</b> {crDetail.schedule_impact_days != null ? traducir('clientstabs.n_dias', { n: crDetail.schedule_impact_days }) : '—'}</div>
              <div><b>{traducir('clients.notas_resolucion')}</b> {crDetail.resolution_notes || '—'}</div>
              <div><b>{traducir('clientstabs.fechas')}</b> {CR_FECHAS.map(f => crDetail[f] && (<span key={f} className="clpata-sp-1">{etiquetaCodigo(traducir, 'estado', f.replace('_at', ''))}: {fmtDateTime(crDetail[f])}</span>))}</div>
            </div>
          ) : (
            <div>{traducir('clients.no_hay_change_request_vinculada_aun_se')}</div>
          )}
        </Modal>
      )}
    </div>
  )
}

export function PortalMensajesTab({ cid, projects }: { cid: string; projects: ClientProjectRef[] }) {
  const { t: traducir } = useAppLang()
  return (
    <div className="u-stack-16">
      <TeamGovernedConversationInbox
        title={traducir('clients.conversaciones_del_cliente')}
        emptyTitle={traducir('clientstabs.sin_conversaciones')}
        emptyDescription={traducir('clientstabs.sin_conversaciones_desc')}
        projectOptions={projects.map(project => ({ id: project.id, name: project.name || project.code || project.id, code: project.code || '' }))}
        initialProjectId={projects[0]?.id || ''}
        clientOrgId={cid}
      />
      <ConversationPoliciesPanel />
    </div>
  )
}

export function PortalDocumentosTab({ cid, projects }: { cid: string; projects: ClientProjectRef[] }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const [selectedProject, setSelectedProject] = useState(projects[0]?.id || '')
  const { data: docs = [], isLoading } = useQuery<TeamPortalDocument[]>({
    queryKey: ['portal-docs-team', cid, selectedProject],
    queryFn: () => selectedProject
      ? portalApi.documents({ project_id: selectedProject }).then(r => r.data)
      : Promise.resolve([]),
    enabled: !!selectedProject,
  })
  if (isLoading) return <Spinner />
  return (
    <div>
      {projects.length > 1 && (
        <SelectorDeContexto>
          <Select label={traducir('clientstabs.proyecto')} placeholder={false} id={`${idCampo}-1`} value={selectedProject} onChange={e => setSelectedProject(e.target.value)}>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </Select>
        </SelectorDeContexto>
      )}
      {!selectedProject
        ? <EmptyState icon={<FolderOpen size={28} />} title={traducir('clients.selecciona_un_proyecto')} description={traducir('clientstabs.elige_proyecto_docs')} />
        : <div className="clpata-box-20">{traducir('clientstabs.n_documentos', { n: docs.length })}</div>}
      {docs.length === 0
        ? <EmptyState icon={<FileText size={28} />} title={traducir('clients.sin_documentos')} description={traducir('clientstabs.sin_docs_proyecto')} />
        : docs.map(d => (
          <div key={d.id} className="clpata-panel3">
            <div className="u-row-center-12">
              {(() => { const DocIcon = DOC_ICON[d.category] ?? FileText; return <span className="clpata-txt-3" aria-hidden="true"><DocIcon size={18} /></span> })()}
              <div>
                <div className="u-md-700">{d.title}</div>
                <div className="u-text2-xs">
                  {d.file_name && `${d.file_name} · `}{d.created_at ? fmtDate(d.created_at) : ''}
                  {d.requires_signature && <span className="clpata-box-15 clpata-ico"><PenLine size={12} aria-hidden="true" />{traducir('clientstabs.requiere_firma')}</span>}
                </div>
              </div>
            </div>
            {d.file_url && isSafeUrl(d.file_url) && (
              <a href={sanitizeUrl(d.file_url)} target="_blank" rel="noopener noreferrer" className="clpata-box-21 clpata-ico">
                <Download size={14} aria-hidden="true" />{traducir('clientstabs.descargar')}
              </a>
            )}
          </div>
        ))}
    </div>
  )
}
