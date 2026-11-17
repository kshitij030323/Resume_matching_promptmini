import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, errorMessage, isAbort, normaliseBase, setApiBase } from './api'
import { readStored, writeStored } from './lib/storage'
import type { Health, MethodInfo } from './types'

export type ThemePref = 'system' | 'light' | 'dark'

const KEY_BASE = 'rjm.apiBase'
const KEY_THEME = 'rjm.theme'
const KEY_LLM = 'rjm.useLlm'

export type HealthState =
  | { status: 'loading'; data: Health | null; error: null }
  | { status: 'ok'; data: Health; error: null }
  | { status: 'error'; data: null; error: string }

interface SettingsValue {
  apiBase: string
  setApiBaseUrl: (url: string) => void
  theme: ThemePref
  setTheme: (t: ThemePref) => void
  useLlm: boolean
  setUseLlm: (v: boolean) => void
  health: HealthState
  refreshHealth: () => void
  /** Method catalogue from GET /api/methods, shared by every screen. */
  methods: MethodInfo[] | null
  methodsError: string | null
  reloadMethods: () => void
}

const SettingsContext = createContext<SettingsValue | null>(null)

// Apply the stored base before the first request goes out.
const initialBase = normaliseBase(readStored(KEY_BASE) ?? '')
setApiBase(initialBase)

function applyTheme(t: ThemePref) {
  const root = document.documentElement
  if (t === 'system') delete root.dataset.theme
  else root.dataset.theme = t
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [apiBase, setBase] = useState(initialBase)
  const [theme, setThemeState] = useState<ThemePref>(() => {
    const t = readStored(KEY_THEME)
    return t === 'light' || t === 'dark' ? t : 'system'
  })
  const [useLlm, setUseLlmState] = useState(() => readStored(KEY_LLM) !== 'false')
  const [health, setHealth] = useState<HealthState>({ status: 'loading', data: null, error: null })
  const [healthTick, setHealthTick] = useState(0)
  const [methods, setMethods] = useState<MethodInfo[] | null>(null)
  const [methodsError, setMethodsError] = useState<string | null>(null)
  const [methodsTick, setMethodsTick] = useState(0)
  const lastHealth = useRef<Health | null>(null)

  useEffect(() => applyTheme(theme), [theme])

  useEffect(() => {
    const ctrl = new AbortController()
    setHealth({ status: 'loading', data: lastHealth.current, error: null })
    api
      .health({ signal: ctrl.signal })
      .then((data) => {
        lastHealth.current = data
        setHealth({ status: 'ok', data, error: null })
      })
      .catch((err) => {
        if (isAbort(err)) return
        lastHealth.current = null
        setHealth({ status: 'error', data: null, error: errorMessage(err) })
      })
    return () => ctrl.abort()
  }, [apiBase, healthTick])

  useEffect(() => {
    const ctrl = new AbortController()
    setMethodsError(null)
    api
      .methods({ signal: ctrl.signal })
      .then(setMethods)
      .catch((err) => {
        if (isAbort(err)) return
        setMethodsError(errorMessage(err))
      })
    return () => ctrl.abort()
  }, [apiBase, methodsTick])

  const setApiBaseUrl = useCallback((url: string) => {
    const clean = normaliseBase(url)
    writeStored(KEY_BASE, clean || null)
    setApiBase(clean)
    setBase(clean)
  }, [])

  const setTheme = useCallback((t: ThemePref) => {
    writeStored(KEY_THEME, t === 'system' ? null : t)
    setThemeState(t)
  }, [])

  const setUseLlm = useCallback((v: boolean) => {
    writeStored(KEY_LLM, v ? null : 'false')
    setUseLlmState(v)
  }, [])

  const value = useMemo<SettingsValue>(
    () => ({
      apiBase,
      setApiBaseUrl,
      theme,
      setTheme,
      useLlm,
      setUseLlm,
      health,
      refreshHealth: () => setHealthTick((n) => n + 1),
      methods,
      methodsError,
      reloadMethods: () => setMethodsTick((n) => n + 1),
    }),
    [apiBase, setApiBaseUrl, theme, setTheme, useLlm, setUseLlm, health, methods, methodsError],
  )

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}

export function useSettings() {
  const ctx = useContext(SettingsContext)
  if (!ctx) throw new Error('useSettings must be used inside <SettingsProvider>')
  return ctx
}
