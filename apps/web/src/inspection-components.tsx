import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import {
  InspectionContext,
  useInspection,
  type InspectionDetail,
} from './inspection-context'

type Pinned = { detail: InspectionDetail; trigger: HTMLElement | null }
type Preview = {
  detail: InspectionDetail
  trigger: HTMLElement
  top: number
  left: number
}

function DetailFields({ detail }: { detail: InspectionDetail }) {
  return (
    <>
      {detail.description && <p>{detail.description}</p>}
      {detail.fields && detail.fields.length > 0 && (
        <dl className="inspection-fields">
          {detail.fields.map((field, index) => (
            <div key={`${field.label}-${index}`}>
              <dt>{field.label}</dt>
              <dd>{field.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </>
  )
}

export function InspectionProvider({
  scope,
  active = true,
  children,
}: {
  scope: string
  active?: boolean
  children: ReactNode
}) {
  const [pinned, setPinned] = useState<Pinned | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previousActive, setPreviousActive] = useState(active)
  if (previousActive !== active) {
    setPreviousActive(active)
    // A hover preview is transient; only pinned selections survive navigation.
    setPreview(null)
  }
  const [mobile, setMobile] = useState(
    () => window.matchMedia?.('(max-width: 767px)').matches ?? false,
  )
  const request = useRef<Pinned | null>(null)
  const restoringFocus = useRef(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const priorScope = useRef(scope)
  const titleId = useId()
  const previewId = useId()
  const dismiss = useCallback(() => {
    const source = request.current?.trigger
    request.current = null
    restoringFocus.current = true
    dialog.current?.close?.()
    setPinned(null)
    setPreview(null)
    if (source?.isConnected && !source.closest('[hidden]')) source.focus()
    restoringFocus.current = false
  }, [])
  const clearPreview = useCallback(() => setPreview(null), [])
  const showPreview = useCallback(
    (detail: InspectionDetail, trigger: HTMLElement) => {
      if (!active || request.current || restoringFocus.current) return
      const bounds = trigger.getBoundingClientRect()
      const width = Math.min(320, window.innerWidth - 32)
      setPreview({
        detail,
        trigger,
        left: Math.max(
          16,
          Math.min(bounds.left, window.innerWidth - width - 16),
        ),
        top: Math.max(
          16,
          Math.min(bounds.bottom + 8, window.innerHeight - 260),
        ),
      })
    },
    [active],
  )
  const inspect = useCallback(
    (detail: InspectionDetail, trigger?: HTMLElement) => {
      if (!active) return
      const next = {
        detail,
        trigger:
          trigger ??
          (document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null),
      }
      request.current = next
      setPreview(null)
      setPinned(next)
    },
    [active],
  )
  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 767px)')
    if (!media) return
    const update = () => setMobile(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    if (priorScope.current !== scope) dismiss()
    priorScope.current = scope
  }, [scope, dismiss])
  useEffect(() => {
    if (!active) {
      if (dialog.current?.open) {
        if (dialog.current.close) dialog.current.close()
        else dialog.current.removeAttribute('open')
      }
      return
    }
    if (!pinned) return
    if (mobile) {
      if (!dialog.current?.open) {
        if (dialog.current?.showModal) dialog.current.showModal()
        else dialog.current?.setAttribute('open', '')
      }
    }
    closeButton.current?.focus()
  }, [pinned, mobile, active])
  useEffect(() => {
    if (!active || (!pinned && !preview)) return
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        dismiss()
      }
    }
    const reposition = () =>
      setPreview((current) => {
        if (!current || document.activeElement !== current.trigger) return null
        const bounds = current.trigger.getBoundingClientRect()
        if (
          !current.trigger.isConnected ||
          bounds.bottom <= 0 ||
          bounds.top >= window.innerHeight
        )
          return null
        const width = Math.min(320, window.innerWidth - 32)
        return {
          ...current,
          left: Math.max(
            16,
            Math.min(bounds.left, window.innerWidth - width - 16),
          ),
          top: Math.max(
            16,
            Math.min(bounds.bottom + 8, window.innerHeight - 260),
          ),
        }
      })
    document.addEventListener('keydown', keydown)
    window.addEventListener('resize', reposition)
    window.addEventListener('scroll', reposition, true)
    return () => {
      document.removeEventListener('keydown', keydown)
      window.removeEventListener('resize', reposition)
      window.removeEventListener('scroll', reposition, true)
    }
  }, [pinned, preview, dismiss, active])

  const detail = pinned?.detail
  const panel = detail && (
    <>
      <div className="inspection-header">
        <div>
          <p className="eyebrow">{detail.scopeLabel || 'Data inspection'}</p>
          <h2 id={titleId}>{detail.title}</h2>
        </div>
        <button
          ref={closeButton}
          type="button"
          className="button inspection-close"
          aria-label="Close inspection"
          onClick={dismiss}
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>
      <DetailFields detail={detail} />
      {detail.content}
      {detail.action && (
        <div className="inspection-actions">
          <button
            type="button"
            className="button button--primary"
            onClick={() => {
              detail.action?.onClick()
              dismiss()
            }}
          >
            {detail.action.label}
          </button>
        </div>
      )}
    </>
  )

  return (
    <InspectionContext.Provider
      value={{
        inspect,
        dismiss,
        preview: showPreview,
        clearPreview,
        previewId: preview ? previewId : undefined,
      }}
    >
      {children}
      {active &&
        preview &&
        createPortal(
          <div
            id={previewId}
            role="tooltip"
            className="inspection-preview"
            style={{ top: preview.top, left: preview.left }}
          >
            {preview.detail.scopeLabel && (
              <p className="eyebrow">{preview.detail.scopeLabel}</p>
            )}
            <strong>{preview.detail.title}</strong>
            <DetailFields
              detail={{
                ...preview.detail,
                fields: preview.detail.fields?.slice(0, 2),
                description: preview.detail.fields?.length
                  ? undefined
                  : preview.detail.description,
              }}
            />
            <p className="inspection-hint">Select for details</p>
          </div>,
          document.body,
        )}
      {pinned &&
        createPortal(
          mobile ? (
            <dialog
              ref={dialog}
              hidden={!active}
              className="inspection-panel inspection-dialog"
              aria-labelledby={titleId}
              onCancel={(event) => {
                event.preventDefault()
                dismiss()
              }}
            >
              {panel}
            </dialog>
          ) : (
            <aside
              hidden={!active}
              className="inspection-panel inspection-side-panel"
              aria-labelledby={titleId}
            >
              {panel}
            </aside>
          ),
          document.body,
        )}
    </InspectionContext.Provider>
  )
}

export function Inspectable({
  detail,
  children,
  className = '',
  onMouseEnter,
  onMouseLeave,
  onFocus,
  onBlur,
  ...props
}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onClick'> & {
  detail: InspectionDetail
  children: ReactNode
}) {
  const { inspect, preview, clearPreview, previewId } = useInspection()
  return (
    <button
      {...props}
      type="button"
      className={`inspection-trigger ${className}`.trim()}
      aria-describedby={previewId}
      onMouseEnter={(event) => {
        preview(detail, event.currentTarget)
        onMouseEnter?.(event)
      }}
      onMouseLeave={(event) => {
        if (document.activeElement !== event.currentTarget) clearPreview()
        onMouseLeave?.(event)
      }}
      onFocus={(event) => {
        preview(detail, event.currentTarget)
        onFocus?.(event)
      }}
      onBlur={(event) => {
        clearPreview()
        onBlur?.(event)
      }}
      onClick={(event) => inspect(detail, event.currentTarget)}
    >
      {children}
    </button>
  )
}
