/**
 * Configuración → Proyectos y trabajo → Campos personalizados (18-11-2026).
 *
 * Antes eran dos pantallas sin relación: `/custom-fields` (campos de las tareas
 * de cada proyecto, tabla `project_custom_fields`) y Ajustes → «Campos extra»
 * (campos globales por entidad, tabla `custom_fields`, escritura solo admin).
 * Son dos alcances distintos (no el mismo dato), así que se mantienen las dos
 * tablas y se juntan en una sección con dos pestañas. La de campos globales
 * solo la ve administración: el backend (`/advanced-config/custom-fields`)
 * exige `require_admin` para escribir.
 */
import { lazy, Suspense, useState } from 'react'
import { Spinner, Tabs } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { useAppLang } from '../../i18n/AppLangContext'
import type { PropsDeSeccion } from './catalogoDeAjustes'

const PorProyecto = lazy(() => import('../CustomFieldsPage'))
const Globales = lazy(() => import('../SettingsPageSections').then(m => ({ default: m.CustomFieldsSection })))

export default function CamposPersonalizados({ subInicial }: PropsDeSeccion) {
  const { t } = useAppLang()
  const { hasRole } = useAuth()
  const pestanas = [
    { id: 'proyecto', label: t('ajustes.campos_por_proyecto') },
    ...(hasRole('admin') ? [{ id: 'globales', label: t('ajustes.campos_globales') }] : []),
  ]
  const [activa, setActiva] = useState(pestanas.some(p => p.id === subInicial) ? String(subInicial) : 'proyecto')
  return (
    <div className="u-stack-14">
      {pestanas.length > 1 && <Tabs items={pestanas} active={activa} onChange={setActiva} ariaLabel={t('ajustes.s_custom_fields')} />}
      <Suspense fallback={<Spinner />}>
        {activa === 'globales' ? <Globales /> : <PorProyecto />}
      </Suspense>
    </div>
  )
}
