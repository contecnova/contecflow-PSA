/**
 * GrcPage — Governance, Risk & Compliance (backbone de seguridad)
 *
 * Pestañas:
 *  1. Matriz de permisos — editable por admin, persiste en DB vía API
 *  2. Segregación SoD    — reglas CRUD (POST/PATCH/DELETE)
 *  3. Violaciones SoD    — instancias detectadas, resolución
 *  4. Flujos de mitigación — workflows de aprobación
 *  5. Audit Log          — historial inmutable de eventos GRC
 *  6. Explicar acceso, informe medido, evidencias por marco (SOC 2 / ISO 27001) y retención
 */
import { useAppLang } from '../i18n/AppLangContext'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { advancedConfigApi } from '../services/settingsApi'
import { FileCheck2, FileText, GitPullRequestArrow, Grid3x3, ScrollText, ShieldAlert, ShieldCheck, Timer, UserCheck } from 'lucide-react'
import { Page, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import './GrcPage.css'
import { type Role, rolesDeReserva } from './GrcComun'
import { MatrixTab } from './GrcMatriz'
import { SodTab, ViolationsTab } from './GrcSod'
import { ApprovalsTab, AuditLogTab } from './GrcAuditoriaYAprobaciones'
import { EvidenciasTab, ExplicarAccesoTab, InformeDeCumplimientoTab, RetencionTab } from './GrcCumplimiento'

export default function GrcPage(): JSX.Element {
  const { t } = useAppLang()
  const _t = useAppT()
  const [tab, setTab] = useState('matrix')

  const { data: rawRoles = [] } = useQuery<{ name: string; description?: string; color: string }[]>({
    queryKey: ['custom-roles'],
    queryFn: () => advancedConfigApi.getRoles().then(r => r.data),
  })
  const roles: Role[] = rawRoles.length > 0
    ? rawRoles.map((r: { name: string; description?: string; color: string }) => ({ id: r.name, label: r.description || r.name, color: r.color }))
    : rolesDeReserva(t)

  const TABS = [
    { id: 'matrix',     label: t('pagina_grc.matriz_de_permisos'), icon: <Grid3x3 size={14} /> },
    { id: 'sod',        label: t('pagina_grc.segregacion_sod'), icon: <ShieldCheck size={14} /> },
    { id: 'violations', label: t('pagina_grc.violaciones'), icon: <ShieldAlert size={14} /> },
    { id: 'approvals',  label: t('pagina_grc.flujos_de_mitigacion'), icon: <GitPullRequestArrow size={14} /> },
    { id: 'auditlog',   label: t('pagina_grc.audit_log'), icon: <ScrollText size={14} /> },
    { id: 'access',     label: _t('grc.acceso_pestana'), icon: <UserCheck size={14} /> },
    { id: 'compliance', label: _t('grc.informe_pestana'), icon: <FileCheck2 size={14} /> },
    { id: 'evidence',   label: _t('grc.evidencias_pestana'), icon: <FileText size={14} /> },
    { id: 'retention',  label: _t('grc.retencion_pestana'), icon: <Timer size={14} /> },
  ]

  return (
    <Page
      icon={<ShieldCheck size={18} />}
      title={_t('nav.grc')}
      subtitle={_t('grc.subtitle')}
    >
      <Tabs items={TABS} active={tab} onChange={setTab} ariaLabel={_t('nav.grc')} />

      <div className="grc-card-15">
        {tab === 'matrix'     && <MatrixTab roles={roles} />}
        {tab === 'sod'        && <SodTab roles={roles} />}
        {tab === 'violations' && <ViolationsTab roles={roles} />}
        {tab === 'approvals'  && <ApprovalsTab />}
        {tab === 'auditlog'   && <AuditLogTab />}
        {tab === 'access'     && <ExplicarAccesoTab />}
        {tab === 'compliance' && <InformeDeCumplimientoTab />}
        {tab === 'evidence'   && <EvidenciasTab />}
        {tab === 'retention'  && <RetencionTab />}
      </div>
    </Page>
  )
}
