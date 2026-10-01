import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import { OrbitalSurface, type OrbitalModule } from './orbital-surface'
import { workbenchPages, type ApplicationRoute } from './application-routes'

type Slots = {
  showcase: HTMLElement | null
  context: HTMLElement | null
  title: HTMLElement | null
}
const ShellSlots = createContext<{
  targets: Slots
  activateShowcase: () => void
} | null>(null)

export function ShellSlot({
  name,
  children,
}: {
  name: keyof Slots
  children: ReactNode | ((activateShowcase: () => void) => ReactNode)
}) {
  const slots = useContext(ShellSlots)
  const target = slots?.targets[name]
  return target && slots
    ? createPortal(
        typeof children === 'function'
          ? children(slots.activateShowcase)
          : children,
        target,
      )
    : null
}

export function NavigationIcon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    Overview: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    Signals: 'M3 17l5-7 5 4 8-10 M3 21h18',
    Datasets: 'M4 4h16v16H4z M4 9h16 M9 4v16',
    Classification: 'M4 5h16 M4 12h10 M4 19h10 M17 15l2 2 3-4',
    Runs: 'M8 4l12 8-12 8z',
    Results: 'M4 20V10 M10 20V4 M16 20v-7 M22 20H2',
    Connections: 'M9 8H7a4 4 0 0 0 0 8h3 M15 8h2a4 4 0 0 1 0 8h-3 M8 12h8',
  }
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.Overview} />
    </svg>
  )
}

export function ApplicationShell({
  route,
  navigate,
  backgroundLoader,
  children,
}: {
  route: ApplicationRoute
  navigate: (route: ApplicationRoute) => void
  backgroundLoader?: () => Promise<OrbitalModule>
  children: ReactNode
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobile, setMobile] = useState(
    () => window.matchMedia?.('(max-width: 767px)').matches ?? false,
  )
  const [menuOpen, setMenuOpen] = useState(false)
  const [showcase, setShowcase] = useState<HTMLElement | null>(null)
  const [context, setContext] = useState<HTMLElement | null>(null)
  const [title, setTitle] = useState<HTMLElement | null>(null)
  const [motionTarget, setMotionTarget] = useState<HTMLElement | null>(null)
  const toggle = useRef<HTMLButtonElement>(null)
  const navigation = useRef<HTMLElement>(null)
  const expanded = mobile ? menuOpen : !collapsed

  useEffect(() => {
    document.querySelector('.application')?.scrollIntoView?.({ block: 'start' })
  }, [route.area, route.page])

  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 767px)')
    if (!media) return
    const change = () => {
      setMobile(media.matches)
      setMenuOpen(false)
    }
    media.addEventListener('change', change)
    return () => media.removeEventListener('change', change)
  }, [])
  useEffect(() => {
    if (!mobile || !menuOpen) return
    navigation.current
      ?.querySelector<HTMLElement>('button:not(:disabled),a')
      ?.focus()
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMenuOpen(false)
        toggle.current?.focus()
      }
    }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  }, [menuOpen, mobile])

  const closeAfterSelection = () => {
    if (mobile) {
      setMenuOpen(false)
      toggle.current?.focus()
    }
  }
  return (
    <ShellSlots.Provider
      value={{
        targets: { showcase, context, title },
        activateShowcase: () => {
          navigate({ area: 'showcase', page: 'Datasets' })
          closeAfterSelection()
        },
      }}
    >
      <div
        className="application oc-application"
        data-header-collapsed={!expanded}
        data-mobile-menu-open={mobile && menuOpen}
      >
        <a className="skip-link" href="#app-content">
          Skip to content
        </a>
        <OrbitalSurface
          controlsTarget={motionTarget}
          loader={backgroundLoader}
        />
        <div className="shell-toolbar">
          <button
            ref={toggle}
            className="header-toggle"
            type="button"
            aria-controls="app-header"
            aria-expanded={expanded}
            aria-label={expanded ? 'Collapse navigation' : 'Open navigation'}
            onClick={() =>
              mobile
                ? setMenuOpen((open) => !open)
                : setCollapsed((value) => !value)
            }
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <path
                d={
                  expanded
                    ? 'M6 6l12 12 M18 6L6 18'
                    : 'M4 6h16 M4 12h16 M4 18h16'
                }
              />
            </svg>
            <span className="mobile-menu-label">Menu</span>
          </button>
          <div className="shell-page-label" aria-live="polite">
            <span ref={setTitle} hidden={route.area !== 'showcase'} />
            {route.area === 'workbench' && `Workbench / ${route.page}`}
          </div>
        </div>
        <aside
          ref={navigation}
          id="app-header"
          className="floating-navigation"
          hidden={!expanded}
          aria-label="Application navigation"
        >
          <a
            className="floating-brand"
            aria-label="Feedback Intelligence"
            href="#showcase"
            onClick={() => {
              navigate({ area: 'showcase', page: 'Datasets' })
              closeAfterSelection()
            }}
          >
            <span className="brand__mark" aria-hidden="true" />
            <span>
              Feedback
              <br />
              Intelligence
            </span>
          </a>
          <span className="rail-section-label">Showcase</span>
          <div ref={setShowcase} />
          <span className="rail-section-label">Workbench</span>
          <nav className="primary-nav" aria-label="Workbench navigation">
            {workbenchPages.map((page) => (
              <button
                key={page}
                type="button"
                aria-current={
                  route.area === 'workbench' && route.page === page
                    ? 'page'
                    : undefined
                }
                onClick={() => {
                  navigate({ area: 'workbench', page })
                  closeAfterSelection()
                }}
              >
                <NavigationIcon name={page} />
                <span>{page}</span>
              </button>
            ))}
          </nav>
          <div
            ref={setContext}
            className="shell-context"
            hidden={route.area !== 'showcase'}
          />
          <div ref={setMotionTarget} className="shell-motion" />
        </aside>
        <div
          id="app-content"
          className="shell-content"
          tabIndex={-1}
          inert={mobile && menuOpen}
        >
          {children}
        </div>
      </div>
    </ShellSlots.Provider>
  )
}
