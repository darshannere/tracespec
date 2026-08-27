async function getJson(path) {
  const response = await fetch(path)
  let body

  try {
    body = await response.json()
  } catch {
    body = null
  }

  if (!response.ok) {
    const message = body?.detail?.message || body?.detail || `Request failed (${response.status})`
    throw new Error(message)
  }

  return body
}

export function getHealth() {
  return getJson('/api/health')
}

export function listTraces({ agent = '', limit = 100 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (agent.trim()) params.set('agent', agent.trim())
  return getJson(`/api/traces?${params}`)
}

export function getTrace(traceId) {
  return getJson(`/api/traces/${encodeURIComponent(traceId)}`)
}
