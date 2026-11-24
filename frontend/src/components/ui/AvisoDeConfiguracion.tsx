import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle, Info, Settings2 } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { SECCIONES_DE_AJUSTES, claveDeSeccion, puedeVerSeccion } from '../../pages/settings/catalogoDeAjustes'
import { Button } from './index'
import { useTextoUi } from './useTextoUi'
import './AvisoDeConfiguracion.css'

/**
 * AvisoDeConfiguracion — el ÚNICO enlace a Configuración desde fuera de Configuración (24-11-2026,
 * decidido por el usuario). Antes había 28 enlaces a `/settings/…` repartidos en 25 pantallas y solo
 * unos 5 miraban el permiso: quien no podía configurar pulsaba y acababa en un 403.
 *
 * - Dice lo que pasa («DocuSign no configurado»): `children`.
 * - Con permiso para la sección (la misma comprobación que el menú de Configuración:
 *   `puedeVerSeccion`, capacidad + bloqueo por ruta), añade el enlace «Ir a Configuración › Sección».
 * - Sin permiso, el mismo aviso con «Pídeselo a tu administrador.» y sin enlace.
 *
 *   <AvisoDeConfiguracion seccion="esign">{t('esign.sin_proveedor')}</AvisoDeConfiguracion>
 *   <AvisoDeConfiguracion seccion="policies" consulta="dominio=licencias" variante="enlace" />
 *   <AvisoDeConfiguracion seccion="git" variante="boton" texto={t('git_integration.conectar_repositorios')} />
 *
 * Variantes:
 * - `caja` (por defecto): el aviso con icono, fondo y borde del tono. Siempre se ve.
 * - `enlace`: solo el enlace, en línea (una ayuda, una barra de herramientas). Sin permiso no pinta nada.
 * - `boton`: un botón secundario con icono (acción de un estado vacío o una fila de botones). Sin permiso no pinta nada.
 */
export type VarianteAvisoDeConfiguracion = 'caja' | 'enlace' | 'boton'
export type TonoAvisoDeConfiguracion = 'aviso' | 'peligro' | 'info'

export interface AvisoDeConfiguracionProps {
  /** Id de la sección de Configuración (`/settings/<seccion>`, catálogo `catalogoDeAjustes`). */
  seccion: string
  /** Query de la sección sin `?` (`dominio=ausencias`, `sub=sd_mailbox`). */
  consulta?: string
  /** Lo que pasa (variante `caja`). */
  children?: ReactNode
  variante?: VarianteAvisoDeConfiguracion
  tono?: TonoAvisoDeConfiguracion
  /** Texto del enlace o del botón. Por defecto «Ir a Configuración › <nombre de la sección>». */
  texto?: ReactNode
  /** Icono del botón o del enlace (por defecto, en el botón, el engranaje). */
  icono?: ReactNode
  /** Se llama al pulsar el enlace (p. ej. cerrar el modal en el que está). */
  alPulsar?: () => void
  className?: string
}

/** Ruta de una sección de Configuración (`/settings/<seccion>?<consulta>`). */
export function rutaDeConfiguracion(seccion: string, consulta?: string): string {
  return `/settings/${seccion}${consulta ? `?${consulta}` : ''}`
}

/** ¿Puede quien mira abrir (y por tanto configurar) esa sección? Misma regla que el menú de Configuración. */
export function usePuedeConfigurar(seccion: string): boolean {
  const { puede, canOpen = () => true } = useAuth()
  const s = SECCIONES_DE_AJUSTES.find(x => x.id === seccion)
  if (!s) return false
  return puedeVerSeccion(s, { puede, canOpen })
}

const ICONO_DEL_TONO = { aviso: AlertTriangle, peligro: AlertTriangle, info: Info } as const

export default function AvisoDeConfiguracion({
  seccion, consulta, children, variante = 'caja', tono = 'aviso', texto, icono, alPulsar, className,
}: AvisoDeConfiguracionProps) {
  const t = useTextoUi()
  const navigate = useNavigate()
  const puede = usePuedeConfigurar(seccion)
  const ruta = rutaDeConfiguracion(seccion, consulta)
  const textoDelEnlace = texto ?? t('uikit.config_ir_a', { seccion: t(claveDeSeccion(seccion)) })

  if (variante === 'boton') {
    if (!puede) return null
    return (
      <Button variant="secondary" icon={icono ?? <Settings2 size={14} />} className={className}
        onClick={() => { alPulsar?.(); navigate(ruta) }}>
        {textoDelEnlace}
      </Button>
    )
  }

  const enlace = (
    <Link to={ruta} onClick={alPulsar} className="ui-aviso-config__enlace">
      {icono}{textoDelEnlace}
    </Link>
  )
  if (variante === 'enlace') {
    if (!puede) return null
    return className ? <span className={className}>{enlace}</span> : enlace
  }

  const Icono = ICONO_DEL_TONO[tono]
  return (
    <div className={`ui-aviso-config ui-aviso-config--${tono}${className ? ` ${className}` : ''}`} role="status">
      <Icono size={14} aria-hidden="true" />
      <div className="ui-aviso-config__texto">
        {children}{children ? ' ' : null}
        {puede ? enlace : <span className="ui-aviso-config__pedir">{t('uikit.config_pide_al_admin')}</span>}
      </div>
    </div>
  )
}
