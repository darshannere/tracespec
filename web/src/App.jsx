import { useEffect, useState } from 'react'
import { getHealth } from './api'
import TraceList from './pages/TraceList'
import TraceView from './pages/TraceView'

const tabs = [
  ['Traces', '#/traces'],
  ['Clusters', '#/clusters'],
  ['Suites', '#/suites'],
  ['Runs', '#/runs'],
  ['Proposals', '#/proposals'],
]

function currentRoute() {
  return window.location.hash.replace(/^#\/?/, '') || 'traces'
}

function decodeTraceId(route) {
  try {
    return decodeURIComponent(route.slice('traces/'.length))
  } catch {
    return route.slice('traces/'.length)
  }
}

function useRoute() {
  const [route, setRoute] = useState(currentRoute)

  useEffect(() => {
    const updateRoute = () => setRoute(currentRoute())
    window.addEventListener('hashchange', updateRoute)
    return () => window.removeEventListener('hashchange', updateRoute)
  }, [])

  return route
}

function Placeholder({ name }) {
  return (
    <section className="placeholder panel" aria-labelledby="placeholder-title">
      <p className="eyebrow">Module queued</p>
      <h2 id="placeholder-title">{name}</h2>
      <p>This console surface is reserved for the next TraceSpec slice.</p>
      <span className="placeholder-mark" aria-hidden="true">/ /</span>
    </section>
  )
}

function App() {
  const route = useRoute()
  const [apiOnline, setApiOnline] = useState(null)
  const isTraceDetail = route.startsWith('traces/')
  const activeTab = isTraceDetail ? 'traces' : route.split('/')[0]
  const selectedTraceId = isTraceDetail ? decodeTraceId(route) : null

  useEffect(() => {
    let active = true
    getHealth()
      .then(() => active && setApiOnline(true))
      .catch(() => active && setApiOnline(false))
    return () => { active = false }
  }, [])

  function renderPage() {
    if (isTraceDetail) return <TraceView traceId={selectedTraceId} />
    if (activeTab === 'traces') return <TraceList />
    const label = tabs.find(([, href]) => href === `#/${activeTab}`)?.[0] || 'Traces'
    return <Placeholder name={label} />
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <aside className="sidebar">
        <a className="brand" href="#/traces" aria-label="TraceSpec home">
          <span className="brand-glyph" aria-hidden="true">TS</span>
          <span>
            <strong>TraceSpec</strong>
            <small>agent evidence console</small>
          </span>
        </a>
        <div className="sidebar-rule" />
        <p className="sidebar-kicker">Observe / distill / improve</p>
        <nav className="tab-nav" aria-label="Primary navigation">
          {tabs.map(([label, href]) => (
            <a className={activeTab === href.slice(2) ? 'active' : ''} href={href} key={label}>
              <span className="nav-index">0{tabs.findIndex(([tab]) => tab === label) + 1}</span>
              {label}
            </a>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className={`status-dot ${apiOnline === false ? 'offline' : ''}`} aria-hidden="true" />
          <span>{apiOnline === false ? 'API unavailable' : 'API connected'}</span>
        </div>
      </aside>

      <main className="main-content" id="main-content" tabIndex="-1">
        <header className="topbar">
          <div>
            <p className="breadcrumb">TRACESPEC <span>/</span> {isTraceDetail ? 'TRACE VIEW' : activeTab.toUpperCase()}</p>
            <p className="topbar-note">A readable record of what your agent actually did.</p>
          </div>
          <div className="signal" aria-label="System status">
            <span className="signal-line" aria-hidden="true" />
            <span>LIVE READ</span>
          </div>
        </header>
        {renderPage()}
      </main>
    </div>
  )
}

export default App
