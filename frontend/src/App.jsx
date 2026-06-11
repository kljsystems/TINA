import { useState, useEffect, useRef, useCallback } from 'react'
import { useTina } from './hooks/useTina'
import TinaFace, { STATE_CFG } from './components/TinaFace'

// ── Palette ───────────────────────────────────────────────────────────────────
const P  = '#8B5CF6'
const PG = '#C4B5FD'
const PD = '#4C1D95'
const PF = '#1E1030'
const PB = '#08040F'

// ── Panel config ──────────────────────────────────────────────────────────────
const PANEL_CFG = {
  weather:  { color: '#4ade80', glow: '#86efac', label: 'WEATHER'  },
  search:   { color: '#06b6d4', glow: '#67e8f9', label: 'SEARCH'   },
  news:     { color: '#f59e0b', glow: '#fcd34d', label: 'NEWS'     },
  vault:    { color: '#a78bfa', glow: '#c4b5fd', label: 'VAULT'    },
  calendar: { color: '#60a5fa', glow: '#93c5fd', label: 'CALENDAR' },
  github:   { color: '#94a3b8', glow: '#cbd5e1', label: 'GITHUB'   },
  logs:     { color: '#f59e0b', glow: '#fcd34d', label: 'LOGS'     },
  system:   { color: '#f59e0b', glow: '#fcd34d', label: 'SYSTEM'   },
  agent:    { color: '#10b981', glow: '#6ee7b7', label: 'AGENT'    },
  default:  { color: P,         glow: PG,        label: 'TOOL'     },
}

// ── ContextPanel ──────────────────────────────────────────────────────────────

function ContextPanel({ panel, onDismiss }) {
  const [visible, setVisible] = useState(false)
  const [dying,   setDying]   = useState(false)
  const cfg = PANEL_CFG[panel.type] ?? PANEL_CFG.default

  useEffect(() => {
    setTimeout(() => setVisible(true), 20)
    if (panel.ttl !== Infinity) {
      const fadeAt  = panel.ts + panel.ttl - 1200
      const killAt  = panel.ts + panel.ttl
      const nowMs   = Date.now()
      const fadeIn  = Math.max(0, fadeAt - nowMs)
      const killIn  = Math.max(0, killAt - nowMs)
      const t1 = setTimeout(() => setDying(true),    fadeIn)
      const t2 = setTimeout(() => onDismiss(panel.id), killIn)
      return () => { clearTimeout(t1); clearTimeout(t2) }
    }
  }, [])

  // Agent panel layout
  if (panel.type === 'agent') {
    return (
      <div style={{
        opacity: dying ? 0 : visible ? 1 : 0,
        transition: 'opacity 0.5s',
        border: `1px solid ${cfg.color}55`,
        borderLeft: `3px solid ${cfg.color}`,
        background: `${PF}dd`,
        borderRadius: 4,
        padding: '12px 14px',
        boxShadow: `0 0 18px ${cfg.glow}18`,
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%', display: 'inline-block',
              background: cfg.color, boxShadow: `0 0 8px ${cfg.glow}`,
              animation: 'agentpulse 1s ease-in-out infinite',
            }} />
            <span style={{ fontSize: 9, letterSpacing: 3, color: cfg.color }}>{(panel.display || panel.name).toUpperCase()}</span>
          </div>
          <span style={{ fontSize: 8, letterSpacing: 1, opacity: 0.4, color: cfg.color }}>RUNNING</span>
        </div>
        <div style={{ fontSize: 10, letterSpacing: 1, color: cfg.color, opacity: 0.75, paddingLeft: 14 }}>
          ↳ {panel.text}
        </div>
      </div>
    )
  }

  // Info panel layout
  return (
    <div style={{
      opacity: dying ? 0 : visible ? 1 : 0,
      transition: 'opacity 0.5s',
      border: `1px solid ${cfg.color}33`,
      borderLeft: `3px solid ${cfg.color}88`,
      background: `${PF}cc`,
      borderRadius: 4,
      padding: '11px 14px',
      boxShadow: `0 0 12px ${cfg.glow}11`,
      flexShrink: 0,
      maxHeight: 200,
      overflow: 'hidden',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 9, letterSpacing: 3, color: cfg.color, opacity: 0.85 }}>{cfg.label}</span>
        <button
          onClick={() => onDismiss(panel.id)}
          style={{ background: 'none', border: 'none', color: cfg.color, opacity: 0.35, cursor: 'pointer', fontSize: 10, padding: 0 }}
        >✕</button>
      </div>
      <div style={{
        fontSize: 10, lineHeight: 1.65, letterSpacing: 0.3, color: PG, opacity: 0.85,
        whiteSpace: 'pre-wrap', overflow: 'hidden',
        display: '-webkit-box', WebkitLineClamp: 8, WebkitBoxOrient: 'vertical',
      }}>
        {panel.text}
      </div>
    </div>
  )
}

