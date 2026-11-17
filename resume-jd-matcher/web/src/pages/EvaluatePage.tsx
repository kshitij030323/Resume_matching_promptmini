import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ChartBar, PenLine, RefreshCw, Trophy } from 'lucide-react'
import { api } from '../api'
import {
  Button,
  ButtonLink,
  EmptyState,
  ErrorState,
  FamilySwatch,
  FamilyTag,
  PageHeader,
  Segmented,
  Skeleton,
  Spinner,
  Tag,
  cx,
} from '../components/ui'
import { useAsync, useDocumentTitle } from '../hooks'
import { FAMILY_BLURB, FAMILY_LABEL, FAMILY_ORDER, fmtScore, fmtSigned } from '../lib/format'
import type { EvaluationMethodResult, EvaluationResponse, MethodFamily, Representation, StaticVsContextual } from '../types'

const TICKS = [0, 0.25, 0.5, 0.75, 1]

function rowKey(r: EvaluationMethodResult) {
  return `${r.method}::${r.representation}`
}

function Leaderboard({ rows, k, showRep }: { rows: EvaluationMethodResult[]; k: number; showRep: boolean }) {
  const families = FAMILY_ORDER.filter((f) => rows.some((r) => r.family === f))
  return (
    <figure className="chart" aria-labelledby="lb-title">
      <figcaption className="chart__head">
        <div>
          <h2 className="section__title" id="lb-title">
            Mean NDCG@{k} by method
          </h2>
          <p className="muted small">Averaged over every graded job. Higher means the ranking agrees more with the human grades.</p>
        </div>
        <ul className="chart__legend" aria-label="Method families">
          {families.map((f) => (
            <li key={f} title={FAMILY_BLURB[f]}>
              <FamilySwatch family={f} />
              {FAMILY_LABEL[f]}
            </li>
          ))}
        </ul>
      </figcaption>
      <div className="bars" role="list">
        <div className="bars__grid" aria-hidden>
          {TICKS.map((t) => (
            <span key={t} style={{ left: `${t * 100}%` }} />
          ))}
        </div>
        {rows.map((r, i) => (
          <div className="bar-row" role="listitem" key={rowKey(r)} tabIndex={0} aria-label={`${r.label}: NDCG@${k} ${fmtScore(r.mean_ndcg, 3)}`}>
            <div className="bar-row__label">
              <span className="bar-row__rank num">{i + 1}</span>
              <span className="bar-row__name" title={r.label}>
                {r.label}
              </span>
              {showRep && <Tag>{r.representation === 'raw' ? 'Raw' : 'Structured'}</Tag>}
            </div>
            <div className="bar-row__track" style={{ ['--w' as string]: `${Math.max(0, Math.min(1, r.mean_ndcg)) * 100}%` }}>
              <span className={cx('bar-row__fill', `fam-bg--${r.family}`)} />
              <span className="bar-row__value num">{fmtScore(r.mean_ndcg, 3)}</span>
            </div>
            <div className="tooltip" role="tooltip">
              <p className="tooltip__title">
                <FamilySwatch family={r.family} /> {r.label}
              </p>
              <dl>
                <dt>NDCG@{k}</dt>
                <dd className="num">{fmtScore(r.mean_ndcg, 3)}</dd>
                {r.mean_ndcg_10 != null && (
                  <>
                    <dt>NDCG@10</dt>
                    <dd className="num">{fmtScore(r.mean_ndcg_10, 3)}</dd>
                  </>
                )}
                {r.mean_precision != null && (
                  <>
                    <dt>Precision@{k}</dt>
                    <dd className="num">{fmtScore(r.mean_precision, 3)}</dd>
                  </>
                )}
                <dt>Family</dt>
                <dd>{FAMILY_LABEL[r.family]}</dd>
                <dt>Input</dt>
                <dd>{r.representation === 'raw' ? 'Raw text' : 'Structured JSON'}</dd>
              </dl>
            </div>
          </div>
        ))}
        <div className="bars__axis" aria-hidden>
          <span />
          <div className="bars__ticks">
            {TICKS.map((t) => (
              <span key={t} style={{ left: `${t * 100}%` }}>
                {t === 0 ? '0' : t.toFixed(2)}
              </span>
            ))}
          </div>
        </div>
      </div>
    </figure>
  )
}

