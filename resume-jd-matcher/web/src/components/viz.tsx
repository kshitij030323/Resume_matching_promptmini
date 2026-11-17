import { useMemo, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { CHAIN_STEPS, VERDICT_TONE } from '../lib/format'
import type { MethodFamily, Verdict } from '../types'
import { cx } from './ui'

// ---------------------------------------------------------------------------
// Score bar: thin track, rounded data end, coloured by method family.
// ---------------------------------------------------------------------------
export function ScoreBar({ value, max = 1, family, label }: { value: number; max?: number; family: MethodFamily; label?: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(1, value / max)) * 100 : 0
  return (
    <div className="scorebar" role="meter" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label ?? 'Score'}>
      <span className={cx('scorebar__fill', `fam-bg--${family}`)} style={{ width: `${pct}%` }} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Fit-score ring (inline SVG).
// ---------------------------------------------------------------------------
export function ScoreRing({ score, verdict, size = 148 }: { score: number; verdict: Verdict; size?: number }) {
  const stroke = Math.max(8, Math.round(size / 13))
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const clamped = Math.max(0, Math.min(100, score))
  const offset = c * (1 - clamped / 100)
  return (
    <div
      className={cx('ring', `tone--${VERDICT_TONE[verdict]}`)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Fit score ${Math.round(clamped)} out of 100`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle className="ring__track" cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} fill="none" />
        <circle
          className="ring__value"
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          style={{ ['--ring-c' as string]: c }}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="ring__label">
        <span className="ring__num" style={{ fontSize: size * 0.3 }}>
          {Math.round(clamped)}
        </span>
        {size >= 110 && <span className="ring__unit">fit score</span>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pretty-printed, syntax-coloured JSON with a copy button.
// ---------------------------------------------------------------------------
const TOKEN_RE = /("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g

function highlightJson(json: string) {
  const out: { text: string; cls?: string }[] = []
  let last = 0
  for (const m of json.matchAll(TOKEN_RE)) {
    const idx = m.index ?? 0
    if (idx > last) out.push({ text: json.slice(last, idx) })
    const tok = m[0]
    let cls = 'j-num'
    if (tok.startsWith('"')) cls = m[2] ? 'j-key' : 'j-str'
    else if (tok === 'true' || tok === 'false') cls = 'j-bool'
    else if (tok === 'null') cls = 'j-null'
    out.push({ text: tok, cls })
    last = idx + tok.length
  }
  if (last < json.length) out.push({ text: json.slice(last) })
  return out
}

export function JsonView({ value, maxHeight = 420 }: { value: unknown; maxHeight?: number }) {
  const text = useMemo(() => JSON.stringify(value, null, 2) ?? 'null', [value])
  const tokens = useMemo(() => highlightJson(text), [text])
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard blocked: ignore */
    }
  }
  return (
    <div className="json">
      <button type="button" className="json__copy" onClick={copy} aria-label="Copy JSON">
        {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
        {copied ? 'Copied' : 'Copy'}
      </button>
      <pre style={{ maxHeight }}>
        <code>
          {tokens.map((t, i) =>
            t.cls ? (
              <span key={i} className={t.cls}>
                {t.text}
              </span>
            ) : (
              t.text
            ),
          )}
        </code>
      </pre>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Progress panel for the slow prompt chain. The API returns only when every
// step is done, so this shows the pipeline and elapsed time, not fake progress.
// ---------------------------------------------------------------------------
export function ChainProgress({ title, seconds, detail }: { title: string; seconds: number; detail?: string }) {
  return (
    <div className="chain-progress" role="status" aria-live="polite">
      <div className="chain-progress__head">
        <p className="chain-progress__title">{title}</p>
        <span className="chain-progress__time">{seconds} s</span>
      </div>
      <div className="indeterminate" aria-hidden>
        <span />
      </div>
      <ol className="chain-progress__steps">
        {CHAIN_STEPS.map((s, i) => (
          <li key={s.name}>
            <span className="step-num">{i + 1}</span>
            <span>
              <strong>{s.name}</strong>
              <span className="muted"> {s.blurb}</span>
            </span>
          </li>
        ))}
      </ol>
      {detail && <p className="muted small">{detail}</p>}
    </div>
  )
}
