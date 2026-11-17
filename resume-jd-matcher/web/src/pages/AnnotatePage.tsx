import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CircleCheck, Save, Search, Undo2, Users } from 'lucide-react'
import { api, errorMessage } from '../api'
import { Button, ButtonLink, ChipList, EmptyState, ErrorState, Notice, PageHeader, Segmented, Skeleton, SkeletonRows, cx } from '../components/ui'
import { useAsync, useDocumentTitle } from '../hooks'
import { GRADES, GRADE_LABEL, norm } from '../lib/format'
import type { Grade, JobSummary, LabelsResponse, ResumeSummary } from '../types'

type Drafts = Record<string, Record<string, Grade>>

function GradePicker({ value, onChange, name }: { value: Grade | null; onChange: (g: Grade) => void; name: string }) {
  return (
    <div className="grade-picker" role="radiogroup" aria-label={`Grade for ${name}`}>
      {GRADES.map((g) => (
        <button
          key={g}
          type="button"
          role="radio"
          aria-checked={value === g}
          className={cx('grade-picker__btn', value === g && `grade-bg--g${g}`)}
          title={`${g}: ${GRADE_LABEL[g]}`}
          onClick={() => onChange(g)}
        >
          {g}
        </button>
      ))}
    </div>
  )
}

export default function AnnotatePage() {
  useDocumentTitle('Annotate grades')
  const [params, setParams] = useSearchParams()
  const jobs = useAsync((signal) => api.jobs({ signal }), [])
  const resumes = useAsync((signal) => api.resumes({ signal }), [])
  const labels = useAsync((signal) => api.labels({ signal }), [])

  const jobId = params.get('job') ?? jobs.data?.[0]?.id ?? null
  const [drafts, setDrafts] = useState<Drafts>({})
  const [filter, setFilter] = useState<'all' | 'ungraded'>('all')
  const [q, setQ] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [savedJob, setSavedJob] = useState<string | null>(null)

  const saved: Record<string, Grade> = (jobId && labels.data?.[jobId]) || {}
  const draft = (jobId && drafts[jobId]) || {}
  const current = { ...saved, ...draft }

  const changedCount = (jid: string) => {
    const d = drafts[jid] ?? {}
    const s = labels.data?.[jid] ?? {}
    return Object.entries(d).filter(([rid, g]) => s[rid] !== g).length
  }
  const dirty = jobId ? changedCount(jobId) : 0
  const anyDirty = Object.keys(drafts).some((j) => changedCount(j) > 0)

  useEffect(() => {
    if (!anyDirty) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [anyDirty])

  const setGrade = (rid: string, g: Grade) => {
    if (!jobId) return
    setSavedJob(null)
    setDrafts((d) => ({ ...d, [jobId]: { ...(d[jobId] ?? {}), [rid]: g } }))
  }

  const selectJob = (id: string) => {
    const next = new URLSearchParams(params)
    next.set('job', id)
    setParams(next, { replace: true })
    setSaveError(null)
    setSavedJob(null)
  }

  const save = async () => {
    if (!jobId) return
    setSaving(true)
    setSaveError(null)
    try {
      const res = await api.saveLabels(jobId, current)
      labels.setData((prev: LabelsResponse | null) => ({ ...(prev ?? {}), [res.job_id]: res.grades }))
      setDrafts((d) => {
        const next = { ...d }
        delete next[jobId]
        return next
      })
      setSavedJob(jobId)
    } catch (err) {
      setSaveError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const terms = norm(q).split(/\s+/).filter(Boolean)
  const list = (resumes.data ?? []).filter((r) => {
      if (filter === 'ungraded' && current[r.id] !== undefined) return false
      if (!terms.length) return true
      const hay = norm([r.id, r.name, r.headline, ...r.top_skills].join(' '))
      return terms.every((t) => hay.includes(t))
    })

  const total = resumes.data?.length ?? 0
  const gradedCount = resumes.data ? resumes.data.filter((r) => current[r.id] !== undefined).length : 0
  const job: JobSummary | undefined = jobs.data?.find((j) => j.id === jobId)
  const loadError = jobs.error || resumes.error || labels.error
  const reloadAll = () => {
    jobs.reload()
    resumes.reload()
    labels.reload()
  }

  return (
    <>
      <PageHeader
        back={{ to: '/evaluate', label: 'Evaluation' }}
        title="Annotate grades"
        lede="Grade how relevant each candidate is to a job. These human grades are the ground truth that NDCG compares every ranking method against."
      />

      <div className="grade-scale" aria-label="Grade scale">
        {GRADES.map((g) => (
          <span key={g} className="grade-scale__item">
            <span className={cx('grade', 'grade--sm', `grade--g${g}`)}>{g}</span>
            {GRADE_LABEL[g]}
          </span>
        ))}
      </div>

      {loadError && !(jobs.data && resumes.data && labels.data) ? (
        <ErrorState title="Couldn't load grading data" message={loadError} onRetry={reloadAll} />
      ) : (
        <div className="annotate">
          <nav className="annotate__jobs" aria-label="Jobs">
            {!jobs.data ? (
              <div className="stack-sm">
                {Array.from({ length: 4 }, (_, i) => (
                  <Skeleton key={i} height={52} radius={12} />
                ))}
              </div>
            ) : jobs.data.length === 0 ? (
              <p className="muted small">No jobs yet.</p>
            ) : (
              jobs.data.map((j) => {
                // Count only candidates currently in the corpus (labels may reference others).
                const merged = { ...(labels.data?.[j.id] ?? {}), ...(drafts[j.id] ?? {}) }
                const n = (resumes.data ?? []).filter((r) => merged[r.id] !== undefined).length
                const unsaved = changedCount(j.id)
                return (
                  <button
                    key={j.id}
                    type="button"
                    className="job-pick"
                    aria-current={j.id === jobId ? 'true' : undefined}
                    onClick={() => selectJob(j.id)}
                  >
                    <span className="job-pick__title">{j.title}</span>
                    <span className="job-pick__meta">
                      <span className="id-tag">{j.id}</span>
                      <span className="muted small num">
                        {n}/{total || '–'} graded
                      </span>
                      {unsaved > 0 && <span className="unsaved-dot" title={`${unsaved} unsaved`} />}
                    </span>
                  </button>
                )
              })
            )}
          </nav>

          <section className="annotate__main" aria-label="Candidates">
            <div className="annotate__head">
              <div>
                <h2 className="section__title">{job ? job.title : <Skeleton width={200} height={20} />}</h2>
                {job && (
                  <p className="muted small">
                    {gradedCount} of {total} candidates graded.{' '}
                    <Link to={`/jobs/${encodeURIComponent(job.id)}`}>See the ranking</Link>
                  </p>
                )}
              </div>
              <div className="toolbar toolbar--tight">
                <div className="search search--sm">
                  <Search size={15} aria-hidden />
                  <input type="search" placeholder="Filter candidates" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter candidates" />
                </div>
                <Segmented<'all' | 'ungraded'>
                  ariaLabel="Show"
                  size="sm"
                  value={filter}
                  onChange={setFilter}
                  options={[
                    { value: 'all', label: 'All' },
                    { value: 'ungraded', label: 'Ungraded' },
                  ]}
                />
              </div>
            </div>
            {job && job.required_skills.length > 0 && (
              <div className="annotate__req">
                <span className="muted small">Required</span>
                <ChipList items={job.required_skills} variant="required" max={10} />
              </div>
            )}

            {!resumes.data || !labels.data ? (
              <div className="panel">
                <SkeletonRows rows={6} />
              </div>
            ) : total === 0 ? (
              <EmptyState icon={Users} title="No candidates to grade">
                Add resumes on the Extract page first.
              </EmptyState>
            ) : list.length === 0 ? (
              <EmptyState icon={CircleCheck} title={filter === 'ungraded' ? 'Every candidate is graded' : 'No candidates match'}>
                {filter === 'ungraded' ? 'Switch to All to review or change grades.' : 'Try a different filter.'}
              </EmptyState>
            ) : (
              <ul className="panel grade-list">
                {list.map((r: ResumeSummary) => {
                  const g = current[r.id] ?? null
                  const changed = draft[r.id] !== undefined && saved[r.id] !== draft[r.id]
                  return (
                    <li key={r.id} className={cx('grade-row', changed && 'is-changed')}>
                      <div className="grade-row__who">
                        <p className="grade-row__name">
                          <Link to={`/candidates/${encodeURIComponent(r.id)}${jobId ? `?job=${encodeURIComponent(jobId)}` : ''}`}>{r.name}</Link>
                          <span className="id-tag">{r.id}</span>
                        </p>
                        <p className="muted small">{r.headline}</p>
                      </div>
                      <div className="grade-row__skills">
                        <ChipList items={r.top_skills} max={4} expandable={false} />
                      </div>
                      <div className="grade-row__pick">
                        <GradePicker value={g} onChange={(v) => setGrade(r.id, v)} name={r.name} />
                        <span className="grade-row__label small muted">{g !== null ? GRADE_LABEL[g] : 'Not graded'}</span>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </div>
      )}

      <div className={cx('save-bar', (dirty > 0 || saving || saveError || savedJob === jobId) && 'is-visible')} role="region" aria-label="Save grades">
        <div className="save-bar__inner">
          {saveError ? (
            <p className="small text-critical">Couldn't save: {saveError}</p>
          ) : savedJob === jobId && dirty === 0 ? (
            <Notice tone="good" icon={CircleCheck}>
              Grades saved. The evaluation now uses them.{' '}
              <Link to="/evaluate">View evaluation</Link>
            </Notice>
          ) : (
            <p className="small">
              <strong className="num">{dirty}</strong> unsaved {dirty === 1 ? 'change' : 'changes'} for {job?.title ?? jobId}
            </p>
          )}
          <div className="row-gap">
            {dirty > 0 && (
              <Button
                variant="ghost"
                icon={Undo2}
                disabled={saving}
                onClick={() =>
                  setDrafts((d) => {
                    const next = { ...d }
                    if (jobId) delete next[jobId]
                    return next
                  })
                }
              >
                Discard
              </Button>
            )}
            {dirty > 0 || saveError ? (
              <Button variant="primary" icon={Save} loading={saving} onClick={save} disabled={dirty === 0 && !saveError}>
                Save grades
              </Button>
            ) : (
              <ButtonLink to="/evaluate" variant="secondary">
                Back to evaluation
              </ButtonLink>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
