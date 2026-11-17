import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Briefcase, Columns3, FileText, MapPin, PenLine, Sparkles, Users } from 'lucide-react'
import { api } from '../api'
import { JobView } from '../components/DocViews'
import { MethodPicker, defaultMethod } from '../components/MethodPicker'
import {
  ButtonLink,
  Chip,
  Collapsible,
  EmptyState,
  ErrorState,
  GradeBadge,
  IconText,
  ModeBadge,
  PageHeader,
  Segmented,
  Skeleton,
  SkeletonRows,
  SkillName,
  Spinner,
  altTitle,
  cx,
} from '../components/ui'
import { ScoreBar } from '../components/viz'
import { useAsync, useDocumentTitle } from '../hooks'
import { FAMILY_LABEL, fmtMs, fmtPct, fmtScore } from '../lib/format'
import { useSettings } from '../settings'
import type { MethodFamily, RankResult, Representation } from '../types'

const TOP_OPTIONS = [
  { value: 10, label: 'Top 10' },
  { value: 20, label: 'Top 20' },
  { value: 100, label: 'All' },
]

function scoreScale(results: RankResult[]) {
  if (!results.length) return 1
  const scores = results.map((r) => r.score)
  const max = Math.max(...scores)
  const min = Math.min(...scores)
  return max <= 1 && min >= 0 ? 1 : max || 1
}

function RankRow({ r, jobId, family, scale }: { r: RankResult; jobId: string; family: MethodFamily; scale: number }) {
  const s = r.skills
  return (
    <li>
      <Link className="rank-row" to={`/candidates/${encodeURIComponent(r.resume_id)}?job=${encodeURIComponent(jobId)}`}>
        <span className="rank-row__rank">{r.rank}</span>
        <div className="rank-row__main">
          <p className="rank-row__name">
            {r.name}
            <span className="id-tag">{r.resume_id}</span>
          </p>
          {r.headline && <p className="rank-row__headline">{r.headline}</p>}
          {(s.matched_required.length > 0 || s.missing_required.length > 0 || s.matched_preferred.length > 0) && (
            <div className="chips chips--tight">
              {s.matched_required.map((k) => (
                <Chip key={`m-${k}`} variant="match" title={`Required skill, matched${altTitle(k) ? `. ${altTitle(k)}` : ''}`}>
                  <SkillName name={k} />
                </Chip>
              ))}
              {s.matched_preferred.map((k) => (
                <Chip key={`p-${k}`} variant="match-soft" title={`Preferred skill, matched${altTitle(k) ? `. ${altTitle(k)}` : ''}`}>
                  <SkillName name={k} />
                </Chip>
              ))}
              {s.missing_required.map((k) => (
                <Chip key={`x-${k}`} variant="missing" title={`Required skill, missing${altTitle(k) ? `. ${altTitle(k)}` : ''}`}>
                  <SkillName name={k} />
                </Chip>
              ))}
            </div>
          )}
        </div>
        <div className="rank-row__score">
          <div className="rank-row__scoreline">
            <span className="num">{fmtScore(r.score, 3)}</span>
            <span className="muted small">score</span>
          </div>
          <ScoreBar value={r.score} max={scale} family={family} label={`Score ${fmtScore(r.score, 3)}`} />
          <span className="muted small">
            Similarity {fmtScore(r.similarity)}, coverage {fmtPct(s.coverage)}
          </span>
        </div>
        <div className="rank-row__grade">
          <GradeBadge grade={r.human_grade} />
        </div>
      </Link>
    </li>
  )
}

function NdcgCallout({ value, jobId }: { value: number | null; jobId: string }) {
  if (value === null || value === undefined) {
    return (
      <div className="ndcg ndcg--empty">
        <p className="ndcg__label">NDCG@5</p>
        <p className="small">
          No human grades for this job yet.{' '}
          <Link to={`/evaluate/annotate?job=${encodeURIComponent(jobId)}`}>Grade candidates</Link> to measure ranking quality.
        </p>
      </div>
    )
  }
  return (
    <div className="ndcg">
      <div>
        <p className="ndcg__label">NDCG@5</p>
        <p className="ndcg__value">{fmtScore(value)}</p>
      </div>
      <div className="ndcg__explain">
        <div className="meter" aria-hidden>
          <span style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
        </div>
        <p className="small muted">How closely this top 5 agrees with the human grades. 1.00 means the same order a recruiter would choose.</p>
      </div>
    </div>
  )
}

