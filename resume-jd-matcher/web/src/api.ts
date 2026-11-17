import type {
  DocKind,
  EvaluationResponse,
  ExtractRequest,
  ExtractResponse,
  Grade,
  Health,
  LlmSettingsUpdate,
  LlmStatus,
  JobDetail,
  JobSummary,
  LabelsResponse,
  LabelsUpdateResponse,
  MethodInfo,
  RankRequest,
  RankResponse,
  ResumeDetail,
  ResumeSummary,
  ShortlistRequest,
  ShortlistResponse,
  SkillGapReport,
  SkillGapRequest,
} from './types'

// ---------------------------------------------------------------------------
// Base URL. Empty string = same origin, so requests go to relative `/api/...`
// paths (proxied to the backend by Vite in dev, served by FastAPI in production).
// The Settings screen can override it with a full address.
// ---------------------------------------------------------------------------
let baseUrl = ''

export function setApiBase(url: string) {
  baseUrl = normaliseBase(url)
}

export function getApiBase() {
  return baseUrl
}

export function normaliseBase(url: string) {
  return url.trim().replace(/\/+$/, '').replace(/\/api$/, '')
}

export function describeBase(base = baseUrl) {
  return base || `${window.location.origin}/api`
}

export type ApiErrorKind = 'network' | 'timeout' | 'http' | 'parse' | 'aborted'

export class ApiError extends Error {
  kind: ApiErrorKind
  status?: number
  constructor(message: string, kind: ApiErrorKind, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
  }
}

export function isAbort(err: unknown) {
  return err instanceof ApiError && err.kind === 'aborted'
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return String(err)
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  body?: unknown
  form?: FormData
  timeoutMs?: number
  signal?: AbortSignal
  /** Use this base instead of the saved one (Settings' connection test). */
  base?: string
}

function detailToMessage(detail: unknown): string | null {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{ loc: [...], msg: '...' }]
    const parts = detail
      .map((d) => {
        if (d && typeof d === 'object' && 'msg' in d) {
          const loc = Array.isArray((d as { loc?: unknown[] }).loc)
            ? (d as { loc: unknown[] }).loc.filter((p) => p !== 'body').join('.')
            : ''
          return loc ? `${loc}: ${(d as { msg: string }).msg}` : (d as { msg: string }).msg
        }
        return null
      })
      .filter(Boolean)
    return parts.length ? parts.join('; ') : null
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return null
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, form, timeoutMs = 20_000, signal } = opts
  const base = opts.base ?? baseUrl
  const controller = new AbortController()
  let timedOut = false
  const timer = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const onCallerAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onCallerAbort, { once: true })
  }

  const url = `${base}${path}`
  let res: Response
  try {
    res = await fetch(url, {
      method,
      signal: controller.signal,
      headers: form ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
    })
  } catch {
    if (controller.signal.aborted) {
      if (timedOut) {
        throw new ApiError(
          `The server took longer than ${Math.round(timeoutMs / 1000)} s to answer ${path}. It may still be loading models; try again in a moment.`,
          'timeout',
        )
      }
      throw new ApiError('Request cancelled.', 'aborted')
    }
    throw new ApiError(
      `Can't reach the API at ${describeBase(base)}. Check that the backend is running, or set the API address in Settings.`,
      'network',
    )
  } finally {
    window.clearTimeout(timer)
    signal?.removeEventListener('abort', onCallerAbort)
  }

  const contentType = res.headers.get('content-type') ?? ''
  const isJson = contentType.includes('application/json')
  let payload: unknown = null
  try {
    payload = isJson ? await res.json() : await res.text()
  } catch {
    payload = null
  }

  if (!res.ok) {
    if (isJson && payload && typeof payload === 'object' && 'detail' in payload) {
      const msg = detailToMessage((payload as { detail: unknown }).detail)
      if (msg) throw new ApiError(msg, 'http', res.status)
    }
    const text = typeof payload === 'string' ? payload.trim() : ''
    if (res.status >= 500 && !isJson && (!text || res.status === 502 || res.status === 503 || res.status === 504)) {
      // An empty 5xx is what the dev proxy sends when it can't connect to the backend.
      throw new ApiError(
        `The API at ${describeBase(base)} isn't responding (HTTP ${res.status}). Check that the backend is running.`,
        'network',
        res.status,
      )
    }
    if (res.status >= 500) {
      const snippet = text && !text.startsWith('<') ? `: ${text.slice(0, 160)}` : ''
      throw new ApiError(`The server hit an error on ${path} (HTTP ${res.status})${snippet}. Try again in a moment.`, 'http', res.status)
    }
    if (res.status === 404) {
      throw new ApiError(`Not found: ${path}`, 'http', 404)
    }
    throw new ApiError(`Request to ${path} failed with HTTP ${res.status}.`, 'http', res.status)
  }

  if (!isJson) {
    const looksHtml = typeof payload === 'string' && payload.trimStart().startsWith('<')
    throw new ApiError(
      looksHtml
        ? `Got a web page instead of data from ${path}. The API address in Settings probably points at the wrong server.`
        : `Unexpected response from ${path} (not JSON).`,
      'parse',
      res.status,
    )
  }
  return payload as T
}

