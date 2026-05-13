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

// ── React Query staleTime defaults ──────────────────────────────────────
export const STALE_5_MIN_MS = 5 * 60_000
export const STALE_15_MIN_MS = 15 * 60_000
export const STALE_1_HOUR_MS = 60 * 60_000

// ── Inactivity / session ────────────────────────────────────────────────
export const IDLE_WARNING_MS = 25 * 60_000   // 25 min — warn user before timeout
export const IDLE_LOGOUT_MS = 30 * 60_000    // 30 min — auto logout

// ── Page sizes ──────────────────────────────────────────────────────────
export const DEFAULT_PAGE_SIZE = 50
export const SMALL_PAGE_SIZE = 20
export const LARGE_PAGE_SIZE = 200
export const MAX_PAGE_SIZE = 500

// ── Retry / backoff ─────────────────────────────────────────────────────
export const RETRY_INITIAL_DELAY_MS = 1000
export const RETRY_MAX_DELAY_MS = 30_000
export const RETRY_BACKOFF_FACTOR = 2

// ── WebSocket ───────────────────────────────────────────────────────────
export const WS_RECONNECT_INITIAL_MS = 1000
export const WS_RECONNECT_MAX_MS = 30_000
export const WS_HEARTBEAT_MS = 25_000

// ── Animations ──────────────────────────────────────────────────────────
export const ANIMATION_FAST_MS = 120
export const ANIMATION_NORMAL_MS = 200
export const ANIMATION_SLOW_MS = 350
