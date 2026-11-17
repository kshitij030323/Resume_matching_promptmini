import { useEffect, useState } from 'react'
import { CircleCheck, ExternalLink, Eye, EyeOff, KeyRound, Trash2 } from 'lucide-react'
import { api, errorMessage } from '../api'
import { useSettings } from '../settings'
import type { LlmStatus } from '../types'
import { Button, ErrorState, ModeBadge, Notice, Skeleton, Switch } from './ui'

/** Settings panel: paste a Gemini API key, verify it with Google, pick the model. */
export function LlmPanel() {
  const { refreshHealth } = useSettings()
  const [status, setStatus] = useState<LlmStatus | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [key, setKey] = useState('')
  const [show, setShow] = useState(false)
  const [remember, setRemember] = useState(true)
  const [busy, setBusy] = useState<null | 'save' | 'model' | 'remove'>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)

  const load = () => {
    setLoadError(null)
    api
      .llm()
      .then(setStatus)
      .catch((err) => setLoadError(errorMessage(err)))
  }
  useEffect(load, [])

  const apply = async (kind: 'save' | 'model' | 'remove', fn: () => Promise<LlmStatus>, note: (s: LlmStatus) => string) => {
    setBusy(kind)
    setError(null)
    setSaved(null)
    try {
      const s = await fn()
      setStatus(s)
      setSaved(note(s))
      if (kind === 'save') setKey('')
      refreshHealth()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  const saveKey = () =>
    apply('save', () => api.saveLlm({ gemini_api_key: key.trim(), remember }), (s) => `Key verified. Gemini is connected and using ${s.gemini.model}.`)
  const changeModel = (model: string) =>
    apply('model', () => api.saveLlm({ gemini_model: model, remember: status?.gemini.remembered ?? remember }), (s) => `Now using ${s.gemini.model}.`)
  const removeKey = () => apply('remove', () => api.removeGeminiKey(), () => 'Key removed from this server.')

  const g = status?.gemini

  return (
    <section className="panel panel--pad stack llm-panel">
      <div className="row-between">
        <h2 className="panel__title">Language model</h2>
        {status && <ModeBadge mode={status.enabled ? 'llm' : 'offline'} model={status.model} />}
      </div>

      {loadError ? (
        <ErrorState compact title="Couldn't read the LLM settings" message={loadError} onRetry={load} />
      ) : !status ? (
        <div className="stack-sm">
          <Skeleton height={18} width="70%" />
          <Skeleton height={42} />
        </div>
      ) : (
        <>
          <p className="muted small">
            {status.enabled
              ? `Extraction and skill-gap reports run on ${status.provider_label} (${status.model}).`
              : 'No key yet, so the offline extractor and offline skill-gap chain run. Paste a Gemini API key to switch to Gemini.'}
          </p>

          {g?.configured && (
            <div className="llm-key-row">
              <KeyRound size={16} aria-hidden />
              <span>
                Gemini key <code>{g.key_hint}</code>{' '}
                <span className="muted small">
                  {g.key_source === 'env' ? '(from GEMINI_API_KEY)' : g.remembered ? '(saved on this server)' : '(until the server restarts)'}
                </span>
              </span>
              {g.key_source === 'settings' && (
                <Button size="sm" variant="ghost" icon={Trash2} onClick={removeKey} loading={busy === 'remove'}>
                  Remove
                </Button>
              )}
            </div>
          )}

          {g?.configured && (g.models?.length ?? 0) > 0 && (
            <div className="field">
              <label className="field__label" htmlFor="gemini-model">
                Gemini model
              </label>
              <select
                id="gemini-model"
                className="select"
                value={g.model}
                disabled={busy !== null}
                onChange={(e) => changeModel(e.target.value)}
              >
                {!g.models!.includes(g.model) && <option value={g.model}>{g.model}</option>}
                {g.models!.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <p className="muted small">Flash models are fast and work on the free tier. Pro models are stronger but have much lower free limits.</p>
            </div>
          )}
          {g?.error && <ErrorState compact title="The saved key did not work" message={g.error} />}

          <form
            className="stack-sm"
            onSubmit={(e) => {
              e.preventDefault()
              if (key.trim()) saveKey()
            }}
          >
            <div className="field">
              <label className="field__label" htmlFor="gemini-key">
                {g?.configured ? 'Replace Gemini API key' : 'Gemini API key'}
              </label>
              <div className="input-with-action">
                <input
                  id="gemini-key"
                  className="input"
                  type={show ? 'text' : 'password'}
                  placeholder="Paste your key, e.g. AIza…"
                  value={key}
                  onChange={(e) => {
                    setKey(e.target.value)
                    setError(null)
                  }}
                  autoComplete="off"
                  spellCheck={false}
                />
                <button type="button" className="input-action" onClick={() => setShow((v) => !v)} aria-label={show ? 'Hide key' : 'Show key'}>
                  {show ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
                </button>
              </div>
              <p className="muted small">
                Get a free key at{' '}
                <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" className="icon-text">
                  aistudio.google.com/apikey <ExternalLink size={12} aria-hidden />
                </a>
                . The key goes only to this app's server and to Google, and is never shown again in full.
              </p>
            </div>
            <Switch
              checked={remember}
              onChange={setRemember}
              label="Remember on this server"
              description="Saves it to backend/storage/llm_settings.json (readable only by you). Off keeps it in memory until the server restarts."
            />
            <div className="row-gap wrap">
              <Button type="submit" variant="primary" icon={KeyRound} loading={busy === 'save'} disabled={!key.trim() || busy !== null}>
                Save &amp; verify
              </Button>
            </div>
          </form>

          {saved && (
            <Notice tone="good" icon={CircleCheck}>
              {saved}
            </Notice>
          )}
          {error && <ErrorState compact title="Not saved" message={error} />}
        </>
      )}
    </section>
  )
}
