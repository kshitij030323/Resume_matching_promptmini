import { useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Sparkles, Target } from 'lucide-react'
import { api } from '../api'
import { ResumeHeaderMeta, ResumeView, type SkillHighlight } from '../components/DocViews'
import { Button, ButtonLink, Chip, Collapsible, ErrorState, ModeBadge, PageHeader, Skeleton, SkillName, altTitle } from '../components/ui'
import { useAsync, useDocumentTitle } from '../hooks'
import { alternativesSet, fmtMs, norm, requirementMet } from '../lib/format'
import type { ResumeSchema } from '../types'

function resumeSkillSet(r: ResumeSchema) {
  const set = new Set<string>()
  r.skills.forEach((s) => set.add(norm(s.name)))
  r.experience.forEach((e) => e.technologies.forEach((t) => set.add(norm(t))))
  r.projects.forEach((p) => p.technologies.forEach((t) => set.add(norm(t))))
  return set
}

export default function CandidatePage() {
  const { resumeId = '' } = useParams()
  const [params] = useSearchParams()
  const jobId = params.get('job')
  const navigate = useNavigate()
  const [pickJob, setPickJob] = useState('')

  const resume = useAsync((signal) => api.resume(resumeId, { signal }), [resumeId])
  const job = useAsync((signal) => api.job(jobId!, { signal }), [jobId], { enabled: !!jobId })
  const jobs = useAsync((signal) => api.jobs({ signal }), [], { enabled: !jobId })
  const r = resume.data?.extracted
  const jd = jobId ? job.data?.extracted : undefined
  useDocumentTitle(r?.name ?? resumeId)

  const highlight = useMemo<SkillHighlight | undefined>(() => {
    if (!jd) return undefined
    return { required: alternativesSet(jd.required_skills), preferred: alternativesSet(jd.preferred_skills) }
  }, [jd])

  const match = useMemo(() => {
    if (!jd || !r) return null
    const have = resumeSkillSet(r)
    const matched = jd.required_skills.filter((s) => requirementMet(s, have))
    const missing = jd.required_skills.filter((s) => !requirementMet(s, have))
    return { matched, missing }
  }, [jd, r])

  const reportHref = jobId ? `/report/${encodeURIComponent(jobId)}/${encodeURIComponent(resumeId)}` : ''

  return (
    <>
      <PageHeader
        back={jobId ? { to: `/jobs/${encodeURIComponent(jobId)}`, label: 'Back to ranking' } : { to: '/candidates', label: 'All candidates' }}
        title={r ? r.name || 'Unnamed candidate' : resume.error ? resumeId : <Skeleton width={260} height={34} />}
        lede={
          r ? (
            <>
              {r.headline && <span className="lede-strong">{r.headline}</span>}
              <ResumeHeaderMeta resume={r} />
            </>
          ) : undefined
        }
      />

      {jobId && (
        <div className="context-banner">
          <div className="context-banner__text">
            <p className="context-banner__eyebrow">
              <Target size={15} aria-hidden /> Viewing against
            </p>
            <p className="context-banner__title">{jd ? jd.title : job.error ? jobId : <Skeleton width={220} height={18} />}</p>
            {match && (
              <div className="context-banner__match">
                <span className="small">
                  <strong className="num">
                    {match.matched.length}/{jd!.required_skills.length}
                  </strong>{' '}
                  required skills found on the resume
                </span>
                {match.missing.length > 0 && (
                  <div className="chips chips--tight">
                    {match.missing.map((s) => (
                      <Chip key={s} variant="missing" title={altTitle(s) ?? 'Required skill not found'}>
                        <SkillName name={s} />
                      </Chip>
                    ))}
                  </div>
                )}
              </div>
            )}
            {job.error && <p className="small text-critical">{job.error}</p>}
          </div>
          <ButtonLink to={reportHref} variant="primary" size="lg" icon={Sparkles}>
            Skill-gap report
          </ButtonLink>
        </div>
      )}

      {!jobId && jobs.data && jobs.data.length > 0 && (
        <form
          className="fit-picker"
          onSubmit={(e) => {
            e.preventDefault()
            if (pickJob) navigate(`/report/${encodeURIComponent(pickJob)}/${encodeURIComponent(resumeId)}`)
          }}
        >
          <label htmlFor="fit-job" className="small">
            Check this candidate against a job
          </label>
          <select id="fit-job" className="select" value={pickJob} onChange={(e) => setPickJob(e.target.value)}>
            <option value="">Choose a job…</option>
            {jobs.data.map((j) => (
              <option key={j.id} value={j.id}>
                {j.title} ({j.id})
              </option>
            ))}
          </select>
          <Button type="submit" icon={Sparkles} disabled={!pickJob}>
            Skill-gap report
          </Button>
        </form>
      )}

      {resume.error ? (
        <ErrorState title="Couldn't load this candidate" message={resume.error} onRetry={resume.reload} />
      ) : !r ? (
        <div className="panel panel--pad stack-sm">
          <Skeleton height={14} width="70%" />
          <Skeleton height={14} width="85%" />
          <Skeleton height={120} />
          <Skeleton height={120} />
        </div>
      ) : (
        <>
          {highlight && (
            <p className="muted small legend-inline">
              <Chip variant="match">Highlighted</Chip> skills are required by this job,{' '}
              <Chip variant="match-soft">lightly highlighted</Chip> ones are preferred.
            </p>
          )}
          <div className="panel panel--pad">
            <ResumeView resume={r} highlight={highlight} />
          </div>
          <div className="extraction-meta extraction-meta--page">
            <span className="muted small">Extracted by</span>
            <ModeBadge mode={resume.data!.meta.method} model={resume.data!.meta.model} />
            <span className="muted small">in {fmtMs(resume.data!.meta.latency_ms)}</span>
          </div>
          {resume.data!.raw_text && (
            <Collapsible summary="Original resume text" className="collapsible--panel">
              <pre className="raw-text">{resume.data!.raw_text}</pre>
            </Collapsible>
          )}
        </>
      )}
    </>
  )
}
