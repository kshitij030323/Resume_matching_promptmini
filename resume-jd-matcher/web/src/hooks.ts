import { useCallback, useEffect, useLayoutEffect, useRef, useState, type DependencyList } from 'react'
import { errorMessage, isAbort } from './api'
import { useSettings } from './settings'

export interface AsyncState<T> {
  data: T | null
  error: string | null
  /** True while a request is in flight (also during reloads, when stale data is kept). */
  loading: boolean
  reload: () => void
  setData: (updater: T | null | ((prev: T | null) => T | null)) => void
}

/**
 * Run an abortable request whenever `deps` (or the API base URL) change.
 * Keeps the previous data while reloading so lists don't flash empty.
 */
export function useAsync<T>(
  fn: (signal: AbortSignal) => Promise<T>,
  deps: DependencyList,
  options: {
    enabled?: boolean
    /**
     * Keep showing the previous result while new `deps` load (filters, method
     * switches). Off by default so a different entity never flashes old data.
     * Manual reloads always keep the current data.
     */
    keepPrevious?: boolean
  } = {},
): AsyncState<T> {
  const { apiBase } = useSettings()
  const enabled = options.enabled ?? true
  const keepPrevious = options.keepPrevious ?? false
  const depsKey = JSON.stringify(deps)
  const lastKey = useRef(depsKey)
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [tick, setTick] = useState(0)
  const fnRef = useRef(fn)
  // Keep the latest closure without re-running the request on every render.
  useLayoutEffect(() => {
    fnRef.current = fn
  })

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    const ctrl = new AbortController()
    if (lastKey.current !== depsKey) {
      lastKey.current = depsKey
      if (!keepPrevious) setData(null)
    }
    setLoading(true)
    setError(null)
    fnRef
      .current(ctrl.signal)
      .then((result) => {
        if (ctrl.signal.aborted) return
        setData(result)
        setLoading(false)
      })
      .catch((err) => {
        if (ctrl.signal.aborted || isAbort(err)) return
        setError(errorMessage(err))
        setLoading(false)
      })
    return () => ctrl.abort()
  }, [...deps, apiBase, tick, enabled])

  const reload = useCallback(() => setTick((n) => n + 1), [])
  return { data, error, loading, reload, setData }
}

/**
 * Seconds elapsed while `running`, counted from `since` (a Date.now() value)
 * when given, otherwise from the moment `running` became true.
 */
export function useElapsed(running: boolean, since?: number | null) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!running) return
    const start = since ?? Date.now()
    const tickFn = () => setSeconds(Math.max(0, Math.floor((Date.now() - start) / 1000)))
    tickFn()
    const id = window.setInterval(tickFn, 500)
    return () => window.clearInterval(id)
  }, [running, since])
  return seconds
}

export function useDocumentTitle(title: string | null | undefined) {
  useEffect(() => {
    document.title = title ? `${title} | Resume–JD Matcher` : 'Resume–JD Matcher'
  }, [title])
}
