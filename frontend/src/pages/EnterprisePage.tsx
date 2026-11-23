/**
 * EnterprisePage v14 — Webhooks, GDPR, Email, Integraciones, SSO, Audit, API Keys
 */
import { useAppLang } from '../i18n/AppLangContext'
import { useState } from 'react'
import { Button, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'

import { useAppT } from '../i18n/AppLangContext'
import { Building2, Key, KeyRound, Mail, Plug, Plus, ScrollText, Send, ShieldCheck, Webhook } from 'lucide-react'
import './EnterprisePage.css'
import { EmailTab, GDPRTab, WebhooksTab } from './EnterpriseWebhooksGdprEmail'
import { IntegrationsTab } from './EnterpriseIntegraciones'
import { APIKeysTab, AuditTab } from './EnterpriseAuditoriaYClaves'
import { SSOTab } from './EnterpriseSso'

// ── Componente principal ───────────────────────────────────────────────────────
export default function EnterprisePage(): JSX.Element {
  const { t } = useAppLang()
  const _t = useAppT()
  // `?tab=<id>` abre esa pestaña (la lista de puesta en marcha enlaza a SSO).
  const [tab, setTabState] = useState(() => new URLSearchParams(window.location.search).get('tab') || 'webhooks')
  // El alta de cada pestaña se abre desde la cabecera: `alta` dice cuál está abierta.
  const [alta, setAlta] = useState<string | null>(null)
  const setTab = (id: string) => { setTabState(id); setAlta(null) }
  const fijarAlta = (id: string) => (v: boolean) => setAlta(v ? id : null)

  const TABS = [
    { id: 'webhooks',     label: t('pagina_ent.webhooks'), icon: <Webhook size={14} /> },
    { id: 'gdpr',         label: t('pagina_ent.rgpd'), icon: <ShieldCheck size={14} /> },
    { id: 'email',        label: t('pagina_ent.email'), icon: <Mail size={14} /> },
    { id: 'integrations', label: t('pagina_ent.integraciones'), icon: <Plug size={14} /> },
    { id: 'sso',          label: 'SSO', icon: <KeyRound size={14} /> },
    { id: 'audit',        label: t('pagina_ent.auditoria'), icon: <ScrollText size={14} /> },
    { id: 'apikeys',      label: t('pagina_ent.api_keys'), icon: <Key size={14} /> },
  ]

  const accion = (id: string, texto: string) => (
    <Button icon={<Plus size={14} />} onClick={() => setAlta(id)}>{texto}</Button>
  )
  const acciones = tab === 'webhooks' ? accion('webhooks', _t('enterprise.nuevo_webhook'))
    : tab === 'gdpr' ? accion('gdpr', _t('enterprise.nueva_solicitud'))
    : tab === 'email' ? (
      <>
        <Button variant="secondary" icon={<Plus size={14} />} onClick={() => setAlta('email-plantilla')}>{t('pagina_ent.plantilla')}</Button>
        <Button icon={<Send size={14} />} onClick={() => setAlta('email-envio')}>{t('pagina_ent.enviar_email')}</Button>
      </>
    )
    : tab === 'sso' ? accion('sso', t('pagina_ent.anadir_proveedor'))
    : tab === 'apikeys' ? accion('apikeys', _t('enterprise.nueva_api_key'))
    : undefined

  return (
    <PageShell>
      <PageHeader
        icon={<Building2 size={18} />}
        title={_t('nav.enterprise')}
        subtitle={_t('enterprise.subtitle')}
        actions={acciones}
        showListExport={false}
      />

      <Tabs items={TABS} active={tab} onChange={setTab} className="ent-tabs" />

      {/* Contenido */}
      {tab === 'webhooks'     && <WebhooksTab showCreate={alta === 'webhooks'} setShowCreate={fijarAlta('webhooks')} />}
      {tab === 'gdpr'         && <GDPRTab showCreate={alta === 'gdpr'} setShowCreate={fijarAlta('gdpr')} />}
      {tab === 'email'        && <EmailTab showCreate={alta === 'email-plantilla'} setShowCreate={fijarAlta('email-plantilla')}
                                   showSend={alta === 'email-envio'} setShowSend={fijarAlta('email-envio')} />}
      {tab === 'integrations' && <IntegrationsTab />}
      {tab === 'sso'          && <SSOTab showCreate={alta === 'sso'} setShowCreate={fijarAlta('sso')} />}
      {tab === 'audit'        && <AuditTab />}
      {tab === 'apikeys'      && <APIKeysTab showCreate={alta === 'apikeys'} setShowCreate={fijarAlta('apikeys')} />}
    </PageShell>
  )
}
