import { useState } from 'react'
import { Tabs, Page } from '../components/ui'
import { Settings } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
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
    label: 'Personal',
    tabs: [
      { id: 'general',      label: 'General',        roles: ['admin'] },
      { id: 'session',      label: 'Sesión',         roles: ['admin'] },
      { id: 'users',        label: 'Usuarios',       roles: ['admin', 'hr'] },
      { id: 'vacations',    label: 'Vacaciones',     roles: ['admin', 'hr'] },
      { id: 'depts',        label: 'Departamentos',  roles: ['admin', 'hr'] },
      { id: 'offices',      label: 'Sedes',          roles: ['admin'] },
      { id: 'idiomas',      label: 'Idiomas',        roles: ['admin'] },
    ],
  },
  {
    label: 'Workspace',
    tabs: [
      { id: 'task-types',   label: 'Tipos tarea',    roles: ['admin', 'pm'] },
      { id: 'rates',        label: 'Tarifas',        roles: ['admin'] },
      { id: 'numbering',    label: 'Numeración',     roles: ['admin'] },
      { id: 'fields',       label: 'Campos extra',   roles: ['admin'] },
      { id: 'alert-config', label: 'Alertas',        roles: ['admin'] },
      { id: 'metrics',      label: 'Métricas',       roles: ['admin'] },
    ],
  },
  {
    label: 'Sistema',
    tabs: [
      { id: 'roles',         label: 'Roles',           roles: ['admin'] },
      { id: 'runtime-flags', label: 'Config. dinámica', roles: ['admin'] },
      { id: 'integrations',  label: 'Credenciales',    roles: ['admin'] },
      { id: 'email-inbound', label: 'Email-to-ticket', roles: ['admin'] },
      { id: 'esign',         label: 'E-firma',         roles: ['admin'] },
      { id: 'log-level',     label: 'Nivel de log',    roles: ['admin'] },
      { id: 'system-state',  label: 'Estado sistema',  roles: ['admin'] },
    ],
  },
]

const TABS = TAB_GROUPS.flatMap(g => g.tabs)

export default function SettingsPage() {
  const { user } = useAuth()
  const { t } = useAppLang()
  const visibleTabs = TABS.filter(tab => tab.roles.includes(user?.role))
  const [activeTab, setActiveTab] = useState(visibleTabs[0]?.id || 'general')

  return (
    <Page
      icon={<Settings size={18} />}
      title={t('settings.title')}
      subtitle={t('settings.subtitle')}
    >
      <div style={{
        borderBottom: '1px solid var(--surface-4)',
        paddingBottom: 'var(--space-3)',
        display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
      }}>
        {TAB_GROUPS.map(group => {
          const groupVisible = group.tabs.filter(tab => tab.roles.includes(user?.role))
          if (groupVisible.length === 0) return null
          return (
            <div key={group.label}>
              <div className="ds-eyebrow" style={{ marginBottom: 5, paddingLeft: 2 }}>
                {group.label}
              </div>
              <Tabs
                items={groupVisible}
                active={activeTab}
                onChange={setActiveTab}
                variant="pill"
                ariaLabel={group.label}
                style={{ marginBottom: 0, borderBottom: 'none' }}
              />
            </div>
          )
        })}
      </div>

      {activeTab === 'general'       && <GeneralSection />}
      {activeTab === 'session'       && <SessionSecuritySection />}
      {activeTab === 'users'         && <UsersSection />}
      {activeTab === 'roles'         && <RolesSection />}
      {activeTab === 'alert-config'  && <AlertConfigSection />}
      {activeTab === 'metrics'       && <MetricsSection />}
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
