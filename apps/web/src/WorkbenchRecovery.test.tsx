import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { Workbench } from './Workbench'
import { visualDashboard, visualWorkbench } from './visual-fixtures'
import {
  WorkbenchError,
  type Connection,
  type workbench,
} from './workbench-api'

afterEach(() => {
  cleanup()
  window.history.replaceState(null, '', '/')
  vi.unstubAllGlobals()
})

function forbidNetwork() {
  const fetch = vi.fn(() =>
    Promise.reject(new Error('Unexpected network request in UI recovery test')),
  )
  vi.stubGlobal('fetch', fetch)
  return fetch
}

function mountApp(client: typeof workbench, page = 'classification') {
  window.history.replaceState(null, '', `/#workbench/${page}`)
  return render(<App client={visualDashboard} workbenchClient={client} />)
}

const sampleName = 'Test a representative sample (up to 25)'
const consentName = /I authorize sending prepared feedback to OpenAI/

async function chooseAI() {
  await screen.findByRole('option', { name: /Demonstration reviews/ })
  fireEvent.change(screen.getByRole('combobox', { name: 'Engine' }), {
    target: { value: 'openai' },
  })
  return screen.getByRole('button', { name: sampleName })
}

describe('workbench recovery and prerequisites', () => {
  it('recovers a failed workspace check without prompting for or transmitting credentials', async () => {
    const fetch = forbidNetwork()
    const ready = visualWorkbench()
    let checks = 0
    const client: typeof workbench = async <T,>(
      path: string,
      body?: unknown,
      method?: string,
      signal?: AbortSignal,
    ) => {
      if (path === '/session' && ++checks === 1)
        throw new Error('Local workspace unreachable')
      return ready<T>(path, body, method, signal)
    }
    render(<Workbench client={client} />)
    await screen.findByRole('heading', { name: 'Local workspace unavailable' })
    expect(screen.queryByLabelText('Owner code')).not.toBeInTheDocument()
    fireEvent.click(
      screen.getByRole('button', { name: 'Retry workspace connection' }),
    )
    await screen.findByRole('heading', { name: 'Choose data' })
    expect(checks).toBe(2)
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each([
    ['locked', 'Unlock your local workspace'],
    ['disabled', 'Start the workbench runtime'],
  ] as const)(
    'retains the explicit %s workspace state',
    async (state, title) => {
      const fetch = forbidNetwork()
      render(
        <Workbench page="Classification" client={visualWorkbench(state)} />,
      )
      await screen.findByRole('heading', { name: title })
      expect(
        screen.queryByRole('button', { name: 'Classify dataset with rules' }),
      ).not.toBeInTheDocument()
      expect(fetch).not.toHaveBeenCalled()
    },
  )

  it('offers a useful empty Results path through the shared application navigation', async () => {
    const fetch = forbidNetwork()
    mountApp(visualWorkbench('empty'), 'results')
    await screen.findByRole('heading', { name: 'No classification runs yet' })
    fireEvent.click(
      screen.getByRole('button', { name: 'Go to Classification' }),
    )
    await screen.findByRole('heading', { name: 'Configure a run' })
    expect(window.location.hash).toBe('#workbench/classification')
    expect(
      screen.getByRole('button', { name: 'Classification' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(
      screen.getByRole('button', { name: 'Classify dataset with rules' }),
    ).toBeDisabled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('opens run-history results through the central route and retains the selected run when returning', async () => {
    const fetch = forbidNetwork()
    mountApp(visualWorkbench(), 'runs')
    fireEvent.click(await screen.findByRole('button', { name: 'Inspect run' }))
    await screen.findByRole('heading', { name: 'Processing and coverage' })
    expect(window.location.hash).toBe('#workbench/results')
    expect(screen.getByRole('button', { name: 'Results' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Connections' }))
    await screen.findByRole('heading', { name: 'ChatGPT plan connection' })
    fireEvent.click(screen.getByRole('button', { name: 'Results' }))
    await screen.findByRole('heading', { name: 'Processing and coverage' })
    expect(screen.getByRole('combobox', { name: 'Selected run' })).toHaveValue(
      'run',
    )
    expect(fetch).not.toHaveBeenCalled()
  })

  it('withholds AI processing when no connection is available, even with consent checked', async () => {
    const fetch = forbidNetwork()
    const ready = visualWorkbench()
    const requests: string[] = []
    const client: typeof workbench = async <T,>(
      path: string,
      body?: unknown,
      method?: string,
      signal?: AbortSignal,
    ) => {
      requests.push(path)
      if (path === '/connections') return [] as T
      return ready<T>(path, body, method, signal)
    }
    mountApp(client)
    const sample = await chooseAI()
    fireEvent.click(screen.getByRole('checkbox', { name: consentName }))
    expect(sample).toBeDisabled()
    expect(
      screen.getByRole('combobox', { name: 'Available model' }),
    ).toBeDisabled()
    expect(
      requests.some(
        (path) => path.includes('/models') || path === '/runs/preview',
      ),
    ).toBe(false)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('sends the selected model and supported effort only after prepared-text approval', async () => {
    const fetch = forbidNetwork()
    const ready = visualWorkbench()
    const requests: { path: string; body: unknown }[] = []
    const client: typeof workbench = async <T,>(
      path: string,
      body?: unknown,
      method?: string,
      signal?: AbortSignal,
    ) => {
      requests.push({ path, body })
      return ready<T>(path, body, method, signal)
    }
    mountApp(client)
    await chooseAI()
    fireEvent.change(screen.getByRole('combobox', { name: 'Connection' }), {
      target: { value: 'connection' },
    })
    await screen.findByRole('option', { name: 'GPT-6.1 Sol · fixture' })
    fireEvent.change(
      screen.getByRole('combobox', { name: 'Available model' }),
      { target: { value: 'gpt-6.1-sol' } },
    )
    const effort = screen.getByRole('combobox', { name: 'Reasoning effort' })
    expect(
      within(effort).queryByRole('option', { name: 'None' }),
    ).not.toBeInTheDocument()
    fireEvent.change(effort, { target: { value: 'high' } })
    fireEvent.click(screen.getByRole('checkbox', { name: consentName }))
    fireEvent.click(screen.getByRole('button', { name: sampleName }))
    const dialog = await screen.findByRole('dialog', {
      name: 'Approve OpenAI processing',
    })
    expect(dialog).toHaveTextContent('gpt-6.1-sol · High effort')
    expect(requests.some((row) => row.path === '/runs' && row.body)).toBe(false)
    fireEvent.click(
      within(dialog).getByRole('button', { name: /Process .* records/ }),
    )
    await waitFor(() =>
      expect(
        requests.find((row) => row.path === '/runs' && row.body)?.body,
      ).toEqual(
        expect.objectContaining({
          model: 'gpt-6.1-sol',
          reasoningEffort: 'high',
        }),
      ),
    )
    expect(fetch).not.toHaveBeenCalled()
  })

  it('starts a 10,000-record rules run without retained AI settings or external consent', async () => {
    const fetch = forbidNetwork()
    const ready = visualWorkbench('dense')
    const requests: { path: string; body: unknown }[] = []
    const client: typeof workbench = async <T,>(
      path: string,
      body?: unknown,
      method?: string,
      signal?: AbortSignal,
    ) => {
      requests.push({ path, body })
      return ready<T>(path, body, method, signal)
    }
    mountApp(client)
    await chooseAI()
    fireEvent.change(screen.getByRole('combobox', { name: 'Connection' }), {
      target: { value: 'connection' },
    })
    await screen.findByRole('option', { name: 'GPT-6.1 Sol · fixture' })
    fireEvent.change(
      screen.getByRole('combobox', { name: 'Available model' }),
      { target: { value: 'gpt-6.1-sol' } },
    )
    fireEvent.change(
      screen.getByRole('combobox', { name: 'Reasoning effort' }),
      { target: { value: 'high' } },
    )
    fireEvent.change(screen.getByRole('combobox', { name: 'Engine' }), {
      target: { value: 'rules' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: 'Classify dataset with rules' }),
    )
    await waitFor(() =>
      expect(
        requests.find((row) => row.path === '/runs' && row.body),
      ).toBeDefined(),
    )
    const body = requests.find((row) => row.path === '/runs' && row.body)!
      .body as Record<string, unknown>
    expect(body).toEqual(
      expect.objectContaining({ engine: 'rules', mode: 'full' }),
    )
    for (const key of [
      'model',
      'connectionId',
      'reasoningEffort',
      'externalConsent',
      'sampleRunId',
    ])
      expect(body).not.toHaveProperty(key)
    expect(requests.some((row) => row.path === '/runs/preview')).toBe(false)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('explains a terminal ChatGPT renewal failure and opens Connections without enabling processing', async () => {
    const ready = visualWorkbench()
    const client: typeof workbench = async <T,>(
      path: string,
      body?: unknown,
      method?: string,
      signal?: AbortSignal,
    ) => {
      if (path.includes('/models'))
        throw new WorkbenchError(
          'The saved ChatGPT session cannot be renewed. Reconnect this account in Connections.',
          400,
          true,
        )
      return ready<T>(path, body, method, signal)
    }
    mountApp(client)
    const sample = await chooseAI()
    fireEvent.change(screen.getByRole('combobox', { name: 'Connection' }), {
      target: { value: 'connection' },
    })
    const reconnect = await screen.findByRole('button', {
      name: 'Reconnect ChatGPT account',
    })
    expect(sample).toBeDisabled()
    expect(
      screen.getByRole('combobox', { name: 'Available model' }),
    ).toBeDisabled()
    fireEvent.click(reconnect)
    await screen.findByRole('heading', { name: 'Connections', level: 1 })
    expect(
      screen.getByRole('button', { name: /Reconnect Demonstration account/ }),
    ).toBeInTheDocument()
  })

  it.each(['models-error', 'models-empty'] as const)(
    'keeps AI processing disabled for %s and offers the appropriate recovery',
    async (state) => {
      const fetch = forbidNetwork()
      mountApp(visualWorkbench(state))
      const sample = await chooseAI()
      fireEvent.change(screen.getByRole('combobox', { name: 'Connection' }), {
        target: { value: 'connection' },
      })
      if (state === 'models-error')
        await screen.findByRole('button', { name: 'Refresh models' })
      else
        await screen.findByText(/No models are available from this connection/)
      fireEvent.click(screen.getByRole('checkbox', { name: consentName }))
      expect(sample).toBeDisabled()
      expect(
        screen.getByRole('combobox', { name: 'Available model' }),
      ).toBeDisabled()
      expect(fetch).not.toHaveBeenCalled()
    },
  )

  it('recovers the catalog explicitly while preserving the separate consent prerequisite', async () => {
    const fetch = forbidNetwork()
    const ready = visualWorkbench()
    let attempts = 0
    const requests: string[] = []
    const client: typeof workbench = async <T,>(
      path: string,
      body?: unknown,
      method?: string,
      signal?: AbortSignal,
    ) => {
      requests.push(path)
      if (path.endsWith('/models') && ++attempts === 1)
        throw new Error('Catalog temporarily unavailable')
      return ready<T>(path, body, method, signal)
    }
    mountApp(client)
    const sample = await chooseAI()
    fireEvent.change(screen.getByRole('combobox', { name: 'Connection' }), {
      target: { value: 'connection' },
    })
    fireEvent.click(
      await screen.findByRole('button', { name: 'Refresh models' }),
    )
    await waitFor(() =>
      expect(
        screen.getByRole('combobox', { name: 'Available model' }),
      ).toHaveValue('demonstration-model'),
    )
    expect(attempts).toBe(2)
    expect(sample).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: consentName }))
    expect(sample).toBeEnabled()
    expect(requests).not.toContain('/runs/preview')
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each(['removed', 'permission-declined'] as const)(
    'withholds AI processing after a selected connection becomes %s',
    async (state) => {
      const ready = visualWorkbench()
      let changed = false
      const client: typeof workbench = async <T,>(
        path: string,
        body?: unknown,
        method?: string,
        signal?: AbortSignal,
      ) => {
        if (changed && path === '/connections') {
          const connections: Connection[] =
            state === 'removed'
              ? []
              : [
                  {
                    id: 'connection',
                    mode: 'chatgpt',
                    label: 'Demonstration account',
                    planEnabled: false,
                  },
                ]
          return connections as T
        }
        return ready<T>(path, body, method, signal)
      }
      mountApp(client)
      const sample = await chooseAI()
      fireEvent.change(screen.getByRole('combobox', { name: 'Connection' }), {
        target: { value: 'connection' },
      })
      await waitFor(() =>
        expect(
          screen.getByRole('combobox', { name: 'Available model' }),
        ).toHaveValue('demonstration-model'),
      )
      fireEvent.click(screen.getByRole('checkbox', { name: consentName }))
      expect(sample).toBeEnabled()
      fireEvent.click(screen.getByRole('button', { name: 'Connections' }))
      changed = true
      fireEvent.click(
        await screen.findByRole('button', { name: 'Refresh connections' }),
      )
      await waitFor(() =>
        expect(
          screen.queryByText('Working on your local request…'),
        ).not.toBeInTheDocument(),
      )
      fireEvent.click(screen.getByRole('button', { name: 'Classification' }))
      await screen.findByRole('heading', { name: 'Configure a run' })
      expect(screen.getByRole('button', { name: sampleName })).toBeDisabled()
    },
  )

  it.each(['/datasets', '/templates'] as const)(
    'withholds a rules run after the selected %s entry disappears',
    async (removedPath) => {
      const fetch = forbidNetwork()
      const ready = visualWorkbench()
      let changed = false
      const client: typeof workbench = async <T,>(
        path: string,
        body?: unknown,
        method?: string,
        signal?: AbortSignal,
      ) => {
        if (changed && path === removedPath) return [] as T
        return ready<T>(path, body, method, signal)
      }
      mountApp(client)
      await screen.findByRole('option', { name: /Demonstration reviews/ })
      expect(
        screen.getByRole('button', { name: 'Classify dataset with rules' }),
      ).toBeEnabled()
      fireEvent.click(screen.getByRole('button', { name: 'Connections' }))
      changed = true
      fireEvent.click(
        await screen.findByRole('button', { name: 'Refresh connections' }),
      )
      await waitFor(() =>
        expect(
          screen.queryByText('Working on your local request…'),
        ).not.toBeInTheDocument(),
      )
      fireEvent.click(screen.getByRole('button', { name: 'Classification' }))
      await screen.findByRole('heading', { name: 'Configure a run' })
      expect(
        screen.getByRole('button', { name: 'Classify dataset with rules' }),
      ).toBeDisabled()
      expect(fetch).not.toHaveBeenCalled()
    },
  )

  it.each(['/datasets', '/templates'] as const)(
    'does not silently switch to a replacement %s on a second refresh',
    async (removedPath) => {
      const base = visualWorkbench()
      let changed = false
      const client: typeof workbench = async <T,>(
        path: string,
        body?: unknown,
        method?: string,
        signal?: AbortSignal,
      ) => {
        if (changed && path === removedPath) {
          const entries = await base<{ id: string; name: string }[]>(path)
          return entries.map((entry) => ({
            ...entry,
            id: 'replacement',
            name: 'Replacement entry',
          })) as T
        }
        return base<T>(path, body, method, signal)
      }
      mountApp(client)
      await screen.findByRole('option', { name: /Demonstration reviews/ })
      fireEvent.click(screen.getByRole('button', { name: 'Connections' }))
      changed = true
      for (let attempt = 0; attempt < 2; attempt++) {
        fireEvent.click(
          await screen.findByRole('button', { name: 'Refresh connections' }),
        )
        await waitFor(() =>
          expect(
            screen.queryByText('Working on your local request…'),
          ).not.toBeInTheDocument(),
        )
      }
      fireEvent.click(screen.getByRole('button', { name: 'Classification' }))
      expect(
        screen.getByRole('combobox', {
          name: removedPath === '/datasets' ? 'Dataset' : 'Template revision',
        }),
      ).toHaveValue('')
      expect(
        screen.getByRole('button', { name: 'Classify dataset with rules' }),
      ).toBeDisabled()
    },
  )

  it('separates configuration fields from actions and groups related connection actions', async () => {
    mountApp(visualWorkbench())
    const classify = await screen.findByRole('button', {
      name: 'Classify dataset with rules',
    })
    await screen.findByRole('option', { name: /Demonstration reviews/ })
    const runActions = screen.getByLabelText('Run actions')
    expect(runActions).toContainElement(classify)
    expect(runActions).not.toContainElement(
      screen.getByRole('combobox', { name: 'Dataset' }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Connections' }))
    const connectionActions = await screen.findByLabelText(
      'ChatGPT connection actions',
    )
    expect(
      within(connectionActions).getByRole('button', {
        name: 'Continue with ChatGPT',
      }),
    ).toBeInTheDocument()
    expect(
      within(connectionActions).getByRole('link', { name: /Manage usage/ }),
    ).toBeInTheDocument()
    expect(
      within(connectionActions).queryByRole('combobox'),
    ).not.toBeInTheDocument()
  })
})
