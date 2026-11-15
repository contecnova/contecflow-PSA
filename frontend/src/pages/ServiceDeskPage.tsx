/**
 * ServiceDeskPage — ITIL/ITSM completo
 * Módulos: Queue · Tickets · Problems/KEDB · Changes · Major Incidents ·
 *          KB · Metrics · Routing · Templates · Config
 * CMDB: sección independiente en /cmdb
 */
import { useState, useEffect, useRef, lazy, Suspense } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { sdApprovalsApi } from '../services/api'
import type { SdAprobacionPendiente } from '../services/api/tipos-sd'
import { useAppT } from '../i18n/AppLangContext'
import { MessageSquare } from 'lucide-react'
import { Button, Spinner, Tabs } from '../components/ui'
import { useTabListKeys } from '../components/ui/Tabs'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { TicketList, MajorIncidents } from './service-desk/QueueAndRoutingSections'
import { useWindowWidth } from './service-desk/sdUtils'
import TicketDetail from './service-desk/TicketDetail'
import CreateTicketModal from './service-desk/CreateTicketModal'
import KanbanTicketsTab from './service-desk/KanbanTicketsTab'
import Config from './service-desk/ConfigTab'
import VoiceAgentPanel from '../components/servicedesk/VoiceAgentPanel'
import IncidentAssignmentPanel from '../components/servicedesk/IncidentAssignmentPanel'
import ChangeRolloutPanel from '../components/servicedesk/ChangeRolloutPanel'
import AutoResolutionPanel from '../components/servicedesk/AutoResolutionPanel'
import AlertCorrelationPanel from '../components/servicedesk/AlertCorrelationPanel'
import { fmtDate } from '../utils/helpers'
import { POLL_DEFAULT_MS } from '../constants/timings'
import './ServiceDeskPage.css'

const LazyChangeManagementTab = lazy(() => import('./service-desk/ChangeManagementTab'))
const LazyITSMKnowledgeTab    = lazy(() => import('./service-desk/ITSMKnowledgeTab'))
const Loading = () => <div className="sdp-loading"><Spinner /></div>

