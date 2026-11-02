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
import { useAppT } from '../i18n/AppLangContext'
import { MessageSquare } from 'lucide-react'
import { Button, Spinner, Tabs } from '../components/ui'
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

const LazyChangeManagementTab = lazy(() => import('./service-desk/ChangeManagementTab'))
const LazyITSMKnowledgeTab    = lazy(() => import('./service-desk/ITSMKnowledgeTab'))
const Loading = () => <div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>

export default function ServiceDeskPage() {
  const t = useAppT()
  // `?ticket=<id>` abre ese ticket: es a donde llevan los avisos (campana y
  // correo). Se abre en «Todos» porque la cola solo muestra los sin asignar.
  const [searchParams] = useSearchParams()
  const ticketEnlazado = searchParams.get('ticket')
  const [tab, setTab] = useState(ticketEnlazado ? 'all' : 'queue')
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
  const { data: porAprobar = [] } = useQuery<PorAprobar[]>({
    queryKey: ['sd-approvals-mine'],
    queryFn: () => sdApprovalsApi.mine().then(r => r.data as PorAprobar[]),
    refetchInterval: 60000,
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
        ariaLabel={t('service_desk.tab_config')}
      />

      {/* Mobile toggle bar when in split mode */}
      {isMobile && splitMode && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <button onClick={() => setMobileView('list')}
            aria-pressed={mobileView === 'list'}
            style={{ flex: 1, padding: '8px 0', borderRadius: 8, fontFamily: 'inherit', fontSize: "var(--text-sm)",
              fontWeight: 600, cursor: 'pointer',
              border: `1px solid ${mobileView === 'list' ? 'var(--accent)' : 'var(--surface-4)'}`,
              background: mobileView === 'list' ? 'var(--accent-muted)' : 'var(--surface-2)',
              color: mobileView === 'list' ? 'var(--accent)' : 'var(--text-2)' }}>
            ← {t('service_desk.tab_all')}
          </button>
          <button onClick={() => setMobileView('detail')}
            aria-pressed={mobileView === 'detail'}
            style={{ flex: 1, padding: '8px 0', borderRadius: 8, fontFamily: 'inherit', fontSize: "var(--text-sm)",
              fontWeight: 600, cursor: 'pointer',
              border: `1px solid ${mobileView === 'detail' ? 'var(--accent)' : 'var(--surface-4)'}`,
              background: mobileView === 'detail' ? 'var(--accent-muted)' : 'var(--surface-2)',
              color: mobileView === 'detail' ? 'var(--accent)' : 'var(--text-2)' }}>
            {t('service_desk.tab_all')} →
          </button>
        </div>
      )}

      {/* Content */}
      <div className="min-w-0" style={!isMobile && splitMode ? {
        display: 'grid',
        gridTemplateColumns: 'minmax(360px, 1fr) minmax(380px, 1fr)',
        gap: 16,
        alignItems: 'start',
      } : undefined}>
        {/* List panel — hidden on mobile when viewing detail */}
        {(!isMobile || !splitMode || mobileView === 'list') && (
          <div>
            {tab === 'queue'    && <div id="sd-panel-queue" role="tabpanel" aria-labelledby="sd-tab-queue"><TicketList queueOnly={true}  onSelect={tk => setSelId(String(tk.id))} /></div>}
            {tab === 'all'      && <div id="sd-panel-all" role="tabpanel" aria-labelledby="sd-tab-all"><TicketList queueOnly={false} onSelect={tk => setSelId(String(tk.id))} /></div>}
            {tab === 'kanban'   && <div id="sd-panel-kanban" role="tabpanel" aria-labelledby="sd-tab-kanban"><KanbanTicketsTab onSelect={tk => setSelId(String(tk.id))} /></div>}
            {tab === 'approvals' && (
              <div id="sd-panel-approvals" role="tabpanel" aria-labelledby="sd-tab-approvals">
                <ListaPorAprobar items={porAprobar} seleccionado={selId} onSelect={setSelId} />
              </div>
            )}
            {tab === 'changes'  && (
              <div id="sd-panel-changes" role="tabpanel" aria-labelledby="sd-tab-changes"><Suspense fallback={<Loading />}>
                <LazyChangeManagementTab />
              </Suspense></div>
            )}
            {tab === 'mi'       && <div id="sd-panel-mi" role="tabpanel" aria-labelledby="sd-tab-mi"><MajorIncidents /></div>}
            {tab === 'problems' && (
              <div id="sd-panel-problems" role="tabpanel" aria-labelledby="sd-tab-problems"><Suspense fallback={<Loading />}>
                <LazyITSMKnowledgeTab mode="problems" />
              </Suspense></div>
            )}
            {tab === 'kedb'     && (
              <div id="sd-panel-kedb" role="tabpanel" aria-labelledby="sd-tab-kedb"><Suspense fallback={<Loading />}>
                <LazyITSMKnowledgeTab mode="kedb" />
              </Suspense></div>
            )}
            {tab === 'kb'       && (
              <div id="sd-panel-kb" role="tabpanel" aria-labelledby="sd-tab-kb"><Suspense fallback={<Loading />}>
                <LazyITSMKnowledgeTab mode="kb" />
              </Suspense></div>
            )}
            {tab === 'tools' && (
              <div role="tablist" aria-label={t('sd_cfg.tab_tools')} style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
                {HERRAMIENTAS.map(h => (
                  <button key={h.id} type="button" role="tab" aria-selected={herramienta === h.id} onClick={() => setHerramienta(h.id)}
                    style={{ padding: '6px 14px', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-sm)', fontWeight: 600,
                      border: `1px solid ${herramienta === h.id ? 'var(--accent)' : 'var(--surface-4)'}`,
                      background: herramienta === h.id ? 'var(--accent-muted)' : 'transparent',
                      color: herramienta === h.id ? 'var(--accent)' : 'var(--text-2)' }}>{h.label}</button>
                ))}
              </div>
            )}
            {tab === 'config'   && <div id="sd-panel-config" role="tabpanel" aria-labelledby="sd-tab-config"><Config /></div>}
            {tab === 'tools' && herramienta === 'voice'    && <div id="sd-panel-voice" role="tabpanel" aria-labelledby="sd-tab-voice"><VoiceAgentPanel /></div>}
            {tab === 'tools' && herramienta === 'assign'   && <div id="sd-panel-assign" role="tabpanel" aria-labelledby="sd-tab-assign"><IncidentAssignmentPanel /></div>}
            {tab === 'tools' && herramienta === 'rollout'     && <div id="sd-panel-rollout" role="tabpanel" aria-labelledby="sd-tab-rollout"><ChangeRolloutPanel /></div>}
            {tab === 'tools' && herramienta === 'autoresolve' && <div id="sd-panel-autoresolve" role="tabpanel" aria-labelledby="sd-tab-autoresolve"><AutoResolutionPanel /></div>}
            {tab === 'tools' && herramienta === 'alertcorr'   && <div id="sd-panel-alertcorr" role="tabpanel" aria-labelledby="sd-tab-alertcorr"><AlertCorrelationPanel /></div>}
          </div>
        )}
        {/* Detail panel — inline on desktop split, full-width on mobile */}
        {splitMode && (!isMobile || mobileView === 'detail') && (
          <div>
            {isMobile && (
              <button onClick={() => setMobileView('list')}
                style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12,
                  background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)',
                  fontSize: "var(--text-base)", fontWeight: 600, fontFamily: 'inherit', padding: 0 }}>
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
          onCreated={tk => { const created = tk as { id?: unknown }; if (created?.id) setSelId(String(created.id)) }}
        />
      )}
    </PageShell>
  )
}


