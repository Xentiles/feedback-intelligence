import { createRoot } from 'react-dom/client'
import { App } from './App'
import {
  visualDashboard,
  visualWorkbench,
  type FixtureState,
} from './visual-fixtures'
import './styles.css'

const root = document.getElementById('root')
if (!root) throw new Error('Visual review root missing')
if (!import.meta.env.DEV)
  throw new Error('Visual review is available only in development')
const state = new URLSearchParams(window.location.search).get(
  'state',
) as FixtureState | null
const motion = new URLSearchParams(window.location.search).get('motion')
const backgroundLoader =
  motion === 'poster' || motion === 'reduced'
    ? async () => {
        const module = await import('./orbital-runtime/orbital-sand.js')
        return {
          createOrbitalSand: (
            host: HTMLElement,
            options?: { paused?: boolean; flat?: boolean },
          ) =>
            module.createOrbitalSand(host, {
              ...options,
              ...(motion === 'poster'
                ? { renderer: 'poster' }
                : { reducedMotion: true }),
            }),
        }
      }
    : undefined
root.dataset.visualFixture = 'true'
root.dataset.fixtureState = state || 'ready'
createRoot(root).render(
  <App
    client={visualDashboard}
    workbenchClient={visualWorkbench(state || 'ready')}
    backgroundLoader={backgroundLoader}
  />,
)
