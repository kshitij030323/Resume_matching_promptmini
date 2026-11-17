// TypeScript mirror of backend/app/schemas.py (Pydantic) plus the REST
// response envelopes described in API.md. Field names match the backend exactly.

// --------------------------------------------------------------------------
// Shared enums
// --------------------------------------------------------------------------
export type SkillCategory =
  | 'programming_language'
  | 'framework_library'
  | 'ml_ai'
  | 'data'
  | 'cloud_devops'
  | 'database'
  | 'mobile_frontend'
  | 'tool'
  | 'methodology'
  | 'soft_skill'
  | 'domain'
  | 'other'

export type Proficiency = 'beginner' | 'intermediate' | 'advanced' | 'expert' | 'unknown'
export type Seniority = 'intern' | 'junior' | 'mid' | 'senior' | 'lead' | 'principal' | 'unknown'

// --------------------------------------------------------------------------
// Resume schema
// --------------------------------------------------------------------------
export interface SkillItem {
  name: string
  category: SkillCategory
  years: number | null
  proficiency: Proficiency
}

export interface ExperienceItem {
  title: string
  company: string
  start: string | null
  end: string | null
  duration_years: number | null
  highlights: string[]
  technologies: string[]
}

export interface EducationItem {
  degree: string
  field: string | null
  institution: string
  year: number | null
}

export interface ProjectItem {
  name: string
  description: string
  technologies: string[]
}

export interface ResumeSchema {
  name: string
  email: string | null
  phone: string | null
  location: string | null
  headline: string
  summary: string
  total_years_experience: number
  seniority: Seniority
  skills: SkillItem[]
  experience: ExperienceItem[]
  education: EducationItem[]
  certifications: string[]
  projects: ProjectItem[]
}

// --------------------------------------------------------------------------
// Job description schema
// --------------------------------------------------------------------------
export interface JobSchema {
  title: string
  company: string | null
  location: string | null
  employment_type: string | null
  seniority: Seniority
  min_years_experience: number | null
  summary: string
  required_skills: string[]
  preferred_skills: string[]
  responsibilities: string[]
  education_requirement: string | null
  domain: string | null
}

// --------------------------------------------------------------------------
// Skill-gap prompt chain
// --------------------------------------------------------------------------
export type Importance = 'required' | 'preferred'
export type AssessmentStatus = 'met' | 'partial' | 'missing'
export type ExperienceFit = 'below' | 'meets' | 'exceeds'
export type Severity = 'critical' | 'moderate' | 'minor'
export type RecommendationType = 'course' | 'project' | 'certification' | 'on_the_job' | 'reading'
export type Priority = 'high' | 'medium' | 'low'
export type Verdict = 'strong_match' | 'good_match' | 'partial_match' | 'weak_match'
export type ChainMode = 'llm' | 'offline'

export interface RequirementAssessment {
  skill: string
  importance: Importance
  status: AssessmentStatus
  evidence: string
  transferable_from: string[]
}

export interface AlignmentOutput {
  assessments: RequirementAssessment[]
  experience_fit: ExperienceFit
  experience_note: string
}

export interface Strength {
  skill: string
  evidence: string
}

export interface Gap {
  skill: string
  importance: Importance
  severity: Severity
  reason: string
  transferable_from: string[]
}

export interface GapAnalysisOutput {
  strengths: Strength[]
  gaps: Gap[]
  fit_score: number
  fit_rationale: string
}

export interface Recommendation {
  skill: string
  action: string
  type: RecommendationType
  resource_hint: string
  effort_weeks: number
  priority: Priority
}

export interface RecommendationOutput {
  recommendations: Recommendation[]
  interview_questions: string[]
}

export interface ReportSynthesis {
  verdict: Verdict
  headline: string
  executive_summary: string
  hiring_recommendation: string
}

export interface ChainStep {
  step: number
  name: string
  mode: ChainMode
  model: string | null
  latency_ms: number
  output: Record<string, unknown>
}

export interface SkillGapReport {
  job_id: string
  resume_id: string
  candidate_name: string
  job_title: string
  fit_score: number
  verdict: Verdict
  headline: string
  executive_summary: string
  hiring_recommendation: string
  experience_fit: ExperienceFit
  experience_note: string
  assessments: RequirementAssessment[]
  strengths: Strength[]
  gaps: Gap[]
  recommendations: Recommendation[]
  interview_questions: string[]
  chain_trace: ChainStep[]
  generated_at: string
}

