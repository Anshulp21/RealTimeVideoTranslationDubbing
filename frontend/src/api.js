const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export async function startSession() {
  const res = await fetch(`${API_BASE}/api/session/start`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to start session')
  return res.json()
}

export async function stopSession(sessionId) {
  const form = new FormData()
  form.append('session_id', sessionId)
  const res = await fetch(`${API_BASE}/api/session/stop`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Failed to stop session')
  return res.json()
}

export async function sendChunk({ blob, clientTs, sourceLang, targetLang, sessionId }) {
  const form = new FormData()
  form.append('audio', blob, 'chunk.webm')
  form.append('client_ts', String(clientTs))
  form.append('source_lang', sourceLang)
  form.append('target_lang', targetLang)
  form.append('session_id', sessionId)
  const res = await fetch(`${API_BASE}/api/chunk`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Chunk failed')
  return res.json()
}

export async function uploadVideo({ blob, sessionId, filename = 'session.webm' }) {
  const form = new FormData()
  form.append('video', blob, filename)
  form.append('session_id', sessionId)
  const res = await fetch(`${API_BASE}/api/video/upload`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Video upload failed')
  return res.json()
}

export async function renderVideo({ sessionId, burnSubs = true }) {
  const form = new FormData()
  form.append('session_id', sessionId)
  form.append('burn_subs', burnSubs ? '1' : '0')
  const res = await fetch(`${API_BASE}/api/video/render`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Render failed')
  return res.json()
}
