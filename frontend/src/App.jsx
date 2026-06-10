import { useState, useEffect, useRef } from 'react'
import { useTina } from './hooks/useTina'
import BgCanvas from './components/BgCanvas'
import RingCanvas from './components/RingCanvas'

const STATE_MAP = {
  listening: { label: 'listening', dot: '#1D9E75', color: 'rgba(29,158,117,0.9)' },
  thinking:  { label: 'processing', dot: '#378ADD', color: 'rgba(55,138,221,0.9)' },
  speaking:  { label: 'speaking',  dot: '#85B7EB', color: 'rgba(133,183,235,0.9)' },
  standby:   { label: 'standby',   dot: '#5F5E5A', color: 'rgba(95,94,90,0.7)' },
  offline:   { label: 'offline',   dot: '#E24B4A', color: 'rgba(226,75,74,0.7)' },
}

function useClock() {
  const [time, setTime] = useState('')
  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])
  return time
}

function useUptime() {
  const start = useRef(Date.now())
  const [uptime, setUptime] = useState('00:00:00')
  useEffect(() => {
    const id = setInterval(() => {
      const s = Math.floor((Date.now() - start.current) / 1000)
      const h = String(Math.floor(s / 3600)).padStart(2, '0')
      const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
      const sc = String(s % 60).padStart(2, '0')
      setUptime(`${h}:${m}:${sc}`)
    }, 1000)
    return () => clearInterval(id)
  }, [])
  return uptime
}