// --------------------------------------------------------------------------
// Extraction metadata
// --------------------------------------------------------------------------
export interface ExtractionMeta {
  method: ChainMode
  model: string | null
  latency_ms: number
  repaired: boolean
  warnings: string[]
}

// --------------------------------------------------------------------------
// REST envelopes (API.md)
// --------------------------------------------------------------------------
export interface GeminiStatus {
  configured: boolean
  key_source: 'settings' | 'env' | null
  key_hint: string | null
  model: string
  remembered: boolean
  /** Only on GET/PUT /api/llm */
  models?: string[]
  error?: string | null
}

export interface LlmStatus {
  enabled: boolean
  /** 'gemini' | 'anthropic' | 'none' */
  provider: string
  provider_label: string
  model: string | null
  preference: string
  disabled: boolean
  gemini: GeminiStatus
  anthropic: { configured: boolean; model: string }
}

export interface LlmSettingsUpdate {
  gemini_api_key?: string
  gemini_model?: string
  remember: boolean
}

export interface Health {
  status: string
  llm: LlmStatus
  counts: { resumes: number; jobs: number }
  vector_db: string
  methods_ready: string[]
}

export interface JobSummary {
  id: string
  title: string
  company: string | null
  location: string | null
  seniority: Seniority
  min_years_experience: number | null
  required_skills: string[]
  preferred_skills: string[]
  summary: string
}

export interface JobDetail {
  id: string
  raw_text: string
  extracted: JobSchema
  meta: ExtractionMeta
}

export interface ResumeSummary {
  id: string
  name: string
  headline: string
  location: string | null
  total_years_experience: number
  seniority: Seniority
  top_skills: string[]
}

export interface ResumeDetail {
  id: string
  raw_text: string
  extracted: ResumeSchema
  meta: ExtractionMeta
}

export type DocKind = 'resume' | 'job'

export interface ExtractRequest {
  kind: DocKind
  text: string
  save: boolean
  use_llm: boolean
}

export interface ExtractResponse {
  id: string | null
  kind: DocKind
  extracted: ResumeSchema | JobSchema
  meta: ExtractionMeta
  /** Only present on POST /api/extract/file. */
  raw_text?: string
}

export type MethodFamily = 'static' | 'contextual' | 'hybrid' | 'lexical'
export type Representation = 'structured' | 'raw'

export interface MethodInfo {
  key: string
  label: string
  family: MethodFamily
  description: string
}

export interface RankRequest {
  job_id: string
  method: string
  representation: Representation
  top_k: number
}

export interface SkillMatch {
  matched_required: string[]
  missing_required: string[]
  matched_preferred: string[]
  coverage: number
}

export type Grade = 0 | 1 | 2 | 3

export interface RankResult {
  rank: number
  resume_id: string
  name: string
  headline: string
  score: number
  similarity: number
  skills: SkillMatch
  human_grade: Grade | null
}

export interface RankResponse {
  job_id: string
  method: string
  representation: Representation
  results: RankResult[]
  ndcg_at_5: number | null
}

export interface EvaluationMethodResult {
  method: string
  label: string
  family: MethodFamily
  representation: Representation
  mean_ndcg: number
  mean_ndcg_10?: number | null
  mean_precision?: number | null
  per_job: Record<string, number | null>
}

export interface StaticVsContextual {
  static_best: number
  contextual_best: number
  delta: number
  static_method?: string
  contextual_method?: string
  static_representation?: Representation
  contextual_representation?: Representation
  /** Number of jobs where the best contextual method beats the best static one. */
  jobs_contextual_wins?: number
  jobs_ties?: number
  /** Two-sided sign-flip permutation test across jobs. */
  p_value_sign_flip?: number
}

export interface EvaluationResponse {
  k: number
  n_candidates?: number
  jobs: { id: string; title: string }[]
  results: EvaluationMethodResult[]
  best: { method: string; representation: Representation; mean_ndcg: number } | null
  static_vs_contextual: StaticVsContextual | null
  static_vs_contextual_by_representation?: Partial<Record<Representation, StaticVsContextual>>
  generated_at?: string
}

/** GET /api/labels: job_id -> resume_id -> grade. */
export type LabelsResponse = Record<string, Record<string, Grade>>

export interface LabelsUpdateResponse {
  job_id: string
  grades: Record<string, Grade>
}

export interface SkillGapRequest {
  job_id: string
  resume_id: string
  use_llm: boolean
}

export interface ShortlistRequest {
  job_id: string
  method: string
  top_n: number
  use_llm: boolean
}

export interface ShortlistResponse {
  job_id: string
  method: string
  reports: SkillGapReport[]
}
