import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import type { DashboardClient } from './dashboard-api'
import {
  DecisionDetail,
  EvidenceTable,
  SignalList,
} from './dashboard-components'
import type {
  EvaluationComparisonResponse,
  MetadataResponse,
  OverviewResponse,
  TrendOverviewResponse,
} from './dashboard-types'
import {
  demoDetail,
  demoEvidence,
  demoEvaluation,
  demoMetadata,
  demoOverview,
  demoSignal,
  demoTrends,
  emptyLiveMetadata,
  liveMetadata,
  liveEvaluation,
  liveOverview,
  liveTrends,
  restrictedDetail,
} from './test-fixtures'

afterEach(() => cleanup())

function createClient(
  overrides: Partial<DashboardClient> = {},
): DashboardClient {
  return {
    metadata: vi.fn(async () => demoMetadata),
    overview: vi.fn(async () => demoOverview),
    trends: vi.fn(async (context) =>
      context === 'live' ? liveTrends : demoTrends,
    ),
    evaluation: vi.fn(async (context) =>
      context === 'live' ? liveEvaluation : demoEvaluation,
    ),
    signal: vi.fn(async () => demoSignal),
    evidence: vi.fn(async (_context, _signal, _filters, page) =>
      demoEvidence(page),
    ),
    detail: vi.fn(async () => demoDetail),
    ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve
  })
  return { promise, resolve }
}