export default function JobDetailPage() {
  const { jobId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const { methods, methodsError, reloadMethods } = useSettings()

  const job = useAsync((signal) => api.job(jobId, { signal }), [jobId])
  useDocumentTitle(job.data?.extracted.title ?? jobId)

  const method = params.get('method') ?? defaultMethod(methods)
  const rep = (params.get('rep') === 'raw' ? 'raw' : 'structured') as Representation
  const top = Number(params.get('top')) || 10
  const methodInfo = methods?.find((m) => m.key === method) ?? null
  const family: MethodFamily = methodInfo?.family ?? 'contextual'

  const rank = useAsync(
    (signal) => api.rank({ job_id: jobId, method: method!, representation: rep, top_k: top }, { signal }),
    [jobId, method, rep, top],
    { enabled: !!method, keepPrevious: true },
  )

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next, { replace: true })
  }

  const jd = job.data?.extracted
  const scale = rank.data ? scoreScale(rank.data.results) : 1
  const stale = rank.loading && !!rank.data

  return (
    <>
      <PageHeader
        back={{ to: '/jobs', label: 'All jobs' }}
        title={jd ? jd.title : job.error ? jobId : <Skeleton width={320} height={34} />}
        lede={
          jd ? (
            <span className="meta-row">
              {jd.company && <IconText icon={Briefcase}>{jd.company}</IconText>}
              {jd.location && <IconText icon={MapPin}>{jd.location}</IconText>}
              <span className="id-tag">{jobId}</span>
            </span>
          ) : undefined
        }
        actions={
          <>
            <ButtonLink to={`/jobs/${encodeURIComponent(jobId)}/compare?rep=${rep}`} icon={Columns3}>
              Compare methods
            </ButtonLink>
            <ButtonLink
              to={`/jobs/${encodeURIComponent(jobId)}/shortlist?method=${encodeURIComponent(method ?? '')}`}
              variant="primary"
              icon={Sparkles}
            >
              Generate shortlist reports
            </ButtonLink>
          </>
        }
      />

      <div className="split">
        <aside className="split__aside">
          <div className="panel panel--pad sticky-panel">
            <h2 className="panel__title">Job description</h2>
            {job.error ? (
              <ErrorState compact title="Couldn't load the job" message={job.error} onRetry={job.reload} />
            ) : !jd ? (
              <div className="stack-sm">
                <Skeleton height={12} />
                <Skeleton height={12} width="90%" />
                <Skeleton height={12} width="70%" />
                <Skeleton height={80} />
              </div>
            ) : (
              <>
                <JobView job={jd} />
                <div className="extraction-meta">
                  <span className="muted small">Extracted by</span>
                  <ModeBadge mode={job.data!.meta.method} model={job.data!.meta.model} />
                  <span className="muted small">in {fmtMs(job.data!.meta.latency_ms)}</span>
                </div>
                {job.data!.raw_text && (
                  <Collapsible summary="Original text">
                    <pre className="raw-text">{job.data!.raw_text}</pre>
                  </Collapsible>
                )}
              </>
            )}
          </div>
        </aside>

        <section className="split__main" aria-labelledby="ranking-title">
          <div className="panel">
            <div className="panel__section">
              <div className="row-between">
                <h2 className="panel__title" id="ranking-title">
                  Ranked candidates
                </h2>
                {rank.loading && <Spinner label="Ranking" />}
              </div>
              {methodsError && !methods ? (
                <ErrorState compact title="Couldn't load ranking methods" message={methodsError} onRetry={reloadMethods} />
              ) : !methods ? (
                <div className="chips">
                  {[90, 110, 80, 96, 70].map((w, i) => (
                    <Skeleton key={i} width={w} height={32} radius={999} />
                  ))}
                </div>
              ) : (
                <MethodPicker methods={methods} value={method} onChange={(k) => update('method', k)} />
              )}
              {methodInfo && (
                <p className="method-desc">
                  <span className={cx('swatch', `fam-bg--${methodInfo.family}`)} aria-hidden />
                  <span>
                    <strong>{methodInfo.label}</strong> ({FAMILY_LABEL[methodInfo.family].toLowerCase()}). {methodInfo.description}
                  </span>
                </p>
              )}
              <div className="controls-row">
                <Segmented<Representation>
                  ariaLabel="Document representation"
                  value={rep}
                  onChange={(v) => update('rep', v)}
                  options={[
                    { value: 'structured', label: 'Structured JSON', title: 'Embed the extracted schema fields' },
                    { value: 'raw', label: 'Raw text', title: 'Embed the original document text' },
                  ]}
                />
                <Segmented<number> ariaLabel="How many candidates" value={top} onChange={(v) => update('top', String(v))} options={TOP_OPTIONS} />
              </div>
            </div>

            {rank.data && (
              <div className="panel__section panel__section--tint">
                <NdcgCallout value={rank.data.ndcg_at_5} jobId={jobId} />
              </div>
            )}

            <div className="panel__section panel__section--flush">
              {rank.error ? (
                <div className="pad">
                  <ErrorState title="Ranking failed" message={rank.error} onRetry={rank.reload} />
                </div>
              ) : !rank.data ? (
                <SkeletonRows rows={6} height={84} />
              ) : rank.data.results.length === 0 ? (
                <div className="pad">
                  <EmptyState icon={Users} title="No candidates to rank">
                    Add resumes on the Extract page with <em>Save to corpus</em> turned on.
                  </EmptyState>
                </div>
              ) : (
                <>
                  <div className="legend-row" aria-label="Legend">
                    <span className="legend-item">
                      <Chip variant="match">Matched</Chip> required skill
                    </span>
                    <span className="legend-item">
                      <Chip variant="match-soft">Matched</Chip> preferred
                    </span>
                    <span className="legend-item">
                      <Chip variant="missing">Missing</Chip> required
                    </span>
                    <span className="legend-item">
                      <GradeBadge grade={3} size="sm" /> human grade (0–3)
                    </span>
                  </div>
                  <ol className={cx('rank-list', stale && 'is-stale')} aria-busy={stale}>
                    {rank.data.results.map((r) => (
                      <RankRow key={r.resume_id} r={r} jobId={jobId} family={family} scale={scale} />
                    ))}
                  </ol>
                </>
              )}
            </div>
          </div>
          <p className="footnote">
            <FileText size={14} aria-hidden /> Tap a candidate to see their extracted resume and open a skill-gap report for this job.{' '}
            <Link to={`/evaluate/annotate?job=${encodeURIComponent(jobId)}`}>
              <PenLine size={13} aria-hidden /> Edit human grades
            </Link>
          </p>
        </section>
      </div>
    </>
  )
}
