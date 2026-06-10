import { useState, useEffect, useRef, useCallback } from 'react'
import { useTina } from './hooks/useTina'
import TinaFace, { STATE_CFG } from './components/TinaFace'

// ── Palette ──────────────────────────────────────────────────────────────────
const P  = '#8B5CF6'
const PG = '#A78BFA'
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
      background: `${PF}cc`, padding: '10px 12px', borderRadius: 3,
      fontFamily: "'Courier New', monospace", color: PG,
      boxShadow: persistent ? `0 0 16px ${P}22` : 'none',
    }}>
      <div style={{ fontSize: 8, letterSpacing: 3, opacity: 0.5, marginBottom: 6, display: 'flex', justifyContent: 'space-between' }}>
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
    <div style={{ marginBottom: 5 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
        <span style={{ fontSize: 8, letterSpacing: 2, opacity: 0.6 }}>{label}</span>
        <span style={{ fontSize: 8 }}>{value}%</span>
      </div>
      <div style={{ height: 1.5, background: '#ffffff11', borderRadius: 1 }}>
        <div style={{ height: '100%', width: `${value}%`, background: `linear-gradient(90deg,${PD},${PG})`, borderRadius: 1, boxShadow: `0 0 4px ${PG}` }} />
      </div>
    </div>
  )
}

