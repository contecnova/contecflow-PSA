/**
 * Pantalla del chat (24-11-2026, «un solo chat»: docs/GUIA_DE_DISENO.md §«Un solo chat»).
 *
 * Las piezas de pantalla del chat interno (`pages/chat/ListaDeConversaciones.tsx`
 * y `PanelDeConversacion.tsx`) extraídas tal cual, para que el chat interno y
 * los tres chats del portal (conversaciones formales, pestaña «Chat» y chat en
 * vivo de Soporte, en los dos lados) sean LA MISMA pantalla:
 *
 * - `PantallaDeChat`: la raíz (`chat-root`): lista a la izquierda y panel.
 * - `ListaDeChats` + `GrupoDeChats` + `FilaDeConversacion`: la columna de
 *   conversaciones con su buscador, sus grupos y sus filas (avatar o icono +
 *   nombre; no leídos discretos al final).
 * - `PanelDeChat` + `CabeceraDeConversacion` + `ZonaDeMensajes`: el panel con
 *   la barra superior (título, subtítulo, acciones: llamar, vídeo, más) y la
 *   zona de mensajes; debajo va `EditorDeChat`.
 *
 * Lo que difiere por permisos se pasa por props (acciones de la cabecera,
 * botón de nueva conversación, indicador de supervisión solo al operador…).
 */
import { type HTMLAttributes, type ReactNode } from 'react'
import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { Buscador, EmptyState, Pulsable } from '../ui'
import { BotonDeChat } from './BotonDeChat'
import './chat.css'

/** Raíz de la pantalla. `incrustada`: dentro de otra página (portal, Service Desk) con alto propio. */
export function PantallaDeChat({ children, incrustada }: { children: ReactNode; incrustada?: boolean }) {
  return <div className={`chat-root${incrustada ? ' chat-root--incrustada' : ''}`}>{children}</div>
}

export function ListaDeChats({ children, estrecha, buscar, cargando, vacio, accion }: {
  children: ReactNode
  estrecha?: boolean
  /** Buscador de la lista (como el del chat interno). */
  buscar?: { valor: string; onCambiar: (v: string) => void; etiqueta: string }
  cargando?: boolean
  /** Lista vacía: título, descripción e icono (con la acción de nueva conversación si la hay). */
  vacio?: { titulo: string; descripcion?: string; icono: ReactNode } | null
  /** Acción principal (p. ej. «Nueva conversación»), donde la pone el chat interno: en el vacío y en la cabecera de la página. */
  accion?: ReactNode
}) {
  return (
    <div className={`chat-list${estrecha ? ' chat-list--narrow' : ''}`}>
      {buscar && (
        <div className="chat-list__search">
          <Buscador className="chat-search-box" aria-label={buscar.etiqueta} value={buscar.valor} onChange={buscar.onCambiar} placeholder={buscar.etiqueta} />
        </div>
      )}
      <div className="chat-list__scroll">
        {cargando && <div className="u-text3-xs" role="status">…</div>}
        {!cargando && vacio && <EmptyState icon={vacio.icono} title={vacio.titulo} description={vacio.descripcion} action={accion} />}
        {children}
      </div>
    </div>
  )
}

/** Grupo de la lista (Directos, Grupos, Equipos…), plegable si se le da `onToggle`. */
export function GrupoDeChats({ titulo, n, children, plegado, onToggle }: {
  titulo: string; n?: number; children?: ReactNode; plegado?: boolean; onToggle?: () => void
}) {
  return (
    <div className="u-mb-12">
      {onToggle ? (
        <Pulsable type="button" onClick={onToggle} aria-expanded={!plegado} className="chat-section-btn chat-section-btn--toggle">
          {plegado ? <ChevronRight size={11} aria-hidden="true" /> : <ChevronDown size={11} aria-hidden="true" />}
          {titulo} {n != null && <span className="chat-section-btn__count">({n})</span>}
        </Pulsable>
      ) : (
        <h3 className="chat-section-btn">
          {titulo} {n != null && <span className="chat-section-btn__count">({n})</span>}
        </h3>
      )}
      {!plegado && children}
    </div>
  )
}

