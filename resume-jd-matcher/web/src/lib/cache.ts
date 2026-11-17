import { api } from '../api'
import type { ShortlistResponse, SkillGapReport } from '../types'

// The skill-gap chain and shortlist calls can take minutes with an LLM. These
// helpers keep finished results in memory for the session and de-duplicate
// in-flight requests, so navigating away and back (or React StrictMode's
// double effects) never starts the same chain twice. Cleared on page reload.

export interface Task<T> {
  promise: Promise<T>
  startedAt: number
}

const reports = new Map<string, SkillGapReport>()
const shortlists = new Map<string, ShortlistResponse>()
const inflight = new Map<string, Task<unknown>>()

const reportKey = (jobId: string, resumeId: string) => `${jobId}::${resumeId}`

export function getCachedReport(jobId: string, resumeId: string) {
  return reports.get(reportKey(jobId, resumeId)) ?? null
}

function track<T>(key: string, run: () => Promise<T>): Task<T> {
  const existing = inflight.get(key) as Task<T> | undefined
  if (existing) return existing
  const task: Task<T> = {
    startedAt: Date.now(),
    promise: run().finally(() => inflight.delete(key)),
  }
  inflight.set(key, task as Task<unknown>)
  return task
}

/** `attempt` > 0 forces a fresh run even when a cached report exists. */
export function startReport(jobId: string, resumeId: string, useLlm: boolean, attempt: number): Task<SkillGapReport> {
  const cached = getCachedReport(jobId, resumeId)
  if (cached && attempt === 0) return { promise: Promise.resolve(cached), startedAt: Date.now() }
  return track(`report::${jobId}::${resumeId}::${useLlm}::${attempt}`, () =>
    api.skillgap({ job_id: jobId, resume_id: resumeId, use_llm: useLlm }).then((r) => {
      reports.set(reportKey(r.job_id, r.resume_id), r)
      return r
    }),
  )
}

const shortlistKey = (jobId: string, method: string, n: number, llm: boolean) => `${jobId}::${method}::${n}::${llm}`

export function startShortlist(
  jobId: string,
  method: string,
  n: number,
  useLlm: boolean,
  attempt: number,
): Task<ShortlistResponse> {
  const key = shortlistKey(jobId, method, n, useLlm)
  const cached = shortlists.get(key)
  if (cached && attempt === 0) return { promise: Promise.resolve(cached), startedAt: Date.now() }
  return track(`shortlist::${key}::${attempt}`, () =>
    api.shortlist({ job_id: jobId, method, top_n: n, use_llm: useLlm }).then((res) => {
      shortlists.set(key, res)
      res.reports.forEach((r) => reports.set(reportKey(r.job_id, r.resume_id), r))
      return res
    }),
  )
}

export function hasCachedShortlist(jobId: string, method: string, n: number, useLlm: boolean) {
  return shortlists.has(shortlistKey(jobId, method, n, useLlm))
}
