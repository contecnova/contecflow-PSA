/**
 * BandejaDesplegable — la campana con contador y su panel de últimos avisos.
 *
 * 16-11-2026 (campana de notificaciones). Un aviso sin leer no se veía si no
 * se entraba en la bandeja. Esta pieza es sólo la vista: los datos y los
 * textos llegan por props, así que la usan igual la barra superior de
 * operadores (`CampanaDeAvisos`) y la cabecera del portal de clientes
 * (`CampanaDelPortal`, con su traductor de 8 idiomas).
 *
 * Teclado: el botón abre y cierra; al abrir, el foco va al panel; Escape lo
 * cierra y devuelve el foco a la campana; salir con Tab o pulsar fuera lo
 * cierra. En móvil el panel ocupa el ancho de la pantalla bajo la cabecera.
 */
import { useEffect, useId, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Bell, CheckCheck } from 'lucide-react'
import { BotonConContador, textoDeContador } from '../ui/BotonConContador'
import { Button, EmptyState, Pulsable, Spinner } from '../ui'
import { fmtRelative } from '../../utils/helpers'
import { COLOR_DE_TONO, estiloDeAviso, sinEmojis } from './iconosDeAviso'
import './BandejaDesplegable.css'

export interface AvisoDeLaBandeja {
  id: string
  titulo: string
  extracto?: string | null
  /** Instante ISO (con zona) en que llegó. */
  fecha?: string | null
  leido: boolean
  /** Tipo del aviso: elige el icono (`iconosDeAviso`). */
  tipo?: string | null
  /** Es una alerta del sistema (`/alerts`): su icono sale de la tabla de alertas. */
  esAlerta?: boolean
  /** Etiqueta del tipo, ya traducida (opcional). */
  etiqueta?: string | null
}

export interface TextosDeLaBandeja {
  /** Nombre de la campana y título del panel («Notificaciones»). */
  titulo: string
  /** Nombre accesible con el número («3 notificaciones sin leer»). */
  sinLeer: (n: number) => string
  marcarTodas: string
  verTodas: string
  vacio: string
  /** Texto (sólo lector de pantalla) de la marca de no leída. */
  noLeido: string
  cargando: string
}

interface Props {
  contador: number
  avisos: AvisoDeLaBandeja[]
  cargando?: boolean
  textos: TextosDeLaBandeja
  /** Se abre el panel: buen momento para pedir la lista. */
  onAbrir?: () => void
  onElegir: (aviso: AvisoDeLaBandeja) => void
  onMarcarTodas: () => void
  onVerTodas: () => void
  marcandoTodas?: boolean
  /** Clase extra para el botón (cada cabecera tiene su tamaño). */
  claseBoton?: string
}

/** «99+» a partir de 100 (24-11-2026: el del kit, `textoDeContador`). */
export const textoDelContador = textoDeContador

/** La lista de avisos (la usa el panel y, en el portal, la página completa). */
export function ListaDeAvisos({ avisos, noLeido, onElegir }: {
  avisos: AvisoDeLaBandeja[]
  noLeido: string
  onElegir: (aviso: AvisoDeLaBandeja) => void
}) {
  return (
    <ul className="bandeja-desplegable__lista">
      {avisos.map(a => {
        const { Icono, tono } = estiloDeAviso(a.tipo, !!a.esAlerta)
        return (
          <li key={a.id}>
            <Pulsable
              className={`bandeja-desplegable__aviso${a.leido ? '' : ' bandeja-desplegable__aviso--nuevo'}`}
              onClick={() => onElegir(a)}
            >
              <span className="bandeja-desplegable__icono" style={{ '--bandeja-tono': COLOR_DE_TONO[tono] } as CSSProperties} aria-hidden>
                <Icono size={14} />
              </span>
              <span className="bandeja-desplegable__texto">
                <span className="bandeja-desplegable__titulo">{sinEmojis(a.titulo)}</span>
                {a.extracto && <span className="bandeja-desplegable__extracto">{sinEmojis(a.extracto)}</span>}
                <span className="bandeja-desplegable__meta">
                  {a.etiqueta && <span>{a.etiqueta}</span>}
                  {a.fecha && <time dateTime={a.fecha}>{fmtRelative(a.fecha)}</time>}
                </span>
              </span>
              {!a.leido && (
                <span className="bandeja-desplegable__punto" data-testid="aviso-no-leido">
                  <span className="u-sr-only">{noLeido}</span>
                </span>
              )}
            </Pulsable>
          </li>
        )
      })}
    </ul>
  )
}

