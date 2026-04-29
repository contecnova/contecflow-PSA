/**
 * ServiceDeskPage — ITIL/ITSM completo
 * Módulos: Queue · Tickets · Problems/KEDB · Changes · Major Incidents ·
 *          KB · Metrics · Routing · Templates · Config
 * CMDB: sección independiente en /cmdb
 */
import { useState, useEffect, lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'
import { useAppT } from '../i18n/AppLangContext'
import { MessageSquare } from 'lucide-react'
import { Button, Spinner } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
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
import AutoResolutionPanel from '../components/servicedesk/AutoResolutionPanel'
import AlertCorrelationPanel from '../components/servicedesk/AlertCorrelationPanel'

const LazyMetricsDashboard    = lazy(() => import('./service-desk/MetricsDashboardTab'))
const LazyChangeManagementTab = lazy(() => import('./service-desk/ChangeManagementTab'))
const LazyITSMKnowledgeTab    = lazy(() => import('./service-desk/ITSMKnowledgeTab'))
const LazyAnnouncements       = lazy(() => import('./service-desk/ConfigTab').then(m => ({ default: m.AnnouncementsConfig })))
const Loading = () => <div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>

export default function ServiceDeskPage() {
  const t = useAppT()
  const [tab, setTab] = useState('queue')
  const [selId, setSelId] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [mobileView, setMobileView] = useState('list') // 'list' | 'detail'
  const windowWidth = useWindowWidth()
  const isMobile = windowWidth < 768
  const splitMode = selId && (tab === 'queue' || tab === 'all' || tab === 'kanban')

  useEffect(() => {
    if (isMobile && selId) setMobileView('detail')
  }, [selId, isMobile])

  useEffect(() => {
    setMobileView('list')
    setSelId(null)
  }, [tab])

  const TABS = [
    { id: 'queue',    label: `${t('service_desk.tab_queue')}` },
    { id: 'all',      label: `${t('service_desk.tab_all')}` },
    { id: 'kanban',   label: `${t('service_desk.tab_kanban')}` },
    { id: 'changes',  label: `${t('service_desk.tab_changes')}` },
    { id: 'mi',       label: `${t('service_desk.tab_mi')}` },
    { id: 'problems', label: `${t('service_desk.tab_problems')}` },
    { id: 'kedb',     label: `${t('service_desk.tab_kedb')}` },
    { id: 'kb',       label: `${t('service_desk.tab_kb')}` },
    { id: 'announcements', label: `${t('service_desk.tab_announcements')}` },
    { id: 'metrics',  label: `${t('service_desk.tab_metrics')}` },
    { id: 'config',   label: `${t('service_desk.tab_config')}` },
    { id: 'voice',       label: t('service_desk.tab_voice') },
    { id: 'assign',      label: t('service_desk.tab_assign') },
    { id: 'rollout',     label: t('service_desk.tab_rollout') },
    { id: 'autoresolve', label: t('service_desk.tab_autoresolve', 'Auto-resolución') },
    { id: 'alertcorr',   label: t('service_desk.tab_alertcorr', 'Correlación alertas') },
  ]

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<MessageSquare size={18} />}
        title={t('service_desk.title')}
        subtitle={t('service_desk.subtitle')}
        actions={
          <Button onClick={() => setShowCreate(true)}>+ {t('service_desk.ticket_create_btn')}</Button>
        }/>

      {/* Tab bar */}
      <div role="tablist" aria-label={t('service_desk.tab_config')} style={{ display: 'flex', gap: 6, marginBottom: 28, flexWrap: 'wrap',
        borderBottom: '1px solid var(--surface-4)', paddingBottom: 16 }}>
        {TABS.map((tb, i) => (
          <button key={tb.id} role="tab" aria-selected={tab===tb.id} aria-controls={`sd-panel-${tb.id}`} id={`sd-tab-${tb.id}`} onClick={() => setTab(tb.id)} style={{
            padding: '7px 16px', borderRadius: 8,
            border: `1px solid ${tab===tb.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
            background: tab===tb.id ? 'var(--accent-muted)' : 'transparent',
            color: tab===tb.id ? 'var(--accent)' : 'var(--text-2)',
            fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            whiteSpace: 'nowrap',
          }}>{tb.label}</button>
        ))}
        <Link to="/cmdb" style={{
          padding: '7px 16px', borderRadius: 8,
          border: '1px dashed var(--surface-4)',
          background: 'transparent', color: 'var(--text-3)',
          fontSize: 12, fontWeight: 600, textDecoration: 'none',
          whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: 4,
        }} title="CMDB es ahora una sección independiente">🖥️ CMDB ↗</Link>
      </div>

      {/* Mobile toggle bar when in split mode */}
      {isMobile && splitMode && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <button onClick={() => setMobileView('list')}
            aria-pressed={mobileView === 'list'}
            style={{ flex: 1, padding: '8px 0', borderRadius: 8, fontFamily: 'inherit', fontSize: 12,
              fontWeight: 600, cursor: 'pointer',
              border: `1px solid ${mobileView === 'list' ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
              background: mobileView === 'list' ? 'var(--accent-muted)' : 'var(--surface-2)',
              color: mobileView === 'list' ? 'var(--accent)' : 'var(--text-2)' }}>
            ← {t('service_desk.tab_all')}
          </button>
          <button onClick={() => setMobileView('detail')}
            aria-pressed={mobileView === 'detail'}
            style={{ flex: 1, padding: '8px 0', borderRadius: 8, fontFamily: 'inherit', fontSize: 12,
              fontWeight: 600, cursor: 'pointer',
              border: `1px solid ${mobileView === 'detail' ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
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
            {tab === 'queue'    && <div id="sd-panel-queue" role="tabpanel" aria-labelledby="sd-tab-queue"><TicketList queueOnly={true}  onSelect={tk => setSelId(tk.id)} /></div>}
            {tab === 'all'      && <div id="sd-panel-all" role="tabpanel" aria-labelledby="sd-tab-all"><TicketList queueOnly={false} onSelect={tk => setSelId(tk.id)} /></div>}
            {tab === 'kanban'   && <div id="sd-panel-kanban" role="tabpanel" aria-labelledby="sd-tab-kanban"><KanbanTicketsTab onSelect={tk => setSelId(tk.id)} /></div>}
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
            {tab === 'metrics'  && (
              <div id="sd-panel-metrics" role="tabpanel" aria-labelledby="sd-tab-metrics"><Suspense fallback={<Loading />}>
                <LazyMetricsDashboard />
              </Suspense></div>
            )}
            {tab === 'announcements' && (
              <div id="sd-panel-announcements" role="tabpanel" aria-labelledby="sd-tab-announcements"><Suspense fallback={<Loading />}>
                <LazyAnnouncements />
              </Suspense></div>
            )}
            {tab === 'config'   && <div id="sd-panel-config" role="tabpanel" aria-labelledby="sd-tab-config"><Config /></div>}
            {tab === 'voice'    && <div id="sd-panel-voice" role="tabpanel" aria-labelledby="sd-tab-voice"><VoiceAgentPanel /></div>}
            {tab === 'assign'   && <div id="sd-panel-assign" role="tabpanel" aria-labelledby="sd-tab-assign"><IncidentAssignmentPanel /></div>}
            {tab === 'rollout'     && <div id="sd-panel-rollout" role="tabpanel" aria-labelledby="sd-tab-rollout"><ChangeRolloutPanel /></div>}
            {tab === 'autoresolve' && <div id="sd-panel-autoresolve" role="tabpanel" aria-labelledby="sd-tab-autoresolve"><AutoResolutionPanel /></div>}
            {tab === 'alertcorr'   && <div id="sd-panel-alertcorr" role="tabpanel" aria-labelledby="sd-tab-alertcorr"><AlertCorrelationPanel /></div>}
            {tab === 'autoresolve' && <div id="sd-panel-autoresolve" role="tabpanel" aria-labelledby="sd-tab-autoresolve"><AutoResolutionPanel /></div>}
            {tab === 'alertcorr'   && <div id="sd-panel-alertcorr" role="tabpanel" aria-labelledby="sd-tab-alertcorr"><AlertCorrelationPanel /></div>}
          </div>
        )}
        {/* Detail panel — inline on desktop split, full-width on mobile */}
        {splitMode && (!isMobile || mobileView === 'detail') && (
          <div>
            {isMobile && (
              <button onClick={() => setMobileView('list')}
                style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12,
                  background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)',
                  fontSize: 13, fontWeight: 600, fontFamily: 'inherit', padding: 0 }}>
                ← Volver a la lista
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
          onCreated={tk => tk?.id && setSelId(tk.id)}
        />
      )}
    </div>
  )
}
