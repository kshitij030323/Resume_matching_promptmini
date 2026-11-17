import { Award, Briefcase, Clock, GraduationCap, Mail, MapPin, Phone } from 'lucide-react'
import {
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  SENIORITY_LABEL,
  fmtRange,
  fmtYears,
  humanize,
  norm,
} from '../lib/format'
import type { JobSchema, ResumeSchema, SkillCategory, SkillItem } from '../types'
import { Chip, ChipList, IconText, Tag, cx, type ChipVariant } from './ui'

// ---------------------------------------------------------------------------
// Job description
// ---------------------------------------------------------------------------
export function JobFacts({ job }: { job: JobSchema }) {
  const facts: { label: string; value: string; wide?: boolean }[] = []
  facts.push({ label: 'Seniority', value: SENIORITY_LABEL[job.seniority] })
  if (job.min_years_experience !== null) facts.push({ label: 'Minimum experience', value: fmtYears(job.min_years_experience) })
  if (job.employment_type) facts.push({ label: 'Employment', value: humanize(job.employment_type) })
  if (job.domain) facts.push({ label: 'Domain', value: humanize(job.domain) })
  if (job.education_requirement) facts.push({ label: 'Education', value: job.education_requirement, wide: true })
  return (
    <dl className="facts">
      {facts.map((f) => (
        <div key={f.label} className={cx('facts__item', f.wide && 'facts__item--wide')}>
          <dt>{f.label}</dt>
          <dd>{f.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function JobView({ job, showHeader }: { job: JobSchema; showHeader?: boolean }) {
  return (
    <div className="doc-view">
      {showHeader && (
        <div className="doc-view__header">
          <h3 className="doc-view__title">{job.title}</h3>
          <div className="meta-row">
            {job.company && <IconText icon={Briefcase}>{job.company}</IconText>}
            {job.location && <IconText icon={MapPin}>{job.location}</IconText>}
          </div>
        </div>
      )}
      {job.summary && <p className="prose">{job.summary}</p>}
      <JobFacts job={job} />
      <div className="doc-block">
        <h4 className="doc-block__title">
          Required skills <span className="count">{job.required_skills.length}</span>
        </h4>
        <ChipList items={job.required_skills} variant="required" empty="None listed" />
      </div>
      <div className="doc-block">
        <h4 className="doc-block__title">
          Preferred skills <span className="count">{job.preferred_skills.length}</span>
        </h4>
        <ChipList items={job.preferred_skills} variant="preferred" empty="None listed" />
      </div>
      {job.responsibilities.length > 0 && (
        <div className="doc-block">
          <h4 className="doc-block__title">Responsibilities</h4>
          <ul className="bullets">
            {job.responsibilities.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Resume
// ---------------------------------------------------------------------------
export interface SkillHighlight {
  required: Set<string>
  preferred: Set<string>
}

function skillVariant(name: string, hl?: SkillHighlight): ChipVariant {
  if (!hl) return 'plain'
  const n = norm(name)
  if (hl.required.has(n)) return 'match'
  if (hl.preferred.has(n)) return 'match-soft'
  return 'plain'
}

function skillTitle(s: SkillItem) {
  const parts = [humanize(s.proficiency)]
  if (s.years !== null) parts.push(fmtYears(s.years))
  return parts.join(', ')
}

export function SkillGroups({ skills, highlight }: { skills: SkillItem[]; highlight?: SkillHighlight }) {
  if (!skills.length) return <p className="muted small">No skills extracted.</p>
  const groups = new Map<SkillCategory, SkillItem[]>()
  for (const s of skills) {
    const cat = (CATEGORY_ORDER.includes(s.category) ? s.category : 'other') as SkillCategory
    if (!groups.has(cat)) groups.set(cat, [])
    groups.get(cat)!.push(s)
  }
  return (
    <div className="skill-groups">
      {CATEGORY_ORDER.filter((c) => groups.has(c)).map((cat) => (
        <div key={cat} className="skill-group">
          <h4 className="skill-group__title">{CATEGORY_LABEL[cat]}</h4>
          <div className="chips">
            {groups.get(cat)!.map((s, i) => (
              <Chip key={`${s.name}-${i}`} variant={skillVariant(s.name, highlight)} title={skillTitle(s)}>
                {s.name}
                {s.years !== null && s.years > 0 && <span className="chip__sub">{Math.round(s.years * 10) / 10}y</span>}
              </Chip>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function ResumeHeaderMeta({ resume }: { resume: ResumeSchema }) {
  return (
    <div className="meta-row">
      {resume.location && <IconText icon={MapPin}>{resume.location}</IconText>}
      <IconText icon={Clock}>{fmtYears(resume.total_years_experience)} experience</IconText>
      <Tag>{SENIORITY_LABEL[resume.seniority]}</Tag>
      {resume.email && <IconText icon={Mail}>{resume.email}</IconText>}
      {resume.phone && <IconText icon={Phone}>{resume.phone}</IconText>}
    </div>
  )
}

export function ExperienceTimeline({ items, highlight }: { items: ResumeSchema['experience']; highlight?: SkillHighlight }) {
  if (!items.length) return <p className="muted small">No work experience extracted.</p>
  return (
    <ol className="timeline">
      {items.map((e, i) => {
        const range = fmtRange(e.start, e.end)
        return (
          <li key={i} className="timeline__item">
            <span className={cx('timeline__dot', i === 0 && 'is-current')} aria-hidden />
            <div className="timeline__head">
              <div>
                <p className="timeline__title">{e.title}</p>
                <p className="timeline__company">{e.company}</p>
              </div>
              <div className="timeline__when">
                {range && <span>{range}</span>}
                {e.duration_years !== null && <span className="muted">{fmtYears(e.duration_years)}</span>}
              </div>
            </div>
            {e.highlights.length > 0 && (
              <ul className="bullets bullets--tight">
                {e.highlights.map((h, j) => (
                  <li key={j}>{h}</li>
                ))}
              </ul>
            )}
            {e.technologies.length > 0 && (
              <ChipList items={e.technologies} max={10} variantFor={(t) => skillVariant(t, highlight)} />
            )}
          </li>
        )
      })}
    </ol>
  )
}

export function ResumeView({
  resume,
  highlight,
  showHeader,
}: {
  resume: ResumeSchema
  highlight?: SkillHighlight
  showHeader?: boolean
}) {
  return (
    <div className="doc-view resume-view">
      {showHeader && (
        <div className="doc-view__header">
          <h3 className="doc-view__title">{resume.name || 'Unnamed candidate'}</h3>
          {resume.headline && <p className="doc-view__subtitle">{resume.headline}</p>}
          <ResumeHeaderMeta resume={resume} />
        </div>
      )}
      <div className="resume-view__grid">
        <div className="resume-view__main">
          {resume.summary && (
            <div className="doc-block">
              <h4 className="doc-block__title">Summary</h4>
              <p className="prose">{resume.summary}</p>
            </div>
          )}
          <div className="doc-block">
            <h4 className="doc-block__title">
              Experience <span className="count">{resume.experience.length}</span>
            </h4>
            <ExperienceTimeline items={resume.experience} highlight={highlight} />
          </div>
          {resume.projects.length > 0 && (
            <div className="doc-block">
              <h4 className="doc-block__title">
                Projects <span className="count">{resume.projects.length}</span>
              </h4>
              <div className="projects">
                {resume.projects.map((p, i) => (
                  <div key={i} className="project">
                    <p className="project__name">{p.name}</p>
                    <p className="project__desc">{p.description}</p>
                    <ChipList items={p.technologies} max={8} variantFor={(t) => skillVariant(t, highlight)} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <aside className="resume-view__side">
          <div className="doc-block">
            <h4 className="doc-block__title">
              Skills <span className="count">{resume.skills.length}</span>
            </h4>
            <SkillGroups skills={resume.skills} highlight={highlight} />
          </div>
          <div className="doc-block">
            <h4 className="doc-block__title">Education</h4>
            {resume.education.length ? (
              <ul className="plain-list">
                {resume.education.map((ed, i) => (
                  <li key={i} className="edu">
                    <GraduationCap size={16} aria-hidden />
                    <div>
                      <p className="edu__degree">
                        {ed.degree}
                        {ed.field ? `, ${ed.field}` : ''}
                      </p>
                      <p className="muted small">
                        {ed.institution}
                        {ed.year ? ` (${ed.year})` : ''}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted small">None listed.</p>
            )}
          </div>
          <div className="doc-block">
            <h4 className="doc-block__title">Certifications</h4>
            {resume.certifications.length ? (
              <ul className="plain-list">
                {resume.certifications.map((c, i) => (
                  <li key={i} className="edu">
                    <Award size={16} aria-hidden />
                    <p>{c}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted small">None listed.</p>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
