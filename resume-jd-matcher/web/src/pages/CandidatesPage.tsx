import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { MapPin, RefreshCw, ScanText, Search, Users, X } from 'lucide-react'
import { api } from '../api'
import { Button, ButtonLink, ChipList, EmptyState, ErrorState, IconText, PageHeader, Segmented, SkeletonRows, Tag } from '../components/ui'
import { useAsync, useDocumentTitle } from '../hooks'
import { SENIORITY_LABEL, fmtYears, initials, norm } from '../lib/format'
import type { Seniority } from '../types'

const SENIORITY_ORDER: Seniority[] = ['intern', 'junior', 'mid', 'senior', 'lead', 'principal', 'unknown']

export default function CandidatesPage() {
  useDocumentTitle('Candidates')
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const level = params.get('level') ?? 'all'
  const { data, error, loading, reload } = useAsync((signal) => api.resumes({ signal }), [])

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (!value || value === 'all') next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  const levels = useMemo(() => {
    const present = new Set((data ?? []).map((r) => r.seniority))
    return SENIORITY_ORDER.filter((s) => present.has(s))
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return []
    const terms = norm(q).split(/\s+/).filter(Boolean)
    return data.filter((r) => {
      if (level !== 'all' && r.seniority !== level) return false
      if (!terms.length) return true
      const hay = norm([r.id, r.name, r.headline, r.location ?? '', ...r.top_skills].join(' '))
      return terms.every((t) => hay.includes(t))
    })
  }, [data, q, level])

  return (
    <>
      <PageHeader
        title="Candidates"
        lede="Every resume in the corpus, extracted into the same schema. Search by name, title, location or skill."
        actions={
          <Button icon={RefreshCw} onClick={reload} loading={loading && !!data} disabled={loading}>
            Refresh
          </Button>
        }
      />

      <div className="toolbar">
        <div className="search">
          <Search size={17} aria-hidden />
          <input
            type="search"
            placeholder="Search candidates, e.g. PyTorch Pune"
            value={q}
            onChange={(e) => setParam('q', e.target.value)}
            aria-label="Search candidates"
          />
          {q && (
            <button type="button" className="search__clear" onClick={() => setParam('q', '')} aria-label="Clear search">
              <X size={15} aria-hidden />
            </button>
          )}
        </div>
        {levels.length > 1 && (
          <Segmented<string>
            ariaLabel="Seniority"
            size="sm"
            value={level}
            onChange={(v) => setParam('level', v)}
            options={[{ value: 'all', label: 'All' }, ...levels.map((s) => ({ value: s, label: SENIORITY_LABEL[s].replace('Seniority unknown', 'Unknown') }))]}
          />
        )}
      </div>

      {error && !data ? (
        <ErrorState title="Couldn't load candidates" message={error} onRetry={reload} />
      ) : !data ? (
        <div className="panel">
          <SkeletonRows rows={8} />
        </div>
      ) : data.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No resumes in the corpus yet"
          action={
            <ButtonLink to="/extract?kind=resume" variant="primary" icon={ScanText}>
              Add a resume
            </ButtonLink>
          }
        >
          Extract a resume with <em>Save to corpus</em> turned on and it will appear here.
        </EmptyState>
      ) : (
        <>
          <p className="muted small summary-line" aria-live="polite">
            {filtered.length === data.length ? `${data.length} candidates` : `${filtered.length} of ${data.length} candidates`}
          </p>
          {filtered.length === 0 ? (
            <EmptyState icon={Search} title="No candidates match">
              Try a shorter search or a different seniority filter.
            </EmptyState>
          ) : (
            <ul className="panel cand-list">
              {filtered.map((r) => (
                <li key={r.id}>
                  <Link to={`/candidates/${encodeURIComponent(r.id)}`} className="cand-row">
                    <span className="avatar" aria-hidden>
                      {initials(r.name)}
                    </span>
                    <div className="cand-row__who">
                      <p className="cand-row__name">
                        {r.name} <span className="id-tag">{r.id}</span>
                      </p>
                      <p className="cand-row__headline">{r.headline}</p>
                      <div className="meta-row">
                        {r.location && <IconText icon={MapPin}>{r.location}</IconText>}
                        <Tag>{SENIORITY_LABEL[r.seniority]}</Tag>
                      </div>
                    </div>
                    <div className="cand-row__skills">
                      <ChipList items={r.top_skills} max={4} expandable={false} />
                    </div>
                    <div className="cand-row__years">
                      <span className="num">{Math.round(r.total_years_experience * 10) / 10}</span>
                      <span className="muted small">{fmtYears(r.total_years_experience).split(' ')[1]}</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  )
}
