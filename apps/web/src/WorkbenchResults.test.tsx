import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { WorkbenchResults } from './WorkbenchResults'
import { visualWorkbench, type FixtureState } from './visual-fixtures'
import {
  type Comparison,
  type Dataset,
  type Results,
  type Run,
  type TrendResult,
  WorkbenchError,
  type workbench,
} from './workbench-api'

type Client = typeof workbench
type Request = {
  path: string
  body?: unknown
  method?: string
  signal?: AbortSignal
}
type Handler = (request: Request, base: Client) => Promise<unknown>

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((accept, decline) => {
    resolve = accept
    reject = decline
  })
  return { promise, resolve, reject }
}

async function setup(state: FixtureState = 'ready', handler?: Handler) {
  const base = visualWorkbench(state)
  const runs = await base<Run[]>('/runs')
  const datasets = await base<Dataset[]>('/datasets')
  const requests: Request[] = []
  const client = (async (
    path: string,
    body?: unknown,
    method?: string,
    signal?: AbortSignal,
  ) => {
    const request = { path, body, method, signal }
    requests.push(request)
    return handler ? handler(request, base) : base(path, body, method, signal)
  }) as Client
  const onRunChange = vi.fn()
  const onUnavailable = vi.fn()
  const props = {
    runId: 'run',
    runs,
    datasets,
    client,
    active: true,
    busy: false,
    onRunChange,
    onUnavailable,
    onClassify: vi.fn(),
    onRemaining: vi.fn(),
  }
  return { base, requests, props }
}

