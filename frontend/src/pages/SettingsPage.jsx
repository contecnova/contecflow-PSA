import React, { useState } from 'react'
import PageHeader from '../components/layout/PageHeader'
import { Settings } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
import {
  GeneralSection,
  UsersSection,
  RolesSection,
  AlertConfigSection,
  TaskTypesSection,
  TemplatesSection,
  RateTablesSection,
  VacationSection,
  DepartmentsSection,
  OfficesSection,
  NumberingSection,
  CustomFieldsSection,
  IdiomasSection,
  EmailInboundSection,
  LogLevelSection,
} from './SettingsPageSections'

const TABS = [
  { id: 'general',      label: 'General',           roles: ['admin'] },
  { id: 'users',        label: 'Usuarios',          roles: ['admin', 'hr'] },
  { id: 'roles',        label: 'Roles',             roles: ['admin'] },
  { id: 'alert-config', label: 'Alertas',           roles: ['admin'] },
  { id: 'task-types',   label: 'Tipos tarea',       roles: ['admin', 'pm'] },
  { id: 'templates',    label: 'Plantillas',        roles: ['admin', 'pm'] },
  { id: 'rates',        label: 'Tarifas',           roles: ['admin'] },
  { id: 'vacations',    label: 'Vacaciones',        roles: ['admin', 'hr'] },
  { id: 'depts',        label: 'Departamentos',     roles: ['admin', 'hr'] },
  { id: 'offices',      label: 'Sedes',             roles: ['admin'] },
  { id: 'numbering',    label: 'Numeración',        roles: ['admin'] },
  { id: 'fields',       label: 'Campos extra',      roles: ['admin'] },
  { id: 'idiomas',      label: 'Idiomas',           roles: ['admin'] },
  { id: 'email-inbound',label: 'Email-to-ticket',   roles: ['admin'] },
  { id: 'log-level',    label: 'Nivel de log',      roles: ['admin'] },
]

export default function SettingsPage() {
  const { user } = useAuth()
  const { t } = useAppLang()
  const visibleTabs = TABS.filter(tab => tab.roles.includes(user?.role))
  const [activeTab, setActiveTab] = useState(visibleTabs[0]?.id || 'general')

  return (
    <div style={{ padding: 32 }}>
      <PageHeader title={t('settings.title')} subtitle={t('settings.subtitle')} icon={<Settings size={18} />} />

      <div style={{ display: 'flex', gap: 6, marginBottom: 20, flexWrap: 'wrap', borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {visibleTabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '7px 14px',
              borderRadius: 8,
              border: `1px solid ${activeTab === tab.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
              background: activeTab === tab.id ? 'var(--accent-muted)' : 'transparent',
              color: activeTab === tab.id ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              fontFamily: 'inherit',
              whiteSpace: 'nowrap',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'general'       && <GeneralSection />}
      {activeTab === 'users'         && <UsersSection />}
      {activeTab === 'roles'         && <RolesSection />}
      {activeTab === 'alert-config'  && <AlertConfigSection />}
      {activeTab === 'task-types'    && <TaskTypesSection />}
      {activeTab === 'templates'     && <TemplatesSection />}
      {activeTab === 'rates'         && <RateTablesSection />}
      {activeTab === 'vacations'     && <VacationSection />}
      {activeTab === 'depts'         && <DepartmentsSection />}
      {activeTab === 'offices'       && <OfficesSection />}
      {activeTab === 'numbering'     && <NumberingSection />}
      {activeTab === 'fields'        && <CustomFieldsSection />}
      {activeTab === 'idiomas'       && <IdiomasSection />}
      {activeTab === 'email-inbound' && <EmailInboundSection />}
      {activeTab === 'log-level'     && <LogLevelSection />}
    </div>
  )
}
