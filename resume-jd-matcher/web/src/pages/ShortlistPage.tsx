import { useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { RefreshCw, Users } from 'lucide-react'
import { api } from '../api'
import { defaultMethod } from '../components/MethodPicker'
import { Button, EmptyState, ErrorState, FamilySwatch, ModeBadge, PageHeader, Segmented, Switch, VerdictPill } from '../components/ui'
import { ChainProgress, ScoreRing } from '../components/viz'
import { useAsync, useDocumentTitle, useElapsed } from '../hooks'
import { startShortlist } from '../lib/cache'
import { fmtMs, plural } from '../lib/format'
import { useSettings } from '../settings'
import type { SkillGapReport } from '../types'

const N_OPTIONS = [3, 5, 8, 10].map((n) => ({ value: n, label: `Top ${n}` }))

function ReportCard({ r }: { r: SkillGapReport }) {
  const critical = r.gaps.filter((g) => g.severity === 'critical').length
  const mode = r.chain_trace[0]?.mode
  return (
    <Link className="report-card" to={`/report/${encodeURIComponent(r.job_id)}/${encodeURIComponent(r.resume_id)}`}>
      <ScoreRing score={r.fit_score} verdict={r.verdict} size={84} />
      <div className="report-card__body">
        <div className="report-card__top">
          <p className="report-card__name">{r.candidate_name}</p>
          <VerdictPill verdict={r.verdict} size="sm" />
        </div>
        <p className="report-card__headline">{r.headline}</p>
        <p className="muted small">
          {plural(r.strengths.length, 'strength')}, {plural(r.gaps.length, 'gap')}
          {critical > 0 && <strong className="text-critical">, {critical} critical</strong>}
          {mode && (
            <>
              {' '}
              <ModeBadge mode={mode} model={r.chain_trace[0]?.model} />
            </>
          )}
        </p>
      </div>
    </Link>
  )
}

export default function ShortlistPage() {
  const { jobId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const { methods, useLlm, setUseLlm, health } = useSettings()
  const method = params.get('method') || defaultMethod(methods) || 'hybrid'
  const n = Number(params.get('n')) || 5
  const methodInfo = methods?.find((m) => m.key === method)
  const [attempt, setAttempt] = useState(0)
  const [startedAt, setStartedAt] = useState<number | null>(null)

  const job = useAsync((signal) => api.job(jobId, { signal }), [jobId])
  useDocumentTitle(job.data ? `Shortlist: ${job.data.extracted.title}` : 'Shortlist')

  const run = useAsync(
    () => {
      const task = startShortlist(jobId, method, n, useLlm, attempt)
      setStartedAt(task.startedAt)
      return task.promise
    },
    [jobId, method, n, useLlm, attempt],
  )
  const seconds = useElapsed(run.loading, startedAt)

  const reports = useMemo(() => [...(run.data?.reports ?? [])].sort((a, b) => b.fit_score - a.fit_score), [run.data])
  const totalMs = useMemo(
    () => reports.reduce((s, r) => s + r.chain_trace.reduce((t, c) => t + (c.latency_ms || 0), 0), 0),
    [reports],
  )
  const llmAvailable = health.status === 'ok' ? health.data.llm.enabled : null
  const llmLabel = health.status === 'ok' && health.data.llm.enabled ? health.data.llm.provider_label : 'LLM'

  const setN = (v: number) => {
    const next = new URLSearchParams(params)
    next.set('n', String(v))
    setParams(next, { replace: true })
  }

  return (
    <>
      <PageHeader
        back={{ to: `/jobs/${encodeURIComponent(jobId)}?method=${encodeURIComponent(method)}`, label: 'Back to ranking' }}
        title="Shortlist reports"
        lede={
          <>
            Skill-gap reports for the top candidates for <strong>{job.data?.extracted.title ?? jobId}</strong>, ranked by{' '}
            <strong>{methodInfo?.label ?? method}</strong>. Each report runs the four-step prompt chain.
          </>
        }
        actions={
          <Button icon={RefreshCw} onClick={() => setAttempt((a) => a + 1)} disabled={run.loading}>
            Regenerate
          </Button>
        }
      />

      <div className="toolbar">
        <Segmented<number> ariaLabel="Shortlist size" value={n} onChange={setN} options={N_OPTIONS} />
        {methodInfo && (
          <span className="family-tag" title={methodInfo.description}>
            <FamilySwatch family={methodInfo.family} />
            Ranked by {methodInfo.label}
          </span>
        )}
        <Switch
          checked={useLlm && llmAvailable !== false}
          onChange={setUseLlm}
          disabled={llmAvailable === false || run.loading}
          label={`Use ${llmLabel}`}
          description={llmAvailable === false ? 'No LLM key is configured (add one in Settings); the offline chain runs instead.' : 'Off runs the faster offline chain.'}
        />
      </div>

      {run.loading ? (
        <ChainProgress
          title={`Generating ${plural(n, 'report')}`}
          seconds={seconds}
          detail="The server runs the chain for each shortlisted candidate and replies once all reports are ready. You can leave this page; the run keeps going and the results will be here when you come back."
        />
      ) : run.error ? (
        <ErrorState title="Shortlist generation failed" message={run.error} onRetry={() => setAttempt((a) => a + 1)} />
      ) : reports.length === 0 ? (
        <EmptyState icon={Users} title="No reports came back">
          The ranking returned no candidates for this job. Add resumes on the Extract page first.
        </EmptyState>
      ) : (
        <>
          <p className="muted small summary-line">
            {plural(reports.length, 'report')}, sorted by fit score. Chain time across all steps: {fmtMs(totalMs)}.
          </p>
          <div className="report-grid">
            {reports.map((r) => (
              <ReportCard key={r.resume_id} r={r} />
            ))}
          </div>
        </>
      )}
    </>
  )
}