// ---------------------------------------------------------------------------
// Endpoints (see API.md)
// ---------------------------------------------------------------------------
type Sig = { signal?: AbortSignal }

export const api = {
  health: ({ signal, base }: Sig & { base?: string } = {}) =>
    request<Health>('/api/health', { signal, base, timeoutMs: 8_000 }),

  llm: ({ signal }: Sig = {}) => request<LlmStatus>('/api/llm', { signal, timeoutMs: 30_000 }),
  saveLlm: (body: LlmSettingsUpdate) => request<LlmStatus>('/api/llm', { method: 'PUT', body, timeoutMs: 30_000 }),
  removeGeminiKey: () => request<LlmStatus>('/api/llm/gemini', { method: 'DELETE', timeoutMs: 30_000 }),

  jobs: ({ signal }: Sig = {}) => request<JobSummary[]>('/api/jobs', { signal }),
  job: (id: string, { signal }: Sig = {}) =>
    request<JobDetail>(`/api/jobs/${encodeURIComponent(id)}`, { signal }),

  resumes: ({ signal }: Sig = {}) => request<ResumeSummary[]>('/api/resumes', { signal }),
  resume: (id: string, { signal }: Sig = {}) =>
    request<ResumeDetail>(`/api/resumes/${encodeURIComponent(id)}`, { signal }),

  extract: (body: ExtractRequest, { signal }: Sig = {}) =>
    request<ExtractResponse>('/api/extract', { method: 'POST', body, signal, timeoutMs: 120_000 }),

  extractFile: (file: File, kind: DocKind, save: boolean, { signal }: Sig = {}) => {
    const form = new FormData()
    form.append('file', file, file.name)
    form.append('kind', kind)
    form.append('save', save ? 'true' : 'false')
    return request<ExtractResponse>('/api/extract/file', { method: 'POST', form, signal, timeoutMs: 120_000 })
  },

  methods: ({ signal }: Sig = {}) => request<MethodInfo[]>('/api/methods', { signal }),

  rank: (body: RankRequest, { signal }: Sig = {}) =>
    request<RankResponse>('/api/rank', { method: 'POST', body, signal, timeoutMs: 90_000 }),

  evaluation: (k: number, { signal }: Sig = {}) =>
    request<EvaluationResponse>(`/api/evaluation?k=${k}`, { signal, timeoutMs: 180_000 }),

  labels: ({ signal }: Sig = {}) => request<LabelsResponse>('/api/labels', { signal }),
  saveLabels: (jobId: string, grades: Record<string, Grade>) =>
    request<LabelsUpdateResponse>(`/api/labels/${encodeURIComponent(jobId)}`, {
      method: 'PUT',
      body: { grades },
      timeoutMs: 60_000,
    }),

  skillgap: (body: SkillGapRequest, { signal }: Sig = {}) =>
    request<SkillGapReport>('/api/skillgap', { method: 'POST', body, signal, timeoutMs: 240_000 }),

  shortlist: (body: ShortlistRequest, { signal }: Sig = {}) =>
    request<ShortlistResponse>('/api/shortlist', { method: 'POST', body, signal, timeoutMs: 900_000 }),
}
