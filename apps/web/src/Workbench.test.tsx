import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { Workbench } from './Workbench'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
describe('workbench product journey', () => {
  it('imports mapped text, confirms exclusions, runs rules and opens prepared evidence', async () => {
    vi.stubGlobal(
      'File',
      class extends File {
        override arrayBuffer(): Promise<ArrayBuffer> {
          return new Promise((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => resolve(reader.result as ArrayBuffer)
            reader.onerror = () =>
              reject(new Error('Test file could not be read'))
            reader.readAsArrayBuffer(this)
          })
        }
      },
    )
    const template = {
      id: 'template',
      name: 'General feedback',
      revision: 'revision',
      payload: {
        name: 'General feedback',
        topics: [
          {
            id: 'service',
            label: 'Service',
            description: 'Customer service',
            keywords: ['support'],
            priority: 0,
          },
        ],
      },
    }
    const dataset = {
      id: 'dataset',
      name: 'My feedback',
      count: 1,
      status: 'ready',
      snapshot: 'snapshot',
      validation: { summary: {} },
    }
    const run = {
      id: 'run',
      dataset_id: 'dataset',
      template_id: 'template',
      status: 'completed',
      target: 1,
      succeeded: 1,
      failed: 0,
      errors: [],
      elapsedSeconds: 1,
      created_at: '2026-09-30T10:00:00Z',
      completed_at: '2026-09-30T10:00:01Z',
      snapshot: {
        engine: 'rules',
        mode: 'full',
        model: 'keywords-1.0.0',
        billingMode: 'none',
        connectionId: null,
        template: template.payload,
        templateRevision: 'revision',
        protocolHash: 'protocol',
        datasetSnapshot: 'snapshot',
      },
    }
    const classification = {
      topic: 'service',
      sentiment: 'positive',
      actionable: false,
      redactedText: 'Great support [REDACTED_EMAIL]',
      matches: [{ topic: 'service', phrases: ['support'], priority: 0 }],
      requestedModel: 'keywords-1.0.0',
      resolvedModel: 'keywords-1.0.0',
      inputTokens: 0,
      outputTokens: 0,
      latencyMs: 0,
      templateRevision: 'revision',
    }
    let imported = false
    let started = false
    const requests: { path: string; body: unknown }[] = []
    vi.stubGlobal(
      'fetch',
      vi
        .fn<typeof globalThis.fetch>()
        .mockImplementation(async (input, options) => {
          const path = String(input).replace('/api/v1/workbench', '')
          const body = options?.body
            ? JSON.parse(String(options.body))
            : undefined
          requests.push({ path, body })
          let response: unknown
          if (path === '/session')
            response = { enabled: true, authenticated: true, csrf: 'test-csrf' }
          else if (path === '/datasets') response = imported ? [dataset] : []
          else if (path === '/templates') response = [template]
          else if (path === '/connections') response = []
          else if (path === '/runs') {
            if (body) {
              started = true
              response = run
            } else response = started ? [run] : []
          } else if (path === '/imports/preview')
            response = {
              uploadId: 'upload',
              columns: ['text'],
              sheets: [],
              rows: [{ text: 'Great support person@example.test' }],
              total: 1,
            }
          else if (path === '/imports/validate')
            response = {
              summary: {
                total: 1,
                accepted: 1,
                invalid: 0,
                empty: 0,
                duplicateIds: 0,
                repeatedText: 0,
                missingDates: 1,
              },
              issues: [],
              privacyPreview: [
                { row: 1, redactedText: classification.redactedText },
              ],
              blocked: 0,
            }
          else if (path === '/imports/commit') {
            imported = true
            response = dataset
          } else if (path.startsWith('/runs/run/results'))
            response = {
              run,
              runUsage: { inputTokens: 0, outputTokens: 0, reusedRecords: 0 },
              summary: {
                total: 1,
                processed: 1,
                dated: 0,
                topics: { service: 1 },
                sentiments: { positive: 1 },
                days: [],
                ratingCount: 0,
                normalizedRatingMean: null,
                reusedRecords: 0,
              },
              rows: [
                {
                  id: 'record',
                  sourceId: 'row-1',
                  position: 1,
                  text: classification.redactedText,
                  occurredAt: null,
                  language: 'en',
                  groups: {},
                  rating: null,
                  result: classification,
                },
              ],
              page: 1,
              filtered: 1,
              groups: {},
              projectionPending: 0,
            }
          else throw new Error('Unexpected request: ' + path)
          return new Response(JSON.stringify(response), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }),
    )
    render(<Workbench />)
    const pasted = await screen.findByLabelText('Or paste one review per line')
    fireEvent.change(pasted, {
      target: { value: 'Great support person@example.test' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Preview upload' }))
    await screen.findByRole('heading', { name: 'Map columns' })
    fireEvent.click(
      screen.getByRole('button', { name: 'Validate mapping and privacy' }),
    )
    await screen.findByRole('heading', { name: 'Validation report' })
    const commit = screen.getByRole('button', { name: 'Import valid records' })
    expect(commit).toBeDisabled()
    fireEvent.click(
      screen.getByRole('checkbox', { name: /I reviewed the report/ }),
    )
    fireEvent.click(commit)
    const start = await screen.findByRole('button', {
      name: 'Classify dataset with rules',
    })
    fireEvent.click(start)
    await screen.findByRole('heading', { name: 'Record evidence' })
    expect(
      screen.getByText('No dated records; time analysis is unavailable.'),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Inspect row 1' }))
    const details = screen.getByRole('complementary')
    expect(
      within(details).getByText(classification.redactedText),
    ).toBeInTheDocument()
    expect(
      within(details).getByText('Recorded date').nextElementSibling,
    ).toHaveTextContent('Not supplied')
    expect(
      requests.find((r) => r.path === '/imports/commit')?.body,
    ).toMatchObject({ acceptExclusions: true })
    expect(
      requests.find((r) => r.path === '/runs' && r.body)?.body,
    ).toMatchObject({ engine: 'rules' })
  })

  it('explains a disabled runtime without requesting protected datasets', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(JSON.stringify({ enabled: false, authenticated: false }), {
        status: 200,
      }),
    )
    vi.stubGlobal('fetch', fetch)
    render(<Workbench />)
    await screen.findByRole('heading', { name: 'Start the workbench runtime' })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