// ── Code files badge ──────────────────────────────────────────────────────────

function CodeFilesBadge({ files, onClick }) {
  if (!files.length) return null
  return (
    <div
      onClick={onClick}
      style={{
        border: `1px solid #10b98155`,
        borderLeft: `3px solid #10b981`,
        background: `${PF}cc`,
        borderRadius: 4,
        padding: '10px 14px',
        cursor: 'pointer',
        flexShrink: 0,
        transition: 'box-shadow 0.2s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%', background: '#10b981',
            display: 'inline-block', animation: 'agentpulse 1.5s ease-in-out infinite',
          }} />
          <span style={{ fontSize: 9, letterSpacing: 3, color: '#10b981' }}>CODE FILES</span>
        </div>
        <span style={{
          fontSize: 9, background: '#10b98133', border: '1px solid #10b98155',
          color: '#10b981', borderRadius: 10, padding: '1px 7px', letterSpacing: 1,
        }}>{files.length}</span>
      </div>
      <div style={{ marginTop: 7, paddingLeft: 14 }}>
        {files.slice(0, 3).map(f => (
          <div key={f.ts} style={{ fontSize: 9, letterSpacing: 0.5, color: '#10b981', opacity: 0.6, marginBottom: 2 }}>
            {f.path.replace(/\\/g, '/').split('/').pop()}
          </div>
        ))}
        {files.length > 3 && (
          <div style={{ fontSize: 9, letterSpacing: 1, opacity: 0.35, color: '#10b981' }}>+{files.length - 3} more</div>
        )}
      </div>
    </div>
  )
}

// ── Diagnostics overlay (unchanged) ──────────────────────────────────────────

