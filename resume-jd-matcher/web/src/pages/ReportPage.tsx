import { useState, type ComponentType } from 'react'
import { useParams } from 'react-router-dom'
import {
  Award,
  BookOpen,
  Briefcase,
  CircleCheck,
  CircleDashed,
  CircleX,
  Clock,
  GraduationCap,
  Hammer,
  Info,
  RefreshCw,
  TriangleExclamationPoint,
  Workflow,
} from 'lucide-react'
import { Button, ButtonLink, Chip, Collapsible, ErrorState, ModeBadge, PageHeader, Section, SkillName, Tag, VerdictPill, cx } from '../components/ui'
import { ChainProgress, JsonView, ScoreRing } from '../components/viz'
import { useAsync, useDocumentTitle, useElapsed } from '../hooks'
import { startReport } from '../lib/cache'
import {
  EXPERIENCE_FIT_LABEL,
  PRIORITY_LABEL,
  REC_TYPE_LABEL,
  SEVERITY_LABEL,
  SEVERITY_ORDER,
  STATUS_LABEL,
  fmtDateTime,
  fmtMs,
  humanize,
} from '../lib/format'
import { useSettings } from '../settings'
import type { AssessmentStatus, Gap, RecommendationType, Severity, SkillGapReport } from '../types'

type Icon = ComponentType<{ size?: number; 'aria-hidden'?: boolean; className?: string }>

const REC_ICON: Record<RecommendationType, Icon> = {
  course: GraduationCap,
  project: Hammer,
  certification: Award,
  on_the_job: Briefcase,
  reading: BookOpen,
}

const SEVERITY_ICON: Record<Severity, Icon> = {
  critical: CircleX,
  moderate: TriangleExclamationPoint,
  minor: Info,
}

const STATUS_ICON: Record<AssessmentStatus, Icon> = {
  met: CircleCheck,
  partial: CircleDashed,
  missing: CircleX,
}

