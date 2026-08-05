const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || ''
const GET_CACHE_TTL_MS = 30_000

const getCache = new Map<string, { expiresAt: number; promise: Promise<unknown> }>()

function normalizeBasePath(path: string) {
  if (!path || path === '/') return ''
  return path.startsWith('/') ? path : `/${path}`
}

function isLocalBrowser() {
  if (typeof window === 'undefined') return false
  return ['localhost', '127.0.0.1'].includes(window.location.hostname)
}

function shouldUseFrontendProxy(apiUrl: string) {
  if (typeof window === 'undefined') return false
  if (!apiUrl || apiUrl.startsWith('/')) return true
  return !isLocalBrowser()
}

function buildApiUrl(endpoint: string) {
  const basePath = normalizeBasePath(BASE_PATH)
  const normalizedEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`

  if (shouldUseFrontendProxy(API_URL)) {
    const proxyBase = (API_URL.startsWith('/') ? API_URL : `${basePath}/api/backend`).replace(/\/$/, '')
    return `${proxyBase}${normalizedEndpoint}`
  }

  return `${API_URL.replace(/\/$/, '')}${basePath}${normalizedEndpoint}`
}

/**
 * A robust API client that handles backend URL resolution and short-lived GET reuse.
 * @param endpoint The API endpoint to call, e.g. '/api/test' or '/api/day90/dashboard'.
 *                 The endpoint should include the '/api' prefix.
 * @param options Standard fetch options (method, body, etc.).
 */
async function apiClientFetch<T = unknown>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {})
  const method = options.method ?? 'GET'
  const fullUrl = buildApiUrl(endpoint)
  const canUseMemoryCache = method === 'GET' && options.cache !== 'no-store'

  if (canUseMemoryCache) {
    const cached = getCache.get(fullUrl)
    if (cached && cached.expiresAt > Date.now()) {
      return cached.promise as Promise<T>
    }
  }

  const request = fetch(fullUrl, { ...options, headers }).then(async (response) => {
    if (response.status === 401) {
      console.warn('[API] 401 Unauthorized - check backend auth/proxy settings')
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: response.statusText,
      }))
      throw new Error(errorData.detail || 'An API error occurred.')
    }

    if (response.status === 204) {
      return null as T
    }

    return response.json() as Promise<T>
  })

  if (canUseMemoryCache) {
    getCache.set(fullUrl, { expiresAt: Date.now() + GET_CACHE_TTL_MS, promise: request })
    request.catch(() => getCache.delete(fullUrl))
  } else if (method !== 'GET') {
    getCache.clear()
  }

  return request
}

/**
 * API client with convenience methods for common HTTP operations.
 */
export const apiClient = {
  /**
   * Perform a GET request.
   */
  get: <T = unknown>(endpoint: string, options?: RequestInit): Promise<T> => {
    return apiClientFetch<T>(endpoint, { ...options, method: 'GET' })
  },

  /**
   * Perform a POST request.
   */
  post: <T = unknown>(endpoint: string, data?: unknown, options?: RequestInit): Promise<T> => {
    return apiClientFetch<T>(endpoint, {
      ...options,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      body: data ? JSON.stringify(data) : undefined,
    })
  },

  /**
   * Perform a PUT request.
   */
  put: <T = unknown>(endpoint: string, data?: unknown, options?: RequestInit): Promise<T> => {
    return apiClientFetch<T>(endpoint, {
      ...options,
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      body: data ? JSON.stringify(data) : undefined,
    })
  },

  /**
   * Perform a PATCH request.
   */
  patch: <T = unknown>(endpoint: string, data?: unknown, options?: RequestInit): Promise<T> => {
    return apiClientFetch<T>(endpoint, {
      ...options,
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      body: data ? JSON.stringify(data) : undefined,
    })
  },

  /**
   * Perform a DELETE request.
   */
  delete: <T = unknown>(endpoint: string, options?: RequestInit): Promise<T> => {
    return apiClientFetch<T>(endpoint, { ...options, method: 'DELETE' })
  },
}

export default apiClientFetch
