import { useCallback, useEffect, useRef, useState } from 'react'
import {
  WorkbenchError,
  type ModelOption,
  type workbench,
} from './workbench-api'

type Catalog = {
  connection: string
  models: ModelOption[]
  status: 'idle' | 'loading' | 'ready' | 'empty' | 'error'
  error: string
  refreshedAt: number | null
  model: string
  effort: string
  loaded: boolean
  reconnectRequired: boolean
}
const initial = (connection = ''): Catalog => ({
  connection,
  models: [],
  status: 'idle',
  error: '',
  refreshedAt: null,
  model: '',
  effort: '',
  loaded: false,
  reconnectRequired: false,
})

export function useModelCatalog(
  client: typeof workbench,
  connection: string,
  permitted: boolean,
  active: boolean,
) {
  const [catalog, setCatalog] = useState<Catalog>(() => initial())
  const pending = useRef<{
    controller: AbortController
    promise: Promise<void>
  } | null>(null)
  const lastRefresh = useRef(0)
  const refresh = useCallback(() => {
    if (!connection || !permitted || !active) return Promise.resolve()
    if (pending.current) return pending.current.promise
    const controller = new AbortController()
    const promise = (async () => {
      await Promise.resolve()
      if (controller.signal.aborted) return
      setCatalog((current) => ({
        ...(current.connection === connection ? current : initial(connection)),
        status: 'loading',
        error: '',
      }))
      try {
        const models = await client<ModelOption[]>(
          `/connections/${connection}/models`,
          undefined,
          'GET',
          controller.signal,
        )
        if (controller.signal.aborted) return
        lastRefresh.current = Date.now()
        setCatalog((current) => {
          const prior =
            current.connection === connection ? current : initial(connection)
          const model = prior.loaded
            ? models.some((row) => row.slug === prior.model)
              ? prior.model
              : ''
            : models[0]?.slug || ''
          return {
            connection,
            models,
            model,
            effort: model === prior.model ? prior.effort : '',
            loaded: true,
            reconnectRequired: false,
            status: models.length ? 'ready' : 'empty',
            error: '',
            refreshedAt: lastRefresh.current,
          }
        })
      } catch (error) {
        if (!controller.signal.aborted)
          setCatalog((current) => ({
            ...current,
            status: 'error',
            reconnectRequired:
              error instanceof WorkbenchError && error.reconnectRequired,
            error:
              error instanceof Error
                ? error.message
                : 'Model catalog unavailable',
          }))
      } finally {
        if (pending.current?.controller === controller) pending.current = null
      }
    })()
    pending.current = { controller, promise }
    return promise
  }, [connection, permitted, active, client])
  useEffect(() => {
    void refresh()
    const scheduled = () => {
      if (!document.hidden) void refresh()
    }
    const focus = () => {
      if (!document.hidden && Date.now() - lastRefresh.current > 60_000)
        void refresh()
    }
    const timer =
      active && permitted ? window.setInterval(scheduled, 300_000) : 0
    window.addEventListener('focus', focus)
    document.addEventListener('visibilitychange', focus)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', focus)
      document.removeEventListener('visibilitychange', focus)
      pending.current?.controller.abort()
      pending.current = null
    }
  }, [refresh, active, permitted])
  const current =
    connection && permitted && catalog.connection === connection
      ? catalog
      : initial(connection)
  const chooseModel = (model: string) =>
    setCatalog((value) => ({ ...value, model, effort: '' }))
  const chooseEffort = (effort: string) =>
    setCatalog((value) => ({ ...value, effort }))
  return { ...current, refresh, chooseModel, chooseEffort }
}

export const effortLabel = (value: string | null | undefined) =>
  value === undefined
    ? 'Not explicitly recorded'
    : value === null || value === ''
      ? 'Provider default'
      : (
          {
            xhigh: 'Extra high',
            none: 'None',
            minimal: 'Minimal',
            low: 'Low',
            medium: 'Medium',
            high: 'High',
            max: 'Max',
          } as Record<string, string>
        )[value] || value
