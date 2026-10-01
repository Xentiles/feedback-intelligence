import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { App } from './App'
import { readRoute } from './application-routes'
import { visualDashboard, visualWorkbench } from './visual-fixtures'

beforeEach(() => window.history.replaceState(null, '', '/'))
afterEach(() => {
  cleanup()
  window.history.replaceState(null, '', '/')
  vi.unstubAllGlobals()
})

describe('shared navigation', () => {
  it.each(['Overview', 'Signals'] as const)(
    'returns from Workbench to %s using its floating navigation button',
    async (destination) => {
      window.history.replaceState(null, '', '/#workbench/classification')
      render(
        <App client={visualDashboard} workbenchClient={visualWorkbench()} />,
      )
      await screen.findByRole('heading', { name: 'Configure a run' })
      // Wait for the retained showcase's metadata before using Signals.
      await screen.findByRole('heading', {
        name: 'Imported feedback',
        hidden: true,
      })
      fireEvent.click(screen.getByRole('button', { name: destination }))
      expect(window.location.hash).toBe('#showcase')
      await screen.findByRole('heading', {
        name:
          destination === 'Overview'
            ? 'Feedback overview'
            : 'Illustrative delivery delay',
        level: 1,
      })
      expect(
        screen.queryByRole('heading', { name: 'Classification', level: 1 }),
      ).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: destination })).toHaveAttribute(
        'aria-current',
        'page',
      )
    },
  )

  it('retains legacy routes and ignores in-page anchors', () => {
    expect(readRoute('#workbench')).toEqual({
      area: 'workbench',
      page: 'Datasets',
    })
    expect(readRoute('#workbench/results')?.page).toBe('Results')
    expect(readRoute('#showcase')?.area).toBe('showcase')
    expect(readRoute('#app-content')).toBeNull()
  })

  it('preserves imports and edited templates across views and collapse', async () => {
    render(<App client={visualDashboard} workbenchClient={visualWorkbench()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Datasets' }))
    const pasted = await screen.findByLabelText('Or paste one review per line')
    fireEvent.change(pasted, {
      target: { value: 'Keep this unfinished upload' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Classification' }))
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit selected template' }),
    )
    fireEvent.change(screen.getByLabelText('Template name'), {
      target: { value: 'My draft' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Collapse navigation' }))
    expect(screen.getByLabelText('Template name')).toHaveValue('My draft')
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))
    await screen.findByRole('heading', { name: 'Feedback overview' })
    fireEvent.click(screen.getByRole('button', { name: 'Classification' }))
    expect(screen.getByLabelText('Template name')).toHaveValue('My draft')
    fireEvent.click(screen.getByRole('button', { name: 'Datasets' }))
    expect(screen.getByLabelText('Or paste one review per line')).toHaveValue(
      'Keep this unfinished upload',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Classification' }))
    expect(screen.getByLabelText('Template name')).toHaveValue('My draft')
    expect(
      screen.getByRole('button', { name: 'Classification' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(document.querySelectorAll('.orbital-backdrop')).toHaveLength(1)
  })

  it('closes the phone menu on selection and Escape, restoring the menu focus', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )
    render(<App client={visualDashboard} workbenchClient={visualWorkbench()} />)
    const open = screen.getByRole('button', { name: 'Open navigation' })
    expect(open).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(open)
    expect(
      screen.getByRole('link', { name: /Feedback Intelligence/ }),
    ).toHaveFocus()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(open).toHaveFocus()
    expect(open).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(open)
    fireEvent.click(screen.getByRole('button', { name: 'Connections' }))
    await screen.findByRole('heading', { name: 'ChatGPT plan connection' })
    expect(open).toHaveFocus()
    expect(open).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(open)
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))
    await screen.findByRole('heading', { name: 'Feedback overview' })
    expect(window.location.hash).toBe('#showcase')
    expect(open).toHaveFocus()
    expect(open).toHaveAttribute('aria-expanded', 'false')
  })

  it('requires an application confirmation before deletion and preserves data when cancelled', async () => {
    const client = vi.fn(visualWorkbench())
    window.history.replaceState(null, '', '/#workbench')
    render(
      <App
        client={visualDashboard}
        workbenchClient={client as ReturnType<typeof visualWorkbench>}
      />,
    )
    const remove = await screen.findByRole('button', {
      name: 'Delete Demonstration reviews',
    })
    remove.focus()
    fireEvent.click(remove)
    const dialog = screen.getByRole('dialog', { name: 'Delete dataset' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(remove).toHaveFocus()
    expect(
      client.mock.calls.some(
        ([path, , method]) =>
          path === '/datasets/dataset' && method === 'DELETE',
      ),
    ).toBe(false)
    fireEvent.click(remove)
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Delete dataset',
      }),
    )
    await screen.findByRole('button', { name: 'Delete Demonstration reviews' })
    expect(
      client.mock.calls.some(
        ([path, , method]) =>
          path === '/datasets/dataset' && method === 'DELETE',
      ),
    ).toBe(true)
  })

  it('does not dispatch an AI sample when the privacy dialog is cancelled', async () => {
    const client = vi.fn(visualWorkbench())
    window.history.replaceState(null, '', '/#workbench/classification')
    render(
      <App
        client={visualDashboard}
        workbenchClient={client as ReturnType<typeof visualWorkbench>}
      />,
    )
    const engine = await screen.findByLabelText('Engine')
    fireEvent.change(engine, { target: { value: 'openai' } })
    fireEvent.change(screen.getByLabelText('Connection'), {
      target: { value: 'connection' },
    })
    await screen.findByRole('option', { name: 'Demonstration model' })
    const start = screen.getByRole('button', {
      name: 'Test a representative sample (up to 25)',
    })
    expect(start).toBeDisabled()
    fireEvent.click(
      screen.getByRole('checkbox', {
        name: /I authorize sending prepared feedback/,
      }),
    )
    start.focus()
    fireEvent.click(start)
    const dialog = await screen.findByRole('dialog', {
      name: 'Approve OpenAI processing',
    })
    expect(
      within(dialog).getByText(/Support explained the compatibility issue/),
    ).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(
      client.mock.calls.some(([path, body]) => path === '/runs' && body),
    ).toBe(false)
  })

  it.each(['loading', 'locked', 'disabled', 'error', 'empty'] as const)(
    'shares navigation in the %s workbench state',
    async (state) => {
      window.history.replaceState(null, '', '/#workbench')
      render(
        <App
          client={visualDashboard}
          workbenchClient={visualWorkbench(state)}
        />,
      )
      const expected = {
        loading: 'Checking local workspace…',
        locked: 'Unlock your local workspace',
        disabled: 'Start the workbench runtime',
        error: 'Fixture: data could not be loaded. Retry the local operation.',
        empty: 'No datasets imported yet.',
      }[state]
      await screen.findByText(expected, { exact: state !== 'error' })
      expect(
        screen.getByRole('navigation', { name: 'Workbench navigation' }),
      ).toBeInTheDocument()
    },
  )
})
