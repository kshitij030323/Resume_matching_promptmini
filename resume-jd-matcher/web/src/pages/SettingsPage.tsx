import { useEffect, useState } from 'react'
import { CircleCheck, Database, Monitor, Moon, Plug, RefreshCw, RotateCcw, Sun } from 'lucide-react'
import { api, describeBase, errorMessage, normaliseBase } from '../api'
import { Button, ErrorState, FamilySwatch, ModeBadge, Notice, PageHeader, Segmented, Skeleton, Switch } from '../components/ui'
import { LlmPanel } from '../components/LlmPanel'
import { useDocumentTitle } from '../hooks'
import { useSettings, type ThemePref } from '../settings'
import type { Health } from '../types'

type TestState = { status: 'idle' } | { status: 'running' } | { status: 'ok'; data: Health; ms: number } | { status: 'error'; message: string }

function isValidBase(v: string) {
  if (!v.trim()) return true
  try {
    const u = new URL(normaliseBase(v))
    return u.protocol === 'http:' || u.protocol === 'https:'
  } catch {
    return false
  }
}

export default function SettingsPage() {
  useDocumentTitle('Settings')
  const { apiBase, setApiBaseUrl, health, refreshHealth, theme, setTheme, useLlm, setUseLlm, methods } = useSettings()
  const [draft, setDraft] = useState(apiBase)
  const [test, setTest] = useState<TestState>({ status: 'idle' })
  const [savedNote, setSavedNote] = useState(false)

  useEffect(() => setDraft(apiBase), [apiBase])

  const valid = isValidBase(draft)
  const changed = normaliseBase(draft) !== apiBase

  const runTest = async () => {
    setTest({ status: 'running' })
    // Test the address in the field, even before it is saved.
    const started = performance.now()
    try {
      const data = await api.health({ base: normaliseBase(draft) })
      setTest({ status: 'ok', data, ms: Math.round(performance.now() - started) })
    } catch (err) {
      setTest({ status: 'error', message: errorMessage(err) })
    }
  }

  const save = () => {
    if (!valid) return
    setApiBaseUrl(draft)
    setSavedNote(true)
    window.setTimeout(() => setSavedNote(false), 2500)
  }

  const h = health.status === 'ok' ? health.data : null
  const familyOf = (key: string) => methods?.find((m) => m.key === key)

  return (
    <>
      <PageHeader title="Settings" lede="Add your Gemini API key, choose where the app finds the API, and check the server status." />

      <div className="settings-grid">
        <LlmPanel />

        <section className="panel panel--pad stack">
          <h2 className="panel__title">API address</h2>
          <div className="field">
            <label className="field__label" htmlFor="api-base">
              Base URL
            </label>
            <input
              id="api-base"
              className="input"
              type="url"
              inputMode="url"
              placeholder="Leave empty to use this site's /api"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value)
                setTest({ status: 'idle' })
              }}
              aria-invalid={!valid}
              spellCheck={false}
            />
            {!valid ? (
              <p className="small text-critical">Enter a full address starting with http:// or https://, or leave it empty.</p>
            ) : (
              <p className="muted small">
                Empty uses relative <code>/api</code> paths: the dev server proxies them to the backend (<code>VITE_API_TARGET</code>, default <code>http://127.0.0.1:8010</code>), and in
                production FastAPI serves both. Set a full address such as <code>http://192.168.1.20:8010</code> only to reach another
                machine (that server must allow CORS).
              </p>
            )}
          </div>
          <div className="row-gap wrap">
            <Button variant="primary" onClick={save} disabled={!valid || !changed}>
              Save address
            </Button>
            <Button icon={Plug} onClick={runTest} loading={test.status === 'running'} disabled={!valid}>
              Test connection
            </Button>
            {apiBase && (
              <Button variant="ghost" icon={RotateCcw} onClick={() => setApiBaseUrl('')}>
                Reset to default
              </Button>
            )}
          </div>
          {savedNote && (
            <Notice tone="good" icon={CircleCheck}>
              Saved. Requests now go to {describeBase()}.
            </Notice>
          )}
          {test.status === 'ok' && (
            <Notice tone="good" icon={CircleCheck}>
              Connected to {describeBase(normaliseBase(draft))} in {test.ms} ms. {test.data.counts.resumes} resumes and {test.data.counts.jobs} jobs.
            </Notice>
          )}
          {test.status === 'error' && <ErrorState compact title="Connection failed" message={test.message} />}
        </section>

        <section className="panel panel--pad stack">
          <div className="row-between">
            <h2 className="panel__title">Server status</h2>
            <Button size="sm" variant="ghost" icon={RefreshCw} onClick={refreshHealth} loading={health.status === 'loading'}>
              Refresh
            </Button>
          </div>
          {health.status === 'error' ? (
            <ErrorState compact title="API unreachable" message={health.error} onRetry={refreshHealth} />
          ) : !h ? (
            <div className="stack-sm">
              <Skeleton height={18} width="60%" />
              <Skeleton height={60} />
              <Skeleton height={18} width="80%" />
            </div>
          ) : (
            <>
              <dl className="status-list">
                <div>
                  <dt>Connection</dt>
                  <dd>
                    <span className="conn-inline">
                      <span className="conn__dot conn__dot--ok" aria-hidden /> {h.status === 'ok' ? 'Online' : h.status}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Extraction and reports</dt>
                  <dd>
                    <ModeBadge mode={h.llm.enabled ? 'llm' : 'offline'} model={h.llm.model} />
                    <span className="muted small">
                      {h.llm.enabled
                        ? ` ${h.llm.model ?? h.llm.provider}`
                        : ' No LLM key configured, so the heuristic extractor and offline chain run.'}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Vector database</dt>
                  <dd className="icon-text">
                    <Database size={14} aria-hidden /> {h.vector_db}
                  </dd>
                </div>
              </dl>
              <div className="counts">
                <div>
                  <p className="counts__num num">{h.counts.resumes}</p>
                  <p className="muted small">resumes</p>
                </div>
                <div>
                  <p className="counts__num num">{h.counts.jobs}</p>
                  <p className="muted small">job descriptions</p>
                </div>
                <div>
                  <p className="counts__num num">{h.methods_ready.length}</p>
                  <p className="muted small">methods ready</p>
                </div>
              </div>
              {h.methods_ready.length > 0 && (
                <div className="chips">
                  {h.methods_ready.map((k) => {
                    const m = familyOf(k)
                    return (
                      <span key={k} className="chip chip--plain" title={m?.description}>
                        {m && <FamilySwatch family={m.family} />}
                        {m?.label ?? k}
                      </span>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </section>

        <section className="panel panel--pad stack">
          <h2 className="panel__title">Preferences</h2>
          <div className="field">
            <span className="field__label">Appearance</span>
            <Segmented<ThemePref>
              ariaLabel="Appearance"
              value={theme}
              onChange={setTheme}
              options={[
                { value: 'system', label: <span className="icon-text"><Monitor size={14} aria-hidden /> System</span> },
                { value: 'light', label: <span className="icon-text"><Sun size={14} aria-hidden /> Light</span> },
                { value: 'dark', label: <span className="icon-text"><Moon size={14} aria-hidden /> Dark</span> },
              ]}
            />
          </div>
          <Switch
            checked={useLlm}
            onChange={setUseLlm}
            label="Use the LLM when available"
            description="Applies to skill-gap reports, shortlists and pasted-text extraction. Turn off to run the faster offline versions."
          />
        </section>
      </div>
    </>
  )
}
