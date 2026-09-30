import { useCallback, useEffect, useRef, useState } from 'react'
import {
  workbench,
  setWorkbenchCsrf,
  type Dataset,
  type Template,
  type Topic,
  type Run,
  type Preview,
  type Validation,
  type Connection,
  type Results,
  type Evidence,
  type Comparison,
  type TrendResult,
} from './workbench-api'
import './workbench.css'
import { priceReference } from './workbench-pricing'

type View = 'Datasets' | 'Classification' | 'Runs' | 'Results' | 'Connections'
const FIELDS = [
  'text',
  'id',
  'date',
  'rating',
  'language',
  'channel',
  'product',
  'group',
]

export function Workbench() {
  const [session, setSession] = useState<
    'loading' | 'disabled' | 'locked' | 'ready'
  >('loading')
  const [view, setView] = useState<View>(
    new URLSearchParams(window.location.search).has('connection')
      ? 'Connections'
      : 'Datasets',
  )
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [templates, setTemplates] = useState<Template[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [connections, setConnections] = useState<Connection[]>([])
  const [datasetId, setDatasetId] = useState('')
  const [templateId, setTemplateId] = useState('')
  const [connectionId, setConnectionId] = useState('')
  const [models, setModels] = useState<{ slug: string; displayName: string }[]>(
    [],
  )
  const [model, setModel] = useState('')
  const [engine, setEngine] = useState('rules')
  const [consent, setConsent] = useState(false)
  const [selectedRun, setSelectedRun] = useState('')
  const [results, setResults] = useState<Results | null>(null)
  const [filters, setFilters] = useState({
    topic: '',
    sentiment: '',
    language: '',
    product: '',
    group: '',
    page: 1,
  })
  const [evidence, setEvidence] = useState<Evidence | null>(null)
  const [compareId, setCompareId] = useState('')
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [trend, setTrend] = useState<TrendResult | null>(null)
  const [originalExport, setOriginalExport] = useState(false)
  const [draft, setDraft] = useState<{ name: string; topics: Topic[] } | null>(
    null,
  )
  const [key, setKey] = useState('')
  const [connectionLabel, setConnectionLabel] = useState('OpenAI API')
  const [notice, setNotice] = useState(
    new URLSearchParams(window.location.search).get('connection') === 'plan'
      ? 'You’re using your ChatGPT plan. Eligible AI requests use your existing allowance. Manage limits in ChatGPT settings.'
      : '',
  )
  const requestKey = useRef(crypto.randomUUID())

  const task = async (fn: () => Promise<void>) => {
    setError('')
    setBusy(true)
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }
  const refresh = useCallback(async () => {
    const [d, t, r, c] = await Promise.all([
      workbench<Dataset[]>('/datasets'),
      workbench<Template[]>('/templates'),
      workbench<Run[]>('/runs'),
      workbench<Connection[]>('/connections'),
    ])
    setDatasets(d)
    setTemplates(t)
    setRuns(r)
    setConnections(c)
    setDatasetId(
      (id) => id || d.find((row) => row.status === 'ready')?.id || '',
    )
    setTemplateId((id) => id || t[0]?.id || '')
  }, [])
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has('connection'))
      window.history.replaceState(null, '', '/#workbench')
    const expired = () => {
      setSession('locked')
      setResults(null)
      setKey('')
      setWorkbenchCsrf('')
    }
    window.addEventListener('workbench-session-expired', expired)
    const abort = new AbortController()
    void workbench<{ enabled: boolean; authenticated: boolean; csrf: string }>(
      '/session',
      undefined,
      'GET',
      abort.signal,
    )
      .then((s) => {
        setWorkbenchCsrf(s.csrf || '')
        setSession(
          !s.enabled ? 'disabled' : s.authenticated ? 'ready' : 'locked',
        )
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(String(e))
      })
    return () => {
      abort.abort()
      window.removeEventListener('workbench-session-expired', expired)
    }
  }, [])
  useEffect(() => {
    if (session !== 'ready') return
    let active = true
    const reload = () => {
      void refresh().catch((e) => {
        if (active) setError(String(e))
      })
    }
    reload()
    const interval = window.setInterval(reload, 5000)
    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [session, refresh])
  useEffect(() => {
    if (!connectionId) return
    const abort = new AbortController()
    void workbench<{ slug: string; displayName: string }[]>(
      `/connections/${connectionId}/models`,
      undefined,
      'GET',
      abort.signal,
    )
      .then((m) => {
        if (abort.signal.aborted) return
        setModels(m)
        setModel(m[0]?.slug || '')
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(String(e))
      })
    return () => abort.abort()
  }, [connectionId])
  const query = new URLSearchParams(
    Object.entries(filters).map(([name, value]) => [name, String(value)]),
  ).toString()
  useEffect(() => {
    if (!selectedRun || session !== 'ready') return
    const abort = new AbortController()
    let generation = 0
    const reload = () => {
      const current = ++generation
      void workbench<Results>(
        `/runs/${selectedRun}/results?${query}`,
        undefined,
        'GET',
        abort.signal,
      )
        .then((data) => {
          if (!abort.signal.aborted && generation === current)
            setResults({ ...data, loadedQuery: query })
        })
        .catch((e) => {
          if (!abort.signal.aborted) setError(String(e))
        })
    }
    reload()
    const interval = window.setInterval(reload, 5000)
    return () => {
      abort.abort()
      window.clearInterval(interval)
    }
  }, [selectedRun, query, session])

  const startRun = async (mode: 'sample' | 'full', sample?: Run) => {
    const options = {
      datasetId: sample?.dataset_id || datasetId,
      templateId: sample?.template_id || templateId,
      engine: sample?.snapshot.engine || engine,
      connectionId: sample?.snapshot.connectionId || connectionId,
      model: sample?.snapshot.model || model,
      mode,
      externalConsent: consent,
      idempotencyKey: requestKey.current,
      sampleRunId: sample?.id,
    }
    if (options.engine === 'openai') {
      const preview = await workbench<{
        selected: number
        blocked: number
        reused: number
        prepared: { row: number; redactedText: string }[]
      }>('/runs/preview', options)
      const examples = preview.prepared
        .map((row) => `Row ${row.row}: ${row.redactedText.slice(0, 500)}`)
        .join('\n\n')
      if (
        !window.confirm(
          `Process ${preview.selected} records with ${options.model}? ${preview.blocked} are privacy-blocked; ${preview.reused} results will be reused. Prepared examples:\n\n${examples}\n\nApproved feedback will be sent to OpenAI using the selected connection. This consumes your plan allowance or API billing.`,
        )
      )
        return
    }
    const run = await workbench<Run>('/runs', options)
    requestKey.current = crypto.randomUUID()
    setSelectedRun(run.id)
    setFilters({
      topic: '',
      sentiment: '',
      language: '',
      product: '',
      group: '',
      page: 1,
    })
    setView('Results')
    await refresh()
  }

  return (
    <div className="wb-shell">
      <header className="wb-header">
        <a href="#">Feedback Intelligence</a>
        <span>Local workbench</span>
        <a href="#">Recorded showcase ↗</a>
      </header>
      <nav className="wb-nav" aria-label="Workbench navigation">
        {(
          [
            'Datasets',
            'Classification',
            'Runs',
            'Results',
            'Connections',
          ] as View[]
        ).map((name) => (
          <button
            key={name}
            aria-current={view === name ? 'page' : undefined}
            onClick={() => setView(name)}
          >
            {name}
          </button>
        ))}
      </nav>
      <main className="wb-main">
        <h1>{view}</h1>
        <p className="wb-muted">
          Your datasets and runs are saved on this machine. Results are
          exploratory; classification agreement is not validated accuracy.
        </p>
        {error && (
          <div role="alert" className="wb-error">
            {error}
            <button onClick={() => setError('')}>Dismiss</button>
          </div>
        )}
        {notice && (
          <div role="status" className="wb-notice">
            {notice}
            <button onClick={() => setNotice('')}>Got it</button>
          </div>
        )}
        {session === 'loading' ? (
          <p role="status">Checking local workspace…</p>
        ) : session === 'disabled' ? (
          <section className="wb-panel">
            <h2>Start the workbench runtime</h2>
            <p>
              Run <code>python3 scripts/start_workbench.py</code> in the
              repository, then open{' '}
              <a href="http://localhost:8081/#workbench">the local workbench</a>
              . The recorded showcase remains available here.
            </p>
          </section>
        ) : session === 'locked' ? (
          <form
            className="wb-panel"
            onSubmit={(e) => {
              e.preventDefault()
              void task(async () => {
                const s = await workbench<{ csrf: string }>('/session', {
                  code,
                })
                setWorkbenchCsrf(s.csrf)
                setCode('')
                setSession('ready')
              })
            }}
          >
            <h2>Unlock your local workspace</h2>
            <p>
              Use the private owner code in{' '}
              <code>.workbench-runtime/api/owner-code</code>. This protects
              uploads and model connections from other local browser pages.
            </p>
            <label>
              Owner code
              <input
                type="password"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <button disabled={busy}>Unlock</button>
          </form>
        ) : (
          <>
            {view === 'Datasets' && (
              <>
                <section className="wb-panel">
                  <h2>Choose data</h2>
                  <p>
                    Start with your own reviews or a reproducible rules
                    scenario. For the existing SemIf/rules/Sol comparison, open
                    the recorded showcase.
                  </p>
                  <button
                    disabled={busy}
                    onClick={() => {
                      void task(async () => {
                        const d = await workbench<Dataset>('/datasets/demo', {
                          count: 10000,
                        })
                        setDatasetId(d.id)
                        await refresh()
                        setView('Classification')
                      })
                    }}
                  >
                    Load 10,000-record synthetic rules scenario
                  </button>
                </section>
                <ImportWizard
                  busy={busy}
                  task={task}
                  imported={async () => {
                    await refresh()
                    setView('Classification')
                  }}
                />
                <section className="wb-panel">
                  <h2>Saved datasets</h2>
                  {datasets.length === 0 ? (
                    <p>No datasets imported yet.</p>
                  ) : (
                    <div className="wb-table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Name</th>
                            <th>Records</th>
                            <th>Status</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {datasets.map((d) => (
                            <tr key={d.id}>
                              <td>{d.name}</td>
                              <td>{d.count.toLocaleString()}</td>
                              <td>{d.status}</td>
                              <td>
                                <button
                                  disabled={d.status !== 'ready'}
                                  onClick={() => {
                                    setDatasetId(d.id)
                                    setView('Classification')
                                  }}
                                >
                                  Use {d.name}
                                </button>
                                <button
                                  disabled={busy || d.status !== 'ready'}
                                  onClick={() => {
                                    if (
                                      window.confirm(
                                        `Delete ${d.name} and all its runs and results? This permanently purges local data.`,
                                      )
                                    )
                                      void task(async () => {
                                        await workbench(
                                          `/datasets/${d.id}`,
                                          undefined,
                                          'DELETE',
                                        )
                                        if (datasetId === d.id) setDatasetId('')
                                        setSelectedRun('')
                                        await refresh()
                                      })
                                  }}
                                >
                                  Delete {d.name}
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              </>
            )}
            {view === 'Classification' && (
              <>
                <section className="wb-panel">
                  <h2>Configure a run</h2>
                  <div className="wb-grid">
                    <label>
                      Dataset
                      <select
                        value={datasetId}
                        onChange={(e) => {
                          setDatasetId(e.target.value)
                          requestKey.current = crypto.randomUUID()
                        }}
                      >
                        <option value="">Choose dataset</option>
                        {datasets
                          .filter((d) => d.status === 'ready')
                          .map((d) => (
                            <option key={d.id} value={d.id}>
                              {d.name} · {d.count} records
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      Template revision
                      <select
                        value={templateId}
                        onChange={(e) => {
                          setTemplateId(e.target.value)
                          setDraft(null)
                          requestKey.current = crypto.randomUUID()
                        }}
                      >
                        {templates.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.name} · {t.revision.slice(0, 8)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Engine
                      <select
                        value={engine}
                        onChange={(e) => {
                          setEngine(e.target.value)
                          requestKey.current = crypto.randomUUID()
                        }}
                      >
                        <option value="rules">Free keyword rules</option>
                        <option value="openai">OpenAI model</option>
                      </select>
                    </label>
                  </div>
                  {engine === 'openai' && (
                    <>
                      <p>
                        Choose a connected account. ChatGPT plan usage and API
                        billing are separate.{' '}
                        <a
                          href="#workbench"
                          onClick={() => setView('Connections')}
                        >
                          Manage connections
                        </a>
                      </p>
                      <div className="wb-grid">
                        <label>
                          Connection
                          <select
                            value={connectionId}
                            onChange={(e) => {
                              setConnectionId(e.target.value)
                              setModels([])
                              setModel('')
                              requestKey.current = crypto.randomUUID()
                            }}
                          >
                            <option value="">Choose connection</option>
                            {connections.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.label} ·{' '}
                                {c.mode === 'chatgpt'
                                  ? 'ChatGPT plan'
                                  : 'API billing'}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Available model
                          <select
                            value={model}
                            onChange={(e) => {
                              setModel(e.target.value)
                              requestKey.current = crypto.randomUUID()
                            }}
                          >
                            {models.map((m) => (
                              <option key={m.slug} value={m.slug}>
                                {m.displayName}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                      <label className="wb-check">
                        <input
                          type="checkbox"
                          checked={consent}
                          onChange={(e) => setConsent(e.target.checked)}
                        />
                        I authorize sending prepared feedback to OpenAI and
                        using the selected connection’s allowance or API
                        billing.
                      </label>
                      <p>
                        {connections.find((c) => c.id === connectionId)
                          ?.mode === 'api' && priceReference(model)
                          ? `API pricing reference as of ${priceReference(model)!.reviewedAt}: $${priceReference(model)!.input} input / $${priceReference(model)!.output} output per million tokens. `
                          : 'No verified API pricing reference is available for this model. '}
                        Subscription allowance is managed in{' '}
                        <a
                          href="https://chatgpt.com/settings/usage"
                          target="_blank"
                          rel="noreferrer"
                        >
                          ChatGPT settings
                        </a>
                        ; API use has separate billing.
                      </p>
                    </>
                  )}
                  <button
                    disabled={
                      busy ||
                      !datasetId ||
                      !templateId ||
                      (engine === 'openai' && (!model || !consent))
                    }
                    onClick={() => {
                      void task(() =>
                        startRun(engine === 'openai' ? 'sample' : 'full'),
                      )
                    }}
                  >
                    {engine === 'rules'
                      ? 'Classify dataset with rules'
                      : 'Test a representative sample (up to 25)'}
                  </button>
                </section>
                <section className="wb-panel">
                  <h2>Topics and keyword rules</h2>
                  <p>
                    Lower priority numbers win. Matching is case-insensitive.
                    Competing matches remain visible; unmatched text is
                    unclassified. A saved edit creates a new revision.
                  </p>
                  <button
                    onClick={() =>
                      setDraft(
                        structuredClone(
                          templates.find((t) => t.id === templateId)
                            ?.payload || {
                            name: 'Custom feedback',
                            topics: [],
                          },
                        ),
                      )
                    }
                  >
                    Edit selected template
                  </button>
                  {draft && (
                    <>
                      <label>
                        Template name
                        <input
                          value={draft.name}
                          onChange={(e) =>
                            setDraft({ ...draft, name: e.target.value })
                          }
                        />
                      </label>
                      {draft.topics.map((topic, i) => (
                        <TopicEditor
                          key={i}
                          topic={topic}
                          change={(next) =>
                            setDraft({
                              ...draft,
                              topics: draft.topics.map((t, index) =>
                                index === i ? next : t,
                              ),
                            })
                          }
                          remove={() =>
                            setDraft({
                              ...draft,
                              topics: draft.topics.filter(
                                (_, index) => index !== i,
                              ),
                            })
                          }
                        />
                      ))}
                      <button
                        onClick={() =>
                          setDraft({
                            ...draft,
                            topics: [
                              ...draft.topics,
                              {
                                id: `topic_${draft.topics.length + 1}`,
                                label: 'New topic',
                                description: 'Describe this topic',
                                keywords: [],
                                priority: draft.topics.length,
                              },
                            ],
                          })
                        }
                      >
                        Add topic
                      </button>
                      <button
                        disabled={busy}
                        onClick={() => {
                          void task(async () => {
                            const saved = await workbench<Template>(
                              '/templates',
                              draft,
                            )
                            setTemplateId(saved.id)
                            setDraft(null)
                            await refresh()
                          })
                        }}
                      >
                        Save new revision
                      </button>
                    </>
                  )}
                </section>
              </>
            )}
            {view === 'Runs' && (
              <section className="wb-panel">
                <h2>Run history</h2>
                {runs.length === 0 ? (
                  <p>Choose a dataset and start a classification run.</p>
                ) : (
                  <div className="wb-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Run</th>
                          <th>Configuration</th>
                          <th>State</th>
                          <th>Coverage</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {runs.map((r) => (
                          <tr key={r.id}>
                            <td>
                              {r.id.slice(0, 8)}
                              <br />
                              <small>
                                {new Date(r.created_at).toLocaleString()}
                              </small>
                            </td>
                            <td>
                              {r.snapshot.template.name}
                              <br />
                              {r.snapshot.engine} · {r.snapshot.model}
                            </td>
                            <td>{r.status}</td>
                            <td>
                              {r.succeeded}/{r.target} processed
                              <br />
                              {r.failed} failed
                            </td>
                            <td>
                              <button
                                onClick={() => {
                                  setSelectedRun(r.id)
                                  setView('Results')
                                }}
                              >
                                Inspect {r.id.slice(0, 8)}
                              </button>
                              {['queued', 'running'].includes(r.status) && (
                                <button
                                  disabled={busy}
                                  onClick={() => {
                                    void task(async () => {
                                      await workbench(
                                        `/runs/${r.id}/cancel`,
                                        {},
                                      )
                                      await refresh()
                                    })
                                  }}
                                >
                                  Cancel {r.id.slice(0, 8)}
                                </button>
                              )}
                              {['paused', 'cancelled', 'failed'].includes(
                                r.status,
                              ) && (
                                <button
                                  disabled={busy}
                                  onClick={() => {
                                    if (
                                      window.confirm(
                                        'Resume unfinished records? Interrupted OpenAI requests can consume additional usage.',
                                      )
                                    )
                                      void task(async () => {
                                        await workbench(
                                          `/runs/${r.id}/resume`,
                                          { externalConsent: true },
                                        )
                                        await refresh()
                                      })
                                  }}
                                >
                                  Resume {r.id.slice(0, 8)}
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}
            {view === 'Results' && (
              <>
                <label>
                  Selected run
                  <select
                    value={selectedRun}
                    onChange={(e) => {
                      setSelectedRun(e.target.value)
                      setEvidence(null)
                      setComparison(null)
                      setTrend(null)
                      setFilters({
                        topic: '',
                        sentiment: '',
                        language: '',
                        product: '',
                        group: '',
                        page: 1,
                      })
                    }}
                  >
                    <option value="">Choose run</option>
                    {runs.map((r) => (
                      <option value={r.id} key={r.id}>
                        {r.id.slice(0, 8)} · {r.snapshot.template.name} ·{' '}
                        {r.snapshot.engine} · {r.status}
                      </option>
                    ))}
                  </select>
                </label>
                {results &&
                results.run.id === selectedRun &&
                results.loadedQuery === query ? (
                  <>
                    <section className="wb-panel">
                      <h2>Processing and coverage</h2>
                      <p>
                        Run duration: {results.run.elapsedSeconds} seconds.
                        Counts include the current filters.
                      </p>
                      {results.run.errors.length > 0 && (
                        <details>
                          <summary>
                            Processing errors and interruptions (
                            {results.run.errors.length} shown)
                          </summary>
                          {results.run.errors.map((e) => (
                            <p key={e.record_id}>
                              {e.record_id.slice(0, 8)} · {e.status} ·{' '}
                              {e.error_code}. Inspect the import report or
                              reconnect before explicitly resuming.
                            </p>
                          ))}
                        </details>
                      )}
                      {results.run.snapshot.billingMode === 'api' &&
                        priceReference(results.run.snapshot.model) && (
                          <p>
                            Estimated API cost for new successful records: $
                            {priceReference(results.run.snapshot.model)!
                              .cost(
                                results.runUsage.inputTokens,
                                results.runUsage.outputTokens,
                              )
                              .toFixed(4)}{' '}
                            using rates reviewed{' '}
                            {
                              priceReference(results.run.snapshot.model)!
                                .reviewedAt
                            }
                            . This is not an invoice; failed attempts and
                            provider billing adjustments can add usage.{' '}
                            {results.run.snapshot.mode === 'sample' &&
                              results.run.succeeded > 0 && (
                                <span>
                                  Linear full-dataset estimate: $
                                  {(
                                    (priceReference(
                                      results.run.snapshot.model,
                                    )!.cost(
                                      results.runUsage.inputTokens,
                                      results.runUsage.outputTokens,
                                    ) *
                                      (datasets.find(
                                        (d) => d.id === results.run.dataset_id,
                                      )?.count || results.run.target)) /
                                    results.run.succeeded
                                  ).toFixed(2)}{' '}
                                  from this sample; actual totals may differ.
                                </span>
                              )}
                          </p>
                        )}
                      <div className="wb-metrics">
                        <Metric
                          label="Run coverage"
                          value={`${results.run.succeeded} / ${results.run.target}`}
                        />
                        <Metric
                          label="Filtered results"
                          value={results.filtered.toLocaleString()}
                        />
                        <Metric
                          label="Dated results"
                          value={results.summary.dated.toLocaleString()}
                        />
                        <Metric
                          label="Recorded tokens"
                          value={`${results.runUsage.inputTokens.toLocaleString()} in / ${results.runUsage.outputTokens.toLocaleString()} out`}
                        />
                      </div>
                      <p>
                        {results.run.status} · {results.run.failed} failed ·{' '}
                        {results.runUsage.reusedRecords} reused sample records ·{' '}
                        {results.projectionPending} awaiting analytical
                        projection. Undated records remain in distributions and
                        evidence.
                      </p>
                      {results.run.snapshot.mode === 'sample' &&
                        results.run.status === 'completed' && (
                          <>
                            <label className="wb-check">
                              <input
                                type="checkbox"
                                checked={consent}
                                onChange={(e) => setConsent(e.target.checked)}
                              />
                              Approve processing the remaining dataset with the
                              same configuration.
                            </label>
                            <button
                              disabled={busy || !consent}
                              onClick={() => {
                                void task(() => startRun('full', results.run))
                              }}
                            >
                              Run remaining dataset
                            </button>
                          </>
                        )}
                    </section>
                    <section className="wb-panel">
                      <h2>Explore classifications</h2>
                      <div className="wb-grid">
                        {(
                          [
                            'topic',
                            'sentiment',
                            'language',
                            'product',
                            'group',
                          ] as const
                        ).map((field) => (
                          <label key={field}>
                            {field}
                            <input
                              list={`wb-${field}`}
                              value={filters[field]}
                              onChange={(e) =>
                                setFilters({
                                  ...filters,
                                  [field]: e.target.value,
                                  page: 1,
                                })
                              }
                            />
                            <datalist id={`wb-${field}`}>
                              {(field === 'topic'
                                ? results.run.snapshot.template.topics
                                    .map((t) => t.id)
                                    .concat('unclassified')
                                : field === 'sentiment'
                                  ? ['positive', 'negative', 'mixed', 'neutral']
                                  : results.groups[field] || ['en', 'sv']
                              ).map((v) => (
                                <option key={v} value={v} />
                              ))}
                            </datalist>
                          </label>
                        ))}
                      </div>
                      <div className="wb-grid">
                        <Distribution
                          title="Topics"
                          values={results.summary.topics}
                          total={results.summary.processed}
                        />
                        <Distribution
                          title="Sentiment"
                          values={results.summary.sentiments}
                          total={results.summary.processed}
                        />
                      </div>
                      <h3>Observed over time</h3>
                      {results.summary.days.length ? (
                        <div
                          className="wb-timeline"
                          role="img"
                          aria-label={`Daily classified record volume over ${results.summary.days.length} observed dates. Missing dates are excluded.`}
                        >
                          {results.summary.days.map((day) => (
                            <div
                              key={day.date}
                              title={`${day.date}: ${day.total} records`}
                              style={{
                                height: `${Math.max(2, (100 * day.total) / Math.max(...results.summary.days.map((d) => d.total)))}%`,
                              }}
                            />
                          ))}
                        </div>
                      ) : (
                        <p>No dated records; time analysis is unavailable.</p>
                      )}
                      <details>
                        <summary>Daily counts and topic rates</summary>
                        <div className="wb-table-wrap">
                          <table>
                            <thead>
                              <tr>
                                <th>Date</th>
                                <th>Records</th>
                                <th>Topic rates</th>
                              </tr>
                            </thead>
                            <tbody>
                              {results.summary.days.map((d) => (
                                <tr key={d.date}>
                                  <td>{d.date}</td>
                                  <td>{d.total}</td>
                                  <td>
                                    {Object.entries(d)
                                      .filter(
                                        ([k]) => k !== 'date' && k !== 'total',
                                      )
                                      .map(
                                        ([k, n]) =>
                                          `${k}: ${((100 * Number(n)) / d.total).toFixed(1)}% (${n}/${d.total})`,
                                      )
                                      .join(' · ')}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </details>
                      <p>
                        Rating coverage: {results.summary.ratingCount}/
                        {results.summary.processed}. Normalized average:{' '}
                        {results.summary.normalizedRatingMean === null
                          ? 'unavailable'
                          : `${(100 * results.summary.normalizedRatingMean).toFixed(1)}% of declared scales`}
                        .
                      </p>
                    </section>
                    <section className="wb-panel">
                      <h2>Record evidence</h2>
                      <div className="wb-table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>Source row</th>
                              <th>Prepared feedback</th>
                              <th>Topic</th>
                              <th>Sentiment</th>
                              <th>Evidence</th>
                            </tr>
                          </thead>
                          <tbody>
                            {results.rows.map((row) => (
                              <tr key={row.id}>
                                <td>{row.position}</td>
                                <td>{row.text.slice(0, 160)}</td>
                                <td>{row.result.topic}</td>
                                <td>{row.result.sentiment || 'Unavailable'}</td>
                                <td>
                                  <button onClick={() => setEvidence(row)}>
                                    Inspect row {row.position}
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div className="wb-actions">
                        <button
                          disabled={filters.page === 1}
                          onClick={() =>
                            setFilters({ ...filters, page: filters.page - 1 })
                          }
                        >
                          Previous
                        </button>
                        <span>
                          Page {filters.page} · {results.filtered} results
                        </span>
                        <button
                          disabled={filters.page * 50 >= results.filtered}
                          onClick={() =>
                            setFilters({ ...filters, page: filters.page + 1 })
                          }
                        >
                          Next
                        </button>
                      </div>
                      {evidence && (
                        <aside className="wb-evidence">
                          <h3>Row {evidence.position}</h3>
                          <p>{evidence.result.redactedText}</p>
                          <dl>
                            <dt>Source ID</dt>
                            <dd>{evidence.sourceId}</dd>
                            <dt>Recorded date</dt>
                            <dd>{evidence.occurredAt || 'Not supplied'}</dd>
                            <dt>Requested / resolved model</dt>
                            <dd>
                              {evidence.result.requestedModel} /{' '}
                              {evidence.result.resolvedModel}
                            </dd>
                            <dt>Template revision</dt>
                            <dd>{evidence.result.templateRevision}</dd>
                          </dl>
                          <h4>Matched rules and competing topics</h4>
                          <p>
                            Prepared input hash:{' '}
                            {evidence.result.inputStateSha256 ||
                              'Not recorded for this earlier preview run'}
                          </p>
                          <p>
                            Detected redactions:{' '}
                            {evidence.result.redactions
                              ? Object.entries(evidence.result.redactions)
                                  .map(([kind, count]) => `${kind}: ${count}`)
                                  .join(', ') || 'none'
                              : 'Not recorded for this earlier preview run'}
                          </p>
                          {evidence.result.matches.length ? (
                            evidence.result.matches.map((m) => (
                              <p key={m.topic}>
                                {m.topic} · priority {m.priority}:{' '}
                                {m.phrases.join(', ')}
                              </p>
                            ))
                          ) : (
                            <p>
                              No keyword explanation; inspect the selected
                              classification method.
                            </p>
                          )}
                          <button onClick={() => setEvidence(null)}>
                            Close record details
                          </button>
                        </aside>
                      )}
                    </section>
                    <section className="wb-panel">
                      <h2>Exploratory trend candidates</h2>
                      <p>
                        Compares the latest 7 days with the previous 28. Dates
                        with no supplied observations have unknown coverage.
                        These candidates are not calibrated business alerts.
                      </p>
                      {['simple_rate_change', 'candidate_statistical'].map(
                        (method) => (
                          <button
                            key={method}
                            disabled={busy}
                            onClick={() => {
                              void task(async () =>
                                setTrend(
                                  await workbench<TrendResult>(
                                    `/runs/${selectedRun}/trends?${query}&method=${method}`,
                                  ),
                                ),
                              )
                            }}
                          >
                            {method === 'simple_rate_change'
                              ? 'Simple rate change'
                              : 'Beta-Binomial candidate'}
                          </button>
                        ),
                      )}
                      {trend && (
                        <div>
                          {trend.reason ||
                            trend.candidates.map((c, i) => (
                              <p key={i}>
                                {c.series_id} · {c.direction} · {c.status} ·{' '}
                                {c.reasons.join(', ')}
                                {c.delta_pp === null
                                  ? ''
                                  : ` · ${c.delta_pp.toFixed(2)} percentage points`}
                              </p>
                            ))}
                        </div>
                      )}
                    </section>
                    <section className="wb-panel">
                      <h2>Compare and export</h2>
                      <label>
                        Compare to run
                        <select
                          value={compareId}
                          onChange={(e) => setCompareId(e.target.value)}
                        >
                          <option value="">Choose matching run</option>
                          {runs
                            .filter(
                              (r) =>
                                r.id !== selectedRun &&
                                r.dataset_id === results.run.dataset_id &&
                                r.snapshot.templateRevision ===
                                  results.run.snapshot.templateRevision,
                            )
                            .map((r) => (
                              <option key={r.id} value={r.id}>
                                {r.id.slice(0, 8)} · {r.snapshot.model} ·{' '}
                                {r.succeeded}/{r.target}
                              </option>
                            ))}
                        </select>
                      </label>
                      <button
                        disabled={busy || !compareId}
                        onClick={() => {
                          void task(async () =>
                            setComparison(
                              await workbench<Comparison>('/compare', {
                                left: selectedRun,
                                right: compareId,
                              }),
                            ),
                          )
                        }}
                      >
                        Compare shared records
                      </button>
                      {comparison && (
                        <>
                          <p>
                            {comparison.label}:{' '}
                            {comparison.agreement === null
                              ? 'unavailable'
                              : `${(100 * comparison.agreement).toFixed(1)}%`}{' '}
                            across {comparison.shared} shared records.{' '}
                            {comparison.disagreementCount} disagreements;
                            left/right coverage {comparison.leftProcessed}/
                            {comparison.rightProcessed}.
                          </p>
                          {comparison.disagreements.map((d) => (
                            <details key={d.recordId}>
                              <summary>
                                {d.left.topic} ↔ {d.right.topic}
                              </summary>
                              <p>{d.text}</p>
                              <p>
                                Sentiment: {d.left.sentiment} ↔{' '}
                                {d.right.sentiment}; actionable:{' '}
                                {String(d.left.actionable)} ↔{' '}
                                {String(d.right.actionable)}
                              </p>
                            </details>
                          ))}
                        </>
                      )}
                      <label className="wb-check">
                        <input
                          type="checkbox"
                          checked={originalExport}
                          onChange={(e) => setOriginalExport(e.target.checked)}
                        />
                        Include original text in this local export.
                      </label>
                      {['csv', 'json'].map((format) => (
                        <button
                          disabled={busy}
                          key={format}
                          onClick={() => {
                            void task(async () => {
                              if (
                                originalExport &&
                                !window.confirm(
                                  'Export original text, including any private content?',
                                )
                              )
                                return
                              const file = await workbench<{
                                filename: string
                                content: string
                              }>(
                                `/runs/${selectedRun}/export?${query}&format=${format}&original=${originalExport}`,
                              )
                              const url = URL.createObjectURL(
                                new Blob([file.content], {
                                  type:
                                    format === 'csv'
                                      ? 'text/csv'
                                      : 'application/json',
                                }),
                              )
                              const link = document.createElement('a')
                              link.href = url
                              link.download = file.filename
                              link.click()
                              URL.revokeObjectURL(url)
                            })
                          }}
                        >
                          Export {format.toUpperCase()}
                        </button>
                      ))}
                    </section>
                  </>
                ) : (
                  <p role="status">
                    {selectedRun
                      ? 'Loading results…'
                      : 'Choose a run to inspect results.'}
                  </p>
                )}
              </>
            )}
            {view === 'Connections' && (
              <>
                <section className="wb-panel">
                  <h2>ChatGPT plan connection</h2>
                  <p>
                    Eligible accounts can grant this local open-source tool
                    permission to use their existing ChatGPT plan. Sign-in and
                    plan usage are separate permissions. Usage consumes the
                    existing allowance.
                  </p>
                  <button
                    disabled={busy}
                    onClick={() => {
                      void task(async () => {
                        const result = await workbench<{ url: string }>(
                          '/connections/chatgpt',
                          {},
                        )
                        window.location.assign(result.url)
                      })
                    }}
                  >
                    Continue with ChatGPT
                  </button>
                  <a
                    href="https://chatgpt.com/settings/usage"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Manage usage ↗
                  </a>
                </section>
                <form
                  className="wb-panel"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void task(async () => {
                      await workbench('/connections/api-key', {
                        key,
                        label: connectionLabel,
                      })
                      setKey('')
                      await refresh()
                      setNotice(
                        'OpenAI API connected. API usage has separate billing; no automatic switch from your ChatGPT plan will occur.',
                      )
                    })
                  }}
                >
                  <h2>Optional API billing</h2>
                  <p>
                    This connection uses your OpenAI API account’s billing. It
                    does not use ChatGPT subscription allowance.
                  </p>
                  <label>
                    Connection label
                    <input
                      value={connectionLabel}
                      onChange={(e) => setConnectionLabel(e.target.value)}
                      maxLength={100}
                    />
                  </label>
                  <label>
                    OpenAI API key
                    <input
                      type="password"
                      value={key}
                      onChange={(e) => setKey(e.target.value)}
                      autoComplete="off"
                      required
                    />
                  </label>
                  <button disabled={busy || !key}>Connect API key</button>
                </form>
                <section className="wb-panel">
                  <h2>Saved connections</h2>
                  <button
                    disabled={busy}
                    onClick={() => {
                      void task(refresh)
                    }}
                  >
                    Refresh connections
                  </button>
                  {connections.map((c) => (
                    <div key={c.id} className="wb-actions">
                      <span>
                        {c.label} ·{' '}
                        {c.mode === 'api'
                          ? 'API billing'
                          : c.planEnabled
                            ? 'Using ChatGPT plan'
                            : 'Plan permission disabled'}
                      </span>
                      {c.mode === 'chatgpt' && (
                        <button
                          disabled={busy}
                          onClick={() => {
                            void task(async () => {
                              const r = await workbench<{ url: string }>(
                                '/connections/chatgpt',
                                { connectionId: c.id },
                              )
                              window.location.assign(r.url)
                            })
                          }}
                        >
                          Reconnect {c.label}
                        </button>
                      )}
                      <button
                        disabled={busy}
                        onClick={() => {
                          void task(async () => {
                            const state = await workbench<{
                              remoteRevocationConfirmed: boolean
                              runsPaused: boolean
                            }>(`/connections/${c.id}`, undefined, 'DELETE')
                            setNotice(
                              state.remoteRevocationConfirmed &&
                                state.runsPaused
                                ? 'Connection removed locally and active runs paused.'
                                : 'Connection removed locally. Remote revocation or run pausing was not confirmed; review Runs and disconnect the app in ChatGPT settings.',
                            )
                            setConnectionId('')
                            await refresh()
                          })
                        }}
                      >
                        Disconnect {c.label}
                      </button>
                    </div>
                  ))}
                </section>
              </>
            )}
            <footer className="wb-footer">
              <button
                onClick={() => {
                  void task(async () => {
                    await workbench('/session', undefined, 'DELETE')
                    setWorkbenchCsrf('')
                    setSession('locked')
                    setResults(null)
                  })
                }}
              >
                Lock workspace
              </button>
              <span>
                Private local installation · source-only workbench preview
              </span>
            </footer>
          </>
        )}
      </main>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
function Distribution({
  title,
  values,
  total,
}: {
  title: string
  values: Record<string, number>
  total: number
}) {
  return (
    <div>
      <h3>{title}</h3>
      {Object.entries(values).map(([label, count]) => (
        <div key={label} className="wb-distribution">
          <span>{label}</span>
          <meter min={0} max={Math.max(total, 1)} value={count}>
            {count}
          </meter>
          <span>
            {count}/{total} · {total ? ((100 * count) / total).toFixed(1) : '0'}
            %
          </span>
        </div>
      ))}
    </div>
  )
}
function TopicEditor({
  topic,
  change,
  remove,
}: {
  topic: Topic
  change: (value: Topic) => void
  remove: () => void
}) {
  return (
    <fieldset className="wb-topic">
      <legend>{topic.label}</legend>
      <div className="wb-grid">
        <label>
          Topic ID
          <input
            value={topic.id}
            onChange={(e) => change({ ...topic, id: e.target.value })}
          />
        </label>
        <label>
          Label
          <input
            value={topic.label}
            onChange={(e) => change({ ...topic, label: e.target.value })}
          />
        </label>
        <label>
          Priority
          <input
            type="number"
            min={0}
            max={1000}
            value={topic.priority}
            onChange={(e) =>
              change({ ...topic, priority: Number(e.target.value) })
            }
          />
        </label>
      </div>
      <label>
        Description
        <textarea
          value={topic.description}
          onChange={(e) => change({ ...topic, description: e.target.value })}
        />
      </label>
      <label>
        Keywords and phrases (comma separated)
        <input
          value={topic.keywords.join(', ')}
          onChange={(e) =>
            change({
              ...topic,
              keywords: e.target.value.split(',').map((w) => w.trim()),
            })
          }
        />
      </label>
      <button onClick={remove}>Remove {topic.label}</button>
    </fieldset>
  )
}

function ImportWizard({
  busy,
  task,
  imported,
}: {
  busy: boolean
  task: (fn: () => Promise<void>) => Promise<void>
  imported: () => Promise<void>
}) {
  const [file, setFile] = useState<File | null>(null)
  const [pasted, setPasted] = useState('')
  const [name, setName] = useState('My feedback')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [validation, setValidation] = useState<Validation | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [timezone, setTimezone] = useState('')
  const [language, setLanguage] = useState('en')
  const [ratingMin, setRatingMin] = useState(1)
  const [ratingMax, setRatingMax] = useState(5)
  const [confirmed, setConfirmed] = useState(false)
  const options = {
    mapping,
    timezone: timezone || null,
    language,
    ratingMin,
    ratingMax,
  }
  const invalidate = () => {
    setValidation(null)
    setConfirmed(false)
  }
  const inspect = async (sheet = 0) => {
    const input =
      file || new File([pasted], 'feedback.txt', { type: 'text/plain' })
    if (input.size > 25 * 1024 * 1024) throw new Error('Upload exceeds 25 MiB')
    const bytes = new Uint8Array(await input.arrayBuffer())
    let binary = ''
    for (let i = 0; i < bytes.length; i += 8192)
      binary += String.fromCharCode(...bytes.subarray(i, i + 8192))
    const data = await workbench<Preview>('/imports/preview', {
      filename: input.name,
      content: btoa(binary),
      sheet,
    })
    setPreview(data)
    setMapping({
      text:
        data.columns.find((c) =>
          /^(text|review|comment|feedback|original_text)$/i.test(c),
        ) ||
        data.columns[0] ||
        '',
    })
    invalidate()
  }
  return (
    <section className="wb-panel">
      <h2>Import feedback</h2>
      <p>
        CSV, XLSX, JSON arrays, JSONL, or text. Up to 25 MiB, 10,000 records,
        and 20,000 characters per review. Only feedback text is required.
      </p>
      <label>
        Dataset name
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={100}
        />
      </label>
      <label>
        Upload file
        <input
          type="file"
          accept=".csv,.tsv,.xlsx,.json,.jsonl,.ndjson,.txt"
          onChange={(e) => {
            setFile(e.target.files?.[0] || null)
            setPreview(null)
            invalidate()
          }}
        />
      </label>
      <label>
        Or paste one review per line
        <textarea
          value={pasted}
          onChange={(e) => {
            setPasted(e.target.value)
            setFile(null)
            setPreview(null)
            invalidate()
          }}
        />
      </label>
      <button
        disabled={busy || (!file && !pasted.trim())}
        onClick={() => {
          void task(() => inspect())
        }}
      >
        Preview upload
      </button>
      {preview && (
        <>
          <h3>Map columns</h3>
          <p>
            {preview.total} source rows. Dates are optional and never replaced
            with import time.
          </p>
          {preview.sheets.length > 1 && (
            <label>
              Workbook sheet
              <select
                onChange={(e) => {
                  void task(() => inspect(Number(e.target.value)))
                }}
              >
                {preview.sheets.map((s, i) => (
                  <option value={i} key={i}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="wb-grid">
            {FIELDS.map((field) => (
              <label key={field}>
                {field}
                {field === 'text' ? ' (required)' : ' (optional)'}
                <select
                  value={mapping[field] || ''}
                  onChange={(e) => {
                    setMapping({ ...mapping, [field]: e.target.value })
                    invalidate()
                  }}
                >
                  <option value="">Not supplied</option>
                  {preview.columns.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <label>
              Timezone for naive dates
              <input
                placeholder="e.g. Europe/Stockholm or UTC"
                value={timezone}
                onChange={(e) => {
                  setTimezone(e.target.value)
                  invalidate()
                }}
              />
            </label>
            <label>
              Default language
              <select
                value={language}
                onChange={(e) => {
                  setLanguage(e.target.value)
                  invalidate()
                }}
              >
                <option value="en">English</option>
                <option value="sv">Swedish</option>
                <option value="">Unknown (rules sentiment unavailable)</option>
              </select>
            </label>
            <label>
              Rating scale minimum
              <input
                type="number"
                value={ratingMin}
                onChange={(e) => {
                  setRatingMin(Number(e.target.value))
                  invalidate()
                }}
              />
            </label>
            <label>
              Rating scale maximum
              <input
                type="number"
                value={ratingMax}
                onChange={(e) => {
                  setRatingMax(Number(e.target.value))
                  invalidate()
                }}
              />
            </label>
          </div>
          <details>
            <summary>Source preview (first ten rows, local only)</summary>
            <pre>{JSON.stringify(preview.rows, null, 2)}</pre>
          </details>
          <button
            disabled={busy || !mapping.text}
            onClick={() => {
              void task(async () =>
                setValidation(
                  await workbench<Validation>('/imports/validate', {
                    uploadId: preview.uploadId,
                    options,
                  }),
                ),
              )
            }}
          >
            Validate mapping and privacy
          </button>
        </>
      )}
      {validation && (
        <>
          <h3>Validation report</h3>
          <div className="wb-metrics">
            {Object.entries(validation.summary).map(([label, count]) => (
              <Metric
                key={label}
                label={label}
                value={count.toLocaleString()}
              />
            ))}
          </div>
          <p>
            {validation.blocked} accepted records are blocked from
            classification by the privacy boundary. Repeated text is retained;
            duplicate source IDs are excluded.
          </p>
          <details>
            <summary>Row errors ({validation.issues.length})</summary>
            {validation.issues.map((issue) => (
              <p key={issue.row}>
                Row {issue.row}: {issue.message}
              </p>
            ))}
          </details>
          <details>
            <summary>Prepared text preview</summary>
            {validation.privacyPreview.map((row) => (
              <p key={row.row}>
                Row {row.row}: {row.redactedText}
              </p>
            ))}
          </details>
          <label className="wb-check">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I reviewed the report and approve importing the{' '}
            {validation.summary.accepted} valid records with the listed
            exclusions.
          </label>
          <button
            disabled={busy || !confirmed || validation.summary.accepted === 0}
            onClick={() => {
              void task(async () => {
                await workbench('/imports/commit', {
                  name,
                  uploadId: preview!.uploadId,
                  options,
                  acceptExclusions: true,
                })
                setPreview(null)
                setValidation(null)
                setFile(null)
                setPasted('')
                await imported()
              })
            }}
          >
            Import valid records
          </button>
        </>
      )}
    </section>
  )
}
