/**
 * Fila de mensaje del chat (24-11-2026, «un solo chat»: docs/GUIA_DE_DISENO.md).
 *
 * 24-11-2026 (pedido del usuario, «como WhatsApp o Teams»): BURBUJAS. Lo que
 * escribe quien mira (`propio`) va a la DERECHA, en una burbuja con el acento
 * suave del tema y sin avatar; lo de los demás va a la IZQUIERDA, en una
 * burbuja de superficie con avatar y nombre (el nombre se puede omitir en 1:1).
 * Dentro de la burbuja: la cita, el texto (traducido o no), los adjuntos y lo
 * que se le pase en `extras`; abajo a la derecha, pequeño, las insignias,
 * «editado», la hora y el estado (Enviado ✓ / Leído ✓✓). Las reacciones van en
 * pastillas debajo. Mensajes seguidos del mismo autor (`compacto`): sin
 * repetir avatar ni nombre y con menos separación. Ancho máximo ~70 %.
 *
 * La barra de acciones (reaccionar, responder, editar…) aparece al pasar el
 * ratón o al enfocar con el teclado, en horizontal y junto a la burbuja: a su
 * izquierda en las propias y a su derecha en las ajenas. Si no cabe al lado
 * sin salirse de la fila o de la ventana, sube encima de la burbuja (nunca
 * tapa el texto) y se mete hacia dentro.
 *
 * La usan TODOS los chats (interno, panel flotante, portal en los dos lados,
 * chat en vivo de Soporte, bandeja de canales y los asistentes de IA). Quien la
 * usa decide `propio` (usuario actual frente a autor; ver la guía).
 */
import { type ReactNode, useLayoutEffect, useRef, useState } from 'react'
import { Bot, Check, CheckCheck } from 'lucide-react'
import { Pulsable } from '../ui'
import { fmtDateTime, formateadorDeFecha, localeActivo } from '../../utils/helpers'
import { BotonDeChat, fmtHora } from './BotonDeChat'
import './chat.css'

/** Las reacciones rápidas de la barra (las del chat interno). */
export const REACCIONES_DE_LA_BARRA = ['👍', '❤️', '😂', '🎉'] as const

export interface AccionDeMensaje {
  clave: string
  /** Nombre accesible y título del botón. */
  etiqueta: string
  icono: ReactNode
  onClick: () => void
  peligro?: boolean
}

export interface ReaccionAgrupada {
  emoji: string
  n: number
  /** La puso quien mira. */
  mia?: boolean
}

export interface TextosDeFila {
  /** aria-label del artículo («Mensaje de {autor}»; se le añade la hora). */
  mensajeDe: string
  /** aria-label de la barra de acciones. */
  acciones?: string
  /** «editado». */
  editado?: string
  /** «Mensaje eliminado» (para la cita borrada). */
  eliminado?: string
  /** Etiqueta del bot y de «fijado». */
  bot?: string
  fijado?: string
  reaccion?: (emoji: string, n: number) => string
  reaccionarCon?: (emoji: string) => string
}

export interface FilaDeMensajeProps {
  autor: string
  /** ISO de la fecha del mensaje. */
  fecha: string | null | undefined
  textos: TextosDeFila
  /** Lo escribió quien mira: burbuja a la DERECHA, con acento y sin avatar. */
  propio?: boolean
  /** Nombre del autor en las ajenas (por defecto sí; en 1:1 se puede omitir). */
  mostrarNombre?: boolean
  /** Mismo autor seguido (menos de 5 min y el mismo día): sin avatar ni nombre. */
  compacto?: boolean
  borrado?: boolean
  esBot?: boolean
  fijado?: ReactNode
  editado?: boolean
  /** Insignias pequeñas dentro de la burbuja, junto a la hora (p. ej. «Cliente», GRC, nota interna). */
  insignias?: ReactNode
  cita?: { autor: string; texto: string; borrada?: boolean } | null
  /** El cuerpo (texto con enlaces seguros, traducido…). */
  cuerpo: ReactNode
  /** Lo que va bajo el texto dentro de la burbuja: adjuntos, tarjetas, botones de revisión… */
  extras?: ReactNode
  reacciones?: ReaccionAgrupada[]
  onReaccionar?: (emoji: string) => void
  /** Botones de icono de la barra flotante (responder, editar, borrar…). */
  acciones?: AccionDeMensaje[]
  /** Acciones que siguen en un mensaje borrado (p. ej. ver historial). Sin ellas, no hay barra. */
  accionesSiBorrado?: AccionDeMensaje[]
  /** Estado de entrega (`EstadoDeEntrega`), dentro de la burbuja tras la hora. */
  pie?: ReactNode
}

