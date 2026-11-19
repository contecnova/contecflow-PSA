/**
 * Configuración: una sola entrada para toda la configuración del operador
 * (reorganización del 18-11-2026; antes 23 pestañas aquí, 20 pantallas sueltas
 * en el menú y pestañas «Configuración» dentro de los módulos).
 *
 * - `/settings/:seccion` pinta la sección; la lista sale del catálogo
 *   (`pages/settings/catalogoDeAjustes.tsx`), agrupada en la navegación lateral
 *   con un buscador (título, descripción y subapartados de cada sección).
 * - Solo se listan las secciones que la persona puede usar (rol, superadmin y
 *   bloqueo por ruta); pedir una que no puede usar lleva a /403.
 * - `/settings` abre la primera sección visible; `/settings?tab=<id>` (enlaces
 *   y marcadores de antes) redirige a `/settings/<id>` (con los ids retirados
 *   traducidos por IDS_ANTIGUOS).
 * - `?sub=<id>` abre una subpestaña de la sección (Ausencias, Service desk,
 *   Campos personalizados).
 * - Las pantallas de módulo se montan dentro con `IncrustadaEnAjustes`:
 *   PageShell/PageHeader se pintan como sección (mismo aspecto en todas).
 */
import { Suspense, useMemo, useState } from 'react'
import { Navigate, NavLink, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ExternalLink, Settings } from 'lucide-react'
import { Button, Page, Select, Spinner } from '../components/ui'
import { SearchInput } from '../components/ui/TableControls'
import { useAppLang } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
import { IncrustadaEnAjustes } from '../components/layout/incrustacion'
import SeccionDeAjustes from './settings-sections/SeccionDeAjustes'
import {
  GRUPOS_DE_AJUSTES, IDS_ANTIGUOS, SECCIONES_DE_AJUSTES, claveDeSeccion, puedeVerSeccion,
  type SeccionDeAjustes as Seccion,
} from './settings/catalogoDeAjustes'
import './SettingsPage.css'

/** Texto comparable: minúsculas y sin acentos. */
const normalizar = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

export default function SettingsPage() {
  const { t } = useAppLang()
  const { seccion } = useParams()
  const { search } = useLocation()
  const navigate = useNavigate()
  const { puede, canOpen } = useAuth()
  const [consulta, setConsulta] = useState('')

  const visibles = useMemo(() => SECCIONES_DE_AJUSTES.filter(s => puedeVerSeccion(s, {
    puede, canOpen: canOpen ?? (() => true),
  })), [puede, canOpen])

  const titulo = (s: Seccion) => t(claveDeSeccion(s.id))
  const descripcion = (s: Seccion) => t(`${claveDeSeccion(s.id)}_d`)
  const nombreDeGrupo = (g: string) => t(`ajustes.g_${g}`)

  const encontradas = useMemo(() => {
    const q = normalizar(consulta.trim())
    if (!q) return visibles
    return visibles.filter(s => normalizar(`${titulo(s)} ${descripcion(s)} ${nombreDeGrupo(s.grupo)}`).includes(q))
  }, [consulta, visibles]) // eslint-disable-line react-hooks/exhaustive-deps

  const params = new URLSearchParams(search)
  const destinoDe = (id: string) => `/settings/${IDS_ANTIGUOS[id] ?? id}`

  // `/settings` (con o sin el `?tab=` de antes).
  if (!seccion) {
    const tab = params.get('tab')
    if (tab) return <Navigate to={destinoDe(tab)} replace />
    if (visibles.length === 0) return <Navigate to="/403" state={{ from: '/settings' }} replace />
    return <Navigate to={`/settings/${visibles[0].id}`} replace />
  }
  if (IDS_ANTIGUOS[seccion]) return <Navigate to={destinoDe(seccion)} replace />

  const actual = visibles.find(s => s.id === seccion)
  if (!actual) {
    const existe = SECCIONES_DE_AJUSTES.some(s => s.id === seccion)
    if (existe || visibles.length === 0) return <Navigate to="/403" state={{ from: `/settings/${seccion}` }} replace />
    return <Navigate to={`/settings/${visibles[0].id}`} replace />
  }

  const sub = params.get('sub') ?? undefined
  const grupoActual = GRUPOS_DE_AJUSTES.find(g => g.id === actual.grupo)
  const Componente = actual.componente

  let panel
  if (actual.enlace) {
    panel = (
      <SeccionDeAjustes icon={grupoActual?.icono} title={titulo(actual)} description={descripcion(actual)}>
        <Button icon={<ExternalLink size={14} />} onClick={() => navigate(actual.enlace as string)}>{t('ajustes.abrir')}</Button>
      </SeccionDeAjustes>
    )
  } else if (Componente && actual.envolver) {
    panel = (
      <SeccionDeAjustes icon={grupoActual?.icono} title={titulo(actual)} description={descripcion(actual)}>
        <Componente subInicial={sub} />
      </SeccionDeAjustes>
    )
  } else if (Componente) {
    panel = <Componente subInicial={sub} />
  }

  return (
    <Page icon={<Settings size={18} />} title={t('settings.title')} subtitle={t('ajustes.subtitulo')}>
      <div className="ajustes">
        <aside className="ajustes-nav" aria-label={t('ajustes.navegacion')}>
          <SearchInput value={consulta} onChange={setConsulta} placeholder={t('ajustes.buscar')} />
          {/* Pantalla estrecha: un desplegable en lugar de la lista. */}
          <Select suelto className="ajustes-nav-movil" aria-label={t('ajustes.navegacion')} placeholder={false}
            value={actual.id} onChange={e => navigate(`/settings/${e.target.value}`)}>
            {GRUPOS_DE_AJUSTES.map(g => {
              const delGrupo = encontradas.filter(s => s.grupo === g.id)
              return delGrupo.length === 0 ? null : (
                <optgroup key={g.id} label={nombreDeGrupo(g.id)}>
                  {delGrupo.map(s => <option key={s.id} value={s.id}>{titulo(s)}</option>)}
                </optgroup>
              )
            })}
          </Select>
          <nav className="ajustes-nav-lista" aria-label={t('ajustes.navegacion')}>
            {GRUPOS_DE_AJUSTES.map(g => {
              const delGrupo = encontradas.filter(s => s.grupo === g.id)
              if (delGrupo.length === 0) return null
              return (
                <div key={g.id} className="ajustes-grupo">
                  <div className="ds-eyebrow ajustes-grupo-titulo">{g.icono}<span>{nombreDeGrupo(g.id)}</span></div>
                  <ul>
                    {delGrupo.map(s => (
                      <li key={s.id}>
                        <NavLink to={`/settings/${s.id}`} title={descripcion(s)}
                          className={({ isActive }) => `ajustes-enlace${isActive ? ' ajustes-enlace--activo' : ''}`}>
                          {titulo(s)}
                          {s.enlace && <ExternalLink size={12} aria-hidden className="ajustes-enlace-icono" />}
                        </NavLink>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
            {encontradas.length === 0 && <p className="ajustes-vacio">{t('ajustes.sin_resultados')}</p>}
          </nav>
        </aside>
        <section className="ajustes-panel" aria-label={titulo(actual)}>
          <div className="ajustes-miga">{nombreDeGrupo(actual.grupo)}</div>
          <IncrustadaEnAjustes.Provider value={true}>
            <Suspense fallback={<Spinner />}>
              <div key={actual.id}>{panel}</div>
            </Suspense>
          </IncrustadaEnAjustes.Provider>
        </section>
      </div>
    </Page>
  )
}