describe('dashboard journey', () => {
  it('collapses and reopens navigation without resetting the selected context', async () => {
    render(<App client={createClient()} />)
    await screen.findByRole('heading', { name: 'Imported feedback' })
    const toggle = screen.getByRole('button', { name: 'Collapse navigation' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(toggle)
    expect(
      screen.queryByRole('navigation', { name: 'Primary navigation' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('group', { name: 'Presentation context' }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Imported feedback' }),
    ).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
    expect(
      screen.getByRole('navigation', { name: 'Primary navigation' }),
    ).toBeInTheDocument()
    expect(
      within(
        screen.getByRole('group', { name: 'Presentation context' }),
      ).getByRole('button', { name: 'Demo' }),
    ).toHaveAttribute('aria-pressed', 'true')
  })

  it('renders the synthetic demo with contract percentages, denominators, and the historical source range', async () => {
    const client = createClient()
    render(<App client={client} />)

    expect(
      await screen.findByRole('heading', { name: 'Imported feedback' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Demo — selectable synthetic decisions'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Imported feedback' }),
    ).toBeInTheDocument()
    const coverageCard = screen
      .getByRole('heading', { name: 'Illustrative analytical coverage' })
      .closest('article')
    expect(coverageCard).not.toBeNull()
    expect(within(coverageCard!).getByText('83.3%')).toBeInTheDocument()
    expect(screen.getByText('12 classified of 12 imported')).toBeInTheDocument()
    expect(screen.getByText('10 eligible of 12 imported')).toBeInTheDocument()
    expect(screen.getAllByText('6 of 10 eligible')).toHaveLength(2)
    expect(screen.queryByText('6,000%')).not.toBeInTheDocument()
    expect(
      screen.getByRole('group', { name: 'Presentation context' }),
    ).toBeInTheDocument()

    expect(screen.getByLabelText('From')).toHaveValue('2026-05-01')
    expect(screen.getByLabelText('To (exclusive)')).toHaveValue('2026-06-01')
    expect(client.overview).toHaveBeenCalledWith(
      'demo',
      expect.objectContaining({
        from: '2026-05-01T00:00:00Z',
        toExclusive: '2026-06-01T00:00:00Z',
      }),
      expect.any(Object),
    )
  })

  it('normalizes exact source instants to stable UTC date boundaries and rejects invalid date edits locally', async () => {
    const client = createClient({
      metadata: vi.fn(async () => ({
        ...demoMetadata,
        availableRange: {
          from: '2026-05-01T11:34:44Z',
          toExclusive: '2026-05-31T17:35:00.001Z',
        },
      })),
    })
    render(<App client={client} />)

    await waitFor(() =>
      expect(client.overview).toHaveBeenLastCalledWith(
        'demo',
        expect.objectContaining({
          from: '2026-05-01T00:00:00Z',
          toExclusive: '2026-06-01T00:00:00Z',
        }),
        expect.any(Object),
      ),
    )
    expect(screen.getByLabelText('From')).toHaveValue('2026-05-01')
    expect(screen.getByLabelText('To (exclusive)')).toHaveValue('2026-06-01')

    const callsBeforeInvalidEdits = vi.mocked(client.overview).mock.calls.length
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('From'), {
      target: { value: '2026-06-01' },
    })
    expect(vi.mocked(client.overview).mock.calls).toHaveLength(
      callsBeforeInvalidEdits,
    )

    fireEvent.change(screen.getByLabelText('To (exclusive)'), {
      target: { value: '2026-05-31' },
    })
    fireEvent.change(screen.getByLabelText('To (exclusive)'), {
      target: { value: '2026-06-01' },
    })
    await waitFor(() =>
      expect(client.overview).toHaveBeenLastCalledWith(
        'demo',
        expect.objectContaining({
          from: '2026-05-01T00:00:00Z',
          toExclusive: '2026-06-01T00:00:00Z',
        }),
        expect.any(Object),
      ),
    )
  })

  it('keeps the newest same-context overview when filter requests resolve in reverse', async () => {
    const topicRequest = deferred<OverviewResponse>()
    const languageRequest = deferred<OverviewResponse>()
    const client = createClient({
      overview: vi.fn((_context, filters) => {
        if (filters?.language === 'en') return languageRequest.promise
        if (filters?.topic === 'delivery_delay') return topicRequest.promise
        return Promise.resolve(demoOverview)
      }),
    })
    render(<App client={client} />)
    await screen.findByRole('heading', { name: 'Imported feedback' })

    fireEvent.change(screen.getByLabelText('Topic'), {
      target: { value: 'delivery_delay' },
    })
    await waitFor(() => expect(client.overview).toHaveBeenCalledTimes(2))
    fireEvent.change(screen.getByLabelText('Language'), {
      target: { value: 'en' },
    })
    await waitFor(() => expect(client.overview).toHaveBeenCalledTimes(3))

    const newest = structuredClone(demoOverview)
    newest.metrics[0]!.value = 222
    newest.metrics[0]!.numerator = 222
    const stale = structuredClone(demoOverview)
    stale.metrics[0]!.value = 111
    stale.metrics[0]!.numerator = 111
    await act(async () => languageRequest.resolve(newest))
    expect(await screen.findByText('222')).toBeInTheDocument()
    await act(async () => topicRequest.resolve(stale))
    expect(screen.getByText('222')).toBeInTheDocument()
    expect(screen.queryByText('111')).not.toBeInTheDocument()
  })

  it('switches the complete demo dataset between SemIf, rules, and Sol', async () => {
    const client = createClient()
    render(<App client={client} />)

    await screen.findByRole('heading', { name: 'Imported feedback' })
    const selector = screen.getByRole('region', {
      name: 'Demo decision method',
    })
    const semif = within(selector).getByRole('button', { name: /SemIf/i })
    const rules = within(selector).getByRole('button', {
      name: /Rules baseline/i,
    })
    const sol = within(selector).getByRole('button', { name: /Sol medium/i })

    expect(sol).toHaveAttribute('aria-pressed', 'true')
    expect(semif).toHaveAttribute('aria-pressed', 'false')
    expect(rules).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(semif)

    await waitFor(() =>
      expect(client.overview).toHaveBeenLastCalledWith(
        'demo',
        expect.objectContaining({
          sourceKey: 'synthetic/feedback-decision-semif/1.0.0',
        }),
        expect.any(Object),
      ),
    )
    expect(semif).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Selected source')).toHaveTextContent(
      'SemIf-reviewed synthetic feedback',
    )
    expect(screen.getByRole('status')).toHaveTextContent(
      'SemIf-reviewed synthetic feedback powers the overview, filters, and evidence.',
    )
  })

  it('renders the experimental AI-reference comparison with an explicit not-human-gold label', async () => {
    render(<App client={createClient()} />)

    expect(
      await screen.findByRole('heading', {
        name: 'Experimental AI-reference comparison',
      }),
    ).toBeInTheDocument()
    expect(screen.getAllByText(/not human gold/i)).toHaveLength(3)
    expect(screen.getByText('gpt-5.6-sol · medium')).toBeInTheDocument()
    expect(
      screen.getByText('semif-qwen3.5-4b-mlx-q4-851bf6e8'),
    ).toBeInTheDocument()
    expect(screen.getByText('rules-1.0.0')).toBeInTheDocument()
    expect(screen.getByText('192 / 480')).toBeInTheDocument()
    expect(screen.getByText('$0.39')).toBeInTheDocument()
    expect(screen.getByText('477,777 tokens')).toBeInTheDocument()
    expect(screen.getByText('$0.98')).toBeInTheDocument()
    expect(screen.getByText('78.3%')).toBeInTheDocument()
    expect(screen.getByText('84.9%')).toBeInTheDocument()
    expect(screen.getByText('99.9%')).toBeInTheDocument()

    const comparison = screen.getByRole('table', {
      name: 'Tested models and methods',
    })
    expect(within(comparison).getByText('83.3%')).toBeInTheDocument()
    expect(within(comparison).getByText('88.1%')).toBeInTheDocument()
    expect(
      within(comparison)
        .getAllByRole('columnheader')
        .map((header) => header.textContent),
    ).toEqual([
      'Measure',
      'Local open modelSemIf · Qwen3.5-4B',
      'General-purpose LLMGPT-5.4 Mini',
      'Deterministic methodRules baseline',
    ])
    expect(within(comparison).getByText('Run status')).toBeInTheDocument()
    expect(within(comparison).getByText('Recorded errors')).toBeInTheDocument()
    expect(
      within(comparison).getByText('Estimated 480-record cost'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/limited linguistic variety in the synthetic corpus/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        /LLM quality values use only the 192 completed records/i,
      ),
    ).toBeInTheDocument()
    const languageTable = screen.getByRole('table', {
      name: 'Primary-topic results by language',
    })
    expect(within(languageTable).getByText('86.9%')).toBeInTheDocument()
    expect(within(languageTable).getByText('90.1%')).toBeInTheDocument()
    expect(within(languageTable).getByText('74.1%')).toBeInTheDocument()
    expect(within(languageTable).getByText('84.8%')).toBeInTheDocument()
    expect(screen.getAllByRole('cell', { name: '302' })).toHaveLength(2)
  })

  it('uses the Orbital Clarity dark surface with an accessible motion control', async () => {
    render(<App client={createClient()} />)

    await screen.findByRole('heading', { name: 'Feedback overview' })
    expect(document.documentElement).not.toHaveAttribute('data-theme')
    expect(
      screen.getByRole('button', { name: /background|texture/i }),
    ).toHaveAttribute('aria-pressed')
    expect(document.querySelector('.orbital-backdrop')).toBeInTheDocument()
  })

  it('keeps live evaluation unavailable while awaiting human labels', async () => {
    const client = createClient({
      metadata: vi.fn(async (context) =>
        context === 'live' ? liveMetadata : demoMetadata,
      ),
      overview: vi.fn(async (context) =>
        context === 'live' ? liveOverview : demoOverview,
      ),
    })
    render(<App client={client} />)
    fireEvent.click(screen.getByRole('button', { name: 'Live' }))

    expect(
      await screen.findByRole('heading', {
        name: 'Evaluation unavailable — awaiting human labels',
      }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', {
        name: 'Experimental AI-reference comparison',
      }),
    ).not.toBeInTheDocument()
  })

  it('ignores a stale demo evaluation response after switching to live', async () => {
    let resolveDemo: ((value: EvaluationComparisonResponse) => void) | undefined
    const delayedDemo = new Promise<EvaluationComparisonResponse>((resolve) => {
      resolveDemo = resolve
    })
    const client = createClient({
      metadata: vi.fn(async (context) =>
        context === 'live' ? liveMetadata : demoMetadata,
      ),
      overview: vi.fn(async (context) =>
        context === 'live' ? liveOverview : demoOverview,
      ),
      evaluation: vi.fn((context) =>
        context === 'demo' ? delayedDemo : Promise.resolve(liveEvaluation),
      ),
    })
    render(<App client={client} />)

    fireEvent.click(screen.getByRole('button', { name: 'Live' }))
    await screen.findByRole('heading', {
      name: 'Evaluation unavailable — awaiting human labels',
    })

    resolveDemo?.(demoEvaluation)
    await Promise.resolve()
    expect(
      screen.queryByRole('heading', {
        name: 'Experimental AI-reference comparison',
      }),
    ).not.toBeInTheDocument()
  })

  it('offers a regional retry after an evaluation failure', async () => {
    let attempt = 0
    const client = createClient({
      evaluation: vi.fn(async () => {
        attempt += 1
        if (attempt === 1) throw new Error('Comparison report unavailable')
        return demoEvaluation
      }),
    })
    render(<App client={client} />)

    const errorHeading = await screen.findByRole('heading', {
      name: 'Evaluation comparison could not be loaded',
    })
    const errorPanel = errorHeading.closest('section')
    expect(errorPanel).not.toBeNull()
    fireEvent.click(within(errorPanel!).getByRole('button', { name: 'Retry' }))

    expect(
      await screen.findByRole('heading', {
        name: 'Experimental AI-reference comparison',
      }),
    ).toBeInTheDocument()
    expect(client.evaluation).toHaveBeenCalledTimes(2)
  })

  it('preserves filters through signal and detail navigation, resets pagination after a filter change, and pages evidence', async () => {
    const client = createClient()
    render(<App client={client} />)
    await screen.findByRole('heading', { name: 'Observed signals' })

    fireEvent.change(screen.getByLabelText('Topic'), {
      target: { value: 'delivery_delay' },
    })
    await waitFor(() =>
      expect(client.overview).toHaveBeenLastCalledWith(
        'demo',
        expect.objectContaining({ topic: 'delivery_delay' }),
        expect.any(Object),
      ),
    )

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Explore Illustrative delivery delay',
      }),
    )
    expect(
      await screen.findByRole('heading', {
        name: 'Illustrative delivery delay',
      }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Topic')).toHaveValue('delivery_delay')
    const numeratorCard = screen
      .getByRole('heading', { name: 'Contributing records' })
      .closest('article')
    const denominatorCard = screen
      .getByRole('heading', { name: 'Eligible denominator' })
      .closest('article')
    expect(numeratorCard).not.toBeNull()
    expect(denominatorCard).not.toBeNull()
    expect(within(numeratorCard!).getByText('6')).toBeInTheDocument()
    expect(within(denominatorCard!).getByText('10')).toBeInTheDocument()
    expect(screen.getByText('+22.5 pp')).toBeInTheDocument()

    await screen.findByText('Page 1 of 2')
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Page 2 of 2')).toBeInTheDocument()
    expect(client.evidence).toHaveBeenLastCalledWith(
      'demo',
      'delivery_delay',
      expect.objectContaining({ topic: 'delivery_delay' }),
      2,
      5,
      expect.any(Object),
    )

    fireEvent.click(
      screen.getByRole('button', {
        name: 'View decision for illustrative-012',
      }),
    )
    expect(
      await screen.findByRole('heading', { name: 'Evidence trace' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Immutable lineage')).toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('button', { name: '← Back to contributing feedback' }),
    )
    expect(await screen.findByText('Page 2 of 2')).toBeInTheDocument()
    expect(screen.getByLabelText('Topic')).toHaveValue('delivery_delay')

    fireEvent.change(screen.getByLabelText('Language'), {
      target: { value: 'en' },
    })
    await waitFor(() =>
      expect(client.evidence).toHaveBeenLastCalledWith(
        'demo',
        'delivery_delay',
        expect.objectContaining({ language: 'en' }),
        1,
        5,
        expect.any(Object),
      ),
    )
    expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument()
  })

  it('keeps the filtered first evidence page when an older second page resolves last', async () => {
    const staleSecondPage = deferred<ReturnType<typeof demoEvidence>>()
    const currentFirstPage = deferred<ReturnType<typeof demoEvidence>>()
    const client = createClient({
      evidence: vi.fn((_context, _signal, filters, page) => {
        if (filters.language === 'en') return currentFirstPage.promise
        if (page === 2) return staleSecondPage.promise
        return Promise.resolve(demoEvidence(1))
      }),
    })
    render(<App client={client} />)
    await screen.findByRole('heading', { name: 'Observed signals' })
    fireEvent.click(
      screen.getByRole('button', {
        name: 'Explore Illustrative delivery delay',
      }),
    )
    await screen.findByText('Page 1 of 2')

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() =>
      expect(client.evidence).toHaveBeenLastCalledWith(
        'demo',
        'delivery_delay',
        expect.any(Object),
        2,
        5,
        expect.any(Object),
      ),
    )
    fireEvent.change(screen.getByLabelText('Language'), {
      target: { value: 'en' },
    })
    await waitFor(() =>
      expect(client.evidence).toHaveBeenLastCalledWith(
        'demo',
        'delivery_delay',
        expect.objectContaining({ language: 'en' }),
        1,
        5,
        expect.any(Object),
      ),
    )

    const current = demoEvidence(1)
    current.items[0]!.sourceRecordId = 'current-filtered-page'
    const stale = demoEvidence(2)
    stale.items[0]!.sourceRecordId = 'stale-unfiltered-page'
    await act(async () => currentFirstPage.resolve(current))
    expect(
      await screen.findByRole('button', {
        name: 'View decision for current-filtered-page',
      }),
    ).toBeInTheDocument()
    await act(async () => staleSecondPage.resolve(stale))
    expect(
      screen.getByRole('button', {
        name: 'View decision for current-filtered-page',
      }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', {
        name: 'View decision for stale-unfiltered-page',
      }),
    ).not.toBeInTheDocument()
  })

  it('gives repeated signal and evidence actions unique contextual names', () => {
    const secondSignal = {
      ...demoOverview.signals[0]!,
      id: 'support_friction',
      label: 'Support friction',
    }
    const evidence = demoEvidence(1)
    evidence.items.push({
      ...evidence.items[0]!,
      feedbackId: '33333333-3333-4333-8333-333333333333',
      decisionId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
      sourceRecordId: 'illustrative-007',
    })

    render(
      <>
        <SignalList
          signals={[demoOverview.signals[0]!, secondSignal]}
          onSelect={vi.fn()}
        />
        <EvidenceTable
          evidence={evidence}
          capabilities={demoMetadata.capabilities}
          onOpen={vi.fn()}
          onPage={vi.fn()}
        />
      </>,
    )

    expect(
      screen.getByRole('button', {
        name: 'Explore Illustrative delivery delay',
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Explore Support friction' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', {
        name: 'View decision for illustrative-006',
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', {
        name: 'View decision for illustrative-007',
      }),
    ).toBeInTheDocument()
  })

  it('isolates contexts and ignores a stale demo response after switching to live', async () => {
    let resolveDemo: ((metadata: MetadataResponse) => void) | undefined
    const delayedDemo = new Promise<MetadataResponse>((resolve) => {
      resolveDemo = resolve
    })
    const client = createClient({
      metadata: vi.fn((context) =>
        context === 'demo' ? delayedDemo : Promise.resolve(emptyLiveMetadata),
      ),
      overview: vi.fn(async (context) => ({
        ...liveOverview,
        context,
        processing: {
          feedbackRecords: 0,
          decisionRuns: 0,
          typedAnswers: 0,
          jobsByStatus: {},
          projectionByDestination: {},
        },
      })),
    })

    render(<App client={client} />)
    fireEvent.click(screen.getByRole('button', { name: 'Live' }))

    expect(
      await screen.findByRole('heading', { name: 'No imported feedback yet' }),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('From')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      'Live — connected data',
    )
    expect(client.overview).not.toHaveBeenCalled()

    resolveDemo?.(demoMetadata)
    await Promise.resolve()
    expect(
      screen.queryByText('Sol-medium reference feedback'),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      'Live — connected data',
    )
  })

  it('shows live processing while treating zero eligible analytics as unavailable', async () => {
    const client = createClient({
      metadata: vi.fn(async (context) =>
        context === 'live' ? liveMetadata : demoMetadata,
      ),
      overview: vi.fn(async (context) =>
        context === 'live' ? liveOverview : demoOverview,
      ),
    })
    render(<App client={client} />)
    await screen.findByRole('heading', { name: 'Feedback overview' })

    fireEvent.click(screen.getByRole('button', { name: 'Live' }))
    expect(
      await screen.findByRole('heading', {
        name: 'Analytics withheld — awaiting calibration',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('126')).toBeInTheDocument()
    expect(screen.getAllByText('Awaiting calibration')).toHaveLength(2)
    expect(screen.getAllByText('—')).toHaveLength(2)
    expect(
      screen.queryByRole('heading', { name: 'Observed signals' }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByText(/does not mean that no complaints/i),
    ).toBeInTheDocument()
  })

  it('renders restricted evidence without exposing an evidence body', () => {
    render(<DecisionDetail detail={restrictedDetail} />)

    expect(
      screen.getByRole('heading', { name: 'Evidence text is restricted' }),
    ).toBeInTheDocument()
    expect(screen.getByText('withheld uncalibrated')).toBeInTheDocument()
    expect(
      screen.queryByText(
        'The sample parcel arrived after the illustrated delivery date. This sentence was written only for the repository-owned demo journey.',
      ),
    ).not.toBeInTheDocument()
  })

  it('offers a working regional retry after an overview failure', async () => {
    let attempt = 0
    const client = createClient({
      overview: vi.fn(async () => {
        attempt += 1
        if (attempt === 1) throw new Error('Temporary read failure')
        return demoOverview
      }),
    })
    render(<App client={client} />)

    expect(
      await screen.findByRole('heading', {
        name: 'Overview could not be loaded',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('Temporary read failure')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(
      await screen.findByRole('heading', { name: 'Imported feedback' }),
    ).toBeInTheDocument()
    expect(client.overview).toHaveBeenCalledTimes(2)
  })

  it('renders the synthetic detector evaluation with raw windows, gates, summary metrics, and every incident outcome', async () => {
    render(<App client={createClient()} />)

    expect(
      await screen.findByRole('heading', {
        name: 'Synthetic detector evaluation',
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('7-day current window vs previous 28-day baseline'),
    ).toBeInTheDocument()
    expect(screen.getAllByText('Emerging signal')).toHaveLength(2)
    expect(screen.getByText('16 / 70')).toBeInTheDocument()
    expect(screen.getByText('18 / 280')).toBeInTheDocument()
    expect(screen.getByText('22.9%')).toBeInTheDocument()
    expect(screen.getByText('+16.4 pp')).toBeInTheDocument()
    expect(screen.getByText('+255.6% relative')).toBeInTheDocument()
    expect(screen.getByText('Current denominator met')).toBeInTheDocument()
    const evaluationSummary = screen.getByLabelText(
      'Detector evaluation summary',
    )
    expect(within(evaluationSummary).getByText('Recall')).toBeInTheDocument()
    expect(within(evaluationSummary).getAllByText('50%')).toHaveLength(2)
    expect(within(evaluationSummary).getByText('2 days')).toBeInTheDocument()
    expect(
      screen.getByText('0.5 per 100 evaluable series-days'),
    ).toBeInTheDocument()

    const incidentTable = screen
      .getByText('Every planted synthetic incident and its detector outcome')
      .closest('table')
    expect(incidentTable).not.toBeNull()
    expect(
      within(incidentTable!).getByText('Delivery delay increase'),
    ).toBeInTheDocument()
    expect(
      within(incidentTable!).getByText('Product defect noise increase'),
    ).toBeInTheDocument()
    expect(within(incidentTable!).getByText('Detected')).toBeInTheDocument()
    expect(within(incidentTable!).getByText('Missed')).toBeInTheDocument()
    expect(within(incidentTable!).getByText('Not detected')).toBeInTheDocument()
    expect(
      screen.queryByText('emerging_signal_not_statistical_significance'),
    ).not.toBeInTheDocument()
  })

  it('renders live trend calibration as unavailable without synthetic results or zeros', async () => {
    const client = createClient({
      metadata: vi.fn(async (context) =>
        context === 'live' ? liveMetadata : demoMetadata,
      ),
      overview: vi.fn(async (context) =>
        context === 'live' ? liveOverview : demoOverview,
      ),
    })
    render(<App client={client} />)
    await screen.findByRole('heading', {
      name: 'Synthetic detector evaluation',
    })

    fireEvent.click(screen.getByRole('button', { name: 'Live' }))

    expect(
      await screen.findByRole('heading', {
        name: 'Trend detection unavailable — awaiting calibration',
      }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', {
        name: 'Synthetic detector evaluation',
      }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('16 / 70')).not.toBeInTheDocument()
  })

  it('ignores a stale demo trend response after switching to live', async () => {
    let resolveDemo: ((value: TrendOverviewResponse) => void) | undefined
    const delayedDemo = new Promise<TrendOverviewResponse>((resolve) => {
      resolveDemo = resolve
    })
    const client = createClient({
      metadata: vi.fn(async (context) =>
        context === 'live' ? liveMetadata : demoMetadata,
      ),
      overview: vi.fn(async (context) =>
        context === 'live' ? liveOverview : demoOverview,
      ),
      trends: vi.fn((context) =>
        context === 'demo' ? delayedDemo : Promise.resolve(liveTrends),
      ),
    })
    render(<App client={client} />)

    fireEvent.click(screen.getByRole('button', { name: 'Live' }))
    expect(
      await screen.findByRole('heading', {
        name: 'Trend detection unavailable — awaiting calibration',
      }),
    ).toBeInTheDocument()

    resolveDemo?.(demoTrends)
    await Promise.resolve()
    expect(
      screen.queryByRole('heading', {
        name: 'Synthetic detector evaluation',
      }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('heading', {
        name: 'Trend detection unavailable — awaiting calibration',
      }),
    ).toBeInTheDocument()
  })

  it('offers a regional retry after a trend evaluation failure', async () => {
    let attempt = 0
    const client = createClient({
      trends: vi.fn(async () => {
        attempt += 1
        if (attempt === 1) throw new Error('Detector report unavailable')
        return demoTrends
      }),
    })
    render(<App client={client} />)

    const errorHeading = await screen.findByRole('heading', {
      name: 'Trend evaluation could not be loaded',
    })
    const errorPanel = errorHeading.closest('section')
    expect(errorPanel).not.toBeNull()
    expect(
      within(errorPanel!).getByText('Detector report unavailable'),
    ).toBeInTheDocument()
    fireEvent.click(within(errorPanel!).getByRole('button', { name: 'Retry' }))

    expect(
      await screen.findByRole('heading', {
        name: 'Synthetic detector evaluation',
      }),
    ).toBeInTheDocument()
    expect(client.trends).toHaveBeenCalledTimes(2)
  })
})
