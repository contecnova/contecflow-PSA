/**
 * logger.ts — Configurable frontend logger for Contecflow PSA
 *
 * Log levels (ascending severity):  debug < info < warn < error
 *
 * Runtime configuration:
 *   • localStorage key `contecflow_log_level`  (e.g. "warn")
 *   • window.CONTECFLOW_LOG_LEVEL              (higher priority)
 *
 * Examples:
 *   import logger from '../utils/logger'
 *   logger.debug('Fetching data', { url })
 *   logger.info('User logged in', { userId })
 *   logger.warn('Token expiring soon')
 *   logger.error('Request failed', err)
 *
 * Change level at runtime from browser console:
 *   window.CONTECFLOW_LOG_LEVEL = 'debug'; location.reload()
 *   // or without reload:
 *   import logger from '…/utils/logger'; logger.setLevel('debug')
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error' | 'silent'

const LEVELS: Record<LogLevel, number> = { debug: 0, info: 1, warn: 2, error: 3, silent: 4 }
const COLORS: Record<Exclude<LogLevel, 'silent'>, string> = {
  debug: '#7c8db5',
  info:  '#4f8ef7',
  warn:  '#f59e0b',
  error: '#f87171',
}

declare global {
  interface Window {
    CONTECFLOW_LOG_LEVEL?: LogLevel
    __contecflowLogger?: Logger
  }
}

function _safeLocalStorageGet(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}

function isLogLevel(value: string): value is LogLevel {
  return value in LEVELS
}

function resolveLevel(): LogLevel {
  const raw = (
    window.CONTECFLOW_LOG_LEVEL ||
    _safeLocalStorageGet('contecflow_log_level') ||
    (import.meta.env.DEV ? 'debug' : 'warn')
  ).toLowerCase()
  return isLogLevel(raw) ? raw : (import.meta.env.DEV ? 'debug' : 'warn')
}

let _currentLevel: LogLevel = resolveLevel()

function shouldLog(level: LogLevel): boolean {
  return LEVELS[level] >= LEVELS[_currentLevel]
}

function formatArgs(level: Exclude<LogLevel, 'silent'>, msg: unknown, ...rest: unknown[]): unknown[] {
  const ts = new Date().toISOString().slice(11, 23)
  return [
    `%c[${ts}] [${level.toUpperCase()}]`,
    `color:${COLORS[level]};font-weight:600`,
    msg,
    ...rest,
  ]
}

export interface Logger {
  debug: (msg: unknown, ...args: unknown[]) => void
  info: (msg: unknown, ...args: unknown[]) => void
  warn: (msg: unknown, ...args: unknown[]) => void
  error: (msg: unknown, ...args: unknown[]) => void
  setLevel: (level: string) => void
  getLevel: () => LogLevel
}

const logger: Logger = {
  debug: (msg, ...args) => { if (shouldLog('debug')) console.warn(...formatArgs('debug', msg, ...args)) },
  info:  (msg, ...args) => { if (shouldLog('info'))  console.warn(...formatArgs('info',  msg, ...args)) },
  warn:  (msg, ...args) => { if (shouldLog('warn'))  console.warn(...formatArgs('warn',  msg, ...args)) },
  error: (msg, ...args) => { if (shouldLog('error')) console.error(...formatArgs('error', msg, ...args)) },

  /** Change log level at runtime */
  setLevel(level: string) {
    const l = level.toLowerCase()
    if (!isLogLevel(l)) {
      console.warn(`[Contecflow logger] Invalid level "${level}". Valid: ${Object.keys(LEVELS).join(', ')}`)
      return
    }
    _currentLevel = l
    localStorage.setItem('contecflow_log_level', l)
    const color = l === 'silent' ? '#fff' : COLORS[l]
    console.warn(`%c[Contecflow logger] Level set to: ${l.toUpperCase()}`, `color:${color};font-weight:600`)
  },

  /** Returns current level name */
  getLevel(): LogLevel { return _currentLevel },
}

// Expose to browser console for easy debugging
if (typeof window !== 'undefined') {
  window.__contecflowLogger = logger
}

export default logger
