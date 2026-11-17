import { useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { X } from 'lucide-react'
import { api, errorMessage } from '../api'
import { ErrorState, FamilyTag, GradeBadge, PageHeader, Segmented, Skeleton, Spinner, cx } from '../components/ui'
import { useAsync, useDocumentTitle } from '../hooks'
import { FAMILY_ORDER, GRADES, GRADE_LABEL, fmtScore } from '../lib/format'
import { useSettings } from '../settings'
import type { Grade, MethodInfo, RankResponse, Representation } from '../types'

const DEPTH = 5

type ColumnResult = { method: MethodInfo; data: RankResponse | null; error: string | null }

export default function ComparePage() {
  const { jobId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const rep = (params.get('rep') === 'raw' ? 'raw' : 'structured') as Representation
  const { methods, methodsError, reloadMethods } = useSettings()
  const [pinned, setPinned] = useState<string | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  const focus = pinned ?? hover

  const job = useAsync((signal) => api.job(jobId, { signal }), [jobId])
  useDocumentTitle(job.data ? `Compare methods: ${job.data.extracted.title}` : 'Compare methods')

  const ordered = useMemo(
    () => (methods ? [...methods].sort((a, b) => FAMILY_ORDER.indexOf(a.family) - FAMILY_ORDER.indexOf(b.family)) : null),
    [methods],
  )

  const cols = useAsync<ColumnResult[]>(
    async (signal) => {
      const settled = await Promise.allSettled(
        ordered!.map((m) => api.rank({ job_id: jobId, method: m.key, representation: rep, top_k: DEPTH }, { signal })),
      )
      return ordered!.map((m, i) => {
        const s = settled[i]
        return s.status === 'fulfilled'
          ? { method: m, data: s.value, error: null }
          : { method: m, data: null, error: errorMessage(s.reason) }
      })
    },
    [jobId, rep, ordered],
    { enabled: !!ordered, keepPrevious: true },
  )

  const bestNdcg = useMemo(() => {
    const vals = (cols.data ?? []).map((c) => c.data?.ndcg_at_5).filter((v): v is number => typeof v === 'number')
    return vals.length ? Math.max(...vals) : null
  }, [cols.data])

  // Consensus: how many methods put each candidate in their top 5.
  const consensus = useMemo(() => {
    const map = new Map<string, { id: string; name: string; count: number; grade: Grade | null; ranks: number[] }>()
    for (const c of cols.data ?? []) {
      for (const r of c.data?.results.slice(0, DEPTH) ?? []) {
        const e = map.get(r.resume_id) ?? { id: r.resume_id, name: r.name, count: 0, grade: r.human_grade, ranks: [] }
        e.count += 1
        e.ranks.push(r.rank)
        map.set(r.resume_id, e)
      }
    }
    return [...map.values()].sort(
      (a, b) => b.count - a.count || a.ranks.reduce((s, x) => s + x, 0) / a.ranks.length - b.ranks.reduce((s, x) => s + x, 0) / b.ranks.length,
    )
  }, [cols.data])

  const totalCols = cols.data?.length ?? 0

  return (
    <>
      <PageHeader
        back={{ to: `/jobs/${encodeURIComponent(jobId)}`, label: 'Back to ranking' }}
        title="Compare methods"
        lede={
          <>
            Top {DEPTH} candidates from every ranking method for{' '}
            <strong>{job.data?.extracted.title ?? jobId}</strong>. Cells are coloured by the recruiter's grade, so a method that agrees
            with the human ranking shows strong-fit colours at the top. Select a candidate to trace them across methods.
          </>
        }
        actions={
          <Segmented<Representation>
            ariaLabel="Document representation"
            value={rep}
            onChange={(v) => {
              const next = new URLSearchParams(params)
              next.set('rep', v)
              setParams(next, { replace: true })
            }}
            options={[
              { value: 'structured', label: 'Structured JSON' },
              { value: 'raw', label: 'Raw text' },
            ]}
          />
        }
      />

      {methodsError && !methods ? (
        <ErrorState title="Couldn't load ranking methods" message={methodsError} onRetry={reloadMethods} />
      ) : cols.error ? (
        <ErrorState title="Comparison failed" message={cols.error} onRetry={cols.reload} />
      ) : (
        <>
          <div className="legend-row legend-row--plain">
            <span className="muted small">Human grade</span>
            {GRADES.map((g) => (
              <span key={g} className="legend-item">
                <GradeBadge grade={g} size="sm" /> {GRADE_LABEL[g]}
              </span>
            ))}
            <span className="legend-item">
              <GradeBadge grade={null} size="sm" /> Not graded
            </span>
            {cols.loading && cols.data && <Spinner label="Updating" />}
            {pinned && (
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setPinned(null)}>
                <X size={14} aria-hidden /> Clear selection
              </button>
            )}
          </div>

          <div className="matrix-scroll">
            <div
              className={cx('matrix', focus && 'has-focus', cols.loading && cols.data && 'is-stale')}
              style={{ gridTemplateColumns: `48px repeat(${Math.max(totalCols, ordered?.length ?? 6)}, minmax(156px, 1fr))` }}
              onMouseLeave={() => setHover(null)}
            >
              <div className="matrix__corner">Rank</div>
              {!cols.data
                ? Array.from({ length: ordered?.length ?? 6 }, (_, i) => (
                    <div key={i} className="matrix__head">
                      <Skeleton width="70%" height={14} />
                      <Skeleton width="40%" height={11} />
                    </div>
                  ))
                : cols.data.map((c) => (
                    <div key={c.method.key} className={cx('matrix__head', `fam-top--${c.method.family}`)}>
                      <p className="matrix__method" title={c.method.description}>
                        {c.method.label}
                      </p>
                      <FamilyTag family={c.method.family} />
                      <p className="matrix__ndcg">
                        NDCG@5{' '}
                        <span className={cx('num', c.data?.ndcg_at_5 != null && c.data.ndcg_at_5 === bestNdcg && 'hl-mark')}>
                          {fmtScore(c.data?.ndcg_at_5)}
                        </span>
                      </p>
                    </div>
                  ))}

              {Array.from({ length: DEPTH }, (_, row) => (
                <Row
                  key={row}
                  row={row}
                  cols={cols.data}
                  placeholderCount={ordered?.length ?? 6}
                  focus={focus}
                  pinned={pinned}
                  onHover={setHover}
                  onPin={(id) => setPinned((p) => (p === id ? null : id))}
                />
              ))}
            </div>
          </div>

          {cols.data && consensus.length > 0 && (
            <section className="section">
              <div className="section__head">
                <h2 className="section__title">Consensus picks</h2>
                <p className="muted small">How many of the {totalCols} methods place each candidate in their top {DEPTH}.</p>
              </div>
              <ul className="consensus">
                {consensus.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      className={cx('consensus__item', focus === c.id && 'is-focus')}
                      onMouseEnter={() => setHover(c.id)}
                      onMouseLeave={() => setHover(null)}
                      onClick={() => setPinned((p) => (p === c.id ? null : c.id))}
                      aria-pressed={pinned === c.id}
                    >
                      <GradeBadge grade={c.grade} size="sm" />
                      <span className="consensus__name">{c.name}</span>
                      <span className="consensus__dots" aria-label={`${c.count} of ${totalCols} methods`}>
                        {Array.from({ length: totalCols }, (_, i) => (
                          <span key={i} className={cx('dot', i < c.count && 'is-on')} />
                        ))}
                      </span>
                      <span className="num small">
                        {c.count}/{totalCols}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <p className="footnote">
                Open a candidate from the <Link to={`/jobs/${encodeURIComponent(jobId)}`}>ranking</Link> to read their resume or a
                skill-gap report.
              </p>
            </section>
          )}
        </>
      )}
    </>
  )
}

function Row({
  row,
  cols,
  placeholderCount,
  focus,
  pinned,
  onHover,
  onPin,
}: {
  row: number
  cols: ColumnResult[] | null
  placeholderCount: number
  focus: string | null
  pinned: string | null
  onHover: (id: string | null) => void
  onPin: (id: string) => void
}) {
  return (
    <>
      <div className="matrix__rank">{row + 1}</div>
      {!cols
        ? Array.from({ length: placeholderCount }, (_, i) => (
            <div key={i} className="matrix__cell matrix__cell--skeleton">
              <Skeleton width="80%" height={12} />
            </div>
          ))
        : cols.map((c) => {
            if (c.error) {
              return row === 0 ? (
                <div key={c.method.key} className="matrix__cell matrix__cell--error" style={{ gridRow: `span ${DEPTH}` }} title={c.error}>
                  <p className="small">This method failed.</p>
                  <p className="muted small">{c.error}</p>
                </div>
              ) : null
            }
            const r = c.data?.results[row]
            if (!r) return <div key={c.method.key} className="matrix__cell matrix__cell--empty">–</div>
            const g = r.human_grade
            const isFocus = focus === r.resume_id
            return (
              <button
                type="button"
                key={c.method.key}
                className={cx('matrix__cell', g !== null ? `grade-bg--g${g}` : 'grade-bg--none', isFocus && 'is-focus')}
                onMouseEnter={() => onHover(r.resume_id)}
                onFocus={() => onHover(r.resume_id)}
                onClick={() => onPin(r.resume_id)}
                aria-pressed={pinned === r.resume_id}
                title={`${r.name} (${r.resume_id}). Score ${fmtScore(r.score, 3)}. ${g !== null ? `Human grade ${g}: ${GRADE_LABEL[g]}` : 'Not graded'}`}
              >
                <span className="matrix__name">{r.name}</span>
                <span className="matrix__sub">
                  {r.resume_id}, {fmtScore(r.score, 2)}
                </span>
              </button>
            )
          })}
    </>
  )
}