function Dumbbell({ s, k, labelOf }: { s: StaticVsContextual; k: number; labelOf: (key?: string) => string | null }) {
  const up = s.delta >= 0
  // Dots don't need a zero baseline, so zoom the axis to the data and label both ends.
  const minV = Math.min(s.static_best, s.contextual_best)
  const domainLo = Math.max(0, Math.floor((minV - 0.05) * 20) / 20)
  const domainHi = 1
  const pos = (v: number) => `${((Math.max(domainLo, Math.min(domainHi, v)) - domainLo) / (domainHi - domainLo)) * 100}%`
  const lo = Math.min(s.static_best, s.contextual_best)
  const hi = Math.max(s.static_best, s.contextual_best)
  const staticName = labelOf(s.static_method)
  const contextualName = labelOf(s.contextual_method)
  const nJobs = (s.jobs_contextual_wins ?? 0) + (s.jobs_ties ?? 0)
  return (
    <div className="delta-card">
      <p className="delta-card__label">Static vs contextual embeddings</p>
      <p className="delta-card__value">
        <span className={cx('num', up ? 'text-good' : 'text-critical')}>{fmtSigned(s.delta, 3)}</span>
        <span className="muted small"> NDCG@{k}</span>
      </p>
      <p className="small muted">
        {up
          ? `The best contextual model${contextualName ? `, ${contextualName},` : ''} beats the best static GloVe model${staticName ? `, ${staticName}` : ''}.`
          : `The best static GloVe model${staticName ? `, ${staticName},` : ''} beats the best contextual model here.`}
        {s.jobs_contextual_wins !== undefined && nJobs > 0 && (
          <>
            {' '}
            Contextual wins on {s.jobs_contextual_wins} {s.jobs_contextual_wins === 1 ? 'job' : 'jobs'}
            {s.jobs_ties ? `, ties on ${s.jobs_ties}` : ''}
            {s.p_value_sign_flip !== undefined ? ` (sign-flip p = ${s.p_value_sign_flip.toFixed(2)})` : ''}.
          </>
        )}
      </p>
      <div className="dumbbell" role="img" aria-label={`Static best ${fmtScore(s.static_best, 3)}, contextual best ${fmtScore(s.contextual_best, 3)}`}>
        <span className="dumbbell__track" />
        <span className="dumbbell__link" style={{ left: pos(lo), width: `calc(${pos(hi)} - ${pos(lo)})` }} />
        <span className="dumbbell__dot fam-bg--static" style={{ left: pos(s.static_best) }} />
        <span className="dumbbell__dot fam-bg--contextual" style={{ left: pos(s.contextual_best) }} />
      </div>
      <div className="dumbbell__axis" aria-hidden>
        <span className="num">{domainLo.toFixed(2)}</span>
        <span className="num">{domainHi.toFixed(2)}</span>
      </div>
      <div className="dumbbell__labels">
        <span>
          <FamilySwatch family="static" /> Static best <strong className="num">{fmtScore(s.static_best, 3)}</strong>
        </span>
        <span>
          <FamilySwatch family="contextual" /> Contextual best <strong className="num">{fmtScore(s.contextual_best, 3)}</strong>
        </span>
      </div>
    </div>
  )
}

