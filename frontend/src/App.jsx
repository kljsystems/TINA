import { useState, useEffect, useRef, useCallback } from 'react'
import { useTina } from './hooks/useTina'
import TinaFace, { STATE_CFG } from './components/TinaFace'

const P  = '#8B5CF6'
const PG = '#C4B5FD'
const PF = '#1E1030'
const PB = '#08040F'

const AGENTS = [
  { key: 'coding',   name: 'SAM',     role: 'Code',     color: '#10b981', glow: '#6ee7b7' },
  { key: 'research', name: 'CHARLIE', role: 'Research', color: '#06b6d4', glow: '#67e8f9' },
  { key: 'email',    name: 'TRISTAN', role: 'Email',    color: '#f59e0b', glow: '#fcd34d' },
  { key: 'data',     name: 'CONNOR',  role: 'Data',     color: '#a78bfa', glow: '#c4b5fd' },
]

const PANEL_CFG = {
  weather:  { color: '#4ade80', label: 'WEATHER'  },
  search:   { color: '#06b6d4', label: 'SEARCH'   },
  news:     { color: '#f59e0b', label: 'NEWS'     },
  vault:    { color: '#a78bfa', label: 'VAULT'    },
  calendar: { color: '#60a5fa', label: 'CALENDAR' },
  github:   { color: '#94a3b8', label: 'GITHUB'   },
  logs:     { color: '#f59e0b', label: 'LOGS'     },
  system:   { color: '#f59e0b', label: 'SYSTEM'   },
  default:  { color: P,         label: 'TOOL'     },
}

function btnStyle(active, dim = false) {
  return {
    padding: '7px 14px', fontSize: 9, letterSpacing: 2,
    background: active ? `${P}33` : 'transparent',
    border: `1px solid ${active ? P : P + '33'}`,
    color: active ? PG : dim ? PG + '44' : PG + '55',
    borderRadius: 3, cursor: active ? 'pointer' : 'not-allowed',
    textTransform: 'uppercase', transition: 'all 0.2s',
    fontFamily: "'Courier New',monospace",
  }
}

// ── Agent card ────────────────────────────────────────────────────────────────

function AgentCard({ agent, status }) {
  const s = status ?? { status: 'idle', tool: null }
  const isActive = s.status === 'running' || s.status === 'active'
  const isDone   = s.status === 'done'

  return (
    <div style={{
      border: `1px solid ${isActive ? agent.color + '66' : agent.color + '1a'}`,
      borderLeft: `2px solid ${isActive ? agent.color : agent.color + '33'}`,
      background: isActive ? `${agent.color}0c` : `${PF}99`,
      borderRadius: 4,
      padding: '8px 10px',
      transition: 'all 0.35s',
      boxShadow: isActive ? `0 0 14px ${agent.glow}18` : 'none',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            width: 5, height: 5, borderRadius: '50%', display: 'inline-block', flexShrink: 0,
            background: isActive ? agent.color : isDone ? agent.color + '88' : agent.color + '33',
            boxShadow: isActive ? `0 0 7px ${agent.glow}` : 'none',
            animation: isActive ? 'agentpulse 1s ease-in-out infinite' : 'none',
          }} />
          <span style={{ fontSize: 9, letterSpacing: 2, color: isActive ? agent.color : agent.color + '77' }}>
            {agent.name}
          </span>
        </div>
        <span style={{
          fontSize: 7, letterSpacing: 1,
          color: isActive ? agent.color : PG,
          opacity: isActive ? 0.9 : 0.2,
        }}>
          {isActive ? 'ACTIVE' : isDone ? 'DONE' : 'IDLE'}
        </span>
      </div>
      <div style={{
        fontSize: 8, letterSpacing: 0.5,
        color: isActive ? agent.color : PG,
        opacity: isActive ? 0.65 : 0.2,
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
      }}>
        {s.tool || agent.role}
      </div>
    </div>
  )
}

// ── Tool result panel ─────────────────────────────────────────────────────────