/** Una conversación de la lista: icono (o avatar con la inicial) + nombre. */
export function FilaDeConversacion({ titulo, activa, onClick, icono, avatar, sangria, noLeidos, etiquetaNoLeidos, title }: {
  titulo: string
  activa: boolean
  onClick: () => void
  /** Icono (canal, grupo…); sin él, avatar con la inicial si `avatar`. */
  icono?: ReactNode
  /** Avatar con la inicial (y lo que se le superponga, p. ej. presencia). */
  avatar?: ReactNode | true
  sangria?: boolean
  noLeidos?: number
  etiquetaNoLeidos?: string
  title?: string
}) {
  return (
    <Pulsable type="button" onClick={onClick} aria-current={activa ? 'true' : undefined} title={title}
      className={`chat-conv-row${sangria ? ' chat-conv-row--indent' : ''}`}>
      {icono}
      {avatar === true
        ? <span className="chat-avatar" aria-hidden="true">{(titulo || '?').charAt(0).toUpperCase()}</span>
        : avatar}
      <span className="chat-ellipsis">{titulo}</span>
      {(noLeidos ?? 0) > 0 && (
        <span className="chat-conv-row__sin-leer" aria-label={etiquetaNoLeidos}>{(noLeidos ?? 0) > 99 ? '99+' : noLeidos}</span>
      )}
    </Pulsable>
  )
}

/** Panel de la conversación (cabecera, mensajes y editor). */
export function PanelDeChat({ etiqueta, children, ...resto }: { etiqueta: string; children: ReactNode } & Omit<HTMLAttributes<HTMLDivElement>, 'className' | 'role'>) {
  return <div role="region" aria-label={etiqueta} className="chat-pane" {...resto}>{children}</div>
}

/** Barra superior del panel: título (con icono y subtítulo) y acciones a la derecha. */
export function CabeceraDeConversacion({ titulo, icono, subtitulo, indicador, acciones, onVolver, etiquetaVolver }: {
  titulo: string
  icono?: ReactNode
  subtitulo?: ReactNode
  /** Indicador discreto junto al título (p. ej. «Con supervisión», solo al operador). */
  indicador?: ReactNode
  /** Botones de la derecha (llamar, vídeo, más…). */
  acciones?: ReactNode
  onVolver?: () => void
  etiquetaVolver?: string
}) {
  return (
    <div className={`chat-pane__head${onVolver ? ' chat-pane__head--back' : ''}`}>
      <div className="chat-pane__title-wrap">
        {onVolver && <BotonDeChat onClick={onVolver} title={etiquetaVolver}><ChevronLeft size={16} aria-hidden="true" /></BotonDeChat>}
        {icono}
        <div className="u-min0">
          <h2 className="chat-pane__title">{titulo}{indicador}</h2>
          {subtitulo && <div className="u-text3-xs">{subtitulo}</div>}
        </div>
      </div>
      {acciones && <div className="chat-pane__actions">{acciones}</div>}
    </div>
  )
}

/** Zona de mensajes (registro en vivo para lectores de pantalla). */
export function ZonaDeMensajes({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return <div className="chat-pane__messages" role="log" aria-live="polite" aria-label={etiqueta}>{children}</div>
}

/** Indicador discreto con el estilo de etiqueta del chat interno y su explicación en el `title`. */
export function IndicadorDeCabecera({ texto, explicacion }: { texto: string; explicacion: string }) {
  return <span className="chat-msg__bot-tag chat-pane__indicador" title={explicacion} aria-label={`${texto}: ${explicacion}`}>{texto}</span>
}

/** Panel sin conversación elegida (el vacío del chat interno). */
export function PanelVacio({ icono, titulo, descripcion, accion }: { icono: ReactNode; titulo: string; descripcion?: string; accion?: ReactNode }) {
  return (
    <div className="chat-pane-empty">
      <EmptyState icon={icono} title={titulo} description={descripcion} action={accion} />
    </div>
  )
}
