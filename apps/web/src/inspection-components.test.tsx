import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { Inspectable, InspectionProvider } from './inspection-components'

beforeEach(() => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('shared data inspection', () => {
  const detail = {
    title: 'Service records',
    scopeLabel: 'Run abc · All records',
    description: 'Successfully processed records.',
    fields: [{ label: 'Count', value: '18 / 24' }],
  }

  it('keeps a focused preview after automatic scrolling and clears a mouse-only preview', () => {
    render(
      <InspectionProvider scope="run">
        <Inspectable detail={detail}>Count</Inspectable>
      </InspectionProvider>,
    )
    const trigger = screen.getByRole('button', { name: 'Count' })
    vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({
      top: 80,
      bottom: 124,
      left: 16,
      right: 116,
      width: 100,
      height: 44,
      x: 16,
      y: 80,
      toJSON: () => ({}),
    })
    act(() => trigger.focus())
    fireEvent.scroll(window)
    fireEvent.mouseLeave(trigger)
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    act(() => trigger.blur())
    fireEvent.mouseEnter(trigger)
    fireEvent.scroll(window)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('previews the same data on hover and focus, pins on click and restores focus on Escape', () => {
    render(
      <InspectionProvider scope="run-a">
        <Inspectable detail={detail}>Service count</Inspectable>
      </InspectionProvider>,
    )
    const trigger = screen.getByRole('button', { name: 'Service count' })
    fireEvent.mouseEnter(trigger)
    expect(
      within(screen.getByRole('tooltip')).getByText('18 / 24'),
    ).toBeInTheDocument()
    fireEvent.mouseLeave(trigger)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    fireEvent.focus(trigger)
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    fireEvent.click(trigger)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    const panel = screen.getByRole('complementary', { name: 'Service records' })
    expect(within(panel).getByText('18 / 24')).toBeInTheDocument()
    expect(
      within(panel).getByRole('button', { name: 'Close inspection' }),
    ).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('applies an explicit detail action and closes the panel', () => {
    const action = vi.fn()
    render(
      <InspectionProvider scope="run-a">
        <Inspectable
          detail={{
            ...detail,
            action: { label: 'View matching records', onClick: action },
          }}
        >
          Service count
        </Inspectable>
      </InspectionProvider>,
    )
    const trigger = screen.getByRole('button', { name: 'Service count' })
    fireEvent.click(trigger)
    fireEvent.click(
      screen.getByRole('button', { name: 'View matching records' }),
    )
    expect(action).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('preserves pinned details during navigation and invalidates them only when scope changes', () => {
    const view = (scope: string, active = true) => (
      <InspectionProvider scope={scope} active={active}>
        <Inspectable detail={detail}>Service count</Inspectable>
      </InspectionProvider>
    )
    const { rerender } = render(view('run-a'))
    fireEvent.click(screen.getByRole('button', { name: 'Service count' }))
    rerender(view('run-b'))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Service count' }))
    rerender(view('run-b', false))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    expect(document.querySelector('.inspection-side-panel')).toHaveAttribute(
      'hidden',
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByRole('button', { name: 'Service count' }))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    rerender(view('run-b'))
    const panel = screen.getByRole('complementary', { name: 'Service records' })
    expect(
      within(panel).getByRole('button', { name: 'Close inspection' }),
    ).toHaveFocus()
    rerender(view('run-b', false))
    rerender(view('run-c', false))
    rerender(view('run-c'))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('clears transient previews when navigating away without showing them on return', () => {
    const view = (active: boolean) => (
      <InspectionProvider scope="run-a" active={active}>
        <Inspectable detail={detail}>Service count</Inspectable>
      </InspectionProvider>
    )
    const { rerender } = render(view(true))
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Service count' }))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    rerender(view(false))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    rerender(view(true))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('uses a native phone dialog and honours cancellation with focus restoration', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )
    const showModal = vi.fn(function (this: HTMLDialogElement) {
      this.setAttribute('open', '')
    })
    const close = vi.fn(function (this: HTMLDialogElement) {
      this.removeAttribute('open')
    })
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
      configurable: true,
      value: showModal,
    })
    Object.defineProperty(HTMLDialogElement.prototype, 'close', {
      configurable: true,
      value: close,
    })
    const view = (active: boolean) => (
      <InspectionProvider scope="run-a" active={active}>
        <Inspectable detail={detail}>Service count</Inspectable>
      </InspectionProvider>
    )
    const { rerender } = render(view(true))
    const trigger = screen.getByRole('button', { name: 'Service count' })
    fireEvent.click(trigger)
    const dialog = screen.getByRole('dialog', { name: 'Service records' })
    expect(showModal).toHaveBeenCalledTimes(1)
    rerender(view(false))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(dialog).not.toHaveAttribute('open')
    expect(close).toHaveBeenCalledTimes(1)
    rerender(view(true))
    expect(screen.getByRole('dialog', { name: 'Service records' })).toBe(dialog)
    expect(showModal).toHaveBeenCalledTimes(2)
    expect(
      within(dialog).getByRole('button', { name: 'Close inspection' }),
    ).toHaveFocus()
    fireEvent(dialog, new Event('cancel', { cancelable: true }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(close).toHaveBeenCalledTimes(2)
    expect(trigger).toHaveFocus()
    delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).showModal
    delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).close
  })
})
