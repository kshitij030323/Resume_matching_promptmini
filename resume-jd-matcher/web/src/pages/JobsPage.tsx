import { Link } from 'react-router-dom'
import { Briefcase, Clock, MapPin, RefreshCw, ScanText } from 'lucide-react'
import { api } from '../api'
import { Button, ButtonLink, ChipList, EmptyState, ErrorState, IconText, PageHeader, Skeleton, Tag } from '../components/ui'
import { useAsync, useDocumentTitle } from '../hooks'
import { SENIORITY_LABEL, fmtYears } from '../lib/format'

function JobCardSkeleton() {
  return (
    <div className="job-card job-card--skeleton" aria-hidden>
      <Skeleton width="65%" height={20} />
      <Skeleton width="40%" height={12} />
      <Skeleton width="90%" height={12} />
      <div className="chips">
        {[60, 72, 54, 80].map((w, i) => (
          <Skeleton key={i} width={w} height={24} radius={999} />
        ))}
      </div>
    </div>
  )
}

export default function JobsPage() {
  useDocumentTitle('Jobs')
  const { data, error, loading, reload } = useAsync((signal) => api.jobs({ signal }), [])

  return (
    <>
      <PageHeader
        title="Jobs"
        lede="Open a job description to rank every candidate against it, compare embedding methods and generate skill-gap reports."
        actions={
          <Button icon={RefreshCw} onClick={reload} loading={loading && !!data} disabled={loading}>
            Refresh
          </Button>
        }
      />
      {error && !data ? (
        <ErrorState title="Couldn't load jobs" message={error} onRetry={reload} />
      ) : !data ? (
        <div className="job-grid">
          {Array.from({ length: 4 }, (_, i) => (
            <JobCardSkeleton key={i} />
          ))}
        </div>
      ) : data.length === 0 ? (
        <EmptyState
          icon={Briefcase}
          title="No job descriptions yet"
          action={
            <ButtonLink to="/extract?kind=job" variant="primary" icon={ScanText}>
              Add a job description
            </ButtonLink>
          }
        >
          Extract a job description with <em>Save to corpus</em> turned on and it will appear here.
        </EmptyState>
      ) : (
        <>
          {error && <ErrorState compact title="Refresh failed" message={error} onRetry={reload} />}
          <div className="job-grid">
            {data.map((job) => (
              <Link key={job.id} to={`/jobs/${encodeURIComponent(job.id)}`} className="job-card">
                <div className="job-card__top">
                  <h2 className="job-card__title">{job.title}</h2>
                  <span className="id-tag">{job.id}</span>
                </div>
                <div className="meta-row">
                  {job.company && <IconText icon={Briefcase}>{job.company}</IconText>}
                  {job.location && <IconText icon={MapPin}>{job.location}</IconText>}
                </div>
                <div className="meta-row">
                  <Tag>{SENIORITY_LABEL[job.seniority]}</Tag>
                  {job.min_years_experience !== null && (
                    <IconText icon={Clock}>{fmtYears(job.min_years_experience)} minimum</IconText>
                  )}
                </div>
                {job.summary && <p className="job-card__summary">{job.summary}</p>}
                <div className="job-card__skills">
                  <span className="job-card__label">Required</span>
                  <ChipList items={job.required_skills} variant="required" max={6} expandable={false} empty="No required skills listed" />
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
    </>
  )
}
