/**
 * ClientPortalPage – Internal PM view for managing the client portal:
 * - Manage client users and their access
 * - Create/manage UAT sessions with test cases
 * - Send messages to clients
 * - Upload documents
 * - View portal stats
 */
import { useState } from 'react'
import { Select, EmptyState, Page, Tabs, SelectorDeContexto } from '../components/ui'
import { Globe, Users, FlaskConical, Lightbulb, FileText, BookOpen, MessageSquare } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import './ClientPortalPage.css'
import { useListaDeProyectos } from '../hooks/useListas'
import { ClientUsersTab } from './ClientPortalUsuarios'
import { UATTab } from './ClientPortalUat'
import { DocumentsTab, FeatureRequestsTab, MessagesTab, StatsPanel, WikiPortalTab } from './ClientPortalSolicitudes'

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ClientPortalPage(): JSX.Element {
  const traducir = useAppT()
  const t = useAppT()
  const [tab, setTab] = useState('clients')
  const [selectedProject, setSelectedProject] = useState('')

  // 23-11-2026 (A8 del 04): la lista compartida de proyectos (sin colisión de clave).
  const { data: projects = [] } = useListaDeProyectos()

  const TABS = [
    { id: 'clients',  label: t('client_portal.tab_contacts'), icon: <Users size={14} /> },
    { id: 'uat',      label: t('client_portal.tab_uat'), icon: <FlaskConical size={14} /> },
    { id: 'requests', label: t('client_portal.tab_requests'), icon: <Lightbulb size={14} /> },
    { id: 'messages', label: t('client_portal.tab_messages'), icon: <MessageSquare size={14} /> },
    { id: 'documents',label: t('client_portal.tab_documents'), icon: <FileText size={14} /> },
    { id: 'wiki',     label: t('client_portal.tab_wiki'), icon: <BookOpen size={14} /> },
  ]

  return (
    <Page
      icon={<Globe size={18} />}
      title={t('client_portal.title')}
      subtitle={t('client_portal.subtitle')}
    >
      {/* 16-11-2026 (pasada de diseño): el selector de proyecto es un filtro y va
          en la barra de filtros, no en la cabecera. */}
      <SelectorDeContexto>
        <Select label={t('uikit.etiqueta_proyecto')} value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
          placeholder={t('client_portal.select_project')}>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </Select>
      </SelectorDeContexto>

      {selectedProject && <StatsPanel projectId={selectedProject} />}

      <Tabs className="cpp-tabs" items={TABS} active={tab} onChange={setTab} ariaLabel={traducir('clientportal.secciones_del_portal_cliente')} />

      {!selectedProject ? (
        <EmptyState svgIcon={<Globe size={36} />} title={t('client_portal.empty_select_title')} description={t('client_portal.empty_select_desc')} />
      ) : (
        <>
          {tab === 'clients'   && <ClientUsersTab projectId={selectedProject} />}
          {tab === 'uat'       && <UATTab projectId={selectedProject} />}
          {tab === 'requests'  && <FeatureRequestsTab projectId={selectedProject} />}
          {tab === 'messages'  && <MessagesTab projectId={selectedProject} />}
          {tab === 'documents' && <DocumentsTab projectId={selectedProject} />}
          {tab === 'wiki'      && <WikiPortalTab projectId={selectedProject} />}
        </>
      )}
    </Page>
  )
}