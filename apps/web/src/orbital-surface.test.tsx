import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { OrbitalSurface, type OrbitalController } from './orbital-surface'
afterEach(() => {
  cleanup()
  localStorage.clear()
})
it('keeps one controller when its parent rerenders and destroys it on unmount', async () => {
  const target = document.createElement('div')
  document.body.append(target)
  const controller: OrbitalController = {
    state: { renderer: 'webgl2', reduced: false, paused: false, running: true },
    setOptions: vi.fn(),
    destroy: vi.fn(),
  }
  const mount = vi.fn(() => controller)
  const loader = vi.fn(async () => ({ createOrbitalSand: mount }))
  const view = render(
    <OrbitalSurface controlsTarget={target} loader={loader} />,
  )
  await screen.findByText('In motion')
  view.rerender(<OrbitalSurface controlsTarget={target} loader={loader} />)
  expect(mount).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: 'Flat' }))
  expect(controller.setOptions).toHaveBeenCalledWith({
    paused: true,
    flat: true,
  })
  expect(document.querySelector('.orbital-backdrop')).toHaveAttribute(
    'data-flat',
    'true',
  )
  view.unmount()
  expect(controller.destroy).toHaveBeenCalledTimes(1)
  target.remove()
})
it('disables animation and shows the poster when the graphics loader fails', async () => {
  const target = document.createElement('div')
  document.body.append(target)
  render(
    <OrbitalSurface
      controlsTarget={target}
      loader={async () => {
        throw new Error('Unavailable')
      }}
    />,
  )
  await screen.findByText('Graphics fallback: still texture')
  expect(screen.getByRole('button', { name: 'Animate' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Still' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  target.remove()
})
