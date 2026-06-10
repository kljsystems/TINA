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

// ── Helpers ──────────────────────────────────────────────────────────────────

let _eid = 0
const ts = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const { connected, tinaState, isRecording, activeAgent, conversation, lastResponse, sendMessage, startRecording, stopRecording } = useTina()

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

  const cfg       = STATE_CFG[tinaState] ?? STATE_CFG.listening
  const isOffline = tinaState === 'offline'
  const dispLabel = activeAgent ? `→ ${activeAgent.name.toUpperCase()}` : cfg.label
  const dispSub   = activeAgent ? 'delegating to specialist' : cfg.sub

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
        { top: 18, left:  18, borderTop:    `1px solid ${P}`, borderLeft:   `1px solid ${P}` },
        { top: 18, right: 18, borderTop:    `1px solid ${P}`, borderRight:  `1px solid ${P}` },
        { bottom: 18, left:  18, borderBottom: `1px solid ${P}`, borderLeft:   `1px solid ${P}` },
        { bottom: 18, right: 18, borderBottom: `1px solid ${P}`, borderRight:  `1px solid ${P}` },
      ].map((s, i) => (
        <div key={i} style={{ position: 'absolute', width: 26, height: 26, opacity: isOffline ? 0.15 : 0.4, ...s }} />
      ))}

      {/* Clock */}
      <div style={{ position: 'absolute', top: 22, right: 38, textAlign: 'right', opacity: 0.3, fontSize: 11, letterSpacing: 2 }}>
        <div>{time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
        <div style={{ fontSize: 9, marginTop: 3 }}>{time.toLocaleDateString([], { weekday: 'short', day: '2-digit', month: 'short' })}</div>
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
      <div style={{ textAlign: 'center', marginBottom: 10, zIndex: 1 }}>
        <div style={{ fontSize: 11, letterSpacing: 6, opacity: 0.35, marginBottom: 4 }}>NEURAL CORE v2.0 · CLAUDE SONNET 4.6</div>
        <div style={{ fontSize: 28, letterSpacing: 12, fontWeight: 'bold', color: '#fff', textShadow: `0 0 30px ${P}` }}>T I N A</div>
        <div style={{ fontSize: 9, letterSpacing: 4, opacity: 0.3, marginTop: 3 }}>
          {connected ? 'WEBSOCKET ACTIVE' : 'CONNECTING...'}
        </div>
      </div>

      {/* Main body */}
      <div style={{ display: 'flex', gap: 18, alignItems: 'flex-start', zIndex: 1, width: '100%', maxWidth: 1300 }}>

        {/* Left column — dynamic HUD elements */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10, minWidth: 240 }}>
          {left.map(el => (
            <DynamicElement key={el.id} spec={el} onExpire={() => removeElement(el.id)} />
          ))}
          {left.length === 0 && (
            <div style={{ border: `1px dashed ${P}18`, borderRadius: 4, padding: 32, textAlign: 'center', opacity: 0.12, fontSize: 10, letterSpacing: 2 }}>
              HUD ZONE A
            </div>
          )}
        </div>

        {/* Centre */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>

          {/* Face + state label */}
          <div style={{ position: 'relative' }}>
            <TinaFace state={tinaState} />
            <div style={{ position: 'absolute', bottom: 58, left: 0, right: 0, textAlign: 'center', pointerEvents: 'none' }}>
              <div style={{ fontSize: 12, letterSpacing: 5, color: activeAgent ? activeAgent.color : PG, opacity: 0.9, transition: 'color 0.4s' }}>{dispLabel}</div>
              <div style={{ fontSize: 9, letterSpacing: 2, opacity: 0.35, marginTop: 3 }}>{dispSub}</div>
            </div>
          </div>

          {/* Active agent panel */}
          <div style={{
            width: '100%', overflow: 'hidden',
            maxHeight: activeAgent ? 100 : 0,
            opacity: activeAgent ? 1 : 0,
            transition: 'max-height 0.4s ease, opacity 0.3s ease',
          }}>
            {activeAgent && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 14,
                border: `1px solid ${activeAgent.color}44`,
                borderRadius: 4, padding: '10px 16px',
                background: `${PF}cc`,
                boxShadow: `0 0 20px ${activeAgent.color}22`,
              }}>
                <TinaFace state="thinking" size={72} ringColor={activeAgent.glow} glowColor={activeAgent.color} />
                <div>
                  <div style={{ fontSize: 11, letterSpacing: 3, color: activeAgent.color, marginBottom: 4 }}>
                    {activeAgent.name.toUpperCase()} AGENT
                  </div>
                  <div style={{ fontSize: 9, letterSpacing: 1, color: activeAgent.color, opacity: 0.5, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ animation: 'micpulse 1s ease-in-out infinite', display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: activeAgent.color }} />
                    ACTIVE
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Response text box */}
          {lastResponse && (
            <div style={{
              width: '100%',
              border: `1px solid ${P}55`,
              borderRadius: 4,
              padding: '12px 14px',
              background: `${PF}cc`,
              boxShadow: `0 0 20px ${P}22`,
              animation: 'fadein 0.3s ease',
            }}>
              <div style={{ fontSize: 9, letterSpacing: 3, opacity: 0.5, marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
                <span>TINA RESPONSE</span>
                <span style={{ color: P, opacity: 0.8 }}>◆ LIVE</span>
              </div>
              <div style={{ fontSize: 11, lineHeight: 1.7, letterSpacing: 0.3, color: PG, opacity: 0.9, whiteSpace: 'pre-wrap' }}>
                {lastResponse}
              </div>
            </div>
          )}

          {/* Activity log */}
          <div style={{ width: '100%', border: `1px solid ${P}22`, borderRadius: 4, padding: '10px 14px', background: `${PF}88` }}>
            <div style={{ fontSize: 9, letterSpacing: 3, opacity: 0.4, marginBottom: 6 }}>ACTIVITY LOG</div>
            {log.map((l, i) => (
              <div key={i} style={{ fontSize: 10, letterSpacing: 0.3, opacity: 1 - i * 0.11, marginBottom: 2, color: i === 0 ? PG : PG + '88' }}>
                {l}
              </div>
            ))}
          </div>

          {/* Input + controls */}
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 8 }}>
            <form onSubmit={handleSend} style={{ display: 'flex', gap: 7 }}>
              <span style={{ fontSize: 14, color: P, opacity: 0.7, alignSelf: 'center', flexShrink: 0 }}>&gt;</span>
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder={connected ? 'send a message...' : 'offline...'}
                disabled={!connected || isRecording}
                autoFocus
                style={{
                  flex: 1, background: `${PF}99`, border: `1px solid ${P}33`,
                  borderRadius: 3, padding: '7px 10px', color: PG,
                  fontFamily: "'Courier New',monospace", fontSize: 13, letterSpacing: 1,
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
                  background:  isRecording ? '#ef444433' : connected ? `${P}33` : 'transparent',
                  border:      `1px solid ${isRecording ? '#ef4444' : connected ? P : P + '33'}`,
                  color:       isRecording ? '#ef4444' : PG,
                  animation:   isRecording ? 'micpulse 0.8s ease-in-out infinite' : 'none',
                  flexShrink:  0,
                }}
              >
                {isRecording ? '■ REC' : '● MIC'}
              </button>
              <button type="submit" disabled={!connected || !input.trim() || isRecording} style={btnStyle(connected && input.trim() && !isRecording)}>
                SEND
              </button>
            </form>

            <div style={{ display: 'flex', gap: 7 }}>
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
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10, minWidth: 240 }}>
          {right.map(el => (
            <DynamicElement key={el.id} spec={el} onExpire={() => removeElement(el.id)} />
          ))}
          {right.length === 0 && (
            <div style={{ border: `1px dashed ${P}18`, borderRadius: 4, padding: 32, textAlign: 'center', opacity: 0.12, fontSize: 10, letterSpacing: 2 }}>
              HUD ZONE B
            </div>
          )}
        </div>
      </div>

      {/* Footer status bar */}
      <div style={{
        position: 'absolute', bottom: 16, left: 38, right: 38,
        display: 'flex', justifyContent: 'space-between',
        fontSize: 9, letterSpacing: 2, opacity: 0.25,
      }}>
        <span>WS: {connected ? 'CONNECTED' : 'OFFLINE'}</span>
        <span>STATE: {cfg.label}</span>
        <span>ELEMENTS: {elements.length} ({elements.filter(e => e.persistent).length} PINNED)</span>
        <span>DEEPGRAM · ELEVENLABS · TAVILY</span>
      </div>

      <style>{`
        @keyframes offblink { 0%,100%{opacity:0.8} 50%{opacity:0.3} }
        @keyframes micpulse { 0%,100%{box-shadow:0 0 6px #ef4444} 50%{box-shadow:0 0 18px #ef4444,0 0 6px #ef444488} }
        @keyframes fadein { from{opacity:0;transform:translateY(-6px)} to{opacity:1;transform:translateY(0)} }
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
