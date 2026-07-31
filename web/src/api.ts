import type { HealthInfo, LiveMetrics, SceneSnapshot, TwinSnapshot } from './types'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

function authHeaders(): HeadersInit {
  const token = (import.meta.env.VITE_TWINOPS_API_TOKEN as string | undefined)?.trim()
  if (!token) {
    return {}
  }
  return { Authorization: `Bearer ${token}` }
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = {
    ...(init.headers || {}),
    ...authHeaders(),
  }
  return fetch(`${API_BASE}${path}`, { ...init, headers })
}

export async function fetchHealth(): Promise<HealthInfo> {
  const response = await apiFetch('/api/health')
  if (!response.ok) {
    throw new Error(`health API ${response.status}`)
  }
  return response.json()
}

export async function fetchTwin(): Promise<TwinSnapshot> {
  const response = await apiFetch('/api/twin')
  if (!response.ok) {
    throw new Error(`API ${response.status}`)
  }
  return response.json()
}

export async function fetchScene(): Promise<SceneSnapshot> {
  const response = await apiFetch('/api/scene')
  if (!response.ok) {
    throw new Error(`scene API ${response.status}`)
  }
  return response.json()
}

export async function fetchMetrics(): Promise<LiveMetrics> {
  const response = await apiFetch('/api/metrics')
  if (!response.ok) {
    throw new Error(`metrics API ${response.status}`)
  }
  return response.json()
}

export async function triggerSpike(): Promise<void> {
  const response = await apiFetch('/api/simulate/spike', { method: 'POST' })
  if (!response.ok) {
    throw new Error(`spike failed: ${response.status}`)
  }
}

export async function triggerReconcile(): Promise<{
  changes: number
  drift: TwinSnapshot['drift']
  scene?: SceneSnapshot
}> {
  const response = await apiFetch('/api/reconcile', { method: 'POST' })
  if (!response.ok) {
    throw new Error(`reconcile failed: ${response.status}`)
  }
  return response.json()
}

export function connectEvents(onMessage: (data: unknown) => void): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = import.meta.env.VITE_WS_HOST ?? window.location.host
  const token = (import.meta.env.VITE_TWINOPS_API_TOKEN as string | undefined)?.trim()
  const url = new URL(`${protocol}://${host}/ws/events`)
  // Browser WebSocket cannot set Authorization headers; use query for demos only.
  if (token) {
    url.searchParams.set('token', token)
  }
  const ws = new WebSocket(url.toString())
  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data))
    } catch {
      // ignore malformed frames
    }
  }
  // Keepalive ping so the server receive loop stays happy.
  const ping = window.setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send('ping')
    }
  }, 15000)
  ws.addEventListener('close', () => window.clearInterval(ping))
  return ws
}
