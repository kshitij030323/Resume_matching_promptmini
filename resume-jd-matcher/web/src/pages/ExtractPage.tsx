import { useEffect, useRef, useState, type DragEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Braces, FileText, ScanText, Trash, TriangleExclamationPoint, Upload, Wand } from 'lucide-react'
import { api, errorMessage, isAbort } from '../api'
import { JobView, ResumeView } from '../components/DocViews'
import { Button, Collapsible, EmptyState, ErrorState, ModeBadge, Notice, PageHeader, Segmented, Switch, Tag, cx } from '../components/ui'
import { JsonView } from '../components/viz'
import { useDocumentTitle, useElapsed } from '../hooks'
import { fmtMs } from '../lib/format'
import { SAMPLE_JOB, SAMPLE_RESUME } from '../lib/samples'
import { useSettings } from '../settings'
import type { DocKind, ExtractResponse, JobSchema, ResumeSchema } from '../types'

type Source = 'text' | 'file'
const ACCEPT = '.pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain'
const MAX_BYTES = 10 * 1024 * 1024

function fmtBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${Math.round(n / 102.4) / 10} KB`
  return `${Math.round(n / 104857.6) / 10} MB`
}

export default function ExtractPage() {
  useDocumentTitle('Extract')
  const [params, setParams] = useSearchParams()
  const kind: DocKind = params.get('kind') === 'job' ? 'job' : 'resume'
  const { health, useLlm: llmPref, refreshHealth } = useSettings()
  const llmAvailable = health.status === 'ok' ? health.data.llm.enabled : null
  const llmLabel = health.status === 'ok' && health.data.llm.enabled ? health.data.llm.provider_label : 'LLM'

  const [source, setSource] = useState<Source>('text')
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [save, setSave] = useState(false)
  const [useLlm, setUseLlm] = useState(llmPref)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ExtractResponse | null>(null)
  const [dragging, setDragging] = useState(false)
  const ctrlRef = useRef<AbortController | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const seconds = useElapsed(running)

  useEffect(() => () => ctrlRef.current?.abort(), [])

  const setKind = (k: DocKind) => {
    const next = new URLSearchParams(params)
    next.set('kind', k)
    setParams(next, { replace: true })
    setResult(null)
    setError(null)
  }

  const pickFile = (f: File | null | undefined) => {
    if (!f) return
    if (f.size > MAX_BYTES) {
      setError(`${f.name} is ${fmtBytes(f.size)}. Choose a file under 10 MB.`)
      return
    }
    if (!/\.(pdf|docx|txt)$/i.test(f.name)) {
      setError(`${f.name} isn't a PDF, DOCX or TXT file.`)
      return
    }
    setError(null)
    setFile(f)
  }

  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    setDragging(false)
    pickFile(e.dataTransfer.files?.[0])
  }

  const canRun = !running && (source === 'text' ? text.trim().length >= 40 : !!file)

  const run = async () => {
    ctrlRef.current?.abort()
    const ctrl = new AbortController()
    ctrlRef.current = ctrl
    setRunning(true)
    setError(null)
    try {
      const res =
        source === 'text'
          ? await api.extract({ kind, text, save, use_llm: useLlm }, { signal: ctrl.signal })
          : await api.extractFile(file!, kind, save, { signal: ctrl.signal })
      setResult(res)
      if (res.id) refreshHealth()
    } catch (err) {
      if (!isAbort(err)) setError(errorMessage(err))
    } finally {
      if (ctrlRef.current === ctrl) setRunning(false)
    }
  }

  const noun = kind === 'resume' ? 'resume' : 'job description'

  return (
    <>
      <PageHeader
        title="Extract"
        lede="Turn a resume or job description into the fixed JSON schema used for ranking and skill-gap analysis. Gemini or Claude does the extraction when an API key is configured in Settings; otherwise the offline heuristic extractor runs."
      />

      <div className="extract-layout">
        <section className="panel panel--pad extract-form" aria-label="Input">
          <div className="field">
            <span className="field__label">Document type</span>
            <Segmented<DocKind>
              ariaLabel="Document type"
              value={kind}
              onChange={setKind}
              options={[
                { value: 'resume', label: 'Resume' },
                { value: 'job', label: 'Job description' },
              ]}
            />
          </div>

          <div className="field">
            <span className="field__label">Source</span>
            <Segmented<Source>
              ariaLabel="Source"
              value={source}
              onChange={setSource}
              options={[
                { value: 'text', label: 'Paste text' },
                { value: 'file', label: 'Upload a file' },
              ]}
            />
          </div>

          {source === 'text' ? (
            <div className="field">
              <div className="row-between">
                <label className="field__label" htmlFor="doc-text">
                  {kind === 'resume' ? 'Resume text' : 'Job description text'}
                </label>
                <div className="row-gap">
                  <button type="button" className="link-btn" onClick={() => setText(kind === 'resume' ? SAMPLE_RESUME : SAMPLE_JOB)}>
                    <Wand size={14} aria-hidden /> Use a sample
                  </button>
                  {text && (
                    <button type="button" className="link-btn" onClick={() => setText('')}>
                      <Trash size={14} aria-hidden /> Clear
                    </button>
                  )}
                </div>
              </div>
              <textarea
                id="doc-text"
                className="textarea"
                rows={16}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={`Paste the full ${noun} here…`}
                spellCheck={false}
              />
              <p className="muted small">{text.trim() ? `${text.trim().split(/\s+/).length} words` : 'At least a few lines of text.'}</p>
            </div>
          ) : (
            <div className="field">
              <span className="field__label">File</span>
              <label
                className={cx('dropzone', dragging && 'is-dragging', file && 'has-file')}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
              >
                <input
                  ref={fileInput}
                  type="file"
                  accept={ACCEPT}
                  className="sr-only"
                  onChange={(e) => {
                    pickFile(e.target.files?.[0])
                    e.target.value = ''
                  }}
                />
                {file ? (
                  <>
                    <FileText size={26} aria-hidden />
                    <span className="dropzone__name">{file.name}</span>
                    <span className="muted small">{fmtBytes(file.size)}. Click to choose another file.</span>
                  </>
                ) : (
                  <>
                    <Upload size={26} aria-hidden />
                    <span className="dropzone__name">Drop a file here or click to browse</span>
                    <span className="muted small">PDF, DOCX or TXT, up to 10 MB</span>
                  </>
                )}
              </label>
              {file && (
                <button type="button" className="link-btn" onClick={() => setFile(null)}>
                  <Trash size={14} aria-hidden /> Remove file
                </button>
              )}
            </div>
          )}

          <div className="field field--switches">
            <Switch
              checked={save}
              onChange={setSave}
              label="Save to corpus"
              description={`Adds the ${noun} to the ${kind === 'resume' ? 'candidates' : 'jobs'} list and indexes it for ranking.`}
            />
            {source === 'text' && (
              <Switch
                checked={useLlm && llmAvailable !== false}
                onChange={setUseLlm}
                disabled={llmAvailable === false}
                label={`Use ${llmLabel}`}
                description={
                  llmAvailable === false
                    ? 'No LLM key is configured (add one in Settings), so the offline extractor runs.'
                    : 'Turn off to compare against the offline heuristic extractor.'
                }
              />
            )}
          </div>

          <Button variant="primary" size="lg" icon={ScanText} loading={running} disabled={!canRun} onClick={run} className="btn--block">
            {running ? `Extracting… ${seconds} s` : `Extract ${noun}`}
          </Button>
        </section>

        <section className="extract-result" aria-label="Result" aria-live="polite">
          {error ? (
            <ErrorState title="Extraction failed" message={error} onRetry={canRun ? run : undefined} />
          ) : running && !result ? (
            <div className="panel panel--pad extract-wait">
              <div className="indeterminate" aria-hidden>
                <span />
              </div>
              <p>
                Reading the {noun} and filling the schema. {seconds} s
              </p>
            </div>
          ) : result ? (
            <ExtractResult result={result} stale={running} />
          ) : (
            <EmptyState icon={Braces} title="Extracted fields appear here">
              Paste text or choose a file, then select <strong>Extract {noun}</strong>. You'll see a formatted view and the raw JSON.
            </EmptyState>
          )}
        </section>
      </div>
    </>
  )
}