function GapGroup({ severity, gaps }: { severity: Severity; gaps: Gap[] }) {
  const Ico = SEVERITY_ICON[severity]
  return (
    <div className={cx('gap-group', `sev--${severity}`)}>
      <h3 className="gap-group__title">
        <Ico size={17} aria-hidden /> {SEVERITY_LABEL[severity]} <span className="count">{gaps.length}</span>
      </h3>
      <ul className="gap-list">
        {gaps.map((g, i) => (
          <li key={`${g.skill}-${i}`} className="gap">
            <div className="gap__head">
              <span className="gap__skill">
                <SkillName name={g.skill} />
              </span>
              <Tag>{humanize(g.importance)}</Tag>
            </div>
            <p className="gap__reason">{g.reason}</p>
            {g.transferable_from.length > 0 && (
              <div className="gap__transfer">
                <span className="muted small">Transferable from</span>
                <div className="chips chips--tight">
                  {g.transferable_from.map((t) => (
                    <Chip key={t} variant="match-soft">
                      {t}
                    </Chip>
                  ))}
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ReportBody({ report }: { report: SkillGapReport }) {
  const bySeverity = SEVERITY_ORDER.map((s) => ({ s, gaps: report.gaps.filter((g) => g.severity === s) })).filter((x) => x.gaps.length)
  const chainMs = report.chain_trace.reduce((t, c) => t + (c.latency_ms || 0), 0)
  const mode = report.chain_trace[0]?.mode
  const met = report.assessments.filter((a) => a.status === 'met').length

  return (
    <>
      <section className="report-hero">
        <ScoreRing score={report.fit_score} verdict={report.verdict} size={164} />
        <div className="report-hero__text">
          <div className="meta-row">
            <VerdictPill verdict={report.verdict} />
            <Tag>{EXPERIENCE_FIT_LABEL[report.experience_fit]}</Tag>
            {mode && <ModeBadge mode={mode} model={report.chain_trace[0]?.model} />}
          </div>
          <p className="report-hero__headline">{report.headline}</p>
          <p className="prose">{report.executive_summary}</p>
        </div>
      </section>

      <div className="report-grid-2">
        <div className="report-main">
          <Section title={<>Strengths <span className="count">{report.strengths.length}</span></>}>
            {report.strengths.length ? (
              <ul className="strengths">
                {report.strengths.map((s, i) => (
                  <li key={i}>
                    <CircleCheck size={18} className="text-good" aria-hidden />
                    <div>
                      <p className="strengths__skill">
                        <span className="hl-mark">{s.skill}</span>
                      </p>
                      <p className="muted">{s.evidence}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No clear strengths against this job's requirements.</p>
            )}
          </Section>

          <Section title={<>Gaps <span className="count">{report.gaps.length}</span></>}>
            {bySeverity.length ? (
              <div className="gap-groups">
                {bySeverity.map(({ s, gaps }) => (
                  <GapGroup key={s} severity={s} gaps={gaps} />
                ))}
              </div>
            ) : (
              <p className="muted">No gaps found. The candidate covers every listed requirement.</p>
            )}
          </Section>

          <Section title={<>Learning plan <span className="count">{report.recommendations.length}</span></>}>
            {report.recommendations.length ? (
              <div className="rec-grid">
                {report.recommendations.map((r, i) => {
                  const Ico = REC_ICON[r.type] ?? BookOpen
                  return (
                    <article key={i} className={cx('rec', `prio--${r.priority}`)}>
                      <div className="rec__head">
                        <span className="rec__icon" aria-hidden>
                          <Ico size={18} />
                        </span>
                        <div>
                          <p className="rec__skill">
                            <SkillName name={r.skill} />
                          </p>
                          <p className="muted small">{REC_TYPE_LABEL[r.type] ?? humanize(r.type)}</p>
                        </div>
                      </div>
                      <p className="rec__action">{r.action}</p>
                      {r.resource_hint && <p className="rec__hint">{r.resource_hint}</p>}
                      <div className="rec__foot">
                        <span className="icon-text">
                          <Clock size={14} aria-hidden />
                          {r.effort_weeks} {r.effort_weeks === 1 ? 'week' : 'weeks'}
                        </span>
                        <span className={cx('prio', `prio--${r.priority}`)}>{PRIORITY_LABEL[r.priority]}</span>
                      </div>
                    </article>
                  )
                })}
              </div>
            ) : (
              <p className="muted">No recommendations.</p>
            )}
          </Section>

          <Section title="Interview questions">
            {report.interview_questions.length ? (
              <ol className="questions">
                {report.interview_questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ol>
            ) : (
              <p className="muted">No questions suggested.</p>
            )}
          </Section>
        </div>

        <aside className="report-side">
          <div className="callout">
            <p className="callout__title">Hiring recommendation</p>
            <p>{report.hiring_recommendation}</p>
          </div>
          <div className="panel panel--pad">
            <h2 className="panel__title">Experience</h2>
            <p className="small">
              <strong>{EXPERIENCE_FIT_LABEL[report.experience_fit]}.</strong> {report.experience_note}
            </p>
          </div>
          <div className="panel panel--pad">
            <div className="row-between">
              <h2 className="panel__title">Requirement checklist</h2>
              <span className="muted small num">
                {met}/{report.assessments.length} met
              </span>
            </div>
            <ul className="checklist">
              {report.assessments.map((a, i) => {
                const Ico = STATUS_ICON[a.status]
                return (
                  <li key={i} className={cx('checklist__item', `st--${a.status}`)} title={a.evidence}>
                    <Ico size={16} aria-hidden />
                    <span className="checklist__skill">
                      <SkillName name={a.skill} />
                    </span>
                    <span className="checklist__status">
                      {STATUS_LABEL[a.status]}
                      {a.importance === 'preferred' && <span className="muted">, preferred</span>}
                    </span>
                    {a.evidence && a.evidence !== 'No evidence' && <p className="checklist__evidence">{a.evidence}</p>}
                  </li>
                )
              })}
            </ul>
          </div>
        </aside>
      </div>

      <Collapsible
        className="collapsible--panel chain-trace"
        summary={
          <span className="icon-text">
            <Workflow size={18} aria-hidden /> Prompt chain trace
          </span>
        }
        meta={`${report.chain_trace.length} steps, ${fmtMs(chainMs)}`}
      >
        <ol className="trace">
          {report.chain_trace.map((step) => (
            <li key={step.step} className="trace__step">
              <span className="step-num">{step.step}</span>
              <div className="trace__body">
                <div className="trace__head">
                  <p className="trace__name">{step.name}</p>
                  <ModeBadge mode={step.mode} model={step.model} />
                  {step.model && <span className="muted small">{step.model}</span>}
                  <span className="muted small num">{fmtMs(step.latency_ms)}</span>
                </div>
                <Collapsible summary="Output JSON" className="collapsible--inline">
                  <JsonView value={step.output} maxHeight={360} />
                </Collapsible>
              </div>
            </li>
          ))}
        </ol>
      </Collapsible>
      {report.generated_at && <p className="footnote">Generated {fmtDateTime(report.generated_at)}.</p>}
    </>
  )
}

export default function ReportPage() {
  const { jobId = '', resumeId = '' } = useParams()
  const { useLlm } = useSettings()
  const [attempt, setAttempt] = useState(0)
  const [startedAt, setStartedAt] = useState<number | null>(null)

  const run = useAsync(
    () => {
      const task = startReport(jobId, resumeId, useLlm, attempt)
      setStartedAt(task.startedAt)
      return task.promise
    },
    [jobId, resumeId, useLlm, attempt],
  )
  const seconds = useElapsed(run.loading, startedAt)
  const report = run.data
  useDocumentTitle(report ? `Report: ${report.candidate_name}` : 'Skill-gap report')

  return (
    <>
      <PageHeader
        back={{ to: `/candidates/${encodeURIComponent(resumeId)}?job=${encodeURIComponent(jobId)}`, label: 'Back to candidate' }}
        title={report ? report.candidate_name : 'Skill-gap report'}
        lede={
          report ? (
            <>
              Skill-gap report for <strong>{report.job_title}</strong>
            </>
          ) : (
            <>
              Candidate <span className="id-tag">{resumeId}</span> against job <span className="id-tag">{jobId}</span>
            </>
          )
        }
        actions={
          <>
            <ButtonLink to={`/jobs/${encodeURIComponent(jobId)}`}>Job ranking</ButtonLink>
            <Button icon={RefreshCw} onClick={() => setAttempt((a) => a + 1)} disabled={run.loading}>
              Regenerate
            </Button>
          </>
        }
      />
      {run.loading ? (
        <ChainProgress
          title="Running the skill-gap prompt chain"
          seconds={seconds}
          detail="With Gemini or Claude this usually takes under a minute; the offline chain is near-instant."
        />
      ) : run.error ? (
        <ErrorState title="Couldn't generate the report" message={run.error} onRetry={() => setAttempt((a) => a + 1)} />
      ) : report ? (
        <ReportBody report={report} />
      ) : null}
    </>
  )
}
