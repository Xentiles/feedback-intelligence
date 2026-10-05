import type { OrbitalController } from '../orbital-surface'
export function createOrbitalSand(
  host: HTMLElement,
  options?: {
    paused?: boolean
    flat?: boolean
    reducedMotion?: boolean
    renderer?: 'auto' | 'poster'
  },
): OrbitalController