type PorAprobar = { approval_id: string; ticket_id: string; number: string; title: string; requester_name?: string; service_item_name?: string; created_at?: string }

function ListaPorAprobar({ items, seleccionado, onSelect }: { items: PorAprobar[]; seleccionado: string | null; onSelect: (id: string) => void }) {
  const t = useAppT()
  if (items.length === 0) {
    return <div style={{ padding: 24, color: 'var(--text-3)', fontSize: 'var(--text-sm)' }}>{t('sd_cfg.apr_empty')}</div>
  }
  return (
    <div className="ds-card" style={{ padding: 0, overflow: 'hidden' }}>
      {items.map((a, i) => (
        <button key={a.approval_id} type="button" onClick={() => onSelect(a.ticket_id)}
          aria-pressed={seleccionado === a.ticket_id}
          style={{ display: 'flex', width: '100%', textAlign: 'left', gap: 12, alignItems: 'center', padding: '12px 16px',
            border: 'none', borderTop: i ? '1px solid var(--surface-4)' : 'none', cursor: 'pointer', fontFamily: 'inherit',
            background: seleccionado === a.ticket_id ? 'var(--accent-muted)' : 'transparent', color: 'var(--text-1)' }}>
          <span style={{ fontWeight: 700, color: 'var(--accent)', fontSize: 'var(--text-sm)' }}>{a.number}</span>
          <span style={{ flex: 1, minWidth: 0 }}>
            <span style={{ display: 'block', fontWeight: 600 }}>{a.title}</span>
            <span style={{ display: 'block', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
              {[a.requester_name, a.service_item_name].filter(Boolean).join(' · ')}
            </span>
          </span>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', whiteSpace: 'nowrap' }}>
            {a.created_at ? new Date(a.created_at).toLocaleDateString() : ''}
          </span>
        </button>
      ))}
    </div>
  )
}
