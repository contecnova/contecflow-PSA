/**
 * Timing constants centralizados para evitar magic numbers dispersos en pages.
 * Audit #74.
 *
 * Convención: milisegundos a menos que `_SECONDS` o `_MINUTES`.
 */

// ── Debounce / throttle ──────────────────────────────────────────────────
export const SEARCH_DEBOUNCE_MS = 300
export const INPUT_DEBOUNCE_MS = 150
export const SCROLL_THROTTLE_MS = 50

// ── Toasts / notifications ──────────────────────────────────────────────
export const TOAST_DEFAULT_MS = 3000
export const TOAST_ERROR_MS = 5000
export const TOAST_SUCCESS_MS = 2000

// ── Modal / overlay ─────────────────────────────────────────────────────
export const MODAL_TRANSITION_MS = 120
export const DROPDOWN_DELAY_MS = 150

// ── Polling intervals ───────────────────────────────────────────────────
export const NOTIFICATIONS_POLL_MS = 30_000  // 30s
export const PRESENCE_POLL_MS = 60_000       // 1 min
export const HEALTH_CHECK_POLL_MS = 60_000   // 1 min

// Escalones genéricos de refetchInterval / setInterval de sondeo
export const POLL_JOB_STATUS_MS = 1_500      // estado de un trabajo/agente en cola hasta que termina
export const POLL_RUN_DETAIL_MS = 4_000      // detalle de una ejecución de flujo en curso
export const POLL_FAST_MS = 5_000
export const POLL_RUN_LIST_MS = 8_000        // lista de ejecuciones de flujo
export const POLL_LIVE_MS = 15_000
export const POLL_ACTIVE_CHAT_MS = 20_000    // mensajes de la conversación abierta en el panel
export const POLL_FREQUENT_MS = 30_000
export const POLL_DEFAULT_MS = 60_000
export const POLL_RELAXED_MS = 2 * 60_000
export const POLL_SLOW_MS = 5 * 60_000
export const CLOCK_TICK_MS = 1_000           // relojes / cronómetros / cuentas atrás de 1s

// Refresco único diferido tras lanzar una operación asíncrona en el backend
export const DELAYED_REFETCH_SHORT_MS = 15_000
export const DELAYED_REFETCH_MS = 30_000

// ── React Query staleTime defaults ──────────────────────────────────────
export const STALE_ALWAYS = 0                       // siempre obsoleto: refetch en cada montaje
export const STALE_VERY_SHORT_MS = 5_000
export const STALE_LIVE_MS = 10_000
export const STALE_NEAR_LIVE_MS = 15_000
export const STALE_PREVIEW_MS = 20_000
export const STALE_SHORT_MS = 30_000
export const STALE_DEFAULT_MS = 60_000
export const STALE_REFERENCE_DATA_MS = 2 * 60_000   // listas para selectores
export const STALE_5_MIN_MS = 5 * 60_000
export const STALE_10_MIN_MS = 10 * 60_000
export const STALE_15_MIN_MS = 15 * 60_000
export const STALE_AI_NARRATIVE_MS = 55 * 60_000    // narrativa IA: justo por debajo de 1h
export const STALE_1_HOUR_MS = 60 * 60_000

// ── React Query gcTime ──────────────────────────────────────────────────
export const GC_DEFAULT_MS = 5 * 60_000

// ── Inactivity / session ────────────────────────────────────────────────
export const IDLE_WARNING_MS = 25 * 60_000   // 25 min — warn user before timeout
export const IDLE_LOGOUT_MS = 30 * 60_000    // 30 min — auto logout
export const SESSION_EXPIRED_NOTICE_MS = 4_000

// ── Page sizes (movidos a ./pagination; re-exportados por compatibilidad) ─
export { DEFAULT_PAGE_SIZE, SMALL_PAGE_SIZE, LARGE_PAGE_SIZE, MAX_PAGE_SIZE } from './pagination'

// ── Feedback de UI (mensajes "guardado"/"copiado", redirecciones) ───────
export const UI_FEEDBACK_MS = 2_000
export const UI_FEEDBACK_SAVED_MS = 2_500
export const UI_FEEDBACK_LONG_MS = 3_000
export const SUCCESS_MESSAGE_MS = 5_000
export const SUCCESS_MESSAGE_LONG_MS = 6_000
export const REDIRECT_AFTER_SUCCESS_MS = 1_400
export const OBJECT_URL_REVOKE_DELAY_MS = 1_000
export const NOTIFICATION_BEEP_MS = 120

// ── Debounces específicos ───────────────────────────────────────────────
export const PREFERENCES_SAVE_DEBOUNCE_MS = 500
export const SLOW_INPUT_DEBOUNCE_MS = 400     // vistas previas / sugerencias pedidas al servidor
export const LIVE_VALIDATION_DEBOUNCE_MS = 600

// ── Chat: indicador "escribiendo" ───────────────────────────────────────
export const TYPING_IDLE_MS = 4_000           // deja de emitir "escribiendo" tras 4s sin teclear
export const TYPING_SWEEP_MS = 2_000          // barrido de usuarios que escriben (página de chat)
export const TYPING_SWEEP_PANEL_MS = 1_500    // barrido en el panel lateral de chat

// ── Retry / backoff ─────────────────────────────────────────────────────
export const RETRY_INITIAL_DELAY_MS = 1000
export const RETRY_MAX_DELAY_MS = 30_000
export const RETRY_BACKOFF_FACTOR = 2

// ── WebSocket ───────────────────────────────────────────────────────────
export const WS_RECONNECT_INITIAL_MS = 1000
export const WS_RECONNECT_MAX_MS = 30_000
export const WS_HEARTBEAT_MS = 25_000
export const WS_RECONNECT_DELAY_MS = 5_000    // reconexión fija (sin backoff)
export const WS_STREAM_RECONNECT_MS = 2_000   // reconexión del stream en vivo de la plataforma de datos
export const WS_PING_INTERVAL_MS = 30_000     // ping de la página de notificaciones

// ── Animations ──────────────────────────────────────────────────────────
export const ANIMATION_FAST_MS = 120
export const ANIMATION_NORMAL_MS = 200
export const ANIMATION_SLOW_MS = 350
export const PROGRESS_BAR_DONE_MS = 600
export const PROGRESS_BAR_RESET_MS = 950
export const FIT_VIEW_DELAY_MS = 100          // esperar al render antes de encuadrar el lienzo
export const FOCUS_DEFER_MS = 10              // esperar al render antes de devolver el foco
