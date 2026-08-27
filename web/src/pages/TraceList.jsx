import { useEffect, useState } from 'react'
import { listTraces } from '../api'

function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], {
    month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function ErrorState({ message, onRetry }) {
  return (
    <div className="state-card error-state" role="alert">
      <span className="state-code">ERR_TRACE_READ</span>
      <h2>Could not load traces</h2>
      <p>{message}</p>
      <button className="button button-dark" type="button" onClick={onRetry}>Try again</button>
    </div>
  )
}

export default function TraceList() {
  const [traces, setTraces] = useState([])
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [agent, setAgent] = useState('')

  function loadTraces() {
    setStatus('loading')
    setError('')
    listTraces({ agent })
      .then((data) => {
        setTraces(data)
        setStatus('ready')
      })
      .catch((reason) => {
        setError(reason.message)
        setStatus('error')
      })
  }

  useEffect(() => { loadTraces() }, [])

  function submitFilter(event) {
    event.preventDefault()
    loadTraces()
  }

  return (
    <section className="page-section" aria-labelledby="traces-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Production evidence</p>
          <h1 id="traces-title">Trace register</h1>
        </div>
        <div className="heading-count" aria-label={`${traces.length} traces shown`}>
          <strong>{status === 'ready' ? traces.length : '-'}</strong>
          <span>captured traces</span>
        </div>
      </div>

      <form className="filter-bar" onSubmit={submitFilter}>
        <label htmlFor="agent-filter">Filter by agent</label>
        <input id="agent-filter" value={agent} onChange={(event) => setAgent(event.target.value)} placeholder="e.g. support-bot" />
        <button className="button button-amber" type="submit">Filter traces</button>
      </form>

      {status === 'loading' && <div className="state-card" role="status"><span className="loader" aria-hidden="true" />Reading trace register...</div>}
      {status === 'error' && <ErrorState message={error} onRetry={loadTraces} />}
      {status === 'ready' && traces.length === 0 && (
        <div className="state-card empty-state">
          <span className="state-code">NO_RECORDS</span>
          <h2>No traces yet</h2>
          <p>Ingest an OTLP or Langfuse trace and it will appear here.</p>
        </div>
      )}
      {status === 'ready' && traces.length > 0 && (
        <div className="table-wrap panel">
          <table className="trace-table">
            <caption>Captured agent traces</caption>
            <thead>
              <tr><th scope="col">Trace ID</th><th scope="col">Agent</th><th scope="col">Started</th><th scope="col">Verdict</th><th scope="col">Spans</th></tr>
            </thead>
            <tbody>
              {traces.map((trace) => (
                <tr key={trace.trace_id}>
                  <td data-label="Trace ID"><a className="trace-link" href={`#/traces/${encodeURIComponent(trace.trace_id)}`}>{trace.trace_id}</a></td>
                  <td data-label="Agent"><span className="agent-name">{trace.agent_name || 'unnamed agent'}</span></td>
                  <td data-label="Started" className="muted-cell">{formatDate(trace.started_at)}</td>
                  <td data-label="Verdict"><span className={`verdict verdict-${trace.verdict || 'unknown'}`}>{trace.verdict || 'unknown'}</span></td>
                  <td data-label="Spans" className="span-count">{trace.span_count ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
