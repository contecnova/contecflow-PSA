/**
 * Configuración › «Menú por defecto» (23-11-2026, feedback «menú personalizable»).
 *
 * El administrador (`org.administrar`) fija, para cada rol de su empresa, el
 * orden de las categorías del menú lateral, el de sus pestañas y las pestañas
 * ocultas con que empieza cada persona. Cada uno puede cambiar el suyo; su
 * «Restablecer» vuelve a este. Se guarda por empresa (`app_settings`,
 * `menu.por_defecto`; sin migración) y queda en `audit_log`
 * (`PUT /settings/menu-default`).
 *
 * Se edita el menú entero: cada persona verá solo lo que su rol permite
 * (ocultar no da ni quita permisos).
 */
import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RotateCcw, Save } from 'lucide-react'
import { Button, Select } from '../../components/ui'
import EditorDeMenu from '../../components/layout/EditorDeMenu'
import { NAV_GROUPS } from '../../components/layout/menuLateral'
import { useAppLang } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { menuPorDefectoApi } from '../../services/api'
import { extractErr } from '../../utils/helpers'
import { normalizarPreferencia, VERSION_DEL_MENU, type PreferenciaDeMenu } from '../../permisos/menuPersonal'
import './MenuPorDefectoSection.css'

/** Roles base (`users.role`, `app/core/capacidades.py::ROLES`). */
const ROLES = ['admin', 'pm', 'team_lead', 'hr', 'employee', 'subcontractor'] as const

type PorRol = Record<string, PreferenciaDeMenu | null>

export default function MenuPorDefectoSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [rol, setRol] = useState<string>('employee')
  const [borrador, setBorrador] = useState<PorRol | null>(null)
  const [guardando, setGuardando] = useState(false)

  const { data, isLoading } = useQuery<PorRol>({
    queryKey: ['menu-default'],
    queryFn: () => menuPorDefectoApi.porRol().then(r => {
      const roles = (r.data?.roles ?? {}) as Record<string, unknown>
      return Object.fromEntries(Object.entries(roles).map(([k, v]) => [k, normalizarPreferencia(v)]))
    }),
  })
  // Sin cambios, `borrador` es null y se ve lo guardado.
  const actual = useMemo<PorRol>(() => borrador ?? data ?? {}, [borrador, data])
  const cambiado = useMemo(() => JSON.stringify(actual) !== JSON.stringify(data ?? {}), [actual, data])
  const opciones = ROLES.map(r => ({ value: r, label: t(`rol_usuario.${r}`) }))

  const cambiar = (p: PreferenciaDeMenu | null) => setBorrador(b => ({ ...(b ?? data ?? {}), [rol]: p }))

  const guardar = async () => {
    setGuardando(true)
    try {
      const roles = Object.fromEntries(Object.entries(actual).filter(([, v]) => v))
      await menuPorDefectoApi.guardar({ version: VERSION_DEL_MENU, roles })
      toast.success(t('menu_personal.guardado'))
      setBorrador(null)
      qc.invalidateQueries({ queryKey: ['menu-default'] })
      qc.invalidateQueries({ queryKey: ['menu-default-mine'] })
    } catch (e) {
      toast.error(extractErr(e, t('menu_personal.error_guardar')))
    } finally {
      setGuardando(false)
    }
  }

  if (isLoading) return null
  return (
    <div className="menu-defecto">
      <p className="menu-defecto__intro">{t('menu_personal.defecto_intro')}</p>
      <div className="menu-defecto__barra">
        <Select label={t('menu_personal.rol')} value={rol} options={opciones} onChange={e => setRol(e.target.value)}
          className="menu-defecto__rol" />
        <span className="menu-defecto__estado">
          {actual[rol] ? t('menu_personal.defecto_propio') : t('menu_personal.defecto_fabrica')}
        </span>
      </div>
      <EditorDeMenu key={rol} grupos={NAV_GROUPS} valor={actual[rol] ?? null} onChange={cambiar} idBase={`menu-defecto-${rol}`} />
      <p className="menu-defecto__nota">{t('menu_personal.defecto_permisos')}</p>
      <div className="menu-defecto__acciones">
        <Button variant="ghost" icon={<RotateCcw size={14} />} disabled={!actual[rol]} onClick={() => cambiar(null)}>
          {t('menu_personal.defecto_restablecer')}
        </Button>
        <Button icon={<Save size={14} />} disabled={!cambiado} loading={guardando} onClick={() => { void guardar() }}>
          {t('menu_personal.guardar')}
        </Button>
      </div>
    </div>
  )
}
