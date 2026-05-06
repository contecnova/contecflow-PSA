import { useState } from 'react'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Tabs } from '../components/ui'
import { Settings } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
import {
  GeneralSection,
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
} from './SettingsPageSections'

const TAB_GROUPS = [
  {
    label: 'Personal',
    tabs: [
      { id: 'general',      label: 'General',        roles: ['admin'] },
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
      { id: 'roles',        label: 'Roles',          roles: ['admin'] },
      { id: 'email-inbound',label: 'Email-to-ticket', roles: ['admin'] },
      { id: 'esign',        label: 'E-firma',         roles: ['admin'] },
      { id: 'log-level',    label: 'Nivel de log',   roles: ['admin'] },
      { id: 'system-state', label: 'Estado sistema', roles: ['admin'] },
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
    <PageShell>
      <PageHeader title={t('settings.title')} subtitle={t('settings.subtitle')} icon={<Settings size={18} />} />

      <div style={{ marginBottom: 20, borderBottom: '1px solid var(--surface-4)', paddingBottom: 14 }}>
        {TAB_GROUPS.map((group, gi) => {
          const groupVisible = group.tabs.filter(tab => tab.roles.includes(user?.role))
          if (groupVisible.length === 0) return null
          return (
            <div key={group.label} style={{ marginBottom: gi < TAB_GROUPS.length - 1 ? 10 : 0 }}>
              <div style={{
                fontSize: "var(--text-3xs-h)", fontWeight: 700, color: 'var(--text-4)',
                textTransform: 'uppercase', letterSpacing: '0.09em',
                marginBottom: 5, paddingLeft: 2,
              }}>
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
    </PageShell>
  )
}
