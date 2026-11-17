import { useEffect } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Briefcase, ChartBar, ScanText, Settings, Users } from 'lucide-react'
import { useSettings } from '../settings'
import { cx } from './ui'

const NAV = [
  { to: '/jobs', label: 'Jobs', icon: Briefcase },
  { to: '/candidates', label: 'Candidates', icon: Users },
  { to: '/extract', label: 'Extract', icon: ScanText },
  { to: '/evaluate', label: 'Evaluate', icon: ChartBar },
  { to: '/settings', label: 'Settings', icon: Settings },
]

function BrandMark() {
  return (
    <svg className="brand__mark" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" className="brand__mark-bg" />
      <path d="M6 19.5c4-1.2 15.5-1.6 20-.6l-.6 4.6c-4.6-.8-15.2-.4-19 .7z" className="brand__mark-hl" />
      <path d="M9 8.5h14M9 13h10M9 17.5h12" className="brand__mark-lines" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}

export function ConnectionStatus({ compact }: { compact?: boolean }) {
  const { health } = useSettings()
  let tone = 'pending'
  let title = 'Checking the API'
  let detail: string | null = null
  if (health.status === 'ok') {
    tone = health.data.llm.enabled ? 'llm' : 'offline'
    title = health.data.llm.enabled ? `${health.data.llm.provider_label} connected` : 'Offline mode'
    detail = `${health.data.counts.resumes} resumes, ${health.data.counts.jobs} jobs`
  } else if (health.status === 'error') {
    tone = 'down'
    title = 'API unreachable'
    detail = 'Open settings to fix'
  }
  return (
    <Link to="/settings" className={cx('conn', `conn--${tone}`, compact && 'conn--compact')} title={title}>
      <span className="conn__dot" aria-hidden />
      {!compact && (
        <span className="conn__text">
          <span className="conn__title">{title}</span>
          {detail && <span className="conn__detail">{detail}</span>}
        </span>
      )}
      {compact && <span className="sr-only">{title}</span>}
    </Link>
  )
}

export default function Layout() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link to="/jobs" className="brand">
          <BrandMark />
          <span className="brand__name">
            Resume–JD
            <br />
            Matcher
          </span>
        </Link>
        <nav className="nav" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cx('nav__link', (isActive || (to === '/jobs' && pathname.startsWith('/report'))) && 'is-active')
              }
            >
              <Icon size={18} aria-hidden />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__foot">
          <ConnectionStatus />
        </div>
        <div className="topbar-status">
          <ConnectionStatus compact />
        </div>
      </aside>
      <main id="main" className="main">
        <div className="container">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