export function FilaDeMensaje({
  autor, fecha, textos, propio, mostrarNombre = true, compacto, borrado, esBot, fijado, editado, insignias, cita, cuerpo, extras,
  reacciones, onReaccionar, acciones = [], accionesSiBorrado, pie,
}: FilaDeMensajeProps) {
  const [barra, setBarra] = useState(false)
  const [arriba, setArriba] = useState(false)
  const [ajuste, setAjuste] = useState(0)
  const filaRef = useRef<HTMLDivElement | null>(null)
  const barraRef = useRef<HTMLDivElement | null>(null)
  const enBarra = borrado ? accionesSiBorrado : acciones
  const conReaccionesRapidas = !borrado && !!onReaccionar
  const hayBarra = barra && (conReaccionesRapidas || (enBarra?.length ?? 0) > 0)
  // La barra va al lado de la burbuja; si no cabe en la fila (o en la ventana), sube
  // encima de la burbuja y se mete hacia dentro. Nunca tapa el texto ni desborda.
  useLayoutEffect(() => {
    if (!hayBarra) { setArriba(false); setAjuste(0); return }
    const el = barraRef.current
    const fila = filaRef.current
    if (!el || !fila || typeof window === 'undefined') return
    const b = el.getBoundingClientRect()
    const f = fila.getBoundingClientRect()
    const min = Math.max(f.left, 8)
    const max = Math.min(f.right, window.innerWidth - 8)
    if (!arriba) {
      if (b.left < min || b.right > max) setArriba(true)
      return
    }
    if (b.left < min) setAjuste(a => a + (min - b.left))
    else if (b.right > max) setAjuste(a => a - (b.right - max))
  }, [hayBarra, arriba])

  const barraDeAcciones = hayBarra ? (
    <div ref={barraRef} className={`chat-msg__actions${arriba ? ' chat-msg__actions--arriba' : ''}`}
      role="toolbar" aria-label={textos.acciones}
      style={ajuste ? { translate: `${ajuste}px 0` } : undefined}>
      {conReaccionesRapidas && REACCIONES_DE_LA_BARRA.map(e => (
        <Pulsable type="button" key={e} onClick={() => onReaccionar?.(e)} className="chat-msg__emoji"
          aria-label={textos.reaccionarCon?.(e) ?? e}>{e}</Pulsable>
      ))}
      {(enBarra || []).map(a => (
        <BotonDeChat key={a.clave} onClick={a.onClick} title={a.etiqueta} variant={a.peligro ? 'danger' : 'ghost'}>
          {a.icono}
        </BotonDeChat>
      ))}
    </div>
  ) : null
  const hora = fmtHora(fecha)
  const verNombre = !propio && !compacto && mostrarNombre
  return (
    <div
      ref={filaRef}
      role="article"
      aria-label={hora ? `${textos.mensajeDe}, ${hora}` : textos.mensajeDe}
      onMouseEnter={() => setBarra(true)}
      onMouseLeave={() => setBarra(false)}
      onFocus={() => setBarra(true)}
      onBlur={() => setBarra(false)}
      className={`chat-msg ${propio ? 'chat-msg--propio' : 'chat-msg--ajeno'}${compacto ? ' chat-msg--compact' : ''}${borrado ? ' chat-msg--deleted' : ''}`}
    >
      {!propio && (!compacto ? (
        <div className={`chat-msg__avatar${esBot ? ' chat-msg__avatar--bot' : ''}`} aria-hidden="true">
          {esBot ? <Bot size={16} /> : (autor?.charAt(0)?.toUpperCase() || '?')}
        </div>
      ) : (
        <div className="chat-msg__avatar-gap" />
      ))}
      <div className="chat-msg__columna">
        <div className="chat-msg__burbuja">
          {barraDeAcciones}
          {verNombre && (
            <div className="chat-msg__autor">
              <span>{autor}</span>
              {esBot && textos.bot && <span className="chat-msg__bot-tag">{textos.bot}</span>}
            </div>
          )}
          {cita && (
            <blockquote className="chat-msg__cita">
              <span className="u-sm-700">{cita.autor}</span>{' '}
              <span className="chat-msg__cita-texto">{cita.borrada ? textos.eliminado : cita.texto}</span>
            </blockquote>
          )}
          {cuerpo}
          {extras}
          <div className="chat-msg__pie">
            {insignias}
            {fijado}
            {editado && textos.editado && <span>{textos.editado}</span>}
            {fecha && <time dateTime={fecha} title={fmtDateTime(fecha)}>{hora}</time>}
            {pie}
          </div>
        </div>
        {(reacciones?.length ?? 0) > 0 && (
          <div className="chat-msg__reactions">
            {reacciones!.map(r => (
              <Pulsable type="button" key={r.emoji} onClick={() => onReaccionar?.(r.emoji)} className="chat-reaction"
                aria-pressed={r.mia} aria-label={textos.reaccion?.(r.emoji, r.n) ?? `${r.emoji} ${r.n}`}>{r.emoji} <span>{r.n}</span></Pulsable>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** Etiqueta pequeña dentro de la burbuja, junto a la hora (p. ej. «Cliente», «Nota interna»). */
export function EtiquetaDeAutor({ children, title }: { children: ReactNode; title?: string }) {
  return <span className="chat-msg__bot-tag" title={title}>{children}</span>
}

/** Enviado (✓) / Leído (✓✓) dentro de la propia burbuja, tras la hora (mismo aspecto en todos los chats).
 *  El texto queda para el lector de pantalla y en el `title`. */
export function EstadoDeEntrega({ leido, textoLeido, textoEnviado }: { leido: boolean; textoLeido: string; textoEnviado: string }) {
  const texto = leido ? textoLeido : textoEnviado
  return (
    <span className={`chat-msg__estado${leido ? ' chat-msg__estado--leido' : ''}`} title={texto} aria-live="polite">
      {leido ? <CheckCheck size={14} aria-hidden="true" /> : <Check size={14} aria-hidden="true" />}
      <span className="u-sr-only">{texto}</span>
    </span>
  )
}

/** Mensaje de sistema («El cliente pide hablar con una persona»…): pastilla discreta centrada. */
export function MensajeDeSistema({ children }: { children: ReactNode }) {
  return <div className="chat-sistema" role="note"><span className="chat-sistema__pastilla">{children}</span></div>
}

/** Día de calendario local de una fecha ISO (para los separadores). */
function claveDeDia(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

/** El mensaje cae en otro día que el anterior (o es el primero): toca separador. */
export function cambiaDeDia(previa: string | null | undefined, actual: string | null | undefined): boolean {
  const a = claveDeDia(actual)
  return !!a && a !== claveDeDia(previa)
}

/** «Hoy», «Ayer» (en el idioma activo) o la fecha larga. */
export function etiquetaDeDia(iso: string): string {
  const d = new Date(iso)
  const hoy = new Date()
  const dias = Math.round((new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate()).getTime()
    - new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) / 86_400_000)
  if (dias === 0 || dias === 1) {
    try {
      const rel = new Intl.RelativeTimeFormat(localeActivo(), { numeric: 'auto' }).format(-dias, 'day')
      return rel.charAt(0).toLocaleUpperCase() + rel.slice(1)
    } catch { /* sin RelativeTimeFormat: fecha larga */ }
  }
  const opciones: Intl.DateTimeFormatOptions = d.getFullYear() === hoy.getFullYear()
    ? { weekday: 'long', day: 'numeric', month: 'long' }
    : { day: 'numeric', month: 'long', year: 'numeric' }
  return formateadorDeFecha(opciones).format(d)
}

/** Separador de día entre mensajes («Hoy», «Ayer», «lunes, 23 de noviembre»). */
export function SeparadorDeDia({ fecha }: { fecha: string | null | undefined }) {
  if (!fecha || !claveDeDia(fecha)) return null
  return (
    <div className="chat-dia">
      <time className="chat-dia__pastilla" dateTime={fecha}>{etiquetaDeDia(fecha)}</time>
    </div>
  )
}

/** Agrupa reacciones `{emoji, user_id, client_user_id}` por emoji y marca las de quien mira. */
export function agruparReacciones(
  reacciones: { emoji: string; user_id?: string | null; client_user_id?: string | null }[] | null | undefined,
  quien?: { userId?: string | null; clientId?: string | null },
): ReaccionAgrupada[] {
  const grupos = new Map<string, ReaccionAgrupada>()
  for (const r of reacciones || []) {
    const g = grupos.get(r.emoji) || { emoji: r.emoji, n: 0, mia: false }
    g.n += 1
    if ((quien?.userId && r.user_id === quien.userId) || (quien?.clientId && r.client_user_id === quien.clientId)) g.mia = true
    grupos.set(r.emoji, g)
  }
  return [...grupos.values()]
}

/** «Escribiendo…» bajo la lista de mensajes (el del chat interno). */
export function Escribiendo({ texto }: { texto: string | null }) {
  if (!texto) return null
  return <div className="chat-typing" role="status">{texto}</div>
}
