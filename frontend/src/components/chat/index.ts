/**
 * Piezas del chat compartidas por el chat interno y los tres chats del portal
 * (24-11-2026, «un solo chat»: docs/GUIA_DE_DISENO.md §«Un solo chat» y
 * docs/portal/CHAT_DEL_PORTAL.md). Vigilado por scripts/kit_pendientes.mjs
 * (los chats del portal tienen que importar de aquí).
 * 24-11-2026: burbujas (propio a la derecha, ajeno a la izquierda) en todos los chats,
 * también el panel flotante, la llamada y los asistentes de IA (GUIA_DE_DISENO §17.1).
 */
export { FilaDeMensaje, Escribiendo, EtiquetaDeAutor, EstadoDeEntrega, MensajeDeSistema, SeparadorDeDia, cambiaDeDia, etiquetaDeDia, agruparReacciones, REACCIONES_DE_LA_BARRA } from './FilaDeMensaje'
export type { AccionDeMensaje, ReaccionAgrupada, TextosDeFila, FilaDeMensajeProps } from './FilaDeMensaje'
export { EditorDeChat, AvisoDelEditor } from './EditorDeChat'
export type { EditorDeChatProps, AdjuntarDelEditor } from './EditorDeChat'
export { BotonDeChat, BotonesDeLlamada, fmtHora } from './BotonDeChat'
export { PantallaDeChat, ListaDeChats, GrupoDeChats, FilaDeConversacion, PanelDeChat, PanelVacio, CabeceraDeConversacion, ZonaDeMensajes, IndicadorDeCabecera } from './Pantalla'
