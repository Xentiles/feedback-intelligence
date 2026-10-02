import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useModelCatalog } from './use-model-catalog'
import { type workbench, type ModelOption } from './workbench-api'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})
const models: ModelOption[] = [
  {
    slug: 'gpt-6.1-sol',
    displayName: 'GPT-6.1 Sol',
    reasoningEfforts: ['low', 'medium', 'high', 'xhigh', 'max'],
  },
  { slug: 'future-model', displayName: 'Future model' },
]
const fixture = (implementation: (...args: unknown[]) => Promise<unknown>) =>
  vi.fn(implementation) as unknown as typeof workbench

describe('connection model catalog', () => {
  it('discovers future models, preserves selections, deduplicates refresh and clears a removed model without replacement', async () => {
    let list = models
    const client = fixture(async () => list)
    const { result } = renderHook(() =>
      useModelCatalog(client, 'account', true, true),
    )
    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(result.current.models.map((row) => row.slug)).toEqual([
      'gpt-6.1-sol',
      'future-model',
    ])
    act(() => {
      result.current.chooseModel('future-model')
    })
    await act(async () => {
      await Promise.all([result.current.refresh(), result.current.refresh()])
    })
    expect(client).toHaveBeenCalledTimes(2)
    expect(result.current.model).toBe('future-model')
    list = [models[0]!]
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.model).toBe('')
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.model).toBe('')
  })
  it('ignores an old account response and retains a stale list after refresh failure', async () => {
    let resolveOld: (value: ModelOption[]) => void = () => {}
    let fail = false
    const client = fixture(async (path) =>
      path === '/connections/old/models'
        ? new Promise<ModelOption[]>((resolve) => {
            resolveOld = resolve
          })
        : fail
          ? Promise.reject(new Error('Unavailable'))
          : models,
    )
    const { result, rerender } = renderHook(
      ({ connection }) => useModelCatalog(client, connection, true, true),
      { initialProps: { connection: 'old' } },
    )
    await waitFor(() => expect(client).toHaveBeenCalled())
    rerender({ connection: 'new' })
    await waitFor(() => expect(result.current.status).toBe('ready'))
    await act(async () => resolveOld([{ slug: 'old', displayName: 'Old' }]))
    expect(result.current.model).toBe('gpt-6.1-sol')
    act(() => result.current.chooseEffort('high'))
    fail = true
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.status).toBe('error')
    expect(result.current.models).toEqual(models)
    expect(result.current.effort).toBe('high')
    expect(result.current.refreshedAt).not.toBeNull()
  })
  it('preserves a withdrawn effort so processing requires an explicit new choice', async () => {
    let list = models
    const client = fixture(async () => list)
    const { result } = renderHook(() =>
      useModelCatalog(client, 'account', true, true),
    )
    await waitFor(() => expect(result.current.status).toBe('ready'))
    act(() => result.current.chooseEffort('max'))
    list = [{ ...models[0]!, reasoningEfforts: ['low'] }]
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.effort).toBe('max')
    expect(result.current.models[0]!.reasoningEfforts).not.toContain('max')
  })

  it('refreshes on view entry, schedules five minutes and refreshes stale focus only while active', async () => {
    vi.useFakeTimers()
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
    const client = fixture(async () => models)
    const { result, rerender } = renderHook(
      ({ active }) => useModelCatalog(client, 'account', true, active),
      { initialProps: { active: true } },
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.status).toBe('ready')
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300_000)
    })
    expect(client).toHaveBeenCalledTimes(2)
    await act(async () => {
      window.dispatchEvent(new Event('focus'))
    })
    expect(client).toHaveBeenCalledTimes(2)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000)
      window.dispatchEvent(new Event('focus'))
    })
    expect(client).toHaveBeenCalledTimes(3)
    rerender({ active: false })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400_000)
      window.dispatchEvent(new Event('focus'))
    })
    expect(client).toHaveBeenCalledTimes(3)
    rerender({ active: true })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(client).toHaveBeenCalledTimes(4)
  })
})
