import { useState, useEffect, useRef, useCallback } from 'react'
import { useTina } from './hooks/useTina'
import TinaFace, { STATE_CFG } from './components/TinaFace'

// ── Palette ──────────────────────────────────────────────────────────────────
const P  = '#8B5CF6'
const PG = '#C4B5FD'
const PD = '#4C1D95'
const PF = '#1E1030'
const PB = '#08040F'

// ── HUD sub-components (from v2) ─────────────────────────────────────────────

function HUDShell({ title, persistent, ephemeral, onExpire, children }) {
  const [opacity, setOpacity] = useState(0)
  const [dying,   setDying]   = useState(false)
  useEffect(() => {
    setTimeout(() => setOpacity(1), 30)
    if (ephemeral) {
      const t1 = setTimeout(() => setDying(true),    ephemeral - 800)
      const t2 = setTimeout(() => onExpire?.(),       ephemeral)
      return () => { clearTimeout(t1); clearTimeout(t2) }
    }
  }, [])
  return (
    <div style={{
      transition: 'opacity 0.6s', opacity: dying ? 0 : opacity,
      border: `1px solid ${persistent ? P + '66' : P + '33'}`,
      background: `${PF}cc`, padding: '14px 16px', borderRadius: 4,
      fontFamily: "'Courier New', monospace", color: PG,
      boxShadow: persistent ? `0 0 20px ${P}22` : 'none',
    }}>
      <div style={{ fontSize: 10, letterSpacing: 3, opacity: 0.5, marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
        <span>{title}</span>
        {persistent && <span style={{ color: P, opacity: 0.8 }}>◆ PINNED</span>}
        {ephemeral  && <span style={{ opacity: 0.4 }}>◌ TEMP</span>}
      </div>
      {children}
    </div>
  )
}

function MiniBar({ label, value }) {
  return (
    <div style={{ marginBottom: 7 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontSize: 10, letterSpacing: 2, opacity: 0.6 }}>{label}</span>
        <span style={{ fontSize: 10 }}>{value}%</span>
      </div>
      <div style={{ height: 3, background: '#ffffff11', borderRadius: 2 }}>
        <div style={{ height: '100%', width: `${value}%`, background: `linear-gradient(90deg,${PD},${PG})`, borderRadius: 2, boxShadow: `0 0 5px ${PG}` }} />
      </div>
    </div>
  )
}

function AgentGrid({ agents }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
      {agents.map(a => (
        <div key={a.name} style={{ padding: '6px 8px', border: `1px solid ${a.active ? P + '55' : '#ffffff11'}`, borderRadius: 3, textAlign: 'center' }}>
          <div style={{ fontSize: 9, letterSpacing: 1, opacity: a.active ? 1 : 0.3 }}>{a.name}</div>
          <div style={{ fontSize: 8, marginTop: 3, color: a.active ? '#4ade80' : '#ffffff33' }}>{a.active ? '● ACTIVE' : '○ IDLE'}</div>
        </div>
      ))}
    </div>
  )
}

function ThoughtTicker({ thoughts }) {
  const [idx, setIdx] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setIdx(i => (i + 1) % thoughts.length), 2800)
    return () => clearInterval(t)
  }, [thoughts.length])
  return <div style={{ fontSize: 10, lineHeight: 1.6, opacity: 0.8, minHeight: 34, letterSpacing: 0.5 }}>{thoughts[idx]}</div>
}

function MemoryNodes({ nodes }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {nodes.map(n => (
        <div key={n} style={{ fontSize: 9, letterSpacing: 1, padding: '3px 8px', border: `1px solid ${P}44`, borderRadius: 10, opacity: 0.7 }}>{n}</div>
      ))}
    </div>
  )
}

function DataFlow({ label, bps }) {
  const [bars, setBars] = useState(Array(12).fill(0.2))
  useEffect(() => {
    const t = setInterval(() => setBars(b => [...b.slice(1), 0.15 + Math.random() * 0.85]), 200)
    return () => clearInterval(t)
  }, [])
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 34, marginBottom: 6 }}>
        {bars.map((h, i) => <div key={i} style={{ flex: 1, height: `${h * 100}%`, background: PG, opacity: 0.4 + h * 0.6, borderRadius: 1 }} />)}
      </div>
      <div style={{ fontSize: 10, opacity: 0.5, letterSpacing: 1 }}>{label} · {bps}</div>
    </div>
  )
}

