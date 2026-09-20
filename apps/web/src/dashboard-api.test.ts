import { afterEach, describe, expect, it, vi } from 'vitest'

import { dashboardClient, DashboardRequestError } from './dashboard-api'
import {
  demoEvaluation,
  demoEvidence,
  demoFilters,
  demoTrends,
} from './test-fixtures'

afterEach(() => vi.restoreAllMocks())

describe('dashboardClient', () => {
  it('uses the typed trend endpoint for the selected context', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify(demoTrends), { status: 200 }),
      )

    await dashboardClient.trends('demo')

    const requested = new URL(
      String(fetchMock.mock.calls[0]?.[0]),
      'http://local',
    )
    expect(requested.pathname).toBe('/api/v1/dashboard/trends')
    expect(Object.fromEntries(requested.searchParams)).toEqual({
      context: 'demo',
    })
  })

  it('uses the typed evaluation endpoint for the selected context', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify(demoEvaluation), { status: 200 }),
      )

    await dashboardClient.evaluation('demo')

    const requested = new URL(
      String(fetchMock.mock.calls[0]?.[0]),
      'http://local',
    )
    expect(requested.pathname).toBe('/api/v1/dashboard/evaluation')
    expect(Object.fromEntries(requested.searchParams)).toEqual({
      context: 'demo',
    })
  })

  it('uses the versioned evidence route with bounded paging and only active filters', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify(demoEvidence(2)), { status: 200 }),
      )

    await dashboardClient.evidence(
      'demo',
      'delivery/delay',
      { ...demoFilters, topic: 'delivery_delay' },
      2,
      5,
    )

    const requested = new URL(
      String(fetchMock.mock.calls[0]?.[0]),
      'http://local',
    )
    expect(requested.pathname).toBe(
      '/api/v1/dashboard/signals/delivery%2Fdelay/evidence',
    )
    expect(Object.fromEntries(requested.searchParams)).toEqual({
      context: 'demo',
      sourceKey: demoFilters.sourceKey,
      from: demoFilters.from,
      toExclusive: demoFilters.toExclusive,
      topic: 'delivery_delay',
      page: '2',
      pageSize: '5',
    })
  })

  it('surfaces structured problem details for regional retry messages', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          title: 'Dashboard source unavailable',
          detail: 'The analytical read path is temporarily unavailable.',
        }),
        {
          status: 503,
          headers: { 'Content-Type': 'application/problem+json' },
        },
      ),
    )

    const request = dashboardClient.metadata('live')
    await expect(request).rejects.toEqual(
      expect.objectContaining<Partial<DashboardRequestError>>({
        name: 'DashboardRequestError',
        status: 503,
        message: 'The analytical read path is temporarily unavailable.',
      }),
    )
  })
})
