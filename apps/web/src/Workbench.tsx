import { useCallback, useEffect, useRef, useState } from 'react'
import {
  workbench as defaultWorkbench,
  setWorkbenchCsrf,
  type Dataset,
  type Template,
  type Topic,
  type Run,
  type Preview,
  type Validation,
  type Connection,
} from './workbench-api'
import { type WorkbenchPage } from './application-routes'
import { useConfirmation } from './confirmation-context'
import { WorkbenchResults } from './WorkbenchResults'
import { priceReference } from './workbench-pricing'

type View = WorkbenchPage
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

export function Workbench({
  page,
  onNavigate,
  visible = true,
  client = defaultWorkbench,
}: {
  page?: WorkbenchPage
  onNavigate?: (view: WorkbenchPage) => void
  visible?: boolean
  client?: typeof defaultWorkbench
} = {}) {
  const workbench = client
  const confirm = useConfirmation()
  const [session, setSession] = useState<
    'loading' | 'disabled' | 'locked' | 'ready' | 'error'
  >('loading')
  const [localView, setLocalView] = useState<View>(
    new URLSearchParams(window.location.search).has('connection')
      ? 'Connections'
      : 'Datasets',
  )
  const view = page ?? localView
  const setView = onNavigate ?? setLocalView
  const [code, setCode] = useState('')
  const [error, setError] = useState(
    new URLSearchParams(window.location.search).get('connection') === 'error'
      ? 'ChatGPT sign-in was not completed. Return to Connections and try again; no plan usage was authorized by this failed attempt.'
      : '',
  )
  const [busy, setBusy] = useState(false)
  const [workspaceLoadError, setWorkspaceLoadError] = useState('')
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
  const [modelsState, setModelsState] = useState<
    'idle' | 'loading' | 'ready' | 'empty' | 'error'
  >('idle')
  const [modelError, setModelError] = useState('')
  const [modelRetry, setModelRetry] = useState(0)
  const [sessionRetry, setSessionRetry] = useState(0)
  const [engine, setEngine] = useState('rules')
  const [consent, setConsent] = useState(false)
  const [selectedRun, setSelectedRun] = useState('')
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
  const initialSelections = useRef(true)
  const connectionPermitted = connections.some(
    (connection) =>
      connection.id === connectionId &&
      (connection.mode === 'api' || connection.planEnabled),
  )
  const datasetReady = datasets.some(
    (dataset) => dataset.id === datasetId && dataset.status === 'ready',
  )
  const templateReady = templates.some((template) => template.id === templateId)

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
    setWorkspaceLoadError('')
    const chooseDefaults = initialSelections.current
    initialSelections.current = false
    setDatasetId((id) =>
      id
        ? d.some((row) => row.id === id && row.status === 'ready')
          ? id
          : ''
        : chooseDefaults
          ? d.find((row) => row.status === 'ready')?.id || ''
          : '',
    )
    setTemplateId((id) =>
      id
        ? t.some((row) => row.id === id)
          ? id
          : ''
        : chooseDefaults
          ? t[0]?.id || ''
          : '',
    )
    setConnectionId((id) =>
      c.some((row) => row.id === id && (row.mode === 'api' || row.planEnabled))
        ? id
        : '',
    )
  }, [workbench])
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has('connection'))
      window.history.replaceState(null, '', '/#workbench/connections')
    const expired = () => {
      setSession('locked')
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
        if (!abort.signal.aborted) {
          setError(String(e))
          setSession('error')
        }
      })
    return () => {
      abort.abort()
      window.removeEventListener('workbench-session-expired', expired)
    }
  }, [workbench, sessionRetry])
  useEffect(() => {
    if (session !== 'ready' || !visible) return
    let active = true
    const reload = () => {
      void refresh().catch((e) => {
        if (active) setWorkspaceLoadError(String(e))
      })
    }
    reload()
    const interval = window.setInterval(reload, 5000)
    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [session, refresh, visible])
  useEffect(() => {
    const abort = new AbortController()
    if (!connectionId || !connectionPermitted) {
      void Promise.resolve().then(() => {
        if (!abort.signal.aborted) {
          setModels([])
          setModel('')
          setModelsState('idle')
          setModelError('')
        }
      })
      return () => abort.abort()
    }
    void workbench<{ slug: string; displayName: string }[]>(
      `/connections/${connectionId}/models`,
      undefined,
      'GET',
      abort.signal,
    )
      .then((m) => {
        if (abort.signal.aborted) return
        setModels(m)
        setModelsState(m.length ? 'ready' : 'empty')
        setModel(m[0]?.slug || '')
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setModels([])
          setModel('')
          setModelError(String(e))
          setModelsState('error')
        }
      })
    return () => abort.abort()
  }, [connectionId, connectionPermitted, workbench, modelRetry])
  const selectRun = (id: string) => {
    setSelectedRun(id)
    setView('Results')
  }

  const startRun = async (
    mode: 'sample' | 'full',
    sample?: Run,
    externalConsent = consent,
  ) => {
    const options = {
      datasetId: sample?.dataset_id || datasetId,
      templateId: sample?.template_id || templateId,
      engine: sample?.snapshot.engine || engine,
      connectionId: sample?.snapshot.connectionId || connectionId,
      model: sample?.snapshot.model || model,
      mode,
      externalConsent,
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
        !(await confirm({
          title: 'Approve OpenAI processing',
          confirmLabel: `Process ${preview.selected} records`,
          message: `Process ${preview.selected} records with ${options.model}? ${preview.blocked} are privacy-blocked; ${preview.reused} results will be reused. Prepared examples:\n\n${examples}\n\nApproved feedback will be sent to OpenAI using the selected connection. This consumes your plan allowance or API billing.`,
        }))
      )
        return
    }
    const run = await workbench<Run>('/runs', options)
    requestKey.current = crypto.randomUUID()
    selectRun(run.id)
    await refresh()
  }

  return (
    <div className="wb-shell">
      <main id="workbench-main" className="wb-main" aria-busy={busy}>
        <p className="eyebrow">Local workbench</p>
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
        {session === 'ready' && workspaceLoadError && (
          <div className="wb-error" role="alert">
            <p>Workspace lists could not be refreshed. {workspaceLoadError}</p>
            <div className="wb-actions">
              <button
                disabled={busy}
                onClick={async () => {
                  setBusy(true)
                  try {
                    await refresh()
                  } catch (failure) {
                    setWorkspaceLoadError(String(failure))
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Retry workspace data
              </button>
            </div>
          </div>
        )}
        {busy && <p role="status">Working on your local request…</p>}
        {session === 'loading' ? (
          <p role="status">Checking local workspace…</p>
        ) : session === 'error' ? (
          <section className="wb-panel">
            <h2>Local workspace unavailable</h2>
            <p>
              Check that the local runtime is running, then retry the
              connection.
            </p>
            <div className="wb-actions">
              <button
                onClick={() => {
                  setError('')
                  setSession('loading')
                  setSessionRetry((value) => value + 1)
                }}
              >
                Retry workspace connection
              </button>
            </div>
          </section>
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
            <section
              hidden={view !== 'Datasets'}
              aria-label="Dataset workspace"
            >
              <section className="wb-panel">
                <h2>Choose data</h2>
                <p>
                  Start with your own reviews or a reproducible rules scenario.
                  For the existing SemIf/rules/Sol comparison, open the recorded
                  showcase.
                </p>
                <button
                  className="button--primary"
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
                client={workbench}
                busy={busy}
                task={task}
                imported={async (dataset) => {
                  setDatasetId(dataset.id)
                  await refresh()
                  setView('Classification')
                }}
              />
              <section className="wb-panel">
                <h2>Saved datasets</h2>
                {datasets.length === 0 ? (
                  <p>No datasets imported yet.</p>
                ) : (
                  <div
                    className="wb-table-wrap"
                    role="region"
                    aria-label="Saved datasets table"
                    tabIndex={0}
                  >
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
                              <div className="wb-actions wb-actions--row">
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
                                  className="button--destructive"
                                  disabled={busy || d.status !== 'ready'}
                                  onClick={async () => {
                                    if (
                                      await confirm({
                                        title: 'Delete dataset',
                                        destructive: true,
                                        confirmLabel: 'Delete dataset',
                                        message: `Delete ${d.name} and all its runs and results? This permanently purges local data.`,
                                      })
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
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </section>
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
                        <option value="">Choose template revision</option>
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
                          href="#workbench/connections"
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
                              setModelsState(
                                e.target.value ? 'loading' : 'idle',
                              )
                              setModelError('')
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
                            disabled={
                              !connectionPermitted || modelsState !== 'ready'
                            }
                            value={model}
                            onChange={(e) => {
                              setModel(e.target.value)
                              requestKey.current = crypto.randomUUID()
                            }}
                          >
                            <option value="">
                              {!connectionId
                                ? 'Choose a connection first'
                                : modelsState === 'loading'
                                  ? 'Loading models…'
                                  : modelsState === 'error'
                                    ? 'Models unavailable'
                                    : modelsState === 'empty'
                                      ? 'No available models'
                                      : 'Choose model'}
                            </option>
                            {models.map((m) => (
                              <option key={m.slug} value={m.slug}>
                                {m.displayName}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                      {modelsState === 'error' && (
                        <div role="alert">
                          <p>{modelError}</p>
                          <div className="wb-actions">
                            <button
                              disabled={busy}
                              onClick={() => {
                                setModelsState('loading')
                                setModelError('')
                                setModelRetry((value) => value + 1)
                              }}
                            >
                              Retry model catalog
                            </button>
                          </div>
                        </div>
                      )}
                      {modelsState === 'empty' && (
                        <p>
                          No models are available from this connection. Review
                          Connections or explicitly choose another account.
                        </p>
                      )}
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
                  <div className="wb-actions" aria-label="Run actions">
                    <button
                      className="button--primary"
                      disabled={
                        busy ||
                        !datasetReady ||
                        !templateReady ||
                        (engine === 'openai' &&
                          (!connectionPermitted ||
                            modelsState !== 'ready' ||
                            !model ||
                            !consent))
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
                  </div>
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
                        className="button--primary"
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
                  <div
                    className="wb-table-wrap"
                    role="region"
                    aria-label="Run history table"
                    tabIndex={0}
                  >
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
                              <div className="wb-actions wb-actions--row">
                                <button
                                  onClick={() => {
                                    selectRun(r.id)
                                  }}
                                >
                                  Inspect {r.id.slice(0, 8)}
                                </button>
                                {['queued', 'running'].includes(r.status) && (
                                  <button
                                    className="button--destructive"
                                    disabled={busy}
                                    onClick={() => {
                                      void task(async () => {
                                        if (
                                          !(await confirm({
                                            title: 'Cancel processing',
                                            confirmLabel: 'Stop run',
                                            message:
                                              'Stop dispatching records? Successful results are retained. An in-flight model request may still consume usage.',
                                          }))
                                        )
                                          return
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
                                    className="button--primary"
                                    disabled={busy}
                                    onClick={async () => {
                                      if (
                                        await confirm({
                                          title: 'Resume unfinished records',
                                          confirmLabel: 'Resume run',
                                          message:
                                            'Resume unfinished records? Interrupted OpenAI requests can consume additional usage.',
                                        })
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
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}
            <section hidden={view !== 'Results'} aria-label="Results workspace">
              <WorkbenchResults
                key={selectedRun || 'none'}
                runId={selectedRun}
                runs={runs}
                datasets={datasets}
                client={workbench}
                active={visible && view === 'Results'}
                busy={busy}
                onRunChange={selectRun}
                onUnavailable={() => {
                  setSelectedRun('')
                  setNotice('This run or dataset is no longer available.')
                }}
                onClassify={() => setView('Classification')}
                onRemaining={(run) => {
                  void task(() => startRun('full', run, true))
                }}
              />
            </section>
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
                  <div
                    className="wb-actions"
                    aria-label="ChatGPT connection actions"
                  >
                    <button
                      className="button--primary"
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
                  </div>
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
      <button className="button--destructive" onClick={remove}>
        Remove {topic.label}
      </button>
    </fieldset>
  )
}

function ImportWizard({
  busy,
  task,
  imported,
  client,
}: {
  busy: boolean
  task: (fn: () => Promise<void>) => Promise<void>
  imported: (dataset: Dataset) => Promise<void>
  client: typeof defaultWorkbench
}) {
  const workbench = client
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
        className="button--primary"
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
            className="button--primary"
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
            className="button--primary"
            disabled={busy || !confirmed || validation.summary.accepted === 0}
            onClick={() => {
              void task(async () => {
                const dataset = await workbench<Dataset>('/imports/commit', {
                  name,
                  uploadId: preview!.uploadId,
                  options,
                  acceptExclusions: true,
                })
                setPreview(null)
                setValidation(null)
                setFile(null)
                setPasted('')
                await imported(dataset)
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
