import {
  Fragment,
  useId,
  useState,
  type ButtonHTMLAttributes,
  type ComponentType,
  type ReactNode,
} from 'react'
import { Link, type LinkProps } from 'react-router-dom'
import { ArrowLeft, ChevronDown, Cpu, LoaderCircle, RefreshCw, Sparkles, TriangleExclamationPoint } from 'lucide-react'
import { FAMILY_LABEL, GRADE_LABEL, VERDICT_LABEL, VERDICT_TONE, splitAlternatives } from '../lib/format'
import type { ChainMode, Grade, MethodFamily, Verdict } from '../types'

type IconType = ComponentType<{ size?: number | string; strokeWidth?: number | string; className?: string; 'aria-hidden'?: boolean }>

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ')
}

// ---------------------------------------------------------------------------
// Page scaffolding
// ---------------------------------------------------------------------------
export function PageHeader({
  title,
  lede,
  actions,
  back,
  children,
}: {
  title: ReactNode
  lede?: ReactNode
  actions?: ReactNode
  back?: { to: string; label: string }
  children?: ReactNode
}) {
  return (
    <header className="page-header">
      {back && (
        <Link className="back-link" to={back.to}>
          <ArrowLeft size={16} aria-hidden /> {back.label}
        </Link>
      )}
      <div className="page-header__row">
        <div className="page-header__text">
          <h1 className="page-title">{title}</h1>
          {lede && <p className="page-lede">{lede}</p>}
        </div>
        {actions && <div className="page-header__actions">{actions}</div>}
      </div>
      {children}
    </header>
  )
}