function ConfidenceMeter({ value, label }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <svg width={90} height={52} viewBox="0 0 90 52">
        <path d="M 10 46 A 35 35 0 0 1 80 46" fill="none" stroke={PF} strokeWidth={5} />
        <path d="M 10 46 A 35 35 0 0 1 80 46" fill="none" stroke={PG} strokeWidth={5}
          strokeDasharray={`${(value / 100) * 110} 110`} strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 4px ${P})` }} />
        <text x="45" y="44" textAnchor="middle" fill={PG} fontSize="13" fontFamily="Courier New">{value}%</text>
      </svg>
      <div style={{ fontSize: 9, letterSpacing: 2, opacity: 0.5 }}>{label}</div>
    </div>
  )
}

function AlertBanner({ message, level }) {
  const colors = { warn: '#f59e0b', error: '#ef4444', info: PG }
  const c = colors[level] ?? PG
  return <div style={{ fontSize: 10, letterSpacing: 1, color: c, padding: '5px 0', borderLeft: `2px solid ${c}`, paddingLeft: 10 }}>{message}</div>
}

function DynamicElement({ spec, onExpire }) {
  let content = null
  switch (spec.type) {
    case 'agent_grid':    content = <AgentGrid agents={spec.agents} />; break
    case 'thought':       content = <ThoughtTicker thoughts={spec.thoughts} />; break
    case 'memory_nodes':  content = <MemoryNodes nodes={spec.nodes} />; break
    case 'data_flow':     content = <DataFlow label={spec.label} bps={spec.bps} />; break
    case 'confidence':    content = <ConfidenceMeter value={spec.value} label={spec.label} />; break
    case 'bars':          content = spec.bars?.map(b => <MiniBar key={b.label} label={b.label} value={b.value} />); break
    case 'alert':         content = <AlertBanner message={spec.message} level={spec.level} />; break
    default:              content = <div style={{ fontSize: 8, opacity: 0.5 }}>unknown: {spec.type}</div>
  }
  return (
    <HUDShell title={spec.title} persistent={spec.persistent} ephemeral={spec.ephemeral} onExpire={onExpire}>
      {content}
    </HUDShell>
  )
}

// ── Permanent HUD panels ─────────────────────────────────────────────────────

function ConnectionStatus({ connected, services }) {
  const rows = [
    { name: 'WEBSOCKET',  ok: connected },
    { name: 'DEEPGRAM',   ok: services?.deepgram },
    { name: 'ELEVENLABS', ok: services?.elevenlabs },
    { name: 'GITHUB',     ok: services?.github },
    { name: 'TAVILY',     ok: services?.tavily },
    { name: 'WEATHER',    ok: services?.weather },
  ]
  return (
    <div style={{ border: `1px solid ${P}55`, borderRadius: 4, padding: '10px 14px', background: `${PF}cc`, flexShrink: 0 }}>
      <div style={{ fontSize: 9, letterSpacing: 3, opacity: 0.65, marginBottom: 8 }}>CONNECTION STATUS</div>
      {rows.map(({ name, ok }) => (
        <div key={name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
          <span style={{ fontSize: 10, letterSpacing: 1, opacity: 0.7 }}>{name}</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 9, letterSpacing: 1 }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%', display: 'inline-block',
              background: ok === undefined ? '#6b7280' : ok ? '#4ade80' : '#ef4444',
              boxShadow: ok === undefined ? 'none' : ok ? '0 0 6px #4ade80' : '0 0 6px #ef4444',
            }} />
            <span style={{ opacity: 0.5 }}>{ok === undefined ? 'UNKNOWN' : ok ? 'ONLINE' : 'OFFLINE'}</span>
          </span>
        </div>
      ))}
    </div>
  )
}

function AgentStatus({ agentStatuses, tinaState }) {
  const agents = [
    { key: 'tina',     label: 'TINA CORE' },
    { key: 'research', label: 'RESEARCH'  },
    { key: 'coding',   label: 'SAM'       },
  ]
  const tinaStatusMap = { listening: 'READY', thinking: 'PROCESSING', speaking: 'RESPONDING', standby: 'STANDBY', offline: 'OFFLINE' }

  return (
    <div style={{ border: `1px solid ${P}55`, borderRadius: 4, padding: '10px 14px', background: `${PF}cc`, flexShrink: 0 }}>
      <div style={{ fontSize: 9, letterSpacing: 3, opacity: 0.65, marginBottom: 8 }}>AGENT STATUS</div>
      {agents.map(({ key, label }) => {
        const ag         = agentStatuses[key]
        const isCore     = key === 'tina'
        const isRunning  = ag.status === 'running'  // background task in progress
        const active     = isCore ? tinaState !== 'offline' && tinaState !== 'standby' : ag.status === 'active' || isRunning
        const status     = isCore ? (tinaStatusMap[tinaState] ?? tinaState.toUpperCase()) : ag.status.toUpperCase()
        const tool       = ag.tool

        return (
          <div key={key} style={{ marginBottom: 8, paddingBottom: 8, borderBottom: `1px solid ${P}11` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: tool ? 4 : 0 }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  width: 5, height: 5, borderRadius: '50%', display: 'inline-block',
                  background: isRunning ? ag.glow : ag.color,
                  boxShadow: active ? `0 0 8px ${ag.glow}` : 'none',
                  opacity: active ? 1 : 0.3,
                  // background agents get a faster pulse to distinguish from blocking active
                  animation: active ? (isRunning ? 'agentpulse 0.9s ease-in-out infinite' : 'agentpulse 2s ease-in-out infinite') : 'none',
                }} />
                <span style={{ fontSize: 10, letterSpacing: 1, color: active ? ag.color : PG, opacity: active ? 1 : 0.4 }}>
                  {label}
                </span>
              </span>
              <span style={{ fontSize: 9, letterSpacing: 1, opacity: 0.45, color: isRunning ? ag.glow : undefined }}>{status}</span>
            </div>
            {tool && (
              <div style={{
                fontSize: 9, letterSpacing: 1, color: ag.color, opacity: 0.8,
                paddingLeft: 11, animation: 'fadein 0.2s ease',
              }}>
                ↳ {tool}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function SessionStats({ turnCount, sessionStart }) {
  const [uptime, setUptime] = useState('00:00:00')
  useEffect(() => {
    const t = setInterval(() => {
      const ms = Date.now() - sessionStart
      const h  = Math.floor(ms / 3600000)
      const m  = Math.floor((ms % 3600000) / 60000)
      const s  = Math.floor((ms % 60000) / 1000)
      setUptime(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`)
    }, 1000)
    return () => clearInterval(t)
  }, [sessionStart])

  return (
    <div style={{ border: `1px solid ${P}55`, borderRadius: 4, padding: '10px 14px', background: `${PF}cc`, flexShrink: 0 }}>
      <div style={{ fontSize: 9, letterSpacing: 3, opacity: 0.65, marginBottom: 8 }}>SESSION</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
        <span style={{ fontSize: 10, letterSpacing: 1, opacity: 0.6 }}>UPTIME</span>
        <span style={{ fontSize: 10, letterSpacing: 1, color: PG }}>{uptime}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 10, letterSpacing: 1, opacity: 0.6 }}>EXCHANGES</span>
        <span style={{ fontSize: 10, letterSpacing: 1, color: PG }}>{turnCount}</span>
      </div>
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────────────

