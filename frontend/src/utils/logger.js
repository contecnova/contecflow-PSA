/**
 * logger.js — Configurable frontend logger for Contecflow PSA
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

const LEVELS = { debug: 0, info: 1, warn: 2, error: 3, silent: 4 }
const COLORS = {
  debug: '#7c8db5',
  info:  '#4f8ef7',
  warn:  '#f59e0b',
  error: '#f87171',
}

function _safeLocalStorageGet(key) {
  try { return localStorage.getItem(key) } catch { return null }
}

function resolveLevel() {
  const raw = (
    window.CONTECFLOW_LOG_LEVEL ||
    _safeLocalStorageGet('contecflow_log_level') ||
    (import.meta.env.DEV ? 'debug' : 'warn')
  ).toLowerCase()
  return LEVELS[raw] !== undefined ? raw : (import.meta.env.DEV ? 'debug' : 'warn')
}

let _currentLevel = resolveLevel()

function shouldLog(level) {
  return LEVELS[level] >= LEVELS[_currentLevel]
}

function formatArgs(level, msg, ...rest) {
  const ts = new Date().toISOString().slice(11, 23)
  return [
    `%c[${ts}] [${level.toUpperCase()}]`,
    `color:${COLORS[level]};font-weight:600`,
    msg,
    ...rest,
  ]
}

const logger = {
  debug: (msg, ...args) => shouldLog('debug') && console.warn(...formatArgs('debug', msg, ...args)),
  info:  (msg, ...args) => shouldLog('info')  && console.warn(...formatArgs('info',  msg, ...args)),
  warn:  (msg, ...args) => shouldLog('warn')  && console.warn(...formatArgs('warn',  msg, ...args)),
  error: (msg, ...args) => shouldLog('error') && console.error(...formatArgs('error', msg, ...args)),

  /** Change log level at runtime */
  setLevel(level) {
    const l = level.toLowerCase()
    if (LEVELS[l] === undefined) {
      console.warn(`[Contecflow logger] Invalid level "${level}". Valid: ${Object.keys(LEVELS).join(', ')}`)
      return
    }
    _currentLevel = l
    localStorage.setItem('contecflow_log_level', l)
    console.warn(`%c[Contecflow logger] Level set to: ${l.toUpperCase()}`, `color:${COLORS[l]||'#fff'};font-weight:600`)
  },

  /** Returns current level name */
  getLevel() { return _currentLevel },
}

// Expose to browser console for easy debugging
if (typeof window !== 'undefined') {
  window.__contecflowLogger = logger
}

export default logger