function PerJobTable({ rows, jobs, showRep }: { rows: EvaluationMethodResult[]; jobs: EvaluationResponse['jobs']; showRep: boolean }) {
  const range = useMemo(() => {
    const vals = rows.flatMap((r) => Object.values(r.per_job)).filter((v): v is number => typeof v === 'number')
    return vals.length ? { min: Math.min(...vals), max: Math.max(...vals) } : { min: 0, max: 1 }
  }, [rows])

  const best = useMemo(() => {
    const out: Record<string, number> = {}
    for (const j of jobs) {
      const vals = rows.map((r) => r.per_job[j.id]).filter((v): v is number => typeof v === 'number')
      if (vals.length) out[j.id] = Math.max(...vals)
    }
    const means = rows.map((r) => r.mean_ndcg)
    if (means.length) out.__mean = Math.max(...means)
    return out
  }, [rows, jobs])

  const cell = (key: string, v: number | null | undefined, isBest: boolean) => (
    <td
      key={key}
      className={cx('heat', isBest && 'is-best')}
      style={{ ['--heat' as string]: typeof v === 'number' && range.max > range.min ? (v - range.min) / (range.max - range.min) : 0 }}
    >
      <span className={cx('num', isBest && 'hl-mark')}>{fmtScore(v, 3)}</span>
    </td>
  )

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col" className="sticky-col">
              Method
            </th>
            {jobs.map((j) => (
              <th key={j.id} scope="col" title={j.title}>
                <Link to={`/jobs/${encodeURIComponent(j.id)}`} className="th-job">
                  <span className="id-tag">{j.id}</span>
                  <span className="th-job__title">{j.title}</span>
                </Link>
              </th>
            ))}
            <th scope="col" className="th-mean">
              Mean
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)}>
              <th scope="row" className="sticky-col">
                <span className="row-method">
                  <FamilySwatch family={r.family} />
                  <span>{r.label}</span>
                  {showRep && <Tag>{r.representation === 'raw' ? 'Raw' : 'Structured'}</Tag>}
                </span>
              </th>
              {jobs.map((j) => {
                const v = r.per_job[j.id]
                return cell(j.id, v, typeof v === 'number' && v === best[j.id])
              })}
              {cell('__mean', r.mean_ndcg, r.mean_ndcg === best.__mean)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function EvaluatePage() {
  useDocumentTitle('Evaluate')
  const [params, setParams] = useSearchParams()
  const k = params.get('k') === '10' ? 10 : 5
  const repFilter = (params.get('rep') ?? 'all') as Representation | 'all'
  const { data, error, loading, reload } = useAsync((signal) => api.evaluation(k, { signal }), [k], { keepPrevious: true })

  const setParam = (key: string, v: string) => {
    const next = new URLSearchParams(params)
    next.set(key, v)
    setParams(next, { replace: true })
  }

  const reps = useMemo(() => [...new Set((data?.results ?? []).map((r) => r.representation))], [data])
  const showRep = reps.length > 1
  const rows = useMemo(() => {
    const all = data?.results ?? []
    const filtered = showRep && repFilter !== 'all' ? all.filter((r) => r.representation === repFilter) : all
    return [...filtered].sort((a, b) => b.mean_ndcg - a.mean_ndcg)
  }, [data, repFilter, showRep])

  const svc = useMemo<StaticVsContextual | null>(() => {
    const byRep = repFilter !== 'all' ? data?.static_vs_contextual_by_representation?.[repFilter] : undefined
    if (byRep) return byRep
    if (data?.static_vs_contextual) return data.static_vs_contextual
    const best = (f: MethodFamily) => {
      const v = (data?.results ?? []).filter((r) => r.family === f).map((r) => r.mean_ndcg)
      return v.length ? Math.max(...v) : null
    }
    const s = best('static')
    const c = best('contextual')
    return s !== null && c !== null ? { static_best: s, contextual_best: c, delta: c - s } : null
  }, [data, repFilter])

  // Jobs where this row ties for the best score among the rows on screen.
  const winsOf = (row: EvaluationMethodResult) =>
    (data?.jobs ?? []).filter((j) => {
      const v = row.per_job[j.id]
      if (typeof v !== 'number') return false
      return rows.every((o) => typeof o.per_job[j.id] !== 'number' || (o.per_job[j.id] as number) <= v)
    }).length

  const labelOf = (key?: string) => (key ? (data?.results.find((r) => r.method === key)?.label ?? key) : null)

  const bestRow = repFilter !== 'all' ? rows[0] : data?.best
    ? (data.results.find((r) => r.method === data.best!.method && r.representation === data.best!.representation) ?? rows[0])
    : rows[0]

  return (
    <>
      <PageHeader
        title="Evaluate"
        lede={
          <>
            Each method's ranking is scored with NDCG@{k} against human relevance grades (0 to 3). NDCG rewards putting the
            strongest candidates first; 1.00 is a perfect match with the human order.
          </>
        }
        actions={
          <>
            <ButtonLink to="/evaluate/annotate" icon={PenLine}>
              Annotate grades
            </ButtonLink>
            <Button icon={RefreshCw} onClick={reload} disabled={loading}>
              Recompute
            </Button>
          </>
        }
      />

      <div className="toolbar">
        <Segmented<number>
          ariaLabel="Cut-off k"
          value={k}
          onChange={(v) => setParam('k', String(v))}
          options={[
            { value: 5, label: 'NDCG@5' },
            { value: 10, label: 'NDCG@10' },
          ]}
        />
        {showRep && (
          <Segmented<string>
            ariaLabel="Representation"
            value={repFilter}
            onChange={(v) => setParam('rep', v)}
            options={[
              { value: 'all', label: 'All inputs' },
              { value: 'structured', label: 'Structured' },
              { value: 'raw', label: 'Raw text' },
            ]}
          />
        )}
        {loading && data && <Spinner label="Recomputing" />}
      </div>

      {error && !data ? (
        <ErrorState title="Couldn't load the evaluation" message={error} onRetry={reload} />
      ) : !data ? (
        <div className="eval-skeleton">
          <div className="eval-hero">
            <Skeleton height={150} radius={18} />
            <Skeleton height={150} radius={18} />
          </div>
          <Skeleton height={320} radius={18} />
        </div>
      ) : data.results.length === 0 ? (
        <EmptyState
          icon={ChartBar}
          title="Nothing to evaluate yet"
          action={
            <ButtonLink to="/evaluate/annotate" variant="primary" icon={PenLine}>
              Grade candidates
            </ButtonLink>
          }
        >
          NDCG needs human grades. Grade candidates for at least one job to see how each method performs.
        </EmptyState>
      ) : (
        <div className={cx('stack-lg', loading && 'is-stale')}>
          {error && <ErrorState compact title="Recompute failed" message={error} onRetry={reload} />}
          <div className="eval-hero">
            {bestRow && (
              <div className="best-card">
                <p className="best-card__label">
                  <Trophy size={16} aria-hidden /> Best method
                </p>
                <p className="best-card__name">{bestRow.label}</p>
                <div className="meta-row">
                  <FamilyTag family={bestRow.family} />
                  <Tag>{bestRow.representation === 'raw' ? 'Raw text input' : 'Structured input'}</Tag>
                </div>
                {data.jobs.length > 0 && (
                  <p className="small best-card__note">
                    Top score on {winsOf(bestRow)} of {data.jobs.length} jobs, precision@{data.k}{' '}
                    {fmtScore(bestRow.mean_precision, 2)}.
                  </p>
                )}
                <p className="best-card__value">
                  <span className="num hl-mark">{fmtScore(bestRow.mean_ndcg, 3)}</span>
                  <span className="muted small"> mean NDCG@{data.k}</span>
                </p>
              </div>
            )}
            {svc && <Dumbbell s={svc} k={data.k} labelOf={labelOf} />}
          </div>

          <div className="panel panel--pad">
            <Leaderboard rows={rows} k={data.k} showRep={showRep && repFilter === 'all'} />
          </div>

          <section className="section">
            <div className="section__head">
              <h2 className="section__title">NDCG@{data.k} per job</h2>
              <p className="muted small">The highlighted cell in each column is the best method for that job.</p>
            </div>
            {data.jobs.length ? (
              <PerJobTable rows={rows} jobs={data.jobs} showRep={showRep && repFilter === 'all'} />
            ) : (
              <p className="muted">No graded jobs yet.</p>
            )}
          </section>
        </div>
      )}
    </>
  )
}
