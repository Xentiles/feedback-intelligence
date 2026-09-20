import { useEffect, useRef, useState } from 'react'

type OrbitalState = {
  paused: boolean
  reduced: boolean
  renderer: 'loading' | 'poster' | 'webgl2'
  running: boolean
}

type OrbitalController = {
  readonly state: OrbitalState
  setOptions(options: { paused?: boolean }): void
  destroy(): void
}

type OrbitalModule = {
  createOrbitalSand(host: HTMLElement): OrbitalController
}

const initialState: OrbitalState = {
  paused: false,
  reduced: false,
  renderer: 'loading',
  running: false,
}

export function OrbitalSurface() {
  const hostRef = useRef<HTMLDivElement>(null)
  const controllerRef = useRef<OrbitalController | null>(null)
  const [state, setState] = useState(initialState)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    let disposed = false
    let controller: OrbitalController | null = null
    const onChange = (event: Event) => {
      setState((event as CustomEvent<OrbitalState>).detail)
    }
    host.addEventListener('orbital-sand-change', onChange)

    const moduleUrl = '/orbital/orbital-sand.js'
    void import(/* @vite-ignore */ moduleUrl)
      .then((loaded: unknown) => {
        if (disposed) return
        const module = loaded as OrbitalModule
        controller = module.createOrbitalSand(host)
        controllerRef.current = controller
        setState(controller.state)
      })
      .catch(() => {
        if (disposed) return
        setState({
          paused: true,
          reduced: true,
          renderer: 'poster',
          running: false,
        })
      })

    return () => {
      disposed = true
      host.removeEventListener('orbital-sand-change', onChange)
      controller?.destroy()
      controllerRef.current = null
    }
  }, [])

  const isStill = state.reduced || state.renderer === 'poster'
  const label = isStill
    ? 'Still texture'
    : state.paused
      ? 'Resume background'
      : state.renderer === 'loading'
        ? 'Preparing background'
        : 'Pause background'

  return (
    <>
      <div ref={hostRef} className="orbital-backdrop" aria-hidden="true" />
      <div className="motion-control">
        <button
          className="motion-toggle"
          type="button"
          aria-pressed={state.paused}
          disabled={isStill || state.renderer === 'loading'}
          onClick={() => {
            const controller = controllerRef.current
            if (!controller) return
            controller.setOptions({ paused: !controller.state.paused })
          }}
        >
          <span className="motion-toggle__mark" aria-hidden="true" />
          {label}
        </button>
        <span className="motion-state" aria-live="polite">
          {state.renderer === 'loading'
            ? 'Loading material'
            : isStill
              ? 'Reduced motion or static fallback'
              : state.running
                ? 'In motion'
                : 'Paused'}
        </span>
      </div>
    </>
  )
}
