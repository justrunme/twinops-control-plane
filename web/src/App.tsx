import { useEffect, useMemo, useState } from 'react'
import { connectEvents, fetchScene, fetchTwin, triggerReconcile, triggerSpike } from './api'
import type { SceneSnapshot, TwinSnapshot } from './types'

const STATUS_COLOR: Record<string, string> = {
  SYNCED: '#1f9d55',
  WARNING: '#d97706',
  MISSING: '#64748b',
  DRIFT: '#dc2626',
  CRITICAL: '#7f1d1d',
}

function shortPrim(prim: string): string {
  return prim.split('/').filter(Boolean).at(-1) ?? prim
}

function display(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

export default function App() {
  const [snap, setSnap] = useState<TwinSnapshot | null>(null)
  const [scene, setScene] = useState<SceneSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [connected, setConnected] = useState(false)
  const [busy, setBusy] = useState<'spike' | 'reconcile' | null>(null)
  const [flash, setFlash] = useState<string | null>(null)

  useEffect(() => {
    let ws: WebSocket | null = null
    let closed = false

    const refreshScene = () => {
      fetchScene()
        .then((data) => {
          if (!closed) setScene(data)
        })
        .catch(() => {
          /* scene is optional while API boots */
        })
    }

    fetchTwin()
      .then((data) => {
        if (!closed) setSnap(data)
      })
      .catch((err: Error) => setError(err.message))
    refreshScene()

    ws = connectEvents((message) => {
      const payload = message as {
        type?: string
        snapshot?: TwinSnapshot
        event?: TwinSnapshot['timeline'][number]
      }
      if (payload.snapshot) {
        setSnap(payload.snapshot)
        setConnected(true)
        setError(null)
        refreshScene()
        return
      }
      if (payload.event) {
        setSnap((prev) => {
          if (!prev) return prev
          const timeline = [
            payload.event!,
            ...prev.timeline.filter((item) => item.id !== payload.event!.id),
          ].slice(0, 80)
          return { ...prev, timeline }
        })
        setConnected(true)
        if (payload.event?.type === 'drift' || payload.event?.type === 'reconcile') {
          refreshScene()
        }
      }
    })
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setError('WebSocket disconnected — is `make serve` running?')

    return () => {
      closed = true
      ws?.close()
    }
  }, [])

  const findings = snap?.drift?.status?.findings ?? []
  const summary = snap?.drift?.status?.summary ?? {}
  const hasDrift = Boolean(snap?.drift?.status?.hasDrift)
  const temp = snap?.simulator?.robot_temp
  const robotStatus = snap?.simulator?.robot_status
  const reconciled = Boolean(snap?.twin?.reconciled)
  const critical = Number(summary.CRITICAL ?? 0)
  const driftCount = Number(summary.DRIFT ?? 0)

  const summaryChips = useMemo(
    () => Object.entries(summary).sort(([a], [b]) => a.localeCompare(b)),
    [summary],
  )

  const demoStep =
    critical > 0 ? 2 : hasDrift && !reconciled ? 1 : reconciled && !hasDrift ? 4 : reconciled ? 3 : 1

  async function onSpike() {
    setBusy('spike')
    setFlash(null)
    try {
      await triggerSpike()
      setFlash('Heat spike injected — critical drift should appear')
      setScene(await fetchScene())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'spike failed')
    } finally {
      setBusy(null)
    }
  }

  async function onReconcile() {
    setBusy('reconcile')
    setFlash(null)
    try {
      const result = await triggerReconcile()
      const stillDrifting = Boolean(result.drift?.status?.hasDrift)
      setFlash(
        stillDrifting
          ? `Applied ${result.changes} changes — residual findings remain`
          : `Applied ${result.changes} changes — twin returned to SYNCED`,
      )
      const refreshed = await fetchTwin()
      setSnap(refreshed)
      setScene(await fetchScene())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'reconcile failed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="brand">TwinOps</p>
          <h1>Live digital twin control plane</h1>
          <p className="lede">
            Desired · Rendered · Observed — streaming reconciliation for industrial OpenUSD twins.
          </p>
        </div>
        <div className="hero-actions">
          <span className={`link ${connected ? 'ok' : 'bad'}`}>
            {connected ? 'LIVE' : 'OFFLINE'}
          </span>
          <button type="button" className="secondary" onClick={onSpike} disabled={busy !== null}>
            {busy === 'spike' ? 'Spiking…' : '1. Trigger heat spike'}
          </button>
          <button type="button" onClick={onReconcile} disabled={busy !== null}>
            {busy === 'reconcile' ? 'Reconciling…' : '2. Apply reconciliation'}
          </button>
        </div>
      </header>

      <ol className="steps">
        <li className={demoStep >= 1 ? 'active' : ''}>Drift visible</li>
        <li className={demoStep >= 2 ? 'active' : ''}>Critical spike</li>
        <li className={demoStep >= 3 ? 'active' : ''}>Reconcile applied</li>
        <li className={demoStep >= 4 ? 'active' : ''}>Synced</li>
      </ol>

      {error ? <div className="banner error">{error}</div> : null}
      {flash ? <div className="banner ok">{flash}</div> : null}

      <section className="status-row">
        <article>
          <span className="label">Twin</span>
          <strong>{snap?.twin?.name ?? '—'}</strong>
          <small>
            variant {snap?.twin?.variant ?? '—'}
            {reconciled ? ' · reconciled' : ''}
          </small>
        </article>
        <article>
          <span className="label">Robot01</span>
          <strong>
            {display(temp)}°C · {display(robotStatus)}
          </strong>
          <small>firmware {display(snap?.simulator?.robot_firmware)}</small>
        </article>
        <article>
          <span className="label">Drift</span>
          <strong className={hasDrift ? 'bad-text' : 'ok-text'}>
            {hasDrift ? 'DETECTED' : 'SYNCED'}
          </strong>
          <small>
            {driftCount} drift · {critical} critical ·{' '}
            {snap?.drift?.metadata?.generatedAt ?? 'waiting for stream'}
          </small>
        </article>
      </section>

      <div className="chips">
        {summaryChips.map(([key, value]) => (
          <span key={key} className="chip" style={{ borderColor: STATUS_COLOR[key] ?? '#64748b' }}>
            {key} {value}
          </span>
        ))}
      </div>

      <section className="panel scene-panel">
        <div className="panel-head">
          <h2>Scene inspector</h2>
          <small>{scene?.protocol?.name ?? 'twinops.highlight.v1'} · no GPU required</small>
        </div>
        <div className="scene-tree">
          {(scene?.prims ?? []).length === 0 ? (
            <p className="scene-empty">Waiting for scene snapshot…</p>
          ) : (
            (scene?.prims ?? []).map((prim) => {
              const color = STATUS_COLOR[prim.status] ?? '#64748b'
              const depth = Math.max(0, prim.prim.split('/').filter(Boolean).length - 3)
              return (
                <div
                  key={prim.prim}
                  className={`scene-node ${prim.highlight.enabled ? 'lit' : ''}`}
                  style={{
                    marginLeft: `${depth * 16}px`,
                    borderColor: color,
                    boxShadow: prim.highlight.enabled
                      ? `0 0 ${10 + prim.highlight.intensity * 18}px ${color}55`
                      : 'none',
                  }}
                >
                  <span className="scene-dot" style={{ background: color }} />
                  <strong>{prim.label}</strong>
                  <code>{prim.prim}</code>
                  <span className="pill" style={{ background: color }}>
                    {prim.status}
                  </span>
                </div>
              )
            })
          )}
        </div>
      </section>

      <div className="grid">
        <section className="panel">
          <div className="panel-head">
            <h2>Findings</h2>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Prim</th>
                  <th>Attr</th>
                  <th>Desired</th>
                  <th>Rendered</th>
                  <th>Observed</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {findings.length === 0 ? (
                  <tr>
                    <td colSpan={6}>Waiting for drift evaluation…</td>
                  </tr>
                ) : (
                  findings.map((finding) => (
                    <tr
                      key={`${finding.prim}-${finding.attribute}-${finding.status}-${finding.message}`}
                    >
                      <td>{shortPrim(finding.prim)}</td>
                      <td>
                        <code>{finding.attribute.replace('twinops:', '')}</code>
                      </td>
                      <td>{display(finding.desired)}</td>
                      <td>{display(finding.rendered)}</td>
                      <td>{display(finding.observed)}</td>
                      <td>
                        <span
                          className="pill"
                          style={{ background: STATUS_COLOR[finding.status] ?? '#334155' }}
                        >
                          {finding.status}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel timeline-panel">
          <div className="panel-head">
            <h2>Timeline</h2>
          </div>
          <ol className="timeline">
            {(snap?.timeline ?? []).map((item) => (
              <li key={item.id} className={`tl ${item.type}`}>
                <div className="tl-meta">
                  <span className="tl-type">{item.type}</span>
                  <time>{new Date(item.timestamp).toLocaleTimeString()}</time>
                </div>
                <p>{item.summary}</p>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  )
}
