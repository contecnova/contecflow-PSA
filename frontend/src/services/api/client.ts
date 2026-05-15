/**
 * Axios instance + auth/refresh/rate-limit interceptors.
 *
 * Authentication is handled exclusively via httpOnly cookies (withCredentials: true).
 * No tokens are read from or written to localStorage to prevent XSS exposure.
 */
import axios, { type AxiosInstance, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'

const BASE_URL: string = (import.meta as ImportMeta & { env: Record<string, string | undefined> }).env?.VITE_API_URL || '/api/v1'

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout: 30000,
})

// Strip Content-Type for FormData so the browser sets the correct multipart boundary.
api.interceptors.request.use((config) => {
  if (config.data instanceof FormData) {
    // headers is an AxiosHeaders instance; delete is safe
    delete (config.headers as Record<string, unknown>)['Content-Type']
  }
  return config
})

// Singleton refresh promise — ensures only one /auth/refresh call is in flight at a time.
let _refreshPromise: Promise<unknown> | null = null

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config as RetriableConfig | undefined
    const status: number | undefined = err.response?.status
    const requestPath: string = original?.url || ''
    const isAuthFlowRequest =
      requestPath.includes('/auth/login') ||
      requestPath.includes('/auth/refresh') ||
      requestPath.includes('/auth/me')

    if (!err.response || original?._retry || isAuthFlowRequest) {
      return Promise.reject(err)
    }

    if (status === 401 && original) {
      original._retry = true
      try {
        if (!_refreshPromise) {
          _refreshPromise = axios
            .post(`${BASE_URL}/auth/refresh`, null, { withCredentials: true })
            .finally(() => {
              _refreshPromise = null
            })
        }
        await _refreshPromise
        return api(original)
      } catch {
        _refreshPromise = null
        window.dispatchEvent(new CustomEvent('auth:session-expired'))
      }
    }

    if (status === 429) {
      const retryAfter = err.response?.headers?.['retry-after']
      window.dispatchEvent(
        new CustomEvent('api:rate-limited', {
          detail: {
            retryAfter: retryAfter ? Number(retryAfter) : null,
            path: original?.url || '',
          },
        }),
      )
    }

    return Promise.reject(err)
  },
)

export { api }
export default api
export type { AxiosRequestConfig }
