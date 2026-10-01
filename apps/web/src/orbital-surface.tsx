import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

type BackgroundMode = 'animate' | 'still' | 'flat'
export type OrbitalState = {
  paused: boolean
  reduced: boolean
  renderer: 'loading' | 'poster' | 'webgl2'
  running: boolean
  flat?: boolean
}
export type OrbitalController = {
  readonly state: OrbitalState
  setOptions(options: { paused?: boolean; flat?: boolean }): void
  destroy(): void
}
export type OrbitalModule = {
  createOrbitalSand(
    host: HTMLElement,
    options?: { paused?: boolean; flat?: boolean },
  ): OrbitalController
}
const loadRuntime = async () => {
  return (await import('./orbital-runtime/orbital-sand.js')) as OrbitalModule
}
function savedMode(): BackgroundMode {
  try {
    const value = localStorage.getItem('feedback-background')
    return value === 'still' || value === 'flat' ? value : 'animate'
  } catch {
    return 'animate'
  }
}

export function OrbitalSurface({
  controlsTarget,
  loader = loadRuntime,
}: {
  controlsTarget?: HTMLElement | null
  loader?: () => Promise<OrbitalModule>
}) {
  const host = useRef<HTMLDivElement>(null)
  const controller = useRef<OrbitalController | null>(null)
  const [mode, setMode] = useState<BackgroundMode>(savedMode)
  const initialMode = useRef(mode)
  const [state, setState] = useState<OrbitalState>({
    paused: false,
    reduced: false,
    renderer: 'loading',
    running: false,
  })
  useEffect(() => {
    const element = host.current
    if (!element) return
    let disposed = false
    let runtime: OrbitalController | null = null
    const onChange = (event: Event) =>
      setState((event as CustomEvent<OrbitalState>).detail)
    element.addEventListener('orbital-sand-change', onChange)
    void loader()
      .then((module) => {
        if (disposed) return
        runtime = module.createOrbitalSand(element, {
          paused: initialMode.current !== 'animate',
          flat: initialMode.current === 'flat',
        })
        controller.current = runtime
        setState(runtime.state)
      })
      .catch(() => {
        if (!disposed)
          setState({
            paused: true,
            reduced:
              window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ??
              false,
            renderer: 'poster',
            running: false,
          })
      })
    return () => {
      disposed = true
      element.removeEventListener('orbital-sand-change', onChange)
      runtime?.destroy()
      controller.current = null
    }
  }, [loader])
  const change = (next: BackgroundMode) => {
    setMode(next)
    controller.current?.setOptions({
      paused: next !== 'animate',
      flat: next === 'flat',
    })
    try {
      localStorage.setItem('feedback-background', next)
    } catch {
      /* Keep in-memory preference. */
    }
  }
  const controls = (
    <div
      className="motion-control"
      role="group"
      aria-label="Background appearance"
    >
      <span className="rail-section-label">Background</span>
      <div className="background-options">
        {(['animate', 'still', 'flat'] as BackgroundMode[]).map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={
              ((state.reduced || state.renderer === 'poster') &&
              mode === 'animate'
                ? 'still'
                : mode) === value
            }
            disabled={
              value === 'animate' &&
              (state.reduced ||
                state.renderer === 'poster' ||
                state.renderer === 'loading')
            }
            onClick={() => change(value)}
          >
            {value === 'animate'
              ? 'Animate'
              : value === 'still'
                ? 'Still'
                : 'Flat'}
          </button>
        ))}
      </div>
      <span className="motion-state" aria-live="polite">
        {state.renderer === 'loading'
          ? 'Preparing material'
          : mode === 'flat'
            ? 'Flat Graphite'
            : state.reduced
              ? 'Reduced motion: still texture'
              : state.renderer === 'poster'
                ? 'Graphics fallback: still texture'
                : state.running
                  ? 'In motion'
                  : 'Paused'}
      </span>
    </div>
  )
  return (
    <>
      <div
        ref={host}
        className="orbital-backdrop oc-backdrop"
        aria-hidden="true"
        data-flat={mode === 'flat'}
      />
      {controlsTarget ? createPortal(controls, controlsTarget) : null}
    </>
  )
}