async function ready() {
  return screen.findByRole('heading', { name: 'Record evidence' })
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Workbench result inspection journey', () => {
  it('uses discovered selectors with All defaults and separates missing product from literal None', async () => {
    const { props, requests } = await setup()
    render(<WorkbenchResults {...props} />)
    await ready()
    for (const field of [
      'Topic',
      'Sentiment',
      'Language',
      'Product',
      'Group',
    ]) {
      const control = screen.getByRole('combobox', { name: field })
      expect(control).toHaveValue('')
      expect(
        within(control).getByRole('option', {
          name: new RegExp(`^All ${field.toLowerCase()}`),
        }),
      ).toBeInTheDocument()
    }
    expect(
      screen.queryByRole('textbox', { name: 'Topic' }),
    ).not.toBeInTheDocument()
    const product = screen.getByRole('combobox', { name: 'Product' })
    expect(
      within(product).getByRole('option', { name: /^None \(/ }),
    ).toHaveValue('"None"')
    expect(
      within(product).getByRole('option', { name: /^Not supplied \(/ }),
    ).toHaveValue('null')
    fireEvent.change(product, { target: { value: '"None"' } })
    await ready()
    expect(requests.at(-1)?.path).toContain('product=None')
    expect(requests.at(-1)?.path).not.toContain('missing=product')
    fireEvent.change(product, { target: { value: 'null' } })
    await ready()
    expect(requests.at(-1)?.path).toContain('missing=product')
    expect(requests.at(-1)?.path).not.toContain('product=None')
    expect(screen.getByRole('combobox', { name: 'Sentiment' })).toContainHTML(
      'Unavailable',
    )
  })

  it('retains run-wide facet counts beyond the first 50 evidence records and exports all filtered pages', async () => {
    const { props, requests } = await setup('dense')
    const createObjectURL = vi.fn(() => 'blob:fixture')
    vi.stubGlobal(
      'URL',
      class extends URL {
        static override createObjectURL = createObjectURL
        static override revokeObjectURL = vi.fn()
      },
    )
    const download = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})
    render(<WorkbenchResults {...props} />)
    await ready()
    const table = screen.getByRole('region', {
      name: 'Classified record evidence table',
    })
    expect(within(table).getAllByRole('row')).toHaveLength(51)
    const product = screen.getByRole('combobox', { name: 'Product' })
    expect(
      within(product).getByRole('option', { name: /None \(1.?429\)/ }),
    ).toBeInTheDocument()
    fireEvent.change(screen.getByRole('combobox', { name: 'Language' }), {
      target: { value: '"en"' },
    })
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await ready()
    expect(requests.at(-1)?.path).toContain('page=2')
    fireEvent.click(screen.getByRole('button', { name: 'Export JSON' }))
    await waitFor(() => expect(download).toHaveBeenCalledTimes(1))
    const exported = [...requests]
      .reverse()
      .find((request) => request.path.includes('/export'))!
    const query = new URLSearchParams(exported.path.split('?')[1])
    expect(query.get('language')).toBe('en')
    expect(query.has('page')).toBe(false)
    expect(query.get('original')).toBe('false')
    expect(createObjectURL).toHaveBeenCalledTimes(1)
  })

  it('keeps filters mounted during delayed requests and rejects reversed older responses', async () => {
    const service = deferred<Results>()
    const quality = deferred<Results>()
    const { props, base, requests } = await setup(
      'ready',
      (request, fixture) => {
        if (request.path.includes('/results?topic=service'))
          return service.promise
        if (request.path.includes('/results?topic=quality'))
          return quality.promise
        return fixture(
          request.path,
          request.body,
          request.method,
          request.signal,
        )
      },
    )
    render(<WorkbenchResults {...props} />)
    await ready()
    const topic = screen.getByRole('combobox', { name: 'Topic' })
    fireEvent.change(topic, { target: { value: '"service"' } })
    expect(screen.getByRole('combobox', { name: 'Topic' })).toBe(topic)
    expect(topic).toBeEnabled()
    expect(screen.getByText('Loading results…')).toBeInTheDocument()
    fireEvent.change(topic, { target: { value: '"quality"' } })
    const qualityResult = await base<Results>(
      '/runs/run/results?topic=quality&page=1',
    )
    await act(async () => quality.resolve(qualityResult))
    await ready()
    expect(screen.getByRole('combobox', { name: 'Topic' })).toHaveValue(
      '"quality"',
    )
    const countBefore = screen.getByRole('button', {
      name: /Filtered results/,
    }).textContent
    const oldResult = await base<Results>(
      '/runs/run/results?topic=service&page=1',
    )
    await act(async () => service.resolve(oldResult))
    expect(
      screen.getByRole('button', { name: /Filtered results/ }).textContent,
    ).toBe(countBefore)
    expect(
      requests.find((request) => request.path.includes('topic=service'))?.signal
        ?.aborted,
    ).toBe(true)
  })

  it('pins a distribution without filtering until explicitly requested, then disables topic trend analysis', async () => {
    const { props, requests } = await setup()
    render(<WorkbenchResults {...props} />)
    await ready()
    const trigger = screen.getByRole('button', { name: /^service/ })
    fireEvent.mouseEnter(trigger)
    expect(screen.getByRole('tooltip')).toHaveTextContent('Topic: service')
    fireEvent.click(trigger)
    const panel = screen.getByRole('complementary', { name: 'Topic: service' })
    expect(within(panel).getByText('Read snapshot (UTC)')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Topic' })).toHaveValue('')
    fireEvent.click(
      within(panel).getByRole('button', { name: 'View matching records' }),
    )
    await ready()
    expect(screen.getByRole('combobox', { name: 'Topic' })).toHaveValue(
      '"service"',
    )
    expect(
      screen.getByRole('button', { name: 'Simple rate change' }),
    ).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Beta-Binomial candidate' }),
    ).toBeDisabled()
    expect(requests.some((request) => request.path.includes('/trends'))).toBe(
      false,
    )
  })

  it('drills a chart period into inclusive dates while keeping record provenance inspectable', async () => {
    const { props, requests } = await setup()
    render(<WorkbenchResults {...props} />)
    await ready()
    const inspect = screen.getByRole('button', { name: 'Inspect row 1' })
    fireEvent.click(inspect)
    const evidence = screen.getByRole('complementary', { name: 'Record 1' })
    expect(within(evidence).getByText('b'.repeat(64))).toBeInTheDocument()
    expect(within(evidence).getByText('a'.repeat(64))).toBeInTheDocument()
    expect(
      within(evidence).getByText('Recorded sentiment matches'),
    ).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(inspect).toHaveFocus()
    const chart = screen.getByRole('button', {
      name: /Inspect observed record volume/,
    })
    fireEvent.keyDown(chart, { key: 'Home' })
    fireEvent.keyDown(chart, { key: 'Enter' })
    const period = screen.getByRole('complementary', { name: '2026-09-02' })
    fireEvent.click(
      within(period).getByRole('button', { name: 'View matching records' }),
    )
    await ready()
    expect(screen.getByLabelText('Date from (UTC)')).toHaveValue('2026-09-02')
    expect(screen.getByLabelText('Date through (UTC)')).toHaveValue(
      '2026-09-02',
    )
    expect(requests.at(-1)?.path).toContain(
      'dateFrom=2026-09-02&dateTo=2026-09-02',
    )
  })

  it.each(['trend', 'comparison', 'export'] as const)(
    'rejects a pending %s response after changing the cohort',
    async (operation) => {
      const pending = deferred<unknown>()
      const { props } = await setup('ready', (request, fixture) => {
        if (
          (operation === 'trend' && request.path.includes('/trends')) ||
          (operation === 'comparison' && request.path === '/compare') ||
          (operation === 'export' && request.path.includes('/export'))
        )
          return pending.promise
        return fixture(
          request.path,
          request.body,
          request.method,
          request.signal,
        )
      })
      const matchingRun = { ...props.runs[0]!, id: 'matching-run' }
      props.runs = [...props.runs, matchingRun]
      const createObjectURL = vi.fn(() => 'blob:fixture')
      vi.stubGlobal(
        'URL',
        class extends URL {
          static override createObjectURL = createObjectURL
          static override revokeObjectURL = vi.fn()
        },
      )
      const download = vi
        .spyOn(HTMLAnchorElement.prototype, 'click')
        .mockImplementation(() => {})
      render(<WorkbenchResults {...props} />)
      await ready()
      if (operation === 'trend')
        fireEvent.click(
          screen.getByRole('button', { name: 'Simple rate change' }),
        )
      else if (operation === 'comparison') {
        fireEvent.change(
          screen.getByRole('combobox', { name: 'Compare to run' }),
          { target: { value: 'matching-run' } },
        )
        fireEvent.click(
          screen.getByRole('button', { name: 'Compare shared records' }),
        )
      } else
        fireEvent.click(screen.getByRole('button', { name: 'Export JSON' }))
      fireEvent.change(screen.getByRole('combobox', { name: 'Language' }), {
        target: { value: '"sv"' },
      })
      await ready()
      const response:
        TrendResult | Comparison | { filename: string; content: string } =
        operation === 'trend'
          ? {
              method: 'simple_rate_change',
              reason: 'stale_unique_result',
              candidates: [],
            }
          : operation === 'comparison'
            ? {
                shared: 24,
                leftProcessed: 24,
                rightProcessed: 24,
                agreement: 0.5,
                disagreements: [],
                disagreementCount: 12,
                label: 'STALE COMPARISON',
              }
            : { filename: 'stale.json', content: '{"stale":true}' }
      await act(async () => pending.resolve(response))
      expect(screen.queryByText('stale unique result')).not.toBeInTheDocument()
      expect(screen.queryByText(/STALE COMPARISON/)).not.toBeInTheDocument()
      expect(createObjectURL).not.toHaveBeenCalled()
      expect(download).not.toHaveBeenCalled()
    },
  )

  it('rejects pending responses after the parent changes the selected run and excludes incompatible comparison options', async () => {
    const oldResults = deferred<Results>()
    const { props, base } = await setup('ready', (request, fixture) => {
      if (request.path.startsWith('/runs/run/results'))
        return oldResults.promise
      if (request.path.startsWith('/runs/next-run/results'))
        return fixture<Results>(
          request.path.replace('/runs/next-run/', '/runs/run/'),
        ).then((result) => ({
          ...result,
          run: { ...result.run, id: 'next-run' },
        }))
      return fixture(request.path, request.body, request.method, request.signal)
    })
    const nextRun = { ...props.runs[0]!, id: 'next-run' }
    const mismatchedRun = {
      ...props.runs[0]!,
      id: 'wrong-protocol',
      snapshot: { ...props.runs[0]!.snapshot, protocolHash: 'other-protocol' },
    }
    props.runs = [...props.runs, nextRun, mismatchedRun]
    const { rerender } = render(<WorkbenchResults key="run" {...props} />)
    expect(screen.getByText('Loading results…')).toBeInTheDocument()
    rerender(<WorkbenchResults key="next-run" {...props} runId="next-run" />)
    await ready()
    await act(async () =>
      oldResults.resolve(await base<Results>('/runs/run/results?page=1')),
    )
    expect(screen.getByRole('combobox', { name: 'Selected run' })).toHaveValue(
      'next-run',
    )
    const compare = screen.getByRole('combobox', { name: 'Compare to run' })
    expect(
      within(compare).queryByRole('option', { name: /wrong-pr/ }),
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Filtered results/ }))
    expect(
      screen.getByRole('complementary', {
        name: 'Filtered successful records',
      }),
    ).toHaveTextContent('Run next-run')
  })

  it('removes a pinned record when authorization is lost without changing the cohort', async () => {
    let forbidden = false
    const { props } = await setup('ready', (request, fixture) =>
      forbidden && request.path.includes('/results')
        ? Promise.reject(new WorkbenchError('Access denied', 403))
        : fixture(request.path, request.body, request.method, request.signal),
    )
    const { rerender } = render(<WorkbenchResults {...props} />)
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Inspect row 1' }))
    expect(
      screen.getByRole('complementary', { name: 'Record 1' }),
    ).toBeInTheDocument()
    rerender(<WorkbenchResults {...props} active={false} />)
    forbidden = true
    rerender(<WorkbenchResults {...props} active={true} />)
    await screen.findByRole('alert')
    expect(
      screen.queryByRole('complementary', { name: 'Record 1' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Record evidence' }),
    ).not.toBeInTheDocument()
  })

  it('does not offer advanced date or missing-value drilldown on an older runtime', async () => {
    const { props } = await setup('ready', async (request, fixture) => {
      const result = await fixture<Results>(
        request.path,
        request.body,
        request.method,
        request.signal,
      )
      if (request.path.includes('/results')) {
        const copy = { ...result }
        delete copy.filters
        delete copy.facets
        return copy
      }
      return result
    })
    render(<WorkbenchResults {...props} />)
    await ready()
    expect(screen.getByLabelText('Date from (UTC)')).toBeDisabled()
    expect(screen.getByLabelText('Date through (UTC)')).toBeDisabled()
    fireEvent.keyDown(
      screen.getByRole('button', { name: /Inspect observed record volume/ }),
      { key: 'Enter' },
    )
    expect(
      screen.queryByRole('button', { name: 'View matching records' }),
    ).not.toBeInTheDocument()
  })

  it('reports request errors with retry rather than leaving Results stuck loading', async () => {
    let fail = true
    const { props } = await setup('ready', (request, fixture) => {
      if (fail && request.path.includes('/results'))
        return Promise.reject(new Error('Results fixture unavailable'))
      return fixture(request.path, request.body, request.method, request.signal)
    })
    render(<WorkbenchResults {...props} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Results fixture unavailable',
    )
    expect(screen.queryByText('Loading results…')).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Topic' })).toBeInTheDocument()
    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Retry results' }))
    await ready()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
