import axios, { AxiosError, type AxiosRequestConfig } from 'axios'

import type { ApiError, TokenPair } from '@/types/api'

const ACCESS = 'ds.access'
const REFRESH = 'ds.refresh'

function read(key: string): string | null {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) sessionStorage.removeItem(key)
    else sessionStorage.setItem(key, value)
  } catch {
    // storage unavailable: tokens live only in memory for this tab
  }
}

let accessToken = read(ACCESS)
let refreshToken = read(REFRESH)
let onLogout: (() => void) | null = null

export function setTokens(tokens: TokenPair | null): void {
  accessToken = tokens?.access_token ?? null
  refreshToken = tokens?.refresh_token ?? null
  write(ACCESS, accessToken)
  write(REFRESH, refreshToken)
}

export function hasSession(): boolean {
  return accessToken !== null
}

export function onSessionExpired(handler: () => void): void {
  onLogout = handler
}

export const http = axios.create({ baseURL: '/api/v1' })

http.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

let refreshing: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  if (!refreshToken) return false
  try {
    const { data } = await axios.post<TokenPair>('/api/v1/auth/refresh', {
      refresh_token: refreshToken,
    })
    setTokens(data)
    return true
  } catch {
    return false
  }
}

http.interceptors.response.use(undefined, async (error: AxiosError) => {
  const original = error.config as (AxiosRequestConfig & { _retried?: boolean }) | undefined
  const isAuthCall = original?.url?.startsWith('/auth/token')
  if (error.response?.status === 401 && original && !original._retried && !isAuthCall) {
    original._retried = true
    refreshing ??= tryRefresh().finally(() => (refreshing = null))
    if (await refreshing) return http(original)
    setTokens(null)
    onLogout?.()
  }
  throw error
})

/** Stable error code from the API ({ detail, code }), for i18n lookup. */
export function errorCode(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as Partial<ApiError> | undefined
    if (data?.code) return data.code
    if (!error.response) return 'NETWORK_ERROR'
  }
  return 'UNKNOWN_ERROR'
}

export function errorDetail(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as Partial<ApiError> | undefined)?.detail
    if (typeof detail === 'string') return detail
  }
  return ''
}