let _eid = 0
const ts = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

// ── App ───────────────────────────────────────────────────────────────────────

function DiagOverlay({ results, running, onClose }) {
  const checks = Object.entries(results)
  const total  = checks.length
  const done   = checks.filter(([, r]) => r.status !== 'running').length
  const passed = checks.filter(([, r]) => r.status === 'pass').length
  const failed = checks.filter(([, r]) => r.status === 'fail').length
  const warned = checks.filter(([, r]) => r.status === 'warn').length

  const dot = status => {
    if (status === 'running') return { bg: '#6b7280', anim: 'agentpulse 0.8s ease-in-out infinite' }
    if (status === 'pass')    return { bg: '#4ade80', anim: 'none' }
    if (status === 'fail')    return { bg: '#ef4444', anim: 'none' }
    if (status === 'warn')    return { bg: '#f59e0b', anim: 'none' }
    return { bg: '#ffffff22', anim: 'none' }
  }

  return (
    <div style={{
      position: 'absolute', inset: 0, zIndex: 30,
      background: 'rgba(8,4,15,0.92)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        width: 560, maxHeight: '80vh', display: 'flex', flexDirection: 'column',
        border: `1px solid ${P}66`, borderRadius: 6,
        background: `${PF}ee`, boxShadow: `0 0 40px ${P}33`,
        fontFamily: "'Courier New', monospace",
      }}>
        {/* Header */}
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

        {/* Progress bar */}
        <div style={{ height: 2, background: '#ffffff11' }}>
          <div style={{
            height: '100%',
            width: total ? `${(done / total) * 100}%` : '0%',
            background: failed > 0 ? '#ef4444' : warned > 0 ? '#f59e0b' : `linear-gradient(90deg,${PD},${PG})`,
            transition: 'width 0.3s ease',
            boxShadow: `0 0 6px ${PG}`,
          }} />
        </div>

        {/* Check list */}
        <div style={{ overflowY: 'auto', padding: '10px 0' }}>
          {checks.map(([id, result]) => {
            const d = dot(result.status)
            return (
              <div key={id} style={{
                display: 'flex', alignItems: 'flex-start', gap: 12,
                padding: '7px 20px',
                borderBottom: `1px solid ${P}11`,
                animation: result.status !== 'running' ? 'fadein 0.2s ease' : 'none',
              }}>
                <span style={{
                  flexShrink: 0, marginTop: 2,
                  width: 7, height: 7, borderRadius: '50%',
                  background: d.bg, display: 'inline-block',
                  boxShadow: result.status !== 'running' ? `0 0 6px ${d.bg}` : 'none',
                  animation: d.anim,
                }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 10, letterSpacing: 2, opacity: result.status === 'running' ? 0.5 : 0.9 }}>
                      {result.label || id.toUpperCase()}
                    </span>
                    <span style={{
                      fontSize: 9, letterSpacing: 1,
                      color: d.bg,
                      opacity: result.status === 'running' ? 0.4 : 0.9,
                    }}>
                      {result.status === 'running' ? '...' : result.status.toUpperCase()}
                    </span>
                  </div>
                  {result.detail && result.status !== 'running' && (
                    <div style={{ fontSize: 9, letterSpacing: 0.5, opacity: 0.45, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {result.detail}
                    </div>
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

export default function App() {
  const { connected, tinaState, isRecording, activeAgent, conversation, lastResponse, services, turnCount, sessionStart, agentStatuses, diagRunning, diagResults, sendMessage, startRecording, stopRecording } = useTina()

  const [elements,       setElements]       = useState([])
  const [loading,        setLoading]        = useState(false)
  const [log,            setLog]            = useState(['System initialised', 'Neural core loading...'])
  const [input,          setInput]          = useState('')
  const [time,           setTime]           = useState(new Date())
  const [showResponse,   setShowResponse]   = useState(false)
  const [showDiag,       setShowDiag]       = useState(false)
  const inputRef        = useRef(null)
  const convoLen        = useRef(0)
  const prevConn        = useRef(false)
  const responseDismiss = useRef(null)
  const diagDismiss     = useRef(null)

  // Show response box as soon as text arrives — no timer yet
  useEffect(() => {
    if (lastResponse) {
      setShowResponse(true)
      if (responseDismiss.current) clearTimeout(responseDismiss.current)
    } else {
      setShowResponse(false)
      if (responseDismiss.current) clearTimeout(responseDismiss.current)
    }
  }, [lastResponse])

  // Start 10s dismiss countdowns only after Tina finishes speaking
  useEffect(() => {
    if (tinaState === 'listening') {
      if (lastResponse) {
        if (responseDismiss.current) clearTimeout(responseDismiss.current)
        responseDismiss.current = setTimeout(() => setShowResponse(false), 10000)
      }
      if (showDiag && !diagRunning) {
        if (diagDismiss.current) clearTimeout(diagDismiss.current)
        diagDismiss.current = setTimeout(() => setShowDiag(false), 10000)
      }
    }
  }, [tinaState])

  // Auto-show diag overlay when running; cancel any pending close timer
  useEffect(() => {
    if (diagRunning) {
      setShowDiag(true)
      if (diagDismiss.current) clearTimeout(diagDismiss.current)
    }
  }, [diagRunning])

  // Clock
  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const addLog = useCallback(msg => {
    setLog(l => [`${ts()} ${msg}`, ...l].slice(0, 8))
  }, [])

  // Log new conversation turns
  useEffect(() => {
    if (conversation.length > convoLen.current) {
      const latest = conversation[conversation.length - 1]
      const who    = latest.role === 'tina' ? 'TINA' : 'KAI'
      const text   = latest.text.length > 52 ? latest.text.slice(0, 52) + '…' : latest.text
      addLog(`${who}: ${text}`)
    }
    convoLen.current = conversation.length
  }, [conversation, addLog])

  // Log connection changes
  useEffect(() => {
    if (connected  && !prevConn.current) addLog('Neural link established')
    if (!connected &&  prevConn.current) addLog('Connection lost — reconnecting...')
    prevConn.current = connected
  }, [connected, addLog])

  // SPAWN HUD — routes through backend so API key stays server-side
  const spawnHud = async () => {
    setLoading(true)
    addLog('Generating HUD elements...')
    try {
      const res   = await fetch('http://localhost:8000/api/spawn-hud', { method: 'POST' })
      const specs = await res.json()
      const fresh = specs.map(s => ({ ...s, id: `el-${_eid++}` }))
      setElements(prev => [...prev.filter(e => e.persistent), ...fresh])
      addLog(`Spawned ${fresh.length} elements (${fresh.filter(e => e.persistent).length} pinned)`)
    } catch {
      addLog('HUD generation failed')
    }
    setLoading(false)
  }

  const removeElement = useCallback(id => setElements(els => els.filter(e => e.id !== id)), [])
  const left  = elements.filter((_, i) => i % 2 === 0)
  const right = elements.filter((_, i) => i % 2 === 1)

  const handleSend = e => {
    e.preventDefault()
    const text = input.trim()
    if (!text || !connected) return
    sendMessage(text)
    setInput('')
    inputRef.current?.focus()
  }

  const cfg       = STATE_CFG[tinaState] ?? STATE_CFG.listening
  const isOffline = tinaState === 'offline'
  const dispLabel = activeAgent ? `→ ${activeAgent.name.toUpperCase()}` : isRecording ? 'LISTENING' : cfg.label
  const dispSub   = activeAgent ? 'delegating to specialist' : isRecording ? 'Recording...' : cfg.sub

  return (
    <div style={{
      height: '100vh', overflow: 'hidden',
      background: PB, display: 'flex', flexDirection: 'column',
      fontFamily: "'Courier New',monospace", color: PG,
      position: 'relative',
    }}>

      {/* Grid background */}
      <div style={{
        position: 'absolute', inset: 0, opacity: 0.06, pointerEvents: 'none',
        backgroundImage: `linear-gradient(${P} 1px,transparent 1px),linear-gradient(90deg,${P} 1px,transparent 1px)`,
        backgroundSize: '40px 40px',
      }} />

      {/* Corner brackets */}
      {[
        { top: 10, left:  10, borderTop: `1px solid ${P}`, borderLeft:  `1px solid ${P}` },
        { top: 10, right: 10, borderTop: `1px solid ${P}`, borderRight: `1px solid ${P}` },
        { bottom: 10, left:  10, borderBottom: `1px solid ${P}`, borderLeft:  `1px solid ${P}` },
        { bottom: 10, right: 10, borderBottom: `1px solid ${P}`, borderRight: `1px solid ${P}` },
      ].map((s, i) => (
        <div key={i} style={{ position: 'absolute', width: 22, height: 22, opacity: isOffline ? 0.2 : 0.5, ...s }} />
      ))}

      {/* Diagnostic overlay */}
      {showDiag && Object.keys(diagResults).length > 0 && (
        <DiagOverlay
          results={diagResults}
          running={diagRunning}
          onClose={() => setShowDiag(false)}
        />
      )}

      {/* Offline overlay */}
      {isOffline && (
        <div style={{
          position: 'absolute', inset: 0, zIndex: 20, display: 'flex',
          alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12,
          background: 'rgba(8,4,15,0.88)',
        }}>
          <div style={{ fontSize: 28, letterSpacing: 8, color: '#E24B4A', opacity: 0.8, animation: 'offblink 2s ease-in-out infinite' }}>
            TINA OFFLINE
          </div>
          <div style={{ fontSize: 9, letterSpacing: 3, color: '#E24B4A', opacity: 0.4 }}>
            START BACKEND — python start.py
          </div>
        </div>
      )}

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div style={{
        flexShrink: 0, zIndex: 1,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 28px', borderBottom: `1px solid ${P}44`,
      }}>
        <div style={{ flex: 1, fontSize: 9, letterSpacing: 3, opacity: 0.55 }}>
          NEURAL CORE v2.0 · CLAUDE SONNET 4.6
        </div>
        <div style={{ fontSize: 22, letterSpacing: 10, fontWeight: 'bold', color: '#fff', textShadow: `0 0 24px ${P}`, textAlign: 'center' }}>
          T I N A
        </div>
        <div style={{ flex: 1, textAlign: 'right', fontSize: 9, letterSpacing: 2, opacity: 0.55 }}>
          <div>{time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
          <div style={{ marginTop: 2 }}>{connected ? 'WS ACTIVE' : 'CONNECTING...'}</div>
        </div>
      </div>

      {/* ── Main 3-column body ──────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', gap: 12, padding: '12px 16px', zIndex: 1 }}>

        {/* Left column — activity log + HUD elements */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10, overflow: 'hidden', minWidth: 200 }}>

          {/* Activity log — permanent */}
          <div style={{ flexShrink: 0, border: `1px solid ${P}22`, borderRadius: 4, padding: '10px 14px', background: `${PF}cc` }}>
            <div style={{ fontSize: 9, letterSpacing: 3, opacity: 0.65, marginBottom: 8 }}>ACTIVITY LOG</div>
            {log.map((l, i) => (
              <div key={i} style={{ fontSize: 10, letterSpacing: 0.3, opacity: Math.max(0.35, 1 - i * 0.09), marginBottom: 3, color: i === 0 ? PG : PG + '88', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {l}
              </div>
            ))}
          </div>

          {/* Dynamic HUD left */}
          {left.map(el => (
            <DynamicElement key={el.id} spec={el} onExpire={() => removeElement(el.id)} />
          ))}
          {left.length === 0 && (
            <div style={{ flex: 1, border: `1px dashed ${P}10`, borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.1, fontSize: 10, letterSpacing: 2 }}>
              HUD ZONE A
            </div>
          )}
        </div>

        {/* Centre column — face + controls */}
        <div style={{ flexShrink: 0, width: 380, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, overflow: 'hidden' }}>

          {/* Face */}
          <div style={{ position: 'relative', flexShrink: 0 }}>
            <TinaFace state={tinaState} size={340} />
            <div style={{ position: 'absolute', bottom: 50, left: 0, right: 0, textAlign: 'center', pointerEvents: 'none' }}>
              <div style={{ fontSize: 11, letterSpacing: 5, color: activeAgent ? activeAgent.color : PG, opacity: 0.9, transition: 'color 0.4s' }}>{dispLabel}</div>
              <div style={{ fontSize: 9, letterSpacing: 2, opacity: 0.35, marginTop: 2 }}>{dispSub}</div>
            </div>
          </div>

          {/* Active agent panel */}
          <div style={{
            width: '100%', overflow: 'hidden', flexShrink: 0,
            maxHeight: activeAgent ? 80 : 0,
            opacity: activeAgent ? 1 : 0,
            transition: 'max-height 0.4s ease, opacity 0.3s ease',
          }}>
            {activeAgent && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 12,
                border: `1px solid ${activeAgent.color}44`,
                borderRadius: 4, padding: '8px 14px',
                background: `${PF}cc`,
                boxShadow: `0 0 20px ${activeAgent.color}22`,
              }}>
                <TinaFace state="thinking" size={60} ringColor={activeAgent.glow} glowColor={activeAgent.color} />
                <div>
                  <div style={{ fontSize: 10, letterSpacing: 3, color: activeAgent.color, marginBottom: 3 }}>
                    {activeAgent.name.toUpperCase()} AGENT
                  </div>
                  <div style={{ fontSize: 9, letterSpacing: 1, color: activeAgent.color, opacity: 0.5, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ animation: 'micpulse 1s ease-in-out infinite', display: 'inline-block', width: 5, height: 5, borderRadius: '50%', background: activeAgent.color }} />
                    ACTIVE
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Input + controls */}
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 7, flexShrink: 0, marginTop: 'auto' }}>
            <form onSubmit={handleSend} style={{ display: 'flex', gap: 6 }}>
              <span style={{ fontSize: 13, color: P, opacity: 0.7, alignSelf: 'center', flexShrink: 0 }}>&gt;</span>
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder={connected ? 'send a message...' : 'offline...'}
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
              <button onClick={spawnHud} disabled={loading || !connected} style={{ ...btnStyle(connected && !loading), flex: 1 }}>
                {loading ? 'THINKING...' : '✦ SPAWN HUD'}
              </button>
              <button
                onClick={() => { fetch('http://localhost:8000/api/diagnostics', { method: 'POST' }); addLog('Diagnostics started') }}
                disabled={!connected || diagRunning}
                style={btnStyle(connected && !diagRunning)}
              >
                {diagRunning ? '...' : 'DIAG'}
              </button>
              <button onClick={() => { setElements(e => e.filter(x => x.persistent)); addLog('Ephemeral cleared') }} style={btnStyle(true, true)}>
                CLEAR
              </button>
              <button onClick={() => { setElements([]); addLog('HUD reset') }} style={btnStyle(false, true)}>
                RESET
              </button>
            </div>
          </div>
        </div>

        {/* Right column — status panels + response box + HUD elements */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10, overflow: 'hidden', minWidth: 200 }}>

          <ConnectionStatus connected={connected} services={services} />
          <AgentStatus agentStatuses={agentStatuses} tinaState={tinaState} />
          <SessionStats turnCount={turnCount} sessionStart={sessionStart} />

          {/* Response text box */}
          {showResponse && lastResponse && (
            <div style={{
              flexShrink: 0,
              border: `1px solid ${P}55`,
              borderRadius: 4,
              padding: '12px 14px',
              background: `${PF}cc`,
              boxShadow: `0 0 20px ${P}22`,
              animation: 'fadein 0.4s ease',
              maxHeight: '45%',
              overflow: 'hidden',
            }}>
              <div style={{ fontSize: 9, letterSpacing: 3, opacity: 0.5, marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
                <span>TINA RESPONSE</span>
                <span style={{ color: P, opacity: 0.8 }}>◆ LIVE</span>
              </div>
              <div style={{ fontSize: 11, lineHeight: 1.7, letterSpacing: 0.3, color: PG, opacity: 0.9, whiteSpace: 'pre-wrap', overflow: 'hidden' }}>
                {lastResponse}
              </div>
            </div>
          )}

          {/* Dynamic HUD right */}
          {right.map(el => (
            <DynamicElement key={el.id} spec={el} onExpire={() => removeElement(el.id)} />
          ))}
          {right.length === 0 && !lastResponse && (
            <div style={{ flex: 1, border: `1px dashed ${P}10`, borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.1, fontSize: 10, letterSpacing: 2 }}>
              HUD ZONE B
            </div>
          )}
        </div>
      </div>

      {/* ── Footer status bar ───────────────────────────────────────────────── */}
      <div style={{
        flexShrink: 0, zIndex: 1,
        display: 'flex', justifyContent: 'space-between',
        padding: '6px 28px', borderTop: `1px solid ${P}44`,
        fontSize: 9, letterSpacing: 2, opacity: 0.45,
      }}>
        <span>WS: {connected ? 'CONNECTED' : 'OFFLINE'}</span>
        <span>STATE: {cfg.label}</span>
        <span>ELEMENTS: {elements.length} ({elements.filter(e => e.persistent).length} PINNED)</span>
        <span>DEEPGRAM · ELEVENLABS · TAVILY · GITHUB</span>
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
