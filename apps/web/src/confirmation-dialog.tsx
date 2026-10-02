import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  ConfirmationContext as Context,
  type Confirmation,
} from './confirmation-context'
type Request = Confirmation & {
  resolve: (accepted: boolean) => void
  source: HTMLElement | null
}

export function ConfirmationProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<Request | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const pending = useRef<Request | null>(null)
  const finish = (accepted: boolean) => {
    const current = pending.current
    if (!current) return
    pending.current = null
    dialog.current?.close?.()
    setRequest(null)
    current.resolve(accepted)
    if (current.source?.isConnected) current.source.focus()
    // Async callers can re-enable their trigger after the promise settles.
    window.setTimeout(() => {
      if (current.source?.isConnected) current.source.focus()
    }, 0)
  }
  useEffect(() => {
    if (!request) return
    if (dialog.current?.showModal) dialog.current.showModal()
    else dialog.current?.setAttribute('open', '')
  }, [request])
  useEffect(
    () => () => {
      pending.current?.resolve(false)
    },
    [],
  )
  const confirm = (options: Confirmation) =>
    new Promise<boolean>((resolve) => {
      if (pending.current) {
        resolve(false)
        return
      }
      const next = {
        ...options,
        resolve,
        source:
          document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null,
      }
      pending.current = next
      setRequest(next)
    })
  return (
    <Context.Provider value={confirm}>
      {children}
      {request && (
        <dialog
          ref={dialog}
          className="confirmation-dialog"
          aria-labelledby="confirmation-title"
          aria-describedby="confirmation-message"
          onCancel={(event) => {
            event.preventDefault()
            finish(false)
          }}
        >
          <p className="eyebrow">
            {request.destructive ? 'Destructive action' : 'Review and confirm'}
          </p>
          <h2 id="confirmation-title">{request.title}</h2>
          <div id="confirmation-message" className="confirmation-message">
            {request.message}
          </div>
          <div className="dialog-actions">
            <button
              type="button"
              className="button button--secondary"
              onClick={() => finish(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className={`button ${request.destructive ? 'button--destructive' : 'button--primary'}`}
              onClick={() => finish(true)}
            >
              {request.confirmLabel || 'Confirm'}
            </button>
          </div>
        </dialog>
      )}
    </Context.Provider>
  )
}