export default function BandejaDesplegable({
  contador, avisos, cargando = false, textos, onAbrir, onElegir, onMarcarTodas, onVerTodas,
  marcandoTodas = false, claseBoton,
}: Props) {
  const [abierta, setAbierta] = useState(false)
  // Borde inferior de la campana: en móvil el panel va fijo justo debajo.
  const [arriba, setArriba] = useState(56)
  const raiz = useRef<HTMLDivElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const idPanel = useId()
  const idTitulo = useId()
  const nombre = contador > 0 ? textos.sinLeer(contador) : textos.titulo

  const alternar = () => {
    if (abierta) { setAbierta(false); return }
    const r = raiz.current?.getBoundingClientRect()
    if (r) setArriba(Math.round(r.bottom + 8))
    setAbierta(true)
    onAbrir?.()
  }

  // Al abrir, el foco entra en el panel.
  useEffect(() => {
    if (abierta) panel.current?.focus()
  }, [abierta])

  // Pulsar fuera cierra.
  useEffect(() => {
    if (!abierta) return undefined
    const fuera = (e: MouseEvent | TouchEvent) => {
      if (raiz.current && !raiz.current.contains(e.target as Node)) setAbierta(false)
    }
    document.addEventListener('mousedown', fuera)
    document.addEventListener('touchstart', fuera)
    return () => {
      document.removeEventListener('mousedown', fuera)
      document.removeEventListener('touchstart', fuera)
    }
  }, [abierta])

  // Escape cierra y devuelve el foco a la campana; salir con Tab, cierra.
  // (Escuchadores en la raíz, no props: la raíz no es un control.)
  useEffect(() => {
    const el = raiz.current
    if (!abierta || !el) return undefined
    const tecla = (e: globalThis.KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      setAbierta(false)
      // Se busca el botón dentro de la raíz.
      el.querySelector<HTMLButtonElement>('[data-boton-campana]')?.focus()
    }
    const salir = (e: globalThis.FocusEvent) => {
      const destino = e.relatedTarget as Node | null
      if (destino && !el.contains(destino)) setAbierta(false)
    }
    el.addEventListener('keydown', tecla)
    el.addEventListener('focusout', salir)
    return () => {
      el.removeEventListener('keydown', tecla)
      el.removeEventListener('focusout', salir)
    }
  }, [abierta])

  const elegir = (a: AvisoDeLaBandeja) => {
    setAbierta(false)
    onElegir(a)
  }

  const verTodas = () => {
    setAbierta(false)
    onVerTodas()
  }

  let cuerpo: ReactNode
  if (cargando && avisos.length === 0) {
    cuerpo = <div className="bandeja-desplegable__estado"><Spinner size={18} label={textos.cargando} /></div>
  } else if (avisos.length === 0) {
    cuerpo = <EmptyState icon={<Bell size={28} strokeWidth={1.5} aria-hidden />} title={textos.vacio} />
  } else {
    cuerpo = <ListaDeAvisos avisos={avisos} noLeido={textos.noLeido} onElegir={elegir} />
  }

  return (
    <div className="bandeja-desplegable" ref={raiz}>
      {/* 24-11-2026: el contador estándar del kit (color de aviso y número al lado, como la bandeja). */}
      <BotonConContador
        icono={<Bell aria-hidden />}
        contador={contador}
        tono="aviso"
        activo={abierta}
        ariaLabel={nombre}
        className={claseBoton}
        onClick={alternar}
        aria-expanded={abierta}
        aria-haspopup="dialog"
        aria-controls={abierta ? idPanel : undefined}
        data-boton-campana=""
      />

      {abierta && (
        <div
          id={idPanel}
          ref={panel}
          role="dialog"
          aria-labelledby={idTitulo}
          tabIndex={-1}
          className="bandeja-desplegable__panel"
          style={{ '--bandeja-arriba': `${arriba}px` } as CSSProperties}
        >
          <div className="bandeja-desplegable__cabecera">
            <h2 id={idTitulo} className="bandeja-desplegable__h">{textos.titulo}</h2>
            {contador > 0 && (
              <Button variant="ghost" size="sm" icon={<CheckCheck size={14} aria-hidden />}
                onClick={onMarcarTodas} loading={marcandoTodas}>
                {textos.marcarTodas}
              </Button>
            )}
          </div>
          <div className="bandeja-desplegable__cuerpo">{cuerpo}</div>
          <div className="bandeja-desplegable__pie">
            <Button variant="secondary" size="sm" onClick={verTodas}>{textos.verTodas}</Button>
          </div>
        </div>
      )}
    </div>
  )
}
