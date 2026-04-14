/**
 * Frontend security utilities.
 *
 * sanitizeUrl — blocks javascript:/vbscript:/data: protocol injection before
 *               a user-supplied value is placed into an href attribute.
 *
 * Usage:
 *   import { sanitizeUrl } from '../utils/security'
 *   <a href={sanitizeUrl(record.website)} ...>
 */

/** Protocols that are safe to embed in href attributes. */
const SAFE_PROTOCOLS = new Set(['http:', 'https:', 'mailto:'])

/**
 * Return `url` when it is safe to use as an href value, otherwise return '#'.
 * Handles relative URLs, absolute URLs, and blocks all dangerous protocols.
 *
 * @param {string|null|undefined} url
 * @returns {string}
 */
export function sanitizeUrl(url) {
  if (!url || typeof url !== 'string') return '#'

  const trimmed = url.trim()
  if (!trimmed) return '#'

  // Relative URLs (start with / or ./) are always safe
  if (trimmed.startsWith('/') || trimmed.startsWith('./') || trimmed.startsWith('../')) {
    return trimmed
  }

  // Parse to extract the protocol — catches encoded variants like "&#106;avascript:"
  try {
    const parsed = new URL(trimmed)
    if (!SAFE_PROTOCOLS.has(parsed.protocol)) return '#'
    return trimmed
  } catch {
    // URL() throws for relative or malformed URLs; treat as relative path
    return trimmed
  }
}

/**
 * Return true only when the URL passes the sanitizeUrl check (not '#').
 * Useful for conditional rendering: {isSafeUrl(c.url) && <a href={c.url}>...}
 *
 * @param {string|null|undefined} url
 * @returns {boolean}
 */
export function isSafeUrl(url) {
  return sanitizeUrl(url) !== '#'
}