export default function App() {
  const { connected, tinaState, conversation, stats, voice, user, lastTool, alert, sendMessage } = useTina()
  const clock = useClock()
  const uptime = useUptime()
  const [input, setInput] = useState('')
  const inputRef = useRef(null)

  const today = new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' }).toLowerCase()
  const stateInfo = STATE_MAP[tinaState] ?? STATE_MAP.listening
  const isOffline = tinaState === 'offline'
  const cornerColor = isOffline ? 'rgba(226,75,74,0.4)' : 'rgba(55,138,221,0.6)'

  function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || !connected) return
    sendMessage(text)
    setInput('')
    inputRef.current?.focus()
  }

  return (
    <div className="hud">
      <BgCanvas />
      <div className="scan" />

      {['tl', 'tr', 'bl', 'br'].map(pos => (
        <div key={pos} className={`corner ${pos}`} style={{ borderColor: cornerColor }} />
      ))}

      {isOffline && (
        <div className="offline-overlay">
          <div className="offline-title offline-blink">TINA OFFLINE</div>
          <div className="offline-sub">start backend — python -m uvicorn backend.main:app</div>
        </div>
      )}

      {alert && <div className={`alert-bar ${alert.type}`}>// {alert.msg}</div>}

      {/* Topbar */}
      <div className="topbar">
        <div className="topbar-title">T.I.N.A &nbsp;·&nbsp; command interface &nbsp;·&nbsp; v2.0</div>
        <div className="topbar-badges">
          <div className="badge badge-blue">claude sonnet 4.6</div>
          <div className={`badge ${connected ? 'badge-green' : 'badge-red'}`}>
            {connected ? 'ws — connected' : 'ws — offline'}
          </div>
          <div className="badge badge-green">{voice.toLowerCase()} — tts</div>
          <div className="badge badge-green">deepgram — stt</div>
        </div>
        <div className="topbar-time">{clock}</div>
      </div>

      {/* Body */}
      <div className="body">
        <div className="left-panels">
          <div className="panel">
            <div className="plabel">neural core</div>
            <div className="pval">claude sonnet 4.6</div>
            <div className="psub">anthropic · {connected ? 'online' : 'offline'}</div>
          </div>
          <div className="panel">
            <div className="plabel">voice engine</div>
            <div className="pval">elevenlabs</div>
            <div className="psub">{voice.toLowerCase()} · active</div>
          </div>
          <div className="panel">
            <div className="plabel">stt module</div>
            <div className="pval">deepgram</div>
            <div className="psub">nova-2 · en-au</div>
          </div>
          <div className="panel">
            <div className="plabel">session uptime</div>
            <div className="pval">{uptime}</div>
            <div className="psub">{today}</div>
          </div>
        </div>

        <div className="center-col">
          <div className="ring-wrap">
            <RingCanvas state={tinaState} />
            <div className="ring-inner">
              <div className="ring-label">system {isOffline ? 'offline' : 'online'}</div>
              <div className="ring-name" style={{ color: isOffline ? 'rgba(226,75,74,0.6)' : '#85B7EB' }}>TINA</div>
              <div className="ring-state" style={{ color: stateInfo.color }}>
                <span
                  className={`dot ${tinaState === 'speaking' ? 'pulse-speak' : tinaState === 'thinking' ? 'pulse-think' : ''}`}
                  style={{ background: stateInfo.dot }}
                />
                <span>{stateInfo.label}</span>
              </div>
            </div>
          </div>
          <div className="stat-row">
            <div className="stat"><div className="stat-val">{stats.facts}</div><div className="stat-label">facts stored</div></div>
            <div className="stat"><div className="stat-val">{stats.sessions}</div><div className="stat-label">sessions logged</div></div>
            <div className="stat"><div className="stat-val">{stats.tools}</div><div className="stat-label">tools online</div></div>
          </div>
        </div>

        <div className="right-panels">
          <div className="panel">
            <div className="plabel">operator</div>
            <div className="pval">{user.name.toLowerCase()}</div>
            <div className="psub">{user.location.toLowerCase()}</div>
          </div>
          <div className="panel">
            <div className="plabel">current state</div>
            <div className="pval">{stateInfo.label}</div>
            <div className="psub">real-time status</div>
          </div>
          <div className="panel">
            <div className="plabel">last tool call</div>
            <div className="pval">{lastTool.name}</div>
            <div className="psub">{lastTool.time}</div>
          </div>
          <div className="panel">
            <div className="plabel">interface</div>
            <div className="pval">websocket</div>
            <div className="psub">fastapi · phase 1</div>
          </div>
        </div>
      </div>

      {/* Conversation */}
      <div className="convo-section">
        {conversation.map((line, i) => (
          <div key={i} className="convo-row">
            <span className={`who ${line.role}`}>{line.role === 'tina' ? 'TINA' : 'Kai'}</span>
            <span className="msg">{line.text}</span>
          </div>
        ))}
      </div>

      {/* Input */}
      <form className="input-bar" onSubmit={handleSend}>
        <span className="input-prompt">&gt;</span>
        <input
          ref={inputRef}
          className="input-field"
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder={connected ? 'send a message to tina...' : 'tina offline...'}
          disabled={!connected}
          autoFocus
        />
        <button className="input-send" type="submit" disabled={!connected || !input.trim()}>
          send
        </button>
      </form>

      {/* Ticker */}
      <div className="ticker">
        <div className="ticker-label">sys</div>
        <div className="ticker-inner">
          TINA v2.0 &nbsp;·&nbsp; TOTALLY INTELLIGENT NEURAL ASSISTANT &nbsp;·&nbsp; PHASE 1 — WEBSOCKET ACTIVE &nbsp;·&nbsp; DEEPGRAM STT ONLINE &nbsp;·&nbsp; ELEVENLABS TTS ACTIVE &nbsp;·&nbsp; FASTAPI BACKEND RUNNING &nbsp;·&nbsp; REACT DASHBOARD CONNECTED &nbsp;·&nbsp; CLAUDE SONNET 4.6 &nbsp;·&nbsp; AWAITING COMMAND &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
          TINA v2.0 &nbsp;·&nbsp; TOTALLY INTELLIGENT NEURAL ASSISTANT &nbsp;·&nbsp; PHASE 1 — WEBSOCKET ACTIVE &nbsp;·&nbsp; DEEPGRAM STT ONLINE &nbsp;·&nbsp; ELEVENLABS TTS ACTIVE &nbsp;·&nbsp; FASTAPI BACKEND RUNNING &nbsp;·&nbsp; REACT DASHBOARD CONNECTED &nbsp;·&nbsp; CLAUDE SONNET 4.6 &nbsp;·&nbsp; AWAITING COMMAND &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
        </div>
      </div>
    </div>
  )
}
