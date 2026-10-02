import { afterEach, describe, expect, it, vi } from 'vitest'
import { setWorkbenchCsrf, workbench } from './workbench-api'

afterEach(() => vi.unstubAllGlobals())
describe('workbench boundary', () => {
  it('uses the local session and CSRF token without a provider credential', async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(
        new Response(JSON.stringify({ id: 'run' }), { status: 200 }),
      )
    vi.stubGlobal('fetch', fetch)
    setWorkbenchCsrf('csrf-value')
    await workbench('/runs', { engine: 'rules' })
    const call = fetch.mock.calls[0]
    if (!call || !call[1]) throw new Error('Expected a request')
    expect(call[0]).toBe('/api/v1/workbench/runs')
    expect(call[1].credentials).toBe('same-origin')
    expect(new Headers(call[1].headers).get('X-Workbench-CSRF')).toBe(
      'csrf-value',
    )
    expect(new Headers(call[1].headers).get('Authorization')).toBeNull()
  })
  it('surfaces unavailable and expired-session errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: () => Promise.resolve({}),
      }),
    )
    await expect(workbench('/datasets')).rejects.toThrow('Unlock')
  })
})