function ExtractResult({ result, stale }: { result: ExtractResponse; stale: boolean }) {
  const { meta } = result
  return (
    <div className={cx('stack', stale && 'is-stale')}>
      <div className="panel panel--pad meta-panel">
        <div className="meta-grid">
          <div>
            <p className="meta-grid__label">Method</p>
            <ModeBadge mode={meta.method} model={meta.model} />
          </div>
          <div>
            <p className="meta-grid__label">Model</p>
            <p className="meta-grid__value">{meta.model ?? 'Heuristic rules'}</p>
          </div>
          <div>
            <p className="meta-grid__label">Latency</p>
            <p className="meta-grid__value num">{fmtMs(meta.latency_ms)}</p>
          </div>
          <div>
            <p className="meta-grid__label">Saved</p>
            <p className="meta-grid__value">
              {result.id ? (
                <>
                  <span className="id-tag">{result.id}</span>
                  <Link to={result.kind === 'resume' ? `/candidates/${encodeURIComponent(result.id)}` : `/jobs/${encodeURIComponent(result.id)}`}>
                    {result.kind === 'resume' ? 'Open candidate' : 'Open job'}
                  </Link>
                </>
              ) : (
                'Not saved'
              )}
            </p>
          </div>
        </div>
        {meta.repaired && (
          <Notice tone="info">
            The first JSON output didn't match the schema and was repaired automatically.
          </Notice>
        )}
        {meta.warnings.length > 0 && (
          <Notice tone="warning" icon={TriangleExclamationPoint}>
            <ul className="plain-list">
              {meta.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </Notice>
        )}
      </div>

      <div className="panel panel--pad">
        <div className="row-between">
          <h2 className="panel__title">{result.kind === 'resume' ? 'Extracted resume' : 'Extracted job description'}</h2>
          <Tag>{result.kind === 'resume' ? 'ResumeSchema' : 'JobSchema'}</Tag>
        </div>
        {result.kind === 'resume' ? (
          <ResumeView resume={result.extracted as ResumeSchema} showHeader />
        ) : (
          <JobView job={result.extracted as JobSchema} showHeader />
        )}
      </div>

      <Collapsible summary="Raw JSON" meta="Exactly what the API returned" className="collapsible--panel" defaultOpen={false}>
        <JsonView value={result.extracted} maxHeight={520} />
      </Collapsible>
      {result.raw_text && (
        <Collapsible summary="Text read from the file" className="collapsible--panel">
          <pre className="raw-text">{result.raw_text}</pre>
        </Collapsible>
      )}
    </div>
  )
}
