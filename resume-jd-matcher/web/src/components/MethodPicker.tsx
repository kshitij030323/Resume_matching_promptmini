import { FAMILY_LABEL, FAMILY_ORDER } from '../lib/format'
import type { MethodInfo } from '../types'
import { FamilySwatch, cx } from './ui'

/** Method chips grouped by family, so the static/contextual/hybrid/lexical taxonomy is visible. */
export function MethodPicker({
  methods,
  value,
  onChange,
}: {
  methods: MethodInfo[]
  value: string | null
  onChange: (key: string) => void
}) {
  const groups = FAMILY_ORDER.map((f) => ({ family: f, items: methods.filter((m) => m.family === f) })).filter(
    (g) => g.items.length,
  )
  const unknown = methods.filter((m) => !FAMILY_ORDER.includes(m.family))
  return (
    <div className="method-picker" role="group" aria-label="Ranking method">
      {groups.map((g) => (
        <div key={g.family} className="method-picker__group">
          <span className="method-picker__family">
            <FamilySwatch family={g.family} />
            {FAMILY_LABEL[g.family]}
          </span>
          <div className="method-picker__items">
            {g.items.map((m) => (
              <button
                key={m.key}
                type="button"
                className={cx('method-chip', `fam--${m.family}`)}
                aria-pressed={value === m.key}
                title={m.description}
                onClick={() => onChange(m.key)}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
      ))}
      {unknown.map((m) => (
        <button key={m.key} type="button" className="method-chip" aria-pressed={value === m.key} onClick={() => onChange(m.key)}>
          {m.label}
        </button>
      ))}
    </div>
  )
}

export function defaultMethod(methods: MethodInfo[] | null) {
  if (!methods?.length) return null
  return (methods.find((m) => m.key === 'hybrid') ?? methods.find((m) => m.family === 'hybrid') ?? methods[0]).key
}
