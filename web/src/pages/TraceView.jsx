import { useEffect, useState } from 'react'
import { getTrace } from '../api'

function formatDuration(span) {
  const duration = span.attrs?.latency_ms ?? (span.end_ms - span.start_ms)
  return duration < 1000 ? `${duration} ms` : `${(duration / 1000).toFixed(2)} s`
}

function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], {
    month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function SpanRow({ span, level = 0 }) {
  const [expanded, setExpanded] = useState(true)
  const children = span.children || []
  const hasChildren = children.length > 0

  return (
    <li className={`span-node ${span.error ? 'has-error' : ''}`}>
      <div className="span-row" style={{ '--depth': level }}>
        <button
          className={`tree-toggle ${hasChildren ? '' : 'is-leaf'}`}
          type="button"
          onClick={() => hasChildren && setExpanded(!expanded)}
          aria-expanded={hasChildren ? expanded : undefined}
          aria-label={hasChildren ? `${expanded ? 'Collapse' : 'Expand'} ${span.name}` : `${span.name} has no children`}
          disabled={!hasChildren}
        >
          {hasChildren ? (expanded ? '-' : '+') : '.'}
        </button>
        <span className={`type-badge type-${String(span.type || 'unknown').toLowerCase()}`}>{span.type || 'UNKNOWN'}</span>
        <span className="span-name">{span.name || 'unnamed span'}</span>
        {span.error && <span className="error-label">ERROR</span>}
        <span className="span-duration">{formatDuration(span)}</span>
      </div>
      {span.error && <p className="span-error"><strong>{span.error}</strong></p>}
      {expanded && hasChildren && (
        <ul className="span-children">
          {children.map((child) => <SpanRow key={child.id} span={child} level={level + 1} />)}
        </ul>
      )}
    </li>
  )
}

function ErrorState({ message }) {
  return <div className="state-card error-state" role="alert"><span className="state-code">ERR_TRACE_DETAIL</span><h2>Trace unavailable</h2><p>{message}</p><a className="button button-dark" href="#/traces">Back to traces</a></div>
}

export default function TraceView({ traceId }) {
  const [trace, setTrace] = useState(null)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')

  useEffect(() => {
    setStatus('loading')
    setError('')
    getTrace(traceId)
      .then((data) => { setTrace(data); setStatus('ready') })
      .catch((reason) => { setError(reason.message); setStatus('error') })
  }, [traceId])

  if (status === 'loading') return <section className="page-section"><div className="state-card" role="status"><span className="loader" aria-hidden="true" />Loading trace detail...</div></section>
  if (status === 'error') return <section className="page-section"><ErrorState message={error} /></section>

  const root = trace.spans
  const spanCount = root ? countSpans(root) : 0

  return (
    <section className="page-section" aria-labelledby="trace-detail-title">
      <a className="back-link" href="#/traces">&lt;- All traces</a>
      <div className="detail-heading">
        <div>
          <p className="eyebrow">Trace evidence</p>
          <h1 id="trace-detail-title">{trace.agent_name || 'Unnamed agent'}</h1>
          <code className="trace-id">{trace.trace_id}</code>
        </div>
        <span className={`verdict verdict-large verdict-${trace.verdict || 'unknown'}`}>{trace.verdict || 'unknown'}</span>
      </div>

      <div className="detail-meta panel">
        <div><span>Started</span><strong>{formatDate(trace.started_at)}</strong></div>
        <div><span>Provider</span><strong>{trace.provider || 'not reported'}</strong></div>
        <div><span>Span count</span><strong>{spanCount}</strong></div>
      </div>

      <div className="tree-panel panel">
        <div className="tree-header">
          <div><p className="eyebrow">Execution anatomy</p><h2>Span tree</h2></div>
          <span className="tree-legend"><i className="legend-dot legend-ok" /> healthy <i className="legend-dot legend-error" /> error</span>
        </div>
        {root ? <ul className="span-tree"><SpanRow span={root} /></ul> : <p className="muted-cell">No root span returned.</p>}
      </div>
    </section>
  )
}

function countSpans(span) {
  return 1 + (span.children || []).reduce((total, child) => total + countSpans(child), 0)
}
