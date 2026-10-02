import { afterEach, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { ConfirmationProvider } from './confirmation-dialog'
import { useConfirmation } from './confirmation-context'
afterEach(cleanup)
function Action() {
  const confirm = useConfirmation()
  const [result, setResult] = useState('Pending')
  return (
    <>
      <button
        onClick={async () =>
          setResult(
            (await confirm({
              title: 'Approve sample',
              message: 'Only prepared text will be sent.',
              confirmLabel: 'Process sample',
            }))
              ? 'Accepted'
              : 'Cancelled',
          )
        }
      >
        Start sample
      </button>
      <output>{result}</output>
    </>
  )
}
it('resolves native Escape cancellation as denial and returns focus', async () => {
  render(
    <ConfirmationProvider>
      <Action />
    </ConfirmationProvider>,
  )
  const source = screen.getByRole('button', { name: 'Start sample' })
  source.focus()
  fireEvent.click(source)
  fireEvent(
    screen.getByRole('dialog'),
    new Event('cancel', { bubbles: false, cancelable: true }),
  )
  await screen.findByText('Cancelled')
  expect(source).toHaveFocus()
})
it('approves only after explicit confirmation', async () => {
  render(
    <ConfirmationProvider>
      <Action />
    </ConfirmationProvider>,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Start sample' }))
  expect(
    screen.getByText('Only prepared text will be sent.'),
  ).toBeInTheDocument()
  expect(screen.getByText('Pending')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Process sample' }))
  await screen.findByText('Accepted')
})