export default function ServiceDeskPage() {
  const t = useAppT()
  // `?ticket=<id>` abre ese ticket: es a donde llevan los avisos (campana y
  // correo). Se abre en «Todos» porque la cola solo muestra los sin asignar.
  const [searchParams] = useSearchParams()
  const ticketEnlazado = searchParams.get('ticket')
  // `?tab=<id>` abre esa pestaña (p. ej. los avisos y las citas de la base de
  // conocimiento llevan a `?tab=kb`).
  const [tab, setTab] = useState(ticketEnlazado ? 'all' : (searchParams.get('tab') || 'queue'))
  const [herramienta, setHerramienta] = useState('assign')
  // `TicketDetail` pide `string | null`: los ids de ticket son cadenas en
  // toda la aplicacion, y el tablero kanban es el unico sitio que los saca
  // como `string | number`. Se normalizan aqui, en la frontera.
  const [selId, setSelId] = useState<string | null>(ticketEnlazado)
  const primeraPestana = useRef(true)
  const [showCreate, setShowCreate] = useState(false)
  const [mobileView, setMobileView] = useState('list') // 'list' | 'detail'
  const windowWidth = useWindowWidth()
  const isMobile = windowWidth < 768
  const splitMode = selId && (tab === 'queue' || tab === 'all' || tab === 'kanban' || tab === 'approvals')
  const { data: porAprobar = [] } = useQuery({
    queryKey: ['sd-approvals-mine'],
    queryFn: () => sdApprovalsApi.mine().then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })

  useEffect(() => {
    if (isMobile && selId) setMobileView('detail')
  }, [selId, isMobile])

  useEffect(() => {
    // Al montar no se limpia: borraria el ticket que trae el enlace.
    if (primeraPestana.current) { primeraPestana.current = false; return }
    setMobileView('list')
    setSelId(null)
  }, [tab])

  useEffect(() => {
    if (ticketEnlazado) { setTab('all'); setSelId(ticketEnlazado) }
  }, [ticketEnlazado])

  const TABS = [
    { id: 'queue',    label: `${t('service_desk.tab_queue')}` },
    { id: 'all',      label: `${t('service_desk.tab_all')}` },
    { id: 'kanban',   label: `${t('service_desk.tab_kanban')}` },
    // Solo si hay algo que aprobar: para el resto seria una pestaña siempre vacia.
    ...(porAprobar.length > 0 || tab === 'approvals'
      ? [{ id: 'approvals', label: `${t('sd_cfg.apr_tab')} (${porAprobar.length})` }] : []),
    { id: 'changes',  label: `${t('service_desk.tab_changes')}` },
    { id: 'mi',       label: `${t('service_desk.tab_mi')}` },
    { id: 'problems', label: `${t('service_desk.tab_problems')}` },
    { id: 'kedb',     label: `${t('service_desk.tab_kedb')}` },
    { id: 'kb',       label: `${t('service_desk.tab_kb')}` },
    // Las herramientas avanzadas van juntas: eran cinco pestañas de primer
    // nivel al lado del trabajo diario, y los anuncios viven en Configuración.
    { id: 'tools',    label: t('sd_cfg.tab_tools') },
    { id: 'config',   label: `${t('service_desk.tab_config')}` },
  ]
  const HERRAMIENTAS = [
    { id: 'assign',      label: t('service_desk.tab_assign') },
    { id: 'autoresolve', label: t('service_desk.tab_autoresolve') },
    { id: 'alertcorr',   label: t('service_desk.tab_alertcorr') },
    { id: 'rollout',     label: t('service_desk.tab_rollout') },
    { id: 'voice',       label: t('service_desk.tab_voice') },
  ]
  const etiquetaDePanel = (id: string) => [...TABS, ...HERRAMIENTAS].find(x => x.id === id)?.label ?? id
  const teclasHerramientas = useTabListKeys(HERRAMIENTAS.map(h => h.id), herramienta, setHerramienta)

  return (
    <PageShell>
      <PageHeader
        icon={<MessageSquare size={18} />}
        title={t('service_desk.title')}
        subtitle={t('service_desk.subtitle')}
        exportTargetSelector='[data-export-table="service-desk-export"]'
        exportFilePrefix='service_desk'
        actions={
          <Button onClick={() => setShowCreate(true)}>+ {t('service_desk.ticket_create_btn')}</Button>
        }/>

      <Tabs
        items={TABS}
        active={tab}
        onChange={setTab}
        variant="pill"
        ariaLabel={t('service_desk.secciones')}
      />

      {/* Mobile toggle bar when in split mode */}
      {isMobile && splitMode && (
        <div className="sdp-mobile-toggle">
          <button type="button" className="sdp-mobile-toggle-btn" onClick={() => setMobileView('list')}
            aria-pressed={mobileView === 'list'}>
            ← {t('service_desk.vista_lista')}
          </button>
          <button type="button" className="sdp-mobile-toggle-btn" onClick={() => setMobileView('detail')}
            aria-pressed={mobileView === 'detail'}>
            {t('service_desk.vista_detalle')} →
          </button>
        </div>
      )}

      {/* Content */}
      <div className={`sdp-main${!isMobile && splitMode ? ' sdp-split' : ''}`}>
        {/* List panel — hidden on mobile when viewing detail */}
        {(!isMobile || !splitMode || mobileView === 'list') && (
          <div>
            {tab === 'queue'    && <div id="sd-panel-queue" role="tabpanel" aria-label={etiquetaDePanel('queue')}><TicketList queueOnly={true}  onSelect={tk => setSelId(String(tk.id))} /></div>}
            {tab === 'all'      && <div id="sd-panel-all" role="tabpanel" aria-label={etiquetaDePanel('all')}><TicketList queueOnly={false} onSelect={tk => setSelId(String(tk.id))} /></div>}
            {tab === 'kanban'   && <div id="sd-panel-kanban" role="tabpanel" aria-label={etiquetaDePanel('kanban')}><KanbanTicketsTab onSelect={tk => setSelId(String(tk.id))} /></div>}
            {tab === 'approvals' && (
              <div id="sd-panel-approvals" role="tabpanel" aria-label={etiquetaDePanel('approvals')}>
                <ListaPorAprobar items={porAprobar} seleccionado={selId} onSelect={setSelId} />
              </div>
            )}
            {tab === 'changes'  && (
              <div id="sd-panel-changes" role="tabpanel" aria-label={etiquetaDePanel('changes')}><Suspense fallback={<Loading />}>
                <LazyChangeManagementTab />
              </Suspense></div>
            )}
            {tab === 'mi'       && <div id="sd-panel-mi" role="tabpanel" aria-label={etiquetaDePanel('mi')}><MajorIncidents /></div>}
            {tab === 'problems' && (
              <div id="sd-panel-problems" role="tabpanel" aria-label={etiquetaDePanel('problems')}><Suspense fallback={<Loading />}>
                <LazyITSMKnowledgeTab mode="problems" />
              </Suspense></div>
            )}
            {tab === 'kedb'     && (
              <div id="sd-panel-kedb" role="tabpanel" aria-label={etiquetaDePanel('kedb')}><Suspense fallback={<Loading />}>
                <LazyITSMKnowledgeTab mode="kedb" />
              </Suspense></div>
            )}
            {tab === 'kb'       && (
              <div id="sd-panel-kb" role="tabpanel" aria-label={etiquetaDePanel('kb')}><Suspense fallback={<Loading />}>
                <LazyITSMKnowledgeTab mode="kb" />
              </Suspense></div>
            )}
            {tab === 'tools' && (
              <div ref={teclasHerramientas.listRef} onKeyDown={teclasHerramientas.onKeyDown} role="tablist" aria-label={t('sd_cfg.tab_tools')} className="sdp-tools">
                {HERRAMIENTAS.map(h => (
                  <button key={h.id} type="button" role="tab" data-tab-id={h.id} tabIndex={h.id === teclasHerramientas.focusId ? 0 : -1} aria-selected={herramienta === h.id} onClick={() => setHerramienta(h.id)}
                    className="sdp-tool">{h.label}</button>
                ))}
              </div>
            )}
            {tab === 'config'   && <div id="sd-panel-config" role="tabpanel" aria-label={etiquetaDePanel('config')}><Config /></div>}
            {tab === 'tools' && herramienta === 'voice'    && <div id="sd-panel-voice" role="tabpanel" aria-label={etiquetaDePanel('voice')}><VoiceAgentPanel /></div>}
            {tab === 'tools' && herramienta === 'assign'   && <div id="sd-panel-assign" role="tabpanel" aria-label={etiquetaDePanel('assign')}><IncidentAssignmentPanel /></div>}
            {tab === 'tools' && herramienta === 'rollout'     && <div id="sd-panel-rollout" role="tabpanel" aria-label={etiquetaDePanel('rollout')}><ChangeRolloutPanel /></div>}
            {tab === 'tools' && herramienta === 'autoresolve' && <div id="sd-panel-autoresolve" role="tabpanel" aria-label={etiquetaDePanel('autoresolve')}><AutoResolutionPanel /></div>}
            {tab === 'tools' && herramienta === 'alertcorr'   && <div id="sd-panel-alertcorr" role="tabpanel" aria-label={etiquetaDePanel('alertcorr')}><AlertCorrelationPanel /></div>}
          </div>
        )}
        {/* Detail panel — inline on desktop split, full-width on mobile */}
        {splitMode && (!isMobile || mobileView === 'detail') && (
          <div>
            {isMobile && (
              <button type="button" className="sdp-back" onClick={() => setMobileView('list')}>
                {t('servicedesk.volver_a_la_lista')}
              </button>
            )}
            <TicketDetail ticketId={selId} onClose={() => { setSelId(null); setMobileView('list') }} embedded={true} />
          </div>
        )}
      </div>

      {/* Create ticket modal */}
      {showCreate && (
        <CreateTicketModal
          onClose={() => setShowCreate(false)}
          onCreated={tk => setSelId(tk.id)}
        />
      )}
    </PageShell>
  )
}


type PorAprobar = SdAprobacionPendiente

function ListaPorAprobar({ items, seleccionado, onSelect }: { items: PorAprobar[]; seleccionado: string | null; onSelect: (id: string) => void }) {
  const t = useAppT()
  if (items.length === 0) {
    return <div className="sdp-apr-empty">{t('sd_cfg.apr_empty')}</div>
  }
  return (
    <div className="ds-card sdp-apr-list">
      {items.map((a) => (
        <button key={a.approval_id} type="button" onClick={() => onSelect(a.ticket_id)}
          aria-pressed={seleccionado === a.ticket_id} className="sdp-apr-item">
          <span className="sdp-apr-number">{a.number}</span>
          <span className="u-flex1-min0">
            <span className="sdp-apr-title">{a.title}</span>
            <span className="sdp-apr-meta">
              {[a.requester_name, a.service_item_name].filter(Boolean).join(' · ')}
            </span>
          </span>
          <span className="sdp-apr-date">
            {a.created_at ? fmtDate(a.created_at) : ''}
          </span>
        </button>
      ))}
    </div>
  )
}
