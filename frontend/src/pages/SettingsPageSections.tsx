/**
 * SettingsPageSections — punto de reexportación de las secciones de Configuración.
 * Troceado (23-11-2026, auditoría M12) en settings-sections/Seccion*.tsx sin cambio de comportamiento;
 * los consumidores (catalogoDeAjustes, CamposPersonalizados) siguen importando de aquí.
 */
import {
  IdiomasSection,
  LogLevelSection,
  SystemStateSection,
  RuntimeFlagsSection,
  IntegrationCredentialsSection,
} from './settings-sections/SettingsAdvancedSections'
import { GeneralSection, SessionSecuritySection } from './settings-sections/SeccionGeneral'
import { RolesSection, UsersSection } from './settings-sections/SeccionUsuariosYRoles'
import { AlertConfigSection, MetricsSection } from './settings-sections/SeccionAlertasYMetricas'
import { DepartmentsSection, NumberingSection, OfficesSection, VacationSection } from './settings-sections/SeccionOrganizacion'
import { CustomFieldsSection } from './settings-sections/SeccionCamposDeEntidad'
import { ESignSettingsSection } from './settings-sections/SeccionFirmaElectronica'
import './SettingsPageSections.css'

export {
  GeneralSection,
  SessionSecuritySection,
  UsersSection,
  RolesSection,
  AlertConfigSection,
  MetricsSection,
  VacationSection,
  DepartmentsSection,
  OfficesSection,
  NumberingSection,
  CustomFieldsSection,
  IdiomasSection,
  LogLevelSection,
  SystemStateSection,
  ESignSettingsSection,
  RuntimeFlagsSection,
  IntegrationCredentialsSection,
}