function ToolPanel({ panel, onDismiss }) {
  const [visible, setVisible] = useState(false)
  const [dying,   setDying]   = useState(false)
  const cfg = PANEL_CFG[panel.type] ?? PANEL_CFG.default

  useEffect(() => {
    setTimeout(() => setVisible(true), 20)
    if (panel.ttl !== Infinity) {
      const fadeAt = panel.ts + panel.ttl - 1200
      const killAt = panel.ts + panel.ttl
      const now    = Date.now()
      const t1 = setTimeout(() => setDying(true),        Math.max(0, fadeAt - now))
      const t2 = setTimeout(() => onDismiss(panel.id),   Math.max(0, killAt - now))
      return () => { clearTimeout(t1); clearTimeout(t2) }
    }
  }, [])

  return (
    <div style={{
      opacity: dying ? 0 : visible ? 1 : 0,
      transition: 'opacity 0.4s',
      border: `1px solid ${cfg.color}1f`,
      borderLeft: `2px solid ${cfg.color}66`,
      background: `${PF}cc`,
      borderRadius: 4,
      padding: '9px 12px',
      flexShrink: 0,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: 8, letterSpacing: 2, color: cfg.color, opacity: 0.85 }}>{cfg.label}</span>
        <button
          onClick={() => onDismiss(panel.id)}
          style={{ background: 'none', border: 'none', color: cfg.color, opacity: 0.3, cursor: 'pointer', fontSize: 9, padding: 0 }}
        >✕</button>
      </div>
      <div style={{
        fontSize: 9, lineHeight: 1.6, color: PG, opacity: 0.75,
        whiteSpace: 'pre-wrap', overflow: 'hidden',
        display: '-webkit-box', WebkitLineClamp: 7, WebkitBoxOrient: 'vertical',
      }}>
        {panel.text}
      </div>
    </div>
  )
}

// ── Diagnostics overlay ───────────────────────────────────────────────────────

