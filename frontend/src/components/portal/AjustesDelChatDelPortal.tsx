/**
 * Configuración › Portal › Chat del portal (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md).
 *
 * Ajustes por empresa del grupo en caliente `portal_chat` (el editor genérico
 * de ajustes, `RuntimeGroupEditor`): llamadas y videollamadas del portal (solo
 * las inicia el equipo; el cliente acepta o rechaza), adjuntos, extensiones
 * permitidas (solo acotan el catálogo aprobado), tamaño máximo, plazo para
 * editar/borrar y segundos de tono. Solo `org.administrar`; cada cambio queda
 * en la auditoría de ajustes.
 */
import { RuntimeGroupEditor } from '../../pages/settings-sections/SettingsAdvancedSections'
import { useAppLang } from '../../i18n/AppLangContext'

export default function AjustesDelChatDelPortal() {
  const { t } = useAppLang()
  return <RuntimeGroupEditor groupId="portal_chat" description={t('ajustes.portal_chat_descripcion')} />
}
