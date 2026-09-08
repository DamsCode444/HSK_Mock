import axios from 'axios'
import { getToken } from '@clerk/vue'

const apiBaseURL = import.meta.env.VITE_API_BASE_URL || '/api'
let unauthorizedEventPending = false

export const http = axios.create({
  baseURL: apiBaseURL.replace(/\/$/, ''),
  timeout: 25000,
  headers: {
    Accept: 'application/json',
  },
})

http.interceptors.request.use(async (config) => {
  if (config._hskAuthRetry && config.headers.Authorization) return config
  const token = await getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config
    if (error.response?.status === 401 && config && !config._hskAuthRetry) {
      config._hskAuthRetry = true
      const freshToken = await getToken({ skipCache: true }).catch(() => null)
      if (freshToken) {
        config.headers.Authorization = `Bearer ${freshToken}`
        return http.request(config)
      }
    }
    if (
      error.response?.status === 401 &&
      !unauthorizedEventPending
    ) {
      unauthorizedEventPending = true
      window.dispatchEvent(new CustomEvent('hsk:unauthorized'))
      window.setTimeout(() => {
        unauthorizedEventPending = false
      }, 1000)
    }
    return Promise.reject(error)
  },
)

export function errorMessage(error, fallback = 'Something went wrong. Please try again.') {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || item.message).filter(Boolean).join(', ') || fallback
  }
  return detail || error?.response?.data?.message || error?.message || fallback
}

export function unwrap(payload, preferredKeys = []) {
  let value = payload?.data ?? payload
  for (const key of preferredKeys) {
    if (value && typeof value === 'object' && value[key] !== undefined) return value[key]
  }
  return value
}

export function asList(payload, preferredKeys = []) {
  const value = unwrap(payload, preferredKeys)
  if (Array.isArray(value)) return value
  if (Array.isArray(value?.items)) return value.items
  if (Array.isArray(value?.results)) return value.results
  return []
}

export function mediaUrl(path) {
  if (!path) return ''
  if (/^(https?:|data:|blob:)/i.test(path)) return path
  const normalized = String(path).replaceAll('\\', '/').replace(/^storage\//i, '/media/')
  const relative = normalized.startsWith('/') ? normalized : `/${normalized}`
  const origin = (import.meta.env.VITE_MEDIA_ORIGIN || '').replace(/\/$/, '')
  return `${origin}${relative}`
}