function DiagOverlay({ results, running, onClose }) {
  const checks = Object.entries(results)
  const total  = checks.length
  const done   = checks.filter(([, r]) => r.status !== 'running').length
  const passed = checks.filter(([, r]) => r.status === 'pass').length
  const failed = checks.filter(([, r]) => r.status === 'fail').length
  const warned = checks.filter(([, r]) => r.status === 'warn').length

  const dot = s => {
    if (s === 'running') return { bg: '#6b7280', anim: 'agentpulse 0.8s ease-in-out infinite' }
    if (s === 'pass')    return { bg: '#4ade80', anim: 'none' }
    if (s === 'fail')    return { bg: '#ef4444', anim: 'none' }
    if (s === 'warn')    return { bg: '#f59e0b', anim: 'none' }
    return { bg: '#ffffff22', anim: 'none' }
  }

  return (
    <div style={{ position: 'absolute', inset: 0, zIndex: 30, background: 'rgba(8,4,15,0.92)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: 540, maxHeight: '80vh', display: 'flex', flexDirection: 'column', border: `1px solid ${P}55`, borderRadius: 6, background: `${PF}ee`, boxShadow: `0 0 40px ${P}33`, fontFamily: "'Courier New',monospace" }}>
        <div style={{ padding: '14px 20px', borderBottom: `1px solid ${P}33`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 11, letterSpacing: 4, color: PG }}>SYSTEM DIAGNOSTICS</div>
            <div style={{ fontSize: 8, letterSpacing: 2, opacity: 0.4, marginTop: 3 }}>
              {running ? `RUNNING · ${done}/${total}` : `COMPLETE · ${passed} PASS · ${warned} WARN · ${failed} FAIL`}
            </div>
          </div>
          <button onClick={onClose} style={{ ...btnStyle(true), padding: '4px 12px' }}>{running ? 'HIDE' : 'CLOSE'}</button>
        </div>
        <div style={{ height: 2, background: '#ffffff0a' }}>
          <div style={{ height: '100%', width: total ? `${(done / total) * 100}%` : '0%', background: failed > 0 ? '#ef4444' : warned > 0 ? '#f59e0b' : `linear-gradient(90deg,#4C1D95,${PG})`, transition: 'width 0.3s ease' }} />
        </div>
        <div style={{ overflowY: 'auto', padding: '8px 0' }}>
          {checks.map(([id, result]) => {
            const d = dot(result.status)
            return (
              <div key={id} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '7px 20px', borderBottom: `1px solid ${P}0d` }}>
                <span style={{ flexShrink: 0, marginTop: 2, width: 6, height: 6, borderRadius: '50%', background: d.bg, display: 'inline-block', animation: d.anim }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 10, letterSpacing: 2, opacity: result.status === 'running' ? 0.45 : 0.9 }}>{result.label || id.toUpperCase()}</span>
                    <span style={{ fontSize: 9, letterSpacing: 1, color: d.bg, opacity: result.status === 'running' ? 0.4 : 1 }}>{result.status === 'running' ? '…' : result.status.toUpperCase()}</span>
                  </div>
                  {result.detail && result.status !== 'running' && (
                    <div style={{ fontSize: 8, opacity: 0.4, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{result.detail}</div>
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

// ── Code preview overlay ──────────────────────────────────────────────────────

function CodePreviewPanel({ files, onClose }) {
  const [selectedIdx, setSelectedIdx] = useState(0)
  useEffect(() => setSelectedIdx(0), [files.length])
  if (!files.length) return null

  const current  = files[selectedIdx]
  const basename = p => p.replace(/\\/g, '/').split('/').pop()
  const ext      = p => { const b = basename(p); const i = b.lastIndexOf('.'); return i > 0 ? b.slice(i + 1) : '' }

  return (
    <div
      style={{ position: 'absolute', inset: 0, zIndex: 25, background: 'rgba(8,4,15,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', animation: 'fadein 0.2s ease' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{ width: '85vw', height: '78vh', display: 'flex', flexDirection: 'column', border: `1px solid ${P}66`, borderRadius: 6, background: `${PF}f2`, boxShadow: `0 0 50px ${P}33`, fontFamily: "'Courier New',monospace", overflow: 'hidden' }}>
        <div style={{ flexShrink: 0, padding: '10px 16px', borderBottom: `1px solid ${P}33`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 10, letterSpacing: 4, color: PG, opacity: 0.7 }}>CODE PREVIEW</span>
            <span style={{ fontSize: 8, letterSpacing: 2, padding: '2px 8px', border: `1px solid ${P}44`, borderRadius: 10, color: P }}>{files.length} file{files.length !== 1 ? 's' : ''}</span>
            <span style={{ fontSize: 8, color: '#10b981', opacity: 0.8, display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#10b981', display: 'inline-block', animation: 'agentpulse 1.2s ease-in-out infinite' }} />
              SAM
            </span>
          </div>
          <button onClick={onClose} style={{ ...btnStyle(true), padding: '3px 12px' }}>✕ CLOSE</button>
        </div>
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <div style={{ width: 190, flexShrink: 0, borderRight: `1px solid ${P}22`, overflowY: 'auto', padding: '6px 0' }}>
            {files.map((f, i) => (
              <div key={f.ts} onClick={() => setSelectedIdx(i)} style={{ padding: '7px 12px', cursor: 'pointer', background: i === selectedIdx ? `${P}22` : 'transparent', borderLeft: `2px solid ${i === selectedIdx ? P : 'transparent'}`, transition: 'all 0.15s' }}>
                <div style={{ fontSize: 9, color: i === selectedIdx ? PG : PG + '77', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{basename(f.path)}</div>
                <div style={{ fontSize: 7, opacity: 0.3, marginTop: 2 }}>.{ext(f.path) || '?'} · {(f.content.length / 1024).toFixed(1)}k</div>
              </div>
            ))}
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ flexShrink: 0, padding: '5px 14px', borderBottom: `1px solid ${P}22`, fontSize: 8, opacity: 0.35, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {current.path.replace(/\\/g, '/')}
            </div>
            <pre style={{ flex: 1, margin: 0, padding: '12px 16px', overflowY: 'auto', fontSize: 11, lineHeight: 1.6, color: PG, opacity: 0.9, whiteSpace: 'pre', tabSize: 2 }}>
              {current.content}
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const {
    connected, tinaState, isRecording, activeAgent,
    lastResponse, services, turnCount, sessionStart,
    agentStatuses, diagRunning, diagResults,
    codePreviewFiles, panels, dismissPanel,
    sendMessage, startRecording, stopRecording,
  } = useTina()

  const [input,           setInput]          = useState('')
  const [time,            setTime]           = useState(new Date())
  const [uptime,          setUptime]         = useState('00:00:00')
  const [messages,        setMessages]       = useState([
    { id: 0, role: 'system', text: 'Neural core online. All systems ready.' },
  ])
  const [showDiag,        setShowDiag]       = useState(false)
  const [showCodePreview, setShowCodePreview] = useState(false)

  const msgIdRef    = useRef(1)
  const inputRef    = useRef(null)
  const chatRef     = useRef(null)
  const prevConn    = useRef(false)
  const prevResp    = useRef(null)
  const diagDismiss = useRef(null)

  const addMessage = useCallback((role, text) => {
    setMessages(prev => [...prev, { id: msgIdRef.current++, role, text, ts: Date.now() }].slice(-60))
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

  // Connection events
  useEffect(() => {
    if ( connected && !prevConn.current) addMessage('system', 'Neural link established')
    if (!connected &&  prevConn.current) addMessage('system', 'Connection lost — reconnecting…')
    prevConn.current = connected
  }, [connected, addMessage])

  // TINA responses
  useEffect(() => {
    if (lastResponse && lastResponse !== prevResp.current) {
      addMessage('tina', lastResponse)
      prevResp.current = lastResponse
    }
  }, [lastResponse, addMessage])

  // Auto-scroll chat to bottom
  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight
  }, [messages.length])

  // Auto-show code preview
  useEffect(() => {
    if (codePreviewFiles.length > 0) {
      setShowCodePreview(true)
      addMessage('system', `SAM wrote ${codePreviewFiles[0].path.replace(/\\/g, '/').split('/').pop()}`)
    }
  }, [codePreviewFiles.length])

  // Diag overlay
  useEffect(() => {
    if (diagRunning) {
      setShowDiag(true)
      if (diagDismiss.current) clearTimeout(diagDismiss.current)
    }
  }, [diagRunning])

  const handleSend = e => {
    e.preventDefault()
    const text = input.trim()
    if (!text || !connected) return
    addMessage('ky', text)
    sendMessage(text)
    setInput('')
    inputRef.current?.focus()
  }

  const cfg       = STATE_CFG[tinaState] ?? STATE_CFG.listening
  const isOffline = tinaState === 'offline'
  const dispLabel = activeAgent ? `→ ${activeAgent.name.toUpperCase()}` : isRecording ? 'LISTENING' : cfg.label
  const dispSub   = activeAgent ? 'delegating' : isRecording ? 'recording…' : cfg.sub

  const toolPanels = panels.filter(p => p.type !== 'agent')

  const svcDots = [
    { key: 'ws', label: 'WS', ok: connected },
    { key: 'dg', label: 'DG', ok: services?.deepgram },
    { key: 'el', label: 'EL', ok: services?.elevenlabs },
    { key: 'gh', label: 'GH', ok: services?.github },
    { key: 'tv', label: 'TV', ok: services?.tavily },
  ]

  return (
    <div style={{
      height: '100vh', overflow: 'hidden',
      background: PB, display: 'flex', flexDirection: 'column',
      fontFamily: "'Courier New',monospace", color: PG,
      position: 'relative',
    }}>

      {/* Subtle grid */}
      <div style={{ position: 'absolute', inset: 0, opacity: 0.025, pointerEvents: 'none', backgroundImage: `linear-gradient(${P} 1px,transparent 1px),linear-gradient(90deg,${P} 1px,transparent 1px)`, backgroundSize: '36px 36px' }} />

      {/* Corner brackets */}
      {[
        { top: 8, left:  8, borderTop: `1px solid ${P}`, borderLeft:  `1px solid ${P}` },
        { top: 8, right: 8, borderTop: `1px solid ${P}`, borderRight: `1px solid ${P}` },
        { bottom: 8, left:  8, borderBottom: `1px solid ${P}`, borderLeft:  `1px solid ${P}` },
        { bottom: 8, right: 8, borderBottom: `1px solid ${P}`, borderRight: `1px solid ${P}` },
      ].map((s, i) => (
        <div key={i} style={{ position: 'absolute', width: 18, height: 18, opacity: isOffline ? 0.1 : 0.3, ...s }} />
      ))}

      {/* Overlays */}
      {showCodePreview && codePreviewFiles.length > 0 && (
        <CodePreviewPanel files={codePreviewFiles} onClose={() => setShowCodePreview(false)} />
      )}
      {showDiag && Object.keys(diagResults).length > 0 && (
        <DiagOverlay results={diagResults} running={diagRunning} onClose={() => setShowDiag(false)} />
      )}
      {isOffline && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, background: 'rgba(8,4,15,0.92)' }}>
          <div style={{ fontSize: 26, letterSpacing: 8, color: '#E24B4A', opacity: 0.85, animation: 'offblink 2s ease-in-out infinite' }}>TINA OFFLINE</div>
          <div style={{ fontSize: 8, letterSpacing: 3, color: '#E24B4A', opacity: 0.35 }}>START BACKEND — python tina.py</div>
        </div>
      )}

      {/* ── Header ── */}
      <div style={{ flexShrink: 0, zIndex: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 22px', borderBottom: `1px solid ${P}1f` }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {svcDots.map(({ key, label, ok }) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{
                width: 5, height: 5, borderRadius: '50%', display: 'inline-block',
                background: ok === undefined ? '#6b7280' : ok ? '#4ade80' : '#ef4444',
                boxShadow:  ok === undefined ? 'none' : ok ? '0 0 5px #4ade80' : '0 0 5px #ef4444',
              }} />
              <span style={{ fontSize: 7, letterSpacing: 1, opacity: 0.3 }}>{label}</span>
            </div>
          ))}
        </div>

        <div style={{ fontSize: 18, letterSpacing: 10, fontWeight: 'bold', color: '#fff', textShadow: `0 0 24px ${P}` }}>
          T I N A
        </div>

        <div style={{ textAlign: 'right', fontSize: 9, letterSpacing: 1, opacity: 0.4 }}>
          <div>{time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
          <div style={{ marginTop: 2, color: isRecording ? '#ef4444' : PG }}>{cfg.label}</div>
        </div>
      </div>

      {/* ── 3-column body ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', zIndex: 1 }}>

        {/* Left — conversation */}
        <div style={{ width: 270, flexShrink: 0, display: 'flex', flexDirection: 'column', borderRight: `1px solid ${P}18` }}>
          <div style={{ flexShrink: 0, padding: '7px 14px 5px', borderBottom: `1px solid ${P}12` }}>
            <span style={{ fontSize: 7, letterSpacing: 3, opacity: 0.22 }}>CONVERSATION</span>
          </div>
          <div ref={chatRef} style={{ flex: 1, overflowY: 'auto', padding: '10px 11px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {messages.map(msg => {
              if (msg.role === 'system') return (
                <div key={msg.id} style={{ textAlign: 'center', fontSize: 7, letterSpacing: 1.5, color: PG, opacity: 0.2, padding: '2px 0' }}>
                  — {msg.text} —
                </div>
              )
              if (msg.role === 'ky') return (
                <div key={msg.id} style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <div style={{
                    maxWidth: '86%', background: `${P}2a`, border: `1px solid ${P}44`,
                    borderRadius: '8px 8px 2px 8px', padding: '6px 10px',
                    fontSize: 10, lineHeight: 1.5, color: PG, letterSpacing: 0.2,
                  }}>
                    {msg.text}
                  </div>
                </div>
              )
              return (
                <div key={msg.id} style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <div style={{
                    maxWidth: '92%', background: `${PF}dd`, border: `1px solid ${P}1a`,
                    borderRadius: '8px 8px 8px 2px', padding: '6px 10px',
                    fontSize: 10, lineHeight: 1.55, color: PG, opacity: 0.82, letterSpacing: 0.2,
                  }}>
                    {msg.text}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Centre — face + controls */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '6px 18px 12px' }}>

          {/* Face */}
          <div style={{ position: 'relative', flexShrink: 0 }}>
            <TinaFace state={tinaState} size={268} />
            <div style={{ position: 'absolute', bottom: 34, left: 0, right: 0, textAlign: 'center', pointerEvents: 'none' }}>
              <div style={{ fontSize: 9, letterSpacing: 5, color: activeAgent ? activeAgent.color : PG, opacity: 0.9, transition: 'color 0.4s' }}>
                {dispLabel}
              </div>
              <div style={{ fontSize: 7, letterSpacing: 2, opacity: 0.22, marginTop: 3 }}>{dispSub}</div>
            </div>
          </div>

          {/* Input + buttons */}
          <div style={{ width: '100%', maxWidth: 310, display: 'flex', flexDirection: 'column', gap: 7, marginTop: 'auto' }}>
            <form onSubmit={handleSend} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={{ fontSize: 12, color: P, opacity: 0.6, flexShrink: 0 }}>&gt;</span>
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder={connected ? 'send a message…' : 'offline…'}
                disabled={!connected || isRecording}
                autoFocus
                style={{
                  flex: 1, background: `${PF}cc`, border: `1px solid ${P}2a`,
                  borderRadius: 3, padding: '7px 10px', color: PG,
                  fontFamily: "'Courier New',monospace", fontSize: 11, letterSpacing: 0.4,
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
                  border: `1px solid ${isRecording ? '#ef4444' : connected ? P : P + '33'}`,
                  color: isRecording ? '#ef4444' : PG,
                  animation: isRecording ? 'micpulse 0.8s ease-in-out infinite' : 'none',
                  flexShrink: 0, padding: '7px 13px',
                }}
              >
                {isRecording ? '■' : '●'}
              </button>
              <button
                type="submit"
                disabled={!connected || !input.trim() || isRecording}
                style={{ ...btnStyle(connected && !!input.trim() && !isRecording), padding: '7px 14px' }}
              >
                SEND
              </button>
            </form>

            <div style={{ display: 'flex', gap: 6 }}>
              <button
                onClick={() => { fetch('http://localhost:8000/api/diagnostics', { method: 'POST' }); setShowDiag(true) }}
                disabled={!connected || diagRunning}
                style={{ ...btnStyle(connected && !diagRunning), flex: 1 }}
              >
                {diagRunning ? '⠿ SCANNING…' : '◎ DIAGNOSTICS'}
              </button>
              <button
                onClick={() => setShowCodePreview(v => !v)}
                disabled={codePreviewFiles.length === 0}
                style={{ ...btnStyle(codePreviewFiles.length > 0), padding: '7px 13px' }}
              >
                CODE{codePreviewFiles.length > 0 ? ` (${codePreviewFiles.length})` : ''}
              </button>
            </div>
          </div>
        </div>

        {/* Right — agent grid + tool panels */}
        <div style={{ width: 270, flexShrink: 0, display: 'flex', flexDirection: 'column', borderLeft: `1px solid ${P}18`, overflow: 'hidden' }}>

          {/* Agent grid */}
          <div style={{ flexShrink: 0, padding: '7px 14px 5px', borderBottom: `1px solid ${P}12` }}>
            <span style={{ fontSize: 7, letterSpacing: 3, opacity: 0.22 }}>AGENTS</span>
          </div>
          <div style={{ flexShrink: 0, padding: '8px 10px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            {AGENTS.map(agent => (
              <AgentCard key={agent.key} agent={agent} status={agentStatuses[agent.key]} />
            ))}
          </div>

          {/* Tool panels */}
          <div style={{ flexShrink: 0, padding: '6px 14px 4px', borderTop: `1px solid ${P}12`, borderBottom: `1px solid ${P}12` }}>
            <span style={{ fontSize: 7, letterSpacing: 3, opacity: 0.22 }}>CONTEXT</span>
          </div>

          {toolPanels.length === 0 ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ fontSize: 7, letterSpacing: 2, opacity: 0.1, textAlign: 'center', lineHeight: 2 }}>
                TOOL RESULTS<br />APPEAR HERE
              </div>
            </div>
          ) : (
            <div style={{ flex: 1, overflowY: 'auto', padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {toolPanels.map(panel => (
                <ToolPanel key={panel.id} panel={panel} onDismiss={dismissPanel} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Footer ── */}
      <div style={{ flexShrink: 0, zIndex: 1, display: 'flex', justifyContent: 'space-between', padding: '5px 22px', borderTop: `1px solid ${P}18`, fontSize: 7, letterSpacing: 2, opacity: 0.28 }}>
        <span>UPTIME {uptime}</span>
        <span>EXCHANGES {turnCount}</span>
        <span>PANELS {panels.length}</span>
        <span>{connected ? 'ONLINE' : 'OFFLINE'} · SONNET 4.6</span>
      </div>

      <style>{`
        * { box-sizing: border-box; }
        body { margin: 0; overflow: hidden; }
        @keyframes offblink   { 0%,100%{opacity:0.85} 50%{opacity:0.25} }
        @keyframes micpulse   { 0%,100%{box-shadow:0 0 6px #ef4444} 50%{box-shadow:0 0 20px #ef4444} }
        @keyframes fadein     { from{opacity:0;transform:translateY(-4px)} to{opacity:1;transform:translateY(0)} }
        @keyframes agentpulse { 0%,100%{opacity:1} 50%{opacity:0.25} }
        ::-webkit-scrollbar { width: 3px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${P}44; border-radius: 2px; }
      `}</style>
    </div>
  )
}