export function Section({
  title,
  aside,
  children,
  className,
  id,
}: {
  title: ReactNode
  aside?: ReactNode
  children: ReactNode
  className?: string
  id?: string
}) {
  return (
    <section className={cx('section', className)} id={id}>
      <div className="section__head">
        <h2 className="section__title">{title}</h2>
        {aside && <div className="section__aside">{aside}</div>}
      </div>
      {children}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Buttons
// ---------------------------------------------------------------------------
type Variant = 'primary' | 'secondary' | 'ghost'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: 'sm' | 'md' | 'lg'
  icon?: IconType
  loading?: boolean
}

export function Button({ variant = 'secondary', size = 'md', icon: Icon, loading, children, className, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      className={cx('btn', `btn--${variant}`, `btn--${size}`, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <LoaderCircle className="spin" size={16} aria-hidden /> : Icon ? <Icon size={16} aria-hidden /> : null}
      {children}
    </button>
  )
}

export function ButtonLink({
  variant = 'secondary',
  size = 'md',
  icon: Icon,
  children,
  className,
  ...rest
}: LinkProps & { variant?: Variant; size?: 'sm' | 'md' | 'lg'; icon?: IconType }) {
  return (
    <Link className={cx('btn', `btn--${variant}`, `btn--${size}`, className)} {...rest}>
      {Icon && <Icon size={16} aria-hidden />}
      {children}
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Chips
// ---------------------------------------------------------------------------
/** Renders "A / B / C" alternatives so the chip can wrap between options. */
export function SkillName({ name }: { name: string }) {
  const parts = splitAlternatives(name)
  if (parts.length < 2) return <>{name}</>
  return (
    <span className="alts">
      {parts.map((p, i) => (
        <Fragment key={i}>
          {i > 0 && (
            <>
              <span className="alts__or" aria-hidden>
                /
              </span>
              <span className="sr-only"> or </span>
            </>
          )}
          <span className="alts__part">{p}</span>
        </Fragment>
      ))}
    </span>
  )
}

export function altTitle(name: string) {
  const parts = splitAlternatives(name)
  return parts.length > 1 ? `Any of: ${parts.join(', ')}` : undefined
}

export type ChipVariant = 'plain' | 'required' | 'preferred' | 'match' | 'match-soft' | 'missing'

export function Chip({ children, variant = 'plain', title }: { children: ReactNode; variant?: ChipVariant; title?: string }) {
  return (
    <span className={cx('chip', `chip--${variant}`)} title={title}>
      {children}
    </span>
  )
}

export function ChipList({
  items,
  variant = 'plain',
  max,
  empty,
  variantFor,
  expandable = true,
}: {
  items: string[]
  variant?: ChipVariant
  max?: number
  empty?: ReactNode
  variantFor?: (item: string) => ChipVariant
  /** Set false inside links: renders the overflow count as text, not a button. */
  expandable?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  if (!items.length) return empty ? <p className="muted small">{empty}</p> : null
  const limit = max && !expanded ? max : items.length
  const shown = items.slice(0, limit)
  const hidden = items.length - shown.length
  return (
    <div className="chips">
      {shown.map((s, i) => (
        <Chip key={`${s}-${i}`} variant={variantFor ? variantFor(s) : variant} title={altTitle(s)}>
          <SkillName name={s} />
        </Chip>
      ))}
      {hidden > 0 && !expandable && <span className="chip chip--more">+{hidden}</span>}
      {hidden > 0 && expandable && (
        <button
          type="button"
          className="chip chip--more"
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            setExpanded(true)
          }}
        >
          +{hidden} more
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Segmented control and switch
// ---------------------------------------------------------------------------
export interface SegOption<T extends string | number> {
  value: T
  label: ReactNode
  title?: string
  className?: string
}

export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  ariaLabel,
  size = 'md',
  className,
}: {
  options: SegOption<T>[]
  value: T | null
  onChange: (v: T) => void
  ariaLabel: string
  size?: 'sm' | 'md'
  className?: string
}) {
  return (
    <div className={cx('seg', `seg--${size}`, className)} role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          className={cx('seg__btn', o.className)}
          aria-pressed={value === o.value}
          title={o.title}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: ReactNode
  description?: ReactNode
  disabled?: boolean
}) {
  const id = useId()
  return (
    <label className={cx('switch', disabled && 'is-disabled')} htmlFor={id}>
      <input
        id={id}
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="switch__track" aria-hidden>
        <span className="switch__thumb" />
      </span>
      <span className="switch__text">
        <span className="switch__label">{label}</span>
        {description && <span className="switch__desc">{description}</span>}
      </span>
    </label>
  )
}

// ---------------------------------------------------------------------------
// Loading, empty and error states
// ---------------------------------------------------------------------------
export function Skeleton({ width = '100%', height = 14, radius = 6, className }: { width?: number | string; height?: number | string; radius?: number; className?: string }) {
  return <span className={cx('skeleton', className)} style={{ width, height, borderRadius: radius }} aria-hidden />
}

export function SkeletonRows({ rows = 5, height = 64 }: { rows?: number; height?: number }) {
  return (
    <div className="skeleton-rows" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton-row" key={i} style={{ minHeight: height }}>
          <Skeleton width={36} height={36} radius={10} />
          <div className="skeleton-row__lines">
            <Skeleton width={`${55 - (i % 3) * 10}%`} height={14} />
            <Skeleton width={`${80 - (i % 2) * 20}%`} height={11} />
          </div>
        </div>
      ))}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner" role="status">
      <LoaderCircle className="spin" size={18} aria-hidden />
      {label && <span>{label}</span>}
    </span>
  )
}

export function ErrorState({
  title = "Couldn't load this",
  message,
  onRetry,
  compact,
}: {
  title?: string
  message: string
  onRetry?: () => void
  compact?: boolean
}) {
  return (
    <div className={cx('state state--error', compact && 'state--compact')} role="alert">
      <TriangleExclamationPoint className="state__icon" size={compact ? 18 : 22} aria-hidden />
      <div className="state__body">
        <p className="state__title">{title}</p>
        <p className="state__msg">{message}</p>
        {onRetry && (
          <Button size="sm" icon={RefreshCw} onClick={onRetry}>
            Try again
          </Button>
        )}
      </div>
    </div>
  )
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon?: IconType
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="state state--empty">
      {Icon && <Icon className="state__icon" size={22} aria-hidden />}
      <div className="state__body">
        <p className="state__title">{title}</p>
        {children && <div className="state__msg">{children}</div>}
        {action}
      </div>
    </div>
  )
}

export function Notice({ tone = 'info', children, icon: Icon }: { tone?: 'info' | 'good' | 'warning'; children: ReactNode; icon?: IconType }) {
  return (
    <div className={cx('notice', `notice--${tone}`)}>
      {Icon && <Icon size={16} aria-hidden />}
      <div>{children}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Domain badges
// ---------------------------------------------------------------------------
export function GradeBadge({ grade, size = 'md', showLabel }: { grade: Grade | null | undefined; size?: 'sm' | 'md'; showLabel?: boolean }) {
  const has = grade !== null && grade !== undefined
  const title = has ? `Human grade ${grade}: ${GRADE_LABEL[grade]}` : 'No human grade yet'
  return (
    <span className="grade-wrap" title={title}>
      <span className={cx('grade', `grade--${size}`, has ? `grade--g${grade}` : 'grade--none')} aria-label={title}>
        {has ? grade : '–'}
      </span>
      {showLabel && <span className="grade-wrap__label">{has ? GRADE_LABEL[grade] : 'Not graded'}</span>}
    </span>
  )
}

export function FamilySwatch({ family }: { family: MethodFamily }) {
  return <span className={cx('swatch', `fam-bg--${family}`)} aria-hidden />
}

export function FamilyTag({ family }: { family: MethodFamily }) {
  return (
    <span className="family-tag">
      <FamilySwatch family={family} />
      {FAMILY_LABEL[family]}
    </span>
  )
}

/** "Gemini" / "Claude" from a model id such as gemini-2.5-flash or claude-opus-5-5. */
export function providerName(model?: string | null) {
  const m = (model ?? '').toLowerCase()
  if (m.startsWith('gemini')) return 'Gemini'
  if (m.startsWith('claude')) return 'Claude'
  return 'LLM'
}

export function ModeBadge({ mode, model }: { mode: ChainMode; model?: string | null }) {
  const isLlm = mode === 'llm'
  return (
    <span className={cx('mode-badge', isLlm ? 'mode-badge--llm' : 'mode-badge--offline')} title={isLlm && model ? model : undefined}>
      {isLlm ? <Sparkles size={13} aria-hidden /> : <Cpu size={13} aria-hidden />}
      {isLlm ? providerName(model) : 'Offline'}
    </span>
  )
}

export function VerdictPill({ verdict, size = 'md' }: { verdict: Verdict; size?: 'sm' | 'md' }) {
  return <span className={cx('verdict', `tone--${VERDICT_TONE[verdict]}`, `verdict--${size}`)}>{VERDICT_LABEL[verdict]}</span>
}

export function Tag({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span className="tag" title={title}>
      {children}
    </span>
  )
}

export function IconText({ icon: Icon, children }: { icon: IconType; children: ReactNode }) {
  return (
    <span className="icon-text">
      <Icon size={14} aria-hidden />
      {children}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Collapsible block built on <details>
// ---------------------------------------------------------------------------
export function Collapsible({
  summary,
  meta,
  children,
  defaultOpen,
  className,
}: {
  summary: ReactNode
  meta?: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  className?: string
}) {
  const [open, setOpen] = useState(!!defaultOpen)
  return (
    <details className={cx('collapsible', className)} open={open} onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>
        <ChevronDown className="collapsible__chev" size={18} aria-hidden />
        <span className="collapsible__summary">{summary}</span>
        {meta && <span className="collapsible__meta">{meta}</span>}
      </summary>
      {open && <div className="collapsible__body">{children}</div>}
    </details>
  )
}
