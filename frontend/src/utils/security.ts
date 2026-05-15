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
const SAFE_PROTOCOLS = new Set<string>(['http:', 'https:', 'mailto:'])

/**
 * Return `url` when it is safe to use as an href value, otherwise return '#'.
 * Handles relative URLs, absolute URLs, and blocks all dangerous protocols.
 */
export function sanitizeUrl(url: string | null | undefined): string {
  if (!url || typeof url !== 'string') return '#'

  const trimmed = url.trim()
  if (!trimmed) return '#'

  // Block protocol-relative URLs (//evil.com) — they switch to http/https on the current protocol
  // and can redirect to external sites.
  if (trimmed.startsWith('//')) return '#'

  // Safe same-origin relative paths
  if (trimmed.startsWith('/') || trimmed.startsWith('./') || trimmed.startsWith('../')) {
    return trimmed
  }

  // Parse to extract the protocol — catches encoded variants like "&#106;avascript:"
  try {
    const parsed = new URL(trimmed)
    if (!SAFE_PROTOCOLS.has(parsed.protocol)) return '#'
    return trimmed
  } catch {
    // URL() throws for relative or malformed URLs; fall through to '#' (unknown is unsafe)
    return '#'
  }
}

/**
 * Return true only when the URL passes the sanitizeUrl check (not '#').
 * Useful for conditional rendering: {isSafeUrl(c.url) && <a href={c.url}>...}
 */
export function isSafeUrl(url: string | null | undefined): boolean {
  return sanitizeUrl(url) !== '#'
}