function DiagOverlay({ results, running, onClose }) {
  const checks  = Object.entries(results)
  const total   = checks.length
  const done    = checks.filter(([, r]) => r.status !== 'running').length
  const passed  = checks.filter(([, r]) => r.status === 'pass').length
  const failed  = checks.filter(([, r]) => r.status === 'fail').length
  const warned  = checks.filter(([, r]) => r.status === 'warn').length

  const dot = s => {
    if (s === 'running') return { bg: '#6b7280', anim: 'agentpulse 0.8s ease-in-out infinite' }
    if (s === 'pass')    return { bg: '#4ade80', anim: 'none' }
    if (s === 'fail')    return { bg: '#ef4444', anim: 'none' }
    if (s === 'warn')    return { bg: '#f59e0b', anim: 'none' }
    return { bg: '#ffffff22', anim: 'none' }
  }

  return (
    <div style={{ position: 'absolute', inset: 0, zIndex: 30, background: 'rgba(8,4,15,0.92)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: 560, maxHeight: '80vh', display: 'flex', flexDirection: 'column', border: `1px solid ${P}66`, borderRadius: 6, background: `${PF}ee`, boxShadow: `0 0 40px ${P}33`, fontFamily: "'Courier New', monospace" }}>
        <div style={{ padding: '14px 20px', borderBottom: `1px solid ${P}33`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 11, letterSpacing: 4, color: PG }}>SYSTEM DIAGNOSTICS</div>
            <div style={{ fontSize: 9, letterSpacing: 2, opacity: 0.45, marginTop: 3 }}>
              {running ? `RUNNING · ${done}/${total} complete` : `COMPLETE · ${passed} PASS · ${warned} WARN · ${failed} FAIL`}
            </div>
          </div>
          <button onClick={onClose} style={{ ...btnStyle(true, false), padding: '4px 12px', fontSize: 9 }}>
            {running ? 'HIDE' : 'CLOSE'}
          </button>
        </div>
        <div style={{ height: 2, background: '#ffffff11' }}>
          <div style={{ height: '100%', width: total ? `${(done / total) * 100}%` : '0%', background: failed > 0 ? '#ef4444' : warned > 0 ? '#f59e0b' : `linear-gradient(90deg,${PD},${PG})`, transition: 'width 0.3s ease', boxShadow: `0 0 6px ${PG}` }} />
        </div>
        <div style={{ overflowY: 'auto', padding: '10px 0' }}>
          {checks.map(([id, result]) => {
            const d = dot(result.status)
            return (
              <div key={id} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '7px 20px', borderBottom: `1px solid ${P}11` }}>
                <span style={{ flexShrink: 0, marginTop: 2, width: 7, height: 7, borderRadius: '50%', background: d.bg, display: 'inline-block', boxShadow: result.status !== 'running' ? `0 0 6px ${d.bg}` : 'none', animation: d.anim }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 10, letterSpacing: 2, opacity: result.status === 'running' ? 0.5 : 0.9 }}>{result.label || id.toUpperCase()}</span>
                    <span style={{ fontSize: 9, letterSpacing: 1, color: d.bg, opacity: result.status === 'running' ? 0.4 : 0.9 }}>{result.status === 'running' ? '...' : result.status.toUpperCase()}</span>
                  </div>
                  {result.detail && result.status !== 'running' && (
                    <div style={{ fontSize: 9, letterSpacing: 0.5, opacity: 0.45, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{result.detail}</div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Code preview panel (overlay) ──────────────────────────────────────────────

function CodePreviewPanel({ files, onClose }) {
  const [selectedIdx, setSelectedIdx] = useState(0)
  useEffect(() => { setSelectedIdx(0) }, [files.length])
  if (!files.length) return null

  const current  = files[selectedIdx]
  const basename = p => p.replace(/\\/g, '/').split('/').pop()
  const ext      = p => { const b = basename(p); const i = b.lastIndexOf('.'); return i > 0 ? b.slice(i + 1) : '' }

  return (
    <div style={{ position: 'absolute', inset: 0, zIndex: 25, background: 'rgba(8,4,15,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', animation: 'fadein 0.25s ease' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{ width: '85vw', height: '78vh', display: 'flex', flexDirection: 'column', border: `1px solid ${P}66`, borderRadius: 6, background: `${PF}f0`, boxShadow: `0 0 50px ${P}33`, fontFamily: "'Courier New', monospace", overflow: 'hidden' }}>
        <div style={{ flexShrink: 0, padding: '10px 16px', borderBottom: `1px solid ${P}33`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 10, letterSpacing: 4, color: PG, opacity: 0.7 }}>CODE PREVIEW</span>
            <span style={{ fontSize: 9, letterSpacing: 2, padding: '2px 8px', border: `1px solid ${P}44`, borderRadius: 10, color: P }}>{files.length} file{files.length !== 1 ? 's' : ''}</span>
            <span style={{ fontSize: 9, letterSpacing: 1, color: '#10b981', opacity: 0.8, display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#10b981', display: 'inline-block', animation: 'agentpulse 1.2s ease-in-out infinite' }} />
              SAM WRITING
            </span>
          </div>
          <button onClick={onClose} style={{ ...btnStyle(true, false), padding: '3px 12px', fontSize: 9 }}>✕ CLOSE</button>
        </div>
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <div style={{ width: 200, flexShrink: 0, borderRight: `1px solid ${P}22`, overflowY: 'auto', padding: '8px 0' }}>
            {files.map((f, i) => (
              <div key={f.ts} onClick={() => setSelectedIdx(i)} style={{ padding: '7px 14px', cursor: 'pointer', background: i === selectedIdx ? `${P}22` : 'transparent', borderLeft: `2px solid ${i === selectedIdx ? P : 'transparent'}`, transition: 'all 0.15s' }}>
                <div style={{ fontSize: 10, letterSpacing: 0.5, color: i === selectedIdx ? PG : PG + '88', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{basename(f.path)}</div>
                <div style={{ fontSize: 8, letterSpacing: 1, opacity: 0.35, marginTop: 2 }}>.{ext(f.path) || '?'}  ·  {(f.content.length / 1024).toFixed(1)}k</div>
              </div>
            ))}
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ flexShrink: 0, padding: '6px 14px', borderBottom: `1px solid ${P}22`, fontSize: 9, letterSpacing: 1, opacity: 0.45, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {current.path.replace(/\\/g, '/')}
            </div>
            <pre style={{ flex: 1, margin: 0, padding: '12px 16px', overflowY: 'auto', overflowX: 'auto', fontSize: 11, lineHeight: 1.6, letterSpacing: 0.3, color: PG, opacity: 0.9, whiteSpace: 'pre', tabSize: 2, animation: 'fadein 0.2s ease' }}>
              {current.content}
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const ts = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

function btnStyle(active, dim = false) {
  return {
    padding: '7px 16px', fontSize: 10, letterSpacing: 2,
    background: active ? `${P}33` : 'transparent',
    border: `1px solid ${active ? P : P + '33'}`,
    color: active ? PG : dim ? PG + '44' : PG + '66',
    borderRadius: 3, cursor: active ? 'pointer' : 'not-allowed',
    textTransform: 'uppercase', transition: 'all 0.2s',
    fontFamily: "'Courier New',monospace",
  }
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const {
    connected, tinaState, isRecording, activeAgent,
    lastResponse, services, turnCount, sessionStart,
    agentStatuses, diagRunning, diagResults,
    codePreviewFiles, panels, dismissPanel, activityLogVisible,
    sendMessage, startRecording, stopRecording,
  } = useTina()

  const [input,           setInput]          = useState('')
  const [time,            setTime]           = useState(new Date())
  const [log,             setLog]            = useState(['System initialised', 'Neural core loading…'])
  const [showDiag,        setShowDiag]       = useState(false)
  const [showCodePreview, setShowCodePreview] = useState(false)
  const [uptime,          setUptime]         = useState('00:00:00')

  const inputRef    = useRef(null)
  const diagDismiss = useRef(null)
  const prevConn    = useRef(false)

  const addLog = useCallback(msg => {
    setLog(l => [`${ts()} ${msg}`, ...l].slice(0, 12))
  }, [])

  // Clock + uptime
  useEffect(() => {
    const t = setInterval(() => {
      setTime(new Date())
      const ms = Date.now() - sessionStart
      const h  = Math.floor(ms / 3600000)
      const m  = Math.floor((ms % 3600000) / 60000)
      const s  = Math.floor((ms % 60000) / 1000)
      setUptime(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`)
    }, 1000)
    return () => clearInterval(t)
  }, [sessionStart])

  // Connection log
  useEffect(() => {
    if ( connected && !prevConn.current) addLog('Neural link established')
    if (!connected &&  prevConn.current) addLog('Connection lost — reconnecting…')
    prevConn.current = connected
  }, [connected, addLog])

  // Log new Tina responses
  const prevResponse = useRef(null)
  useEffect(() => {
    if (lastResponse && lastResponse !== prevResponse.current) {
      addLog(`TINA: ${lastResponse.slice(0, 60)}${lastResponse.length > 60 ? '…' : ''}`)
      prevResponse.current = lastResponse
    }
  }, [lastResponse, addLog])

  // Log tool panels arriving
  useEffect(() => {
    const latest = panels.filter(p => p.type !== 'agent').at(-1)
    if (latest) addLog(`${latest.type.toUpperCase()}: ${latest.text.slice(0, 50)}…`)
  }, [panels.length])

  // Auto-show code preview when Sam writes
  useEffect(() => {
    if (codePreviewFiles.length > 0) {
      setShowCodePreview(true)
      addLog(`SAM wrote: ${codePreviewFiles[0].path.replace(/\\/g, '/').split('/').pop()}`)
    }
  }, [codePreviewFiles.length, addLog])

  // Diag overlay
  useEffect(() => {
    if (diagRunning) {
      setShowDiag(true)
      if (diagDismiss.current) clearTimeout(diagDismiss.current)
    }
  }, [diagRunning])
  useEffect(() => {
    if (tinaState === 'listening' && showDiag && !diagRunning) {
      if (diagDismiss.current) clearTimeout(diagDismiss.current)
      diagDismiss.current = setTimeout(() => setShowDiag(false), 10000)
    }
  }, [tinaState])

  const handleSend = e => {
    e.preventDefault()
    const text = input.trim()
    if (!text || !connected) return
    addLog(`KAI: ${text.slice(0, 60)}${text.length > 60 ? '…' : ''}`)
    sendMessage(text)
    setInput('')
    inputRef.current?.focus()
  }

  const cfg       = STATE_CFG[tinaState] ?? STATE_CFG.listening
  const isOffline = tinaState === 'offline'
  const dispLabel = activeAgent ? `→ ${activeAgent.name.toUpperCase()}` : isRecording ? 'LISTENING' : cfg.label
  const dispSub   = activeAgent ? 'delegating' : isRecording ? 'recording…' : cfg.sub

  // Panel routing
  const infoPanels     = panels.filter(p => p.type !== 'agent')
  const activityPanels = panels.filter(p => p.type === 'agent')

  // Service dots for header
  const svcDots = [
    { key: 'ws',  label: 'WS',  ok: connected },
    { key: 'dg',  label: 'DG',  ok: services?.deepgram },
    { key: 'el',  label: 'EL',  ok: services?.elevenlabs },
    { key: 'gh',  label: 'GH',  ok: services?.github },
    { key: 'tv',  label: 'TV',  ok: services?.tavily },
  ]

  return (
    <div style={{
      height: '100vh', overflow: 'hidden',
      background: PB, display: 'flex', flexDirection: 'column',
      fontFamily: "'Courier New',monospace", color: PG,
      position: 'relative',
    }}>

      {/* Grid background */}
      <div style={{ position: 'absolute', inset: 0, opacity: 0.04, pointerEvents: 'none', backgroundImage: `linear-gradient(${P} 1px,transparent 1px),linear-gradient(90deg,${P} 1px,transparent 1px)`, backgroundSize: '40px 40px' }} />

      {/* Corner brackets */}
      {[
        { top: 10, left:  10, borderTop: `1px solid ${P}`, borderLeft:  `1px solid ${P}` },
        { top: 10, right: 10, borderTop: `1px solid ${P}`, borderRight: `1px solid ${P}` },
        { bottom: 10, left:  10, borderBottom: `1px solid ${P}`, borderLeft:  `1px solid ${P}` },
        { bottom: 10, right: 10, borderBottom: `1px solid ${P}`, borderRight: `1px solid ${P}` },
      ].map((s, i) => (
        <div key={i} style={{ position: 'absolute', width: 22, height: 22, opacity: isOffline ? 0.15 : 0.4, ...s }} />
      ))}

      {/* Overlays */}
      {showCodePreview && codePreviewFiles.length > 0 && (
        <CodePreviewPanel files={codePreviewFiles} onClose={() => setShowCodePreview(false)} />
      )}
      {showDiag && Object.keys(diagResults).length > 0 && (
        <DiagOverlay results={diagResults} running={diagRunning} onClose={() => setShowDiag(false)} />
      )}

      {/* Offline overlay */}
      {isOffline && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, background: 'rgba(8,4,15,0.88)' }}>
          <div style={{ fontSize: 28, letterSpacing: 8, color: '#E24B4A', opacity: 0.8, animation: 'offblink 2s ease-in-out infinite' }}>TINA OFFLINE</div>
          <div style={{ fontSize: 9, letterSpacing: 3, color: '#E24B4A', opacity: 0.4 }}>START BACKEND — python start.py</div>
        </div>
      )}

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div style={{ flexShrink: 0, zIndex: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 24px', borderBottom: `1px solid ${P}33` }}>
        {/* Service dots */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {svcDots.map(({ key, label, ok }) => (
            <div key={key} title={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{
                width: 5, height: 5, borderRadius: '50%', display: 'inline-block',
                background: ok === undefined ? '#6b7280' : ok ? '#4ade80' : '#ef4444',
                boxShadow:  ok === undefined ? 'none' : ok ? '0 0 5px #4ade80' : '0 0 5px #ef4444',
              }} />
              <span style={{ fontSize: 7, letterSpacing: 1, opacity: 0.4 }}>{label}</span>
            </div>
          ))}
        </div>

        {/* Title */}
        <div style={{ fontSize: 20, letterSpacing: 10, fontWeight: 'bold', color: '#fff', textShadow: `0 0 20px ${P}` }}>
          T I N A
        </div>

        {/* Time + state */}
        <div style={{ textAlign: 'right', fontSize: 9, letterSpacing: 2, opacity: 0.5 }}>
          <div>{time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
          <div style={{ marginTop: 2, color: isRecording ? '#ef4444' : PG }}>{cfg.label}</div>
        </div>
      </div>

      {/* ── 3-column body ─────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', gap: 10, padding: '10px 14px', zIndex: 1 }}>

        {/* Left — info panels (tool results) */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8, overflow: 'hidden', minWidth: 180 }}>
          {infoPanels.length === 0 ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ fontSize: 8, letterSpacing: 3, opacity: 0.08, textAlign: 'center' }}>
                CONTEXT ZONE<br />TOOL RESULTS APPEAR HERE
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, overflowY: 'auto' }}>
              {infoPanels.map(panel => (
                <ContextPanel key={panel.id} panel={panel} onDismiss={dismissPanel} />
              ))}
            </div>
          )}
        </div>

        {/* Centre — face + controls */}
        <div style={{ flexShrink: 0, width: 360, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, overflow: 'hidden' }}>

          {/* Face */}
          <div style={{ position: 'relative', flexShrink: 0 }}>
            <TinaFace state={tinaState} size={310} />
            <div style={{ position: 'absolute', bottom: 42, left: 0, right: 0, textAlign: 'center', pointerEvents: 'none' }}>
              <div style={{ fontSize: 10, letterSpacing: 5, color: activeAgent ? activeAgent.color : PG, opacity: 0.9, transition: 'color 0.4s' }}>{dispLabel}</div>
              <div style={{ fontSize: 8, letterSpacing: 2, opacity: 0.3, marginTop: 2 }}>{dispSub}</div>
            </div>
          </div>

          {/* Input + buttons */}
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 7, flexShrink: 0, marginTop: 'auto' }}>
            <form onSubmit={handleSend} style={{ display: 'flex', gap: 6 }}>
              <span style={{ fontSize: 13, color: P, opacity: 0.7, alignSelf: 'center', flexShrink: 0 }}>&gt;</span>
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder={connected ? 'send a message…' : 'offline…'}
                disabled={!connected || isRecording}
                autoFocus
                style={{
                  flex: 1, background: `${PF}99`, border: `1px solid ${P}33`,
                  borderRadius: 3, padding: '6px 10px', color: PG,
                  fontFamily: "'Courier New',monospace", fontSize: 12, letterSpacing: 1,
                  outline: 'none',
                }}
              />
              <button
                type="button"
                onMouseDown={startRecording}
                onMouseUp={stopRecording}
                onMouseLeave={stopRecording}
                onTouchStart={e => { e.preventDefault(); startRecording() }}
                onTouchEnd={stopRecording}
                disabled={!connected}
                title="Hold to talk"
                style={{
                  ...btnStyle(connected),
                  background: isRecording ? '#ef444433' : connected ? `${P}33` : 'transparent',
                  border:     `1px solid ${isRecording ? '#ef4444' : connected ? P : P + '33'}`,
                  color:      isRecording ? '#ef4444' : PG,
                  animation:  isRecording ? 'micpulse 0.8s ease-in-out infinite' : 'none',
                  flexShrink: 0,
                }}
              >
                {isRecording ? '■ REC' : '● MIC'}
              </button>
              <button type="submit" disabled={!connected || !input.trim() || isRecording} style={btnStyle(connected && input.trim() && !isRecording)}>
                SEND
              </button>
            </form>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                onClick={() => { fetch('http://localhost:8000/api/diagnostics', { method: 'POST' }); addLog('Diagnostics started') }}
                disabled={!connected || diagRunning}
                style={{ ...btnStyle(connected && !diagRunning), flex: 1 }}
              >
                {diagRunning ? '⠿ SCANNING…' : '◎ DIAGNOSTICS'}
              </button>
              <button onClick={() => setShowCodePreview(v => !v)} disabled={codePreviewFiles.length === 0} style={{ ...btnStyle(codePreviewFiles.length > 0), position: 'relative' }}>
                CODE{codePreviewFiles.length > 0 ? ` (${codePreviewFiles.length})` : ''}
              </button>
            </div>
          </div>
        </div>

        {/* Right — agent panels + activity log */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8, overflow: 'hidden', minWidth: 180 }}>

          {/* Agent panels */}
          {activityPanels.map(panel => (
            <ContextPanel key={panel.id} panel={panel} onDismiss={dismissPanel} />
          ))}

          {/* Code files badge */}
          <CodeFilesBadge files={codePreviewFiles} onClick={() => setShowCodePreview(true)} />

          {/* Activity log — toggleable via "Tina, hide the activity log" */}
          {activityLogVisible && (
            <div style={{ flex: 1, border: `1px solid ${P}18`, borderRadius: 4, padding: '10px 12px', background: `${PF}88`, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              <div style={{ fontSize: 8, letterSpacing: 3, opacity: 0.35, marginBottom: 8 }}>ACTIVITY</div>
              <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 3 }}>
                {log.map((l, i) => (
                  <div key={i} style={{ fontSize: 9, letterSpacing: 0.2, opacity: Math.max(0.2, 1 - i * 0.07), color: i === 0 ? PG : PG + '99', lineHeight: 1.4 }}>
                    {l}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <div style={{ flexShrink: 0, zIndex: 1, display: 'flex', justifyContent: 'space-between', padding: '5px 24px', borderTop: `1px solid ${P}22`, fontSize: 8, letterSpacing: 2, opacity: 0.35 }}>
        <span>UPTIME {uptime}</span>
        <span>EXCHANGES {turnCount}</span>
        <span>PANELS {panels.length}</span>
        <span>{connected ? 'CONNECTED' : 'OFFLINE'} · CLAUDE SONNET 4.6</span>
      </div>

      <style>{`
        * { box-sizing: border-box; }
        body { margin: 0; overflow: hidden; }
        @keyframes offblink   { 0%,100%{opacity:0.8} 50%{opacity:0.3} }
        @keyframes micpulse   { 0%,100%{box-shadow:0 0 6px #ef4444} 50%{box-shadow:0 0 18px #ef4444,0 0 6px #ef444488} }
        @keyframes fadein     { from{opacity:0;transform:translateY(-4px)} to{opacity:1;transform:translateY(0)} }
        @keyframes agentpulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
      `}</style>
    </div>
  )
}