function AgentGrid({ agents }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
      {agents.map(a => (
        <div key={a.name} style={{ padding: '4px 6px', border: `1px solid ${a.active ? P + '55' : '#ffffff11'}`, borderRadius: 2, textAlign: 'center' }}>
          <div style={{ fontSize: 7, letterSpacing: 1, opacity: a.active ? 1 : 0.3 }}>{a.name}</div>
          <div style={{ fontSize: 6, marginTop: 2, color: a.active ? '#4ade80' : '#ffffff33' }}>{a.active ? '● ACTIVE' : '○ IDLE'}</div>
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
  return <div style={{ fontSize: 8, lineHeight: 1.6, opacity: 0.8, minHeight: 28, letterSpacing: 0.5 }}>{thoughts[idx]}</div>
}

function MemoryNodes({ nodes }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {nodes.map(n => (
        <div key={n} style={{ fontSize: 7, letterSpacing: 1, padding: '2px 6px', border: `1px solid ${P}44`, borderRadius: 10, opacity: 0.7 }}>{n}</div>
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
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 24, marginBottom: 4 }}>
        {bars.map((h, i) => <div key={i} style={{ flex: 1, height: `${h * 100}%`, background: PG, opacity: 0.4 + h * 0.6, borderRadius: 1 }} />)}
      </div>
      <div style={{ fontSize: 8, opacity: 0.5, letterSpacing: 1 }}>{label} · {bps}</div>
    </div>
  )
}

function ConfidenceMeter({ value, label }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <svg width={70} height={40} viewBox="0 0 70 40">
        <path d="M 10 35 A 25 25 0 0 1 60 35" fill="none" stroke={PF} strokeWidth={4} />
        <path d="M 10 35 A 25 25 0 0 1 60 35" fill="none" stroke={PG} strokeWidth={4}
          strokeDasharray={`${(value / 100) * 78.5} 78.5`} strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 3px ${P})` }} />
        <text x="35" y="34" textAnchor="middle" fill={PG} fontSize="10" fontFamily="Courier New">{value}%</text>
      </svg>
      <div style={{ fontSize: 7, letterSpacing: 2, opacity: 0.5 }}>{label}</div>
    </div>
  )
}

function AlertBanner({ message, level }) {
  const colors = { warn: '#f59e0b', error: '#ef4444', info: PG }
  const c = colors[level] ?? PG
  return <div style={{ fontSize: 8, letterSpacing: 1, color: c, padding: '4px 0', borderLeft: `2px solid ${c}`, paddingLeft: 8 }}>{message}</div>
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

// ── Helpers ──────────────────────────────────────────────────────────────────

let _eid = 0
const ts = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const { connected, tinaState, conversation, sendMessage } = useTina()

  const [elements, setElements] = useState([])
  const [loading,  setLoading]  = useState(false)
  const [log,      setLog]      = useState(['System initialised', 'Neural core loading...'])
  const [input,    setInput]    = useState('')
  const [time,     setTime]     = useState(new Date())
  const inputRef   = useRef(null)
  const convoLen   = useRef(0)
  const prevConn   = useRef(false)

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

  const cfg      = STATE_CFG[tinaState] ?? STATE_CFG.listening
  const isOffline = tinaState === 'offline'

  return (
    <div style={{
      minHeight: '100vh', background: PB, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      fontFamily: "'Courier New',monospace", color: PG,
      padding: '12px 16px', position: 'relative', overflow: 'hidden',
    }}>

      {/* Grid background */}
      <div style={{
        position: 'absolute', inset: 0, opacity: 0.04,
        backgroundImage: `linear-gradient(${P} 1px,transparent 1px),linear-gradient(90deg,${P} 1px,transparent 1px)`,
        backgroundSize: '40px 40px',
      }} />

      {/* Corner brackets */}
      {[
        { top: 14, left:  14, borderTop:    `1px solid ${P}`, borderLeft:   `1px solid ${P}` },
        { top: 14, right: 14, borderTop:    `1px solid ${P}`, borderRight:  `1px solid ${P}` },
        { bottom: 14, left:  14, borderBottom: `1px solid ${P}`, borderLeft:   `1px solid ${P}` },
        { bottom: 14, right: 14, borderBottom: `1px solid ${P}`, borderRight:  `1px solid ${P}` },
      ].map((s, i) => (
        <div key={i} style={{ position: 'absolute', width: 18, height: 18, opacity: isOffline ? 0.15 : 0.4, ...s }} />
      ))}

      {/* Clock */}
      <div style={{ position: 'absolute', top: 18, right: 32, textAlign: 'right', opacity: 0.3, fontSize: 9, letterSpacing: 2 }}>
        <div>{time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
        <div style={{ fontSize: 7, marginTop: 2 }}>{time.toLocaleDateString([], { weekday: 'short', day: '2-digit', month: 'short' })}</div>
      </div>

      {/* Offline overlay */}
      {isOffline && (
        <div style={{
          position: 'absolute', inset: 0, zIndex: 20, display: 'flex',
          alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12,
          background: 'rgba(8,4,15,0.85)',
        }}>
          <div style={{ fontSize: 28, letterSpacing: 8, color: '#E24B4A', opacity: 0.8, animation: 'offblink 2s ease-in-out infinite' }}>
            TINA OFFLINE
          </div>
          <div style={{ fontSize: 9, letterSpacing: 3, color: '#E24B4A', opacity: 0.4 }}>
            START BACKEND — uvicorn backend.main:app --port 8000
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: 4, zIndex: 1 }}>
        <div style={{ fontSize: 9, letterSpacing: 6, opacity: 0.35, marginBottom: 2 }}>NEURAL CORE v2.0 · CLAUDE SONNET 4.6</div>
        <div style={{ fontSize: 18, letterSpacing: 8, fontWeight: 'bold', color: '#fff', textShadow: `0 0 20px ${P}` }}>T I N A</div>
        <div style={{ fontSize: 7, letterSpacing: 4, opacity: 0.3, marginTop: 1 }}>
          {connected ? 'WEBSOCKET ACTIVE' : 'CONNECTING...'}
        </div>
      </div>

      {/* Main body */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', zIndex: 1, width: '100%', maxWidth: 960 }}>

        {/* Left column — dynamic HUD elements */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8, minWidth: 175 }}>
          {left.map(el => (
            <DynamicElement key={el.id} spec={el} onExpire={() => removeElement(el.id)} />
          ))}
          {left.length === 0 && (
            <div style={{ border: `1px dashed ${P}18`, borderRadius: 3, padding: 24, textAlign: 'center', opacity: 0.12, fontSize: 8, letterSpacing: 2 }}>
              HUD ZONE A
            </div>
          )}
        </div>

        {/* Centre */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>

          {/* Face + state label */}
          <div style={{ position: 'relative' }}>
            <TinaFace state={tinaState} />
            <div style={{ position: 'absolute', bottom: 48, left: 0, right: 0, textAlign: 'center', pointerEvents: 'none' }}>
              <div style={{ fontSize: 9, letterSpacing: 4, color: PG, opacity: 0.9 }}>{cfg.label}</div>
              <div style={{ fontSize: 7, letterSpacing: 2, opacity: 0.35, marginTop: 2 }}>{cfg.sub}</div>
            </div>
          </div>

          {/* Activity log */}
          <div style={{ width: '100%', border: `1px solid ${P}22`, borderRadius: 3, padding: '7px 10px', background: `${PF}88` }}>
            <div style={{ fontSize: 7, letterSpacing: 3, opacity: 0.4, marginBottom: 4 }}>ACTIVITY LOG</div>
            {log.map((l, i) => (
              <div key={i} style={{ fontSize: 7, letterSpacing: 0.3, opacity: 1 - i * 0.11, marginBottom: 1, color: i === 0 ? PG : PG + '88' }}>
                {l}
              </div>
            ))}
          </div>

          {/* Input + controls */}
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 5 }}>
            <form onSubmit={handleSend} style={{ display: 'flex', gap: 5 }}>
              <span style={{ fontSize: 11, color: P, opacity: 0.7, alignSelf: 'center', flexShrink: 0 }}>&gt;</span>
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder={connected ? 'send a message...' : 'offline...'}
                disabled={!connected}
                autoFocus
                style={{
                  flex: 1, background: `${PF}99`, border: `1px solid ${P}33`,
                  borderRadius: 2, padding: '5px 8px', color: PG,
                  fontFamily: "'Courier New',monospace", fontSize: 11, letterSpacing: 1,
                  outline: 'none',
                }}
              />
              <button type="submit" disabled={!connected || !input.trim()} style={btnStyle(connected && input.trim())}>
                SEND
              </button>
            </form>

            <div style={{ display: 'flex', gap: 5 }}>
              <button onClick={spawnHud} disabled={loading || !connected} style={{
                ...btnStyle(connected && !loading), flex: 1,
                boxShadow: connected && !loading ? `0 0 10px ${P}33` : 'none',
              }}>
                {loading ? 'THINKING...' : '✦ SPAWN HUD'}
              </button>
              <button onClick={() => { setElements(e => e.filter(x => x.persistent)); addLog('Ephemeral cleared') }} style={btnStyle(true, true)}>
                CLEAR TEMP
              </button>
              <button onClick={() => { setElements([]); addLog('HUD reset') }} style={btnStyle(false, true)}>
                RESET
              </button>
            </div>
          </div>
        </div>

        {/* Right column — dynamic HUD elements */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8, minWidth: 175 }}>
          {right.map(el => (
            <DynamicElement key={el.id} spec={el} onExpire={() => removeElement(el.id)} />
          ))}
          {right.length === 0 && (
            <div style={{ border: `1px dashed ${P}18`, borderRadius: 3, padding: 24, textAlign: 'center', opacity: 0.12, fontSize: 8, letterSpacing: 2 }}>
              HUD ZONE B
            </div>
          )}
        </div>
      </div>

      {/* Footer status bar */}
      <div style={{
        position: 'absolute', bottom: 14, left: 32, right: 32,
        display: 'flex', justifyContent: 'space-between',
        fontSize: 7, letterSpacing: 2, opacity: 0.2,
      }}>
        <span>WS: {connected ? 'CONNECTED' : 'OFFLINE'}</span>
        <span>STATE: {cfg.label}</span>
        <span>ELEMENTS: {elements.length} ({elements.filter(e => e.persistent).length} PINNED)</span>
        <span>DEEPGRAM · ELEVENLABS · TAVILY</span>
      </div>

      <style>{`@keyframes offblink{0%,100%{opacity:0.8}50%{opacity:0.3}}`}</style>
    </div>
  )
}

function btnStyle(active, dim = false) {
  return {
    padding: '5px 12px', fontSize: 8, letterSpacing: 2,
    background: active ? `${P}33` : 'transparent',
    border: `1px solid ${active ? P : P + '33'}`,
    color: active ? PG : dim ? PG + '44' : PG + '66',
    borderRadius: 2, cursor: active ? 'pointer' : 'not-allowed',
    textTransform: 'uppercase', transition: 'all 0.2s',
    fontFamily: "'Courier New',monospace",
  }
}
