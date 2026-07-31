import type { TwinSnapshot } from './types'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export async function fetchTwin(): Promise<TwinSnapshot> {
  const response = await fetch(`${API_BASE}/api/twin`)
  if (!response.ok) {
    throw new Error(`API ${response.status}`)
  }
  return response.json()
}

export async function triggerSpike(): Promise<void> {
  const response = await fetch(`${API_BASE}/api/simulate/spike`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(`spike failed: ${response.status}`)
  }
}

export async function triggerReconcile(): Promise<{
  changes: number
  drift: TwinSnapshot['drift']
}> {
  const response = await fetch(`${API_BASE}/api/reconcile`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(`reconcile failed: ${response.status}`)
  }
  return response.json()
}

export function connectEvents(onMessage: (data: unknown) => void): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = import.meta.env.VITE_WS_HOST ?? window.location.host
  const ws = new WebSocket(`${protocol}://${host}/ws/events`)
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
