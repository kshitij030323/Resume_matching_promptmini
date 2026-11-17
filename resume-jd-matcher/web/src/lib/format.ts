import type {
  AssessmentStatus,
  ExperienceFit,
  Grade,
  MethodFamily,
  Priority,
  RecommendationType,
  Seniority,
  Severity,
  SkillCategory,
  Verdict,
} from '../types'

export const FAMILY_ORDER: MethodFamily[] = ['static', 'contextual', 'hybrid', 'lexical']

export const FAMILY_LABEL: Record<MethodFamily, string> = {
  static: 'Static',
  contextual: 'Contextual',
  hybrid: 'Hybrid',
  lexical: 'Lexical',
}

export const FAMILY_BLURB: Record<MethodFamily, string> = {
  static: 'GloVe word vectors, averaged',
  contextual: 'Transformer sentence embeddings in ChromaDB',
  hybrid: 'Contextual similarity plus skill coverage',
  lexical: 'BM25 keyword baseline',
}

export const GRADES: Grade[] = [0, 1, 2, 3]

export const GRADE_LABEL: Record<Grade, string> = {
  0: 'Not relevant',
  1: 'Weak or adjacent',
  2: 'Good fit',
  3: 'Strong fit',
}

export const SENIORITY_LABEL: Record<Seniority, string> = {
  intern: 'Intern',
  junior: 'Junior',
  mid: 'Mid-level',
  senior: 'Senior',
  lead: 'Lead',
  principal: 'Principal',
  unknown: 'Seniority unknown',
}

export const CATEGORY_LABEL: Record<SkillCategory, string> = {
  programming_language: 'Languages',
  framework_library: 'Frameworks and libraries',
  ml_ai: 'Machine learning and AI',
  data: 'Data',
  cloud_devops: 'Cloud and DevOps',
  database: 'Databases',
  mobile_frontend: 'Mobile and frontend',
  tool: 'Tools',
  methodology: 'Methodologies',
  soft_skill: 'Soft skills',
  domain: 'Domain knowledge',
  other: 'Other',
}

export const CATEGORY_ORDER = Object.keys(CATEGORY_LABEL) as SkillCategory[]

export const VERDICT_LABEL: Record<Verdict, string> = {
  strong_match: 'Strong match',
  good_match: 'Good match',
  partial_match: 'Partial match',
  weak_match: 'Weak match',
}

/** Verdicts map onto the reserved status palette. */
export const VERDICT_TONE: Record<Verdict, 'good' | 'fair' | 'warning' | 'critical'> = {
  strong_match: 'good',
  good_match: 'fair',
  partial_match: 'warning',
  weak_match: 'critical',
}

export const SEVERITY_ORDER: Severity[] = ['critical', 'moderate', 'minor']
export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Critical',
  moderate: 'Moderate',
  minor: 'Minor',
}

export const STATUS_LABEL: Record<AssessmentStatus, string> = {
  met: 'Met',
  partial: 'Partial',
  missing: 'Missing',
}

export const EXPERIENCE_FIT_LABEL: Record<ExperienceFit, string> = {
  below: 'Below the experience bar',
  meets: 'Meets the experience bar',
  exceeds: 'Exceeds the experience bar',
}

export const REC_TYPE_LABEL: Record<RecommendationType, string> = {
  course: 'Course',
  project: 'Project',
  certification: 'Certification',
  on_the_job: 'On the job',
  reading: 'Reading',
}

export const PRIORITY_LABEL: Record<Priority, string> = {
  high: 'High priority',
  medium: 'Medium priority',
  low: 'Low priority',
}

export const CHAIN_STEPS = [
  { name: 'Requirement alignment', blurb: 'Checks each required and preferred skill against the resume.' },
  { name: 'Gap prioritisation', blurb: 'Ranks gaps by severity and scores overall fit.' },
  { name: 'Recommendations', blurb: 'Builds a learning plan and interview probes.' },
  { name: 'Report synthesis', blurb: 'Writes the verdict and summary for the hiring manager.' },
]

export function fmtScore(n: number | null | undefined, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '–'
  return n.toFixed(digits)
}

export function fmtPct(n: number | null | undefined) {
  if (n === null || n === undefined || Number.isNaN(n)) return '–'
  return `${Math.round(n * 100)}%`
}

export function fmtSigned(n: number, digits = 2) {
  const s = n.toFixed(digits)
  return n > 0 ? `+${s}` : s
}

export function fmtYears(n: number | null | undefined) {
  if (n === null || n === undefined) return '–'
  const v = Math.round(n * 10) / 10
  return `${v} ${v === 1 ? 'yr' : 'yrs'}`
}

export function fmtMs(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return '–'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function fmtMonth(v: string | null | undefined) {
  if (!v) return null
  if (v.toLowerCase() === 'present') return 'Present'
  const m = /^(\d{4})-(\d{2})/.exec(v)
  if (m) {
    const idx = Number(m[2]) - 1
    return idx >= 0 && idx < 12 ? `${MONTHS[idx]} ${m[1]}` : m[1]
  }
  return v
}

export function fmtRange(start: string | null, end: string | null) {
  const s = fmtMonth(start)
  const e = fmtMonth(end)
  if (s && e) return `${s} – ${e}`
  if (s) return `From ${s}`
  if (e) return `Until ${e}`
  return null
}

export function fmtDateTime(iso: string | null | undefined) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function humanize(s: string) {
  const t = s.replace(/_/g, ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

export function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}

export const norm = (s: string) => s.trim().toLowerCase()

/** Requirements can be alternatives joined by " / " ("Tableau / Power BI"); "CI/CD" stays whole. */
export function splitAlternatives(skill: string) {
  return skill
    .split(/\s+\/\s+/)
    .map((p) => p.trim())
    .filter(Boolean)
}

/** Normalised set of every alternative in a list of requirements. */
export function alternativesSet(skills: string[]) {
  const set = new Set<string>()
  skills.forEach((s) => {
    set.add(norm(s))
    splitAlternatives(s).forEach((p) => set.add(norm(p)))
  })
  return set
}

/** A requirement is met when any of its alternatives is in `have`. */
export function requirementMet(skill: string, have: Set<string>) {
  return have.has(norm(skill)) || splitAlternatives(skill).some((p) => have.has(norm(p)))
}

export function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`
}
