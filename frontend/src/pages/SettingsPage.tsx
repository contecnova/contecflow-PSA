import PuestaEnMarchaSection from './settings-sections/PuestaEnMarchaSection'
import MarcaSection from './settings-sections/MarcaSection'
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Tabs, Page } from '../components/ui'
import { Settings } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
import './SettingsPage.css'
import {
  GeneralSection,
  SessionSecuritySection,
  UsersSection,
  RolesSection,
  AlertConfigSection,
  MetricsSection,
  TaskTypesSection,
  RateTablesSection,
  VacationSection,
  DepartmentsSection,
  OfficesSection,
  NumberingSection,
  CustomFieldsSection,
  IdiomasSection,
  EmailInboundSection,
  LogLevelSection,
  SystemStateSection,
  ESignSettingsSection,
  RuntimeFlagsSection,
  IntegrationCredentialsSection,
} from './SettingsPageSections'

const TAB_GROUPS = [
  {
    id: 'personal',
    label: 'settings_page.grupo_personal',
    tabs: [
      { id: 'setup',        label: 'settings_page.tab_setup', roles: ['admin'] },
      { id: 'general',      label: 'settings_page.tab_general',        roles: ['admin'] },
      { id: 'session',      label: 'settings_page.tab_session',         roles: ['admin'] },
      { id: 'users',        label: 'settings_page.tab_users',       roles: ['admin', 'hr'] },
      { id: 'vacations',    label: 'settings_page.tab_vacations',     roles: ['admin', 'hr'] },
      { id: 'depts',        label: 'settings_page.tab_depts',  roles: ['admin', 'hr'] },
      { id: 'offices',      label: 'settings_page.tab_offices',          roles: ['admin'] },
      { id: 'idiomas',      label: 'settings_page.tab_idiomas',        roles: ['admin'] },
    ],
  },
  {
    id: 'workspace',
    label: 'settings_page.grupo_workspace',
    tabs: [
      { id: 'task-types',   label: 'settings_page.tab_task_types',    roles: ['admin', 'pm'] },
      { id: 'rates',        label: 'settings_page.tab_rates',        roles: ['admin'] },
      { id: 'numbering',    label: 'settings_page.tab_numbering',     roles: ['admin'] },
      { id: 'fields',       label: 'settings_page.tab_fields',   roles: ['admin'] },
      { id: 'alert-config', label: 'settings_page.tab_alert_config',        roles: ['admin'] },
      { id: 'metrics',      label: 'settings_page.tab_metrics',       roles: ['admin'] },
      { id: 'branding',     label: 'settings_page.tab_branding',          roles: ['admin'] },
    ],
  },
  {
    id: 'sistema',
    label: 'settings_page.grupo_sistema',
    tabs: [
      { id: 'roles',         label: 'settings_page.tab_roles',           roles: ['admin'] },
      { id: 'runtime-flags', label: 'settings_page.tab_runtime_flags', roles: ['admin'] },
      { id: 'integrations',  label: 'settings_page.tab_integrations',    roles: ['admin'] },
      { id: 'email-inbound', label: 'settings_page.tab_email_inbound', roles: ['admin'] },
      { id: 'esign',         label: 'settings_page.tab_esign',         roles: ['admin'] },
      { id: 'log-level',     label: 'settings_page.tab_log_level',    roles: ['admin'] },
      { id: 'system-state',  label: 'settings_page.tab_system_state',  roles: ['admin'] },
    ],
  },
]

const TABS = TAB_GROUPS.flatMap(g => g.tabs)

export default function SettingsPage() {
  const { user } = useAuth()
  const { t } = useAppLang()
  // `user?.role` es `string | undefined` y `includes` no lo acepta. Un rol
  // ausente no encaja en ninguna pestaña, que es justo lo que hacía antes
  // `includes(undefined)`: devolver falso.
  const rol = user?.role ?? ''
  const visibleTabs = TABS.filter(tab => tab.roles.includes(rol))
  // `?tab=<id>` abre esa pestaña: desde el Service Desk se llega a Credenciales.
  const { search } = useLocation()
  const pedida = new URLSearchParams(search).get('tab')
  const [activeTab, setActiveTab] = useState(
    visibleTabs.some(tab => tab.id === pedida) ? (pedida as string) : (visibleTabs[0]?.id || 'general'))
  // Revisión 2026-11: la puesta en marcha enlaza a otras pestañas de esta misma
  // página; navegar sin desmontarla no volvía a leer `?tab=`.
  useEffect(() => {
    if (pedida && visibleTabs.some(tab => tab.id === pedida)) setActiveTab(pedida)
  }, [search]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Page
      icon={<Settings size={18} />}
      title={t('settings.title')}
      subtitle={t('settings.subtitle')}
    >
      <div className="stp-groups">
        {TAB_GROUPS.map(group => {
          const groupVisible = group.tabs.filter(tab => tab.roles.includes(rol))
          if (groupVisible.length === 0) return null
          return (
            <div key={group.id}>
              <div className="ds-eyebrow stp-group-label">
                {t(group.label)}
              </div>
              <Tabs
                items={groupVisible.map(tab => ({ ...tab, label: t(tab.label) }))}
                active={activeTab}
                onChange={setActiveTab}
                variant="pill"
                ariaLabel={t(group.label)}
                style={{ marginBottom: 0 }}
              />
            </div>
          )
        })}
      </div>

      {activeTab === 'general'       && <GeneralSection />}
      {activeTab === 'session'       && <SessionSecuritySection />}
      {activeTab === 'users'         && <UsersSection />}
      {activeTab === 'roles'         && <RolesSection />}
      {activeTab === 'setup'         && <PuestaEnMarchaSection />}
      {activeTab === 'alert-config'  && <AlertConfigSection />}
      {activeTab === 'metrics'       && <MetricsSection />}
      {activeTab === 'branding'      && <MarcaSection />}
      {activeTab === 'task-types'    && <TaskTypesSection />}
      {activeTab === 'rates'         && <RateTablesSection />}
      {activeTab === 'vacations'     && <VacationSection />}
      {activeTab === 'depts'         && <DepartmentsSection />}
      {activeTab === 'offices'       && <OfficesSection />}
      {activeTab === 'numbering'     && <NumberingSection />}
      {activeTab === 'fields'        && <CustomFieldsSection />}
      {activeTab === 'idiomas'       && <IdiomasSection />}
      {activeTab === 'email-inbound' && <EmailInboundSection />}
      {activeTab === 'log-level'     && <LogLevelSection />}
      {activeTab === 'system-state'  && <SystemStateSection />}
      {activeTab === 'esign'         && <ESignSettingsSection />}
      {activeTab === 'runtime-flags' && <RuntimeFlagsSection />}
      {activeTab === 'integrations'  && <IntegrationCredentialsSection />}
    </Page>
  )
}
