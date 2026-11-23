/**
 * 16-11-2026 (pasada de diseño): subpestañas con <Tabs>; botones del kit con
 * iconos lucide (sin «+» ni emojis en el texto); vacíos con icono lucide;
 * formularios con `ds-input`; insignias con StatusBadge/PBadge; los avisos y
 * etiquetas que reutilizaban textos de otra cosa (un aviso que decía «Nueva
 * categoría», «Nombre de la regla» como categoría) pasan a claves `sd_cfg.cfg_*`.
 *
 * 18-11-2026: esta pantalla es la sección «Service desk» de Configuración
 * (`/settings/sd?sub=…`); ya no es una pestaña del módulo. La revisión de
 * traducciones del portal pasa a Configuración → Portal de clientes. Las
 * subpestañas se filtran por rol como el backend: todo es require_admin salvo
 * las respuestas rápidas (require_any_manager: admin, pm, team_lead, hr).
 */
import { useState } from 'react'
import { useAppT } from '../../i18n/AppLangContext'
import { Tabs } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { EscalationConfig, NotificationsConfig } from './ConfigEscaladoYAvisos'
import { CiclosDeVida, ReglasSlaYOla } from './ConfigSlaYCiclos'
import ConfigCanales from './ConfigCanales'
import ConfigCorreoEntrante from './ConfigCorreoEntrante'
import { GuardiasConfig, MonitorizacionConfig } from './ConfigGuardiasYMonitor'
import ConfigPaginaDeEstado from './ConfigPaginaDeEstado'
import { RoutingRules } from './QueueAndRoutingSections'
import './ConfigTab.css'
import { CatalogConfig } from './ConfigCatalogo'
import { SLAConfig } from './ConfigSla'
import { GroupsConfig, TemplatesConfig } from './ConfigGruposYPlantillas'
import { AnnouncementsConfig, CannedResponsesManager } from './ConfigRespuestasYAnuncios'
export { AnnouncementsConfig } from './ConfigRespuestasYAnuncios'

// ── Config wrapper (tab nav) ──────────────────────────────────────────────────
/** Subpestañas que no son de administración: el backend deja escribir
 *  respuestas rápidas a cualquier responsable (require_any_manager). */
const SUB_DE_RESPONSABLES = new Set(['canned'])

export default function Config({ subInicial }: { subInicial?: string }) {
  const t = useAppT()
  const esAdmin = useAuth().puede('sd.administrar')
  const todas = [
    {id:'catalog',  label:t('sd_cfg.cfg_tab_catalog')},
    {id:'sla',      label:t('sd_cfg.cfg_tab_sla')},
    {id:'sla_rules', label:t('sd_mercado.tab_sla_reglas')},
    {id:'lifecycles', label:t('sd_mercado.tab_ciclos')},
    {id:'channels', label:t('sd_mercado.tab_canales')},
    {id:'groups',   label:t('sd_cfg.cfg_tab_groups')},
    {id:'routing',  label:t('sd_cfg.cfg_tab_routing')},
    {id:'escalation', label:t('sd_cfg.tab_escalation')},
    {id:'notifications', label:t('sd_cfg.tab_notifications')},
    {id:'mail', label:t('sd_cfg.tab_mail')},
    {id:'monitoring', label:t('sd_cfg.tab_monitoring')},
    {id:'oncall', label:t('sd_cfg.tab_oncall')},
    {id:'status_page', label:t('sd_cfg.tab_status_page')},
    {id:'templates',label:t('sd_cfg.cfg_tab_templates')},
    {id:'canned',   label:t('sd_cfg.cfg_tab_canned')},
    {id:'announcements', label:t('service_desk.tab_announcements')},
  ]
  const tabs = esAdmin ? todas : todas.filter(x => SUB_DE_RESPONSABLES.has(x.id))
  const [sub, setSub] = useState(() => (subInicial && tabs.some(x => x.id === subInicial) ? subInicial : tabs[0]?.id ?? 'canned'))
  const visible = tabs.some(x => x.id === sub) ? sub : tabs[0]?.id
  return (
    <div>
      <Tabs items={tabs} active={visible ?? ''} onChange={setSub} ariaLabel={t('sd_cfg.cfg_nav')} />
      {visible === 'catalog'       && <CatalogConfig />}
      {visible === 'sla'           && <SLAConfig />}
      {visible === 'sla_rules'     && <ReglasSlaYOla />}
      {visible === 'lifecycles'    && <CiclosDeVida />}
      {visible === 'channels'      && <ConfigCanales />}
      {visible === 'groups'        && <GroupsConfig />}
      {visible === 'routing'       && <RoutingRules />}
      {visible === 'escalation'    && <EscalationConfig />}
      {visible === 'notifications' && <NotificationsConfig />}
      {visible === 'mail'          && <ConfigCorreoEntrante />}
      {visible === 'monitoring'    && <MonitorizacionConfig />}
      {visible === 'oncall'        && <GuardiasConfig />}
      {visible === 'status_page'   && <ConfigPaginaDeEstado />}
      {visible === 'templates'     && <TemplatesConfig />}
      {visible === 'canned'        && <CannedResponsesManager />}
      {visible === 'announcements' && <AnnouncementsConfig />}
    </div>
  )
}
