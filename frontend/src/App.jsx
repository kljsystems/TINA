import { useState, useEffect, useRef, useCallback } from 'react'
import { useTina } from './hooks/useTina'
import TinaFace, { STATE_CFG } from './components/TinaFace'
import RingCanvas from './components/RingCanvas'
import BgCanvas from './components/BgCanvas'

const P  = '#8B5CF6'
const PG = '#C4B5FD'
const PF = '#1E1030'
const PB = '#08040F'

const AGENTS = [
  { key: 'coding',    name: 'SAM',     role: 'Code',      color: '#10b981', glow: '#6ee7b7' },
  { key: 'research',  name: 'CHARLIE', role: 'Research',  color: '#06b6d4', glow: '#67e8f9' },
  { key: 'email',     name: 'TRISTAN', role: 'Email',     color: '#f59e0b', glow: '#fcd34d' },
  { key: 'data',      name: 'CONNOR',  role: 'Data',      color: '#a78bfa', glow: '#c4b5fd' },
  { key: 'marketing', name: 'WADE',    role: 'Marketing', color: '#ec4899', glow: '#f9a8d4' },
  { key: 'website',   name: 'JAMIE',   role: 'Web',       color: '#0ea5e9', glow: '#7dd3fc' },
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

function relTime(ts) {
  const d = Date.now() - ts
  if (d < 60000)   return `${Math.floor(d / 1000)}s`
  if (d < 3600000) return `${Math.floor(d / 60000)}m`
  return `${Math.floor(d / 3600000)}h`
}

// ── Section header ────────────────────────────────────────────────────────────

function Section({ label, children, style }) {
  return (
    <div style={{ marginBottom: 6, ...style }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 14px 3px' }}>
        <span style={{ fontSize: 9, letterSpacing: 3, color: P, opacity: 0.65, whiteSpace: 'nowrap' }}>{label}</span>
        <div style={{ flex: 1, height: 1, background: `linear-gradient(90deg, ${P}55, transparent)` }} />
      </div>
      {children}
    </div>
  )
}

// ── Agent card ────────────────────────────────────────────────────────────────

function AgentCard({ agent, status }) {
  const s = status ?? { status: 'idle', tool: null }
  const isActive = s.status === 'running' || s.status === 'active'
  const isDone   = s.status === 'done'

  return (
    <div style={{
      border: `1px solid ${isActive ? agent.color + '55' : agent.color + '18'}`,
      borderLeft: `2px solid ${isActive ? agent.color : agent.color + '28'}`,
      background: isActive ? `${agent.color}0d` : `${PF}88`,
      borderRadius: 4, padding: '7px 9px',
      transition: 'all 0.35s',
      boxShadow: isActive ? `0 0 16px ${agent.glow}1a` : 'none',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{
            width: 5, height: 5, borderRadius: '50%', display: 'inline-block', flexShrink: 0,
            background: isActive ? agent.color : isDone ? agent.color + '77' : agent.color + '2a',
            boxShadow: isActive ? `0 0 8px ${agent.glow}` : 'none',
            animation: isActive ? 'pulse 1s ease-in-out infinite' : 'none',
          }} />
          <span style={{ fontSize: 11, letterSpacing: 1, color: isActive ? agent.color : agent.color + '99' }}>
            {agent.name}
          </span>
        </div>
        <span style={{
          fontSize: 8, letterSpacing: 1,
          color: isActive ? agent.color : PG,
          opacity: isActive ? 0.9 : 0.55,
        }}>
          {isActive ? 'ACTIVE' : isDone ? 'DONE' : 'IDLE'}
        </span>
      </div>
      <div style={{
        fontSize: 9, letterSpacing: 0.3,
        color: isActive ? agent.color : PG,
        opacity: isActive ? 0.8 : 0.55,
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
      const t1 = setTimeout(() => setDying(true),      Math.max(0, fadeAt - now))
      const t2 = setTimeout(() => onDismiss(panel.id), Math.max(0, killAt - now))
      return () => { clearTimeout(t1); clearTimeout(t2) }
    }
  }, [])

  return (
    <div style={{
      opacity: dying ? 0 : visible ? 1 : 0, transition: 'opacity 0.4s',
      border: `1px solid ${cfg.color}1a`, borderLeft: `2px solid ${cfg.color}55`,
      background: `${PF}cc`, borderRadius: 4, padding: '8px 11px', flexShrink: 0,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
        <span style={{ fontSize: 10, letterSpacing: 2, color: cfg.color, opacity: 0.8 }}>{cfg.label}</span>
        <button onClick={() => onDismiss(panel.id)}
          style={{ background: 'none', border: 'none', color: cfg.color, opacity: 0.35, cursor: 'pointer', fontSize: 11, padding: 0 }}
        >✕</button>
      </div>
      <div style={{
        fontSize: 11, lineHeight: 1.6, color: PG, opacity: 0.8,
        whiteSpace: 'pre-wrap', overflow: 'hidden',
        display: '-webkit-box', WebkitLineClamp: 6, WebkitBoxOrient: 'vertical',
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
    if (s === 'running') return { bg: '#6b7280', anim: 'pulse 0.8s ease-in-out infinite' }
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
          <button onClick={onClose} style={{ padding: '4px 12px', fontSize: 9, letterSpacing: 2, background: `${P}33`, border: `1px solid ${P}`, color: PG, borderRadius: 3, cursor: 'pointer', fontFamily: "'Courier New',monospace" }}>
            {running ? 'HIDE' : 'CLOSE'}
          </button>
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
    <div style={{ position: 'absolute', inset: 0, zIndex: 25, background: 'rgba(8,4,15,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{ width: '85vw', height: '78vh', display: 'flex', flexDirection: 'column', border: `1px solid ${P}66`, borderRadius: 6, background: `${PF}f5`, boxShadow: `0 0 60px ${P}2a`, fontFamily: "'Courier New',monospace", overflow: 'hidden' }}>
        <div style={{ flexShrink: 0, padding: '10px 16px', borderBottom: `1px solid ${P}33`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 10, letterSpacing: 4, color: PG, opacity: 0.7 }}>CODE PREVIEW</span>
            <span style={{ fontSize: 8, letterSpacing: 2, padding: '2px 8px', border: `1px solid ${P}44`, borderRadius: 10, color: P }}>{files.length} file{files.length !== 1 ? 's' : ''}</span>
            <span style={{ fontSize: 8, color: '#10b981', opacity: 0.8, display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#10b981', display: 'inline-block', animation: 'pulse 1.2s ease-in-out infinite' }} />
              SAM
            </span>
          </div>
          <button onClick={onClose} style={{ padding: '3px 12px', fontSize: 9, letterSpacing: 2, background: `${P}33`, border: `1px solid ${P}`, color: PG, borderRadius: 3, cursor: 'pointer', fontFamily: "'Courier New',monospace" }}>✕ CLOSE</button>
        </div>
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <div style={{ width: 190, flexShrink: 0, borderRight: `1px solid ${P}22`, overflowY: 'auto', padding: '6px 0' }}>
            {files.map((f, i) => (
              <div key={f.ts} onClick={() => setSelectedIdx(i)} style={{ padding: '7px 12px', cursor: 'pointer', background: i === selectedIdx ? `${P}22` : 'transparent', borderLeft: `2px solid ${i === selectedIdx ? P : 'transparent'}`, transition: 'all 0.15s' }}>
                <div style={{ fontSize: 9, color: i === selectedIdx ? PG : PG + '66', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{basename(f.path)}</div>
                <div style={{ fontSize: 7, opacity: 0.3, marginTop: 2 }}>.{ext(f.path) || '?'} · {(f.content.length / 1024).toFixed(1)}k</div>
              </div>
            ))}
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ flexShrink: 0, padding: '5px 14px', borderBottom: `1px solid ${P}22`, fontSize: 8, opacity: 0.3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
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

// ── System info overlay data ──────────────────────────────────────────────────

const SVC_INFO = [
  { key: 'ws',         abbr: 'WS', label: 'WebSocket',   color: '#4ade80',
    desc: 'Live bidirectional connection to the TINA FastAPI backend. All agent commands, voice input, tool calls, and state updates flow through this channel in real time. If this is red, nothing works.',
    apiVar: null },
  { key: 'deepgram',   abbr: 'DG', label: 'Deepgram',    color: '#06b6d4',
    desc: 'Real-time speech-to-text transcription. Converts your voice into text during conversation mode. Required for all voice input — without it, you can only type.',
    apiVar: 'DEEPGRAM_API_KEY' },
  { key: 'elevenlabs', abbr: 'EL', label: 'ElevenLabs',  color: '#8B5CF6',
    desc: "Text-to-speech synthesis. Produces TINA's spoken voice responses. Without this, responses are text-only and the speaker stays silent.",
    apiVar: 'ELEVENLABS_API_KEY' },
  { key: 'github',     abbr: 'GH', label: 'GitHub',      color: '#e2e8f0',
    desc: 'Personal access token for the KLJ Systems GitHub organisation. Sam uses this to read repos, open pull requests, check CI status, and browse issues.',
    apiVar: 'GITHUB_TOKEN' },
  { key: 'tavily',     abbr: 'TV', label: 'Tavily',      color: '#f59e0b',
    desc: 'AI-optimised web search API. Charlie uses this to find up-to-date information, news, competitor research, and reference material from the live web.',
    apiVar: 'TAVILY_API_KEY' },
  { key: 'slack',      abbr: 'SL', label: 'Slack',       color: '#4ade80',
    desc: 'Bot token for the KLJ Slack workspace. TINA can read channels, post messages, monitor team activity, and surface important alerts from Slack.',
    apiVar: 'SLACK_TINA_BOT_TOKEN' },
  { key: 'weather',    abbr: 'WX', label: 'OpenWeather', color: '#38bdf8',
    desc: 'Current weather and forecast data for your location. Used during morning routine and whenever you ask about the weather.',
    apiVar: 'OPENWEATHER_API_KEY' },
]

const AGENT_INFO = [
  { key: 'tina',      name: 'TINA',    color: '#8B5CF6', glow: '#A78BFA', role: 'Orchestrator',
    desc: 'Core AI brain. Handles all conversations, decides when to delegate to specialist agents, and coordinates multi-step workflows across the whole team. Every request starts here.',
    tools: ['open_browser', 'dashboard_popup', 'vault', 'filesystem', 'restart_backend', 'read_logs'] },
  { key: 'research',  name: 'Charlie', color: '#06b6d4', glow: '#67e8f9', role: 'Research',
    desc: 'Web research and information gathering. Searches the live web, reads news, analyses sources, and produces structured research reports. Vault-aware — checks prior research before starting.',
    tools: ['web_search', 'news_search', 'web_read', 'vault_read', 'vault_write', 'fs_write'] },
  { key: 'coding',    name: 'Sam',     color: '#10b981', glow: '#6ee7b7', role: 'Coding',
    desc: 'Full-stack developer. Reads, writes, and edits code files across the whole project. Opens terminals for dependency installs, previews changed files in the dashboard, and restarts the backend after changes.',
    tools: ['fs_read', 'fs_write', 'fs_edit', 'fs_list', 'open_terminal', 'open_browser', 'code_preview', 'restart_backend'] },
  { key: 'email',     name: 'Tristan', color: '#f59e0b', glow: '#fcd34d', role: 'Email',
    desc: 'Gmail management. Triages inbox, summarises threads, drafts and sends replies, searches email history, and flags what needs urgent attention. Stores summaries to vault.',
    tools: ['email_list', 'email_read', 'email_send', 'email_search', 'vault_write'] },
  { key: 'data',      name: 'Connor',  color: '#a78bfa', glow: '#c4b5fd', role: 'Data Analysis',
    desc: 'Data analyst. Reads CSV, Excel, and JSON files, runs calculations and aggregations, generates charts, and produces business reports with insights and anomaly flags.',
    tools: ['data_read', 'data_query', 'data_chart', 'data_write', 'kaos_overview', 'stripe_overview', 'vault_write'] },
  { key: 'marketing', name: 'Wade',    color: '#ec4899', glow: '#f9a8d4', role: 'Marketing',
    desc: 'Social media and content. Creates posts for Meta and Instagram, researches trending topics, analyses engagement metrics, schedules content, and helps plan campaigns.',
    tools: ['meta_analytics', 'instagram_analytics', 'web_search', 'vault_read', 'vault_write', 'fs_write'] },
  { key: 'website',   name: 'Jamie',   color: '#0ea5e9', glow: '#7dd3fc', role: 'Web Development',
    desc: 'Web developer and site builder. Builds and edits static sites, manages file structure, previews pages in the browser, takes screenshots to verify results, and handles HTML/CSS/JS.',
    tools: ['fs_read', 'fs_write', 'fs_edit', 'open_browser', 'take_screenshot', 'vault_write'] },
]

const TOOL_MODULES = [
  { name: 'System',         color: P,         desc: 'Dashboard control — open browsers, send popup data cards, restart the backend, read runtime logs, set UI preferences.' },
  { name: 'Vault',          color: '#C4B5FD', desc: 'Obsidian Markdown vault — store and retrieve memories, project notes, briefing docs, and agent task logs across sessions.' },
  { name: 'Filesystem',     color: '#10b981', desc: 'Local file operations — read, write, edit, list, move, and delete files and directories on the host machine.' },
  { name: 'KAOS',           color: '#f59e0b', desc: 'KLJ SaaS platform operator access — workspace health, active user counts, subscriptions, support tickets, and waitlist signups.' },
  { name: 'Stripe',         color: '#4ade80', desc: 'Revenue and billing — MRR, active subscriptions, failed payments, churn signals, customer list, and revenue history by period.' },
  { name: 'Data Analysis',  color: '#a78bfa', desc: 'CSV/Excel/JSON processing — filter, group, aggregate, generate charts (PNG), and write processed results back to disk.' },
  { name: 'Social Media',   color: '#ec4899', desc: 'Meta Business Suite and Instagram — page impressions, post engagement, follower growth, reach, and ad performance metrics.' },
  { name: 'Email (Gmail)',   color: '#f59e0b', desc: 'Gmail read and send — list inbox, read full threads, draft and send replies, search email history by keyword or sender.' },
  { name: 'Docs',           color: '#06b6d4', desc: 'Document generation — create formatted Word, PDF, and Markdown documents from data or templates, saved to the filesystem.' },
  { name: 'Web Search',     color: '#38bdf8', desc: 'Tavily-powered web and news search — find current information, retrieve articles, research topics, and summarise sources.' },
  { name: 'Calendar',       color: '#60a5fa', desc: 'Google Calendar — read upcoming events, check availability windows, and schedule or modify meetings.' },
  { name: 'Weather',        color: '#7dd3fc', desc: 'OpenWeather API — current conditions, hourly and daily forecasts, wind, humidity, and UV index for your location.' },
]

// ── Email drafts overlay ───────────────────────────────────────────────────────

function DraftsOverlay({ data, onClose, onDismiss }) {
  const drafts = data?.drafts || []
  const [sent,    setSent]    = useState({})   // index → 'sending'|'sent'|'failed'
  const [expanded, setExpanded] = useState(null)

  const priorityColor = p => p === 'URGENT' ? '#ef4444' : '#60a5fa'

  const accountLabel = a => ({
    personal:         'Personal Gmail',
    business_gmail:   'Business Gmail',
    business_outlook: 'Outlook',
  }[a] || a)

  const handleSend = async (idx, draft) => {
    setSent(s => ({ ...s, [idx]: 'sending' }))
    try {
      const r = await fetch('http://localhost:8000/api/email-send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account: draft.account,
          to:      draft.from,
          subject: draft.subject,
          body:    draft.body,
        }),
      })
      const res = await r.json()
      setSent(s => ({ ...s, [idx]: res.error ? 'failed' : 'sent' }))
    } catch {
      setSent(s => ({ ...s, [idx]: 'failed' }))
    }
  }

  const allDone = drafts.length > 0 && drafts.every((_, i) => sent[i] === 'sent' || sent[i] === 'failed')

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(8,4,15,0.92)',
      zIndex: 70, display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        width: 640, maxHeight: '85vh', background: '#0d0820',
        border: `1px solid ${P}55`, borderRadius: 8,
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          padding: '11px 18px', borderBottom: `1px solid ${P}22`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0,
        }}>
          <span style={{ fontSize: 11, letterSpacing: 3, color: PG }}>EMAIL DRAFTS</span>
          <span style={{ fontSize: 9, color: PG + '55', letterSpacing: 1 }}>
            {drafts.length} PENDING · {data?.source || ''}
          </span>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: PG + '55',
            cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 0,
          }}>✕</button>
        </div>

        {/* Draft list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          {drafts.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', fontSize: 11, color: PG + '44', letterSpacing: 1 }}>
              NO PENDING DRAFTS
            </div>
          ) : drafts.map((draft, idx) => {
            const state  = sent[idx]
            const isOpen = expanded === idx
            const color  = priorityColor(draft.priority)
            return (
              <div key={idx} style={{
                margin: '6px 12px', borderRadius: 5,
                background: state === 'sent' ? '#4ade8008' : `${P}08`,
                border: `1px solid ${state === 'sent' ? '#4ade8033' : state === 'failed' ? '#ef444433' : P + '22'}`,
                opacity: state === 'sent' ? 0.6 : 1,
                transition: 'all 0.2s',
              }}>
                {/* Draft header row */}
                <div
                  onClick={() => setExpanded(isOpen ? null : idx)}
                  style={{
                    padding: '10px 14px', cursor: 'pointer',
                    display: 'grid', gridTemplateColumns: 'auto 1fr auto',
                    gap: 10, alignItems: 'center',
                  }}
                >
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span style={{
                      padding: '2px 7px', fontSize: 8, letterSpacing: 1, borderRadius: 3,
                      background: color + '22', color, border: `1px solid ${color}55`,
                    }}>{draft.priority}</span>
                    <span style={{ fontSize: 8, color: PG + '44', letterSpacing: 1 }}>{accountLabel(draft.account)}</span>
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 11, color: PG, opacity: 0.9, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {draft.subject}
                    </div>
                    <div style={{ fontSize: 10, color: PG, opacity: 0.5, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {draft.from}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
                    {state === 'sent'    && <span style={{ fontSize: 9, color: '#4ade80', letterSpacing: 1 }}>SENT ✓</span>}
                    {state === 'failed'  && <span style={{ fontSize: 9, color: '#ef4444', letterSpacing: 1 }}>FAILED</span>}
                    {state === 'sending' && <span style={{ fontSize: 9, color: PG + '66', letterSpacing: 1 }}>SENDING…</span>}
                    {!state && (
                      <button
                        onClick={e => { e.stopPropagation(); handleSend(idx, draft) }}
                        style={{
                          padding: '3px 12px', fontSize: 9, letterSpacing: 2,
                          background: '#4ade8022', border: '1px solid #4ade8055',
                          color: '#4ade80', borderRadius: 3, cursor: 'pointer',
                          fontFamily: "'Courier New',monospace",
                        }}
                      >SEND</button>
                    )}
                    <span style={{ fontSize: 10, color: PG + '33' }}>{isOpen ? '▲' : '▼'}</span>
                  </div>
                </div>

                {/* Expanded body */}
                {isOpen && (
                  <div style={{ padding: '0 14px 12px' }}>
                    <div style={{ fontSize: 9, color: PG + '44', letterSpacing: 1, marginBottom: 6 }}>DRAFT REPLY</div>
                    <div style={{
                      background: '#1a0f35', border: `1px solid ${P}22`,
                      borderRadius: 4, padding: '10px 12px',
                      fontSize: 12, color: PG, lineHeight: 1.7,
                      whiteSpace: 'pre-wrap', maxHeight: 260, overflowY: 'auto',
                      opacity: 0.85,
                    }}>{draft.body}</div>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Footer */}
        <div style={{
          padding: '10px 18px', borderTop: `1px solid ${P}22`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0,
        }}>
          <span style={{ fontSize: 9, color: PG + '44', letterSpacing: 1 }}>
            {Object.values(sent).filter(s => s === 'sent').length} SENT · {Object.values(sent).filter(s => s === 'failed').length} FAILED
          </span>
          <button onClick={onClose} style={{
            padding: '4px 16px', fontSize: 9, letterSpacing: 2,
            background: `${P}22`, border: `1px solid ${P}55`,
            color: PG, borderRadius: 3, cursor: 'pointer',
            fontFamily: "'Courier New',monospace",
          }}>DONE</button>
        </div>
      </div>
    </div>
  )
}

// ── System info overlay ────────────────────────────────────────────────────────

function SystemInfoOverlay({ onClose, services, connected }) {
  const [tab, setTab] = useState('services')

  return (
    <div
      style={{ position: 'absolute', inset: 0, zIndex: 40, background: 'rgba(8,4,15,0.93)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        width: '88vw', maxWidth: 960, height: '82vh',
        display: 'flex', flexDirection: 'column',
        border: `1px solid ${P}55`, borderRadius: 8,
        background: `${PF}f8`,
        boxShadow: `0 0 80px ${P}1a`,
        fontFamily: "'Courier New',monospace",
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{ flexShrink: 0, padding: '14px 22px', borderBottom: `1px solid ${P}33`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span style={{ fontSize: 13, letterSpacing: 6, color: PG, opacity: 0.9 }}>SYSTEM</span>
            <div style={{ display: 'flex', gap: 3 }}>
              {['SERVICES', 'AGENTS', 'TOOLS'].map(t => (
                <button key={t} onClick={() => setTab(t.toLowerCase())}
                  style={{
                    padding: '5px 16px', fontSize: 9, letterSpacing: 2,
                    background: tab === t.toLowerCase() ? `${P}44` : 'transparent',
                    border: `1px solid ${tab === t.toLowerCase() ? P : P + '33'}`,
                    color: tab === t.toLowerCase() ? PG : PG + '66',
                    borderRadius: 3, cursor: 'pointer',
                    fontFamily: "'Courier New',monospace",
                    transition: 'all 0.15s',
                  }}
                >{t}</button>
              ))}
            </div>
          </div>
          <button onClick={onClose}
            style={{ padding: '5px 16px', fontSize: 9, letterSpacing: 2, background: `${P}33`, border: `1px solid ${P}`, color: PG, borderRadius: 3, cursor: 'pointer', fontFamily: "'Courier New',monospace" }}
          >✕ CLOSE</button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '18px 22px' }}>

          {/* ── SERVICES ── */}
          {tab === 'services' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {SVC_INFO.map(svc => {
                const ok = svc.key === 'ws' ? connected : (services?.[svc.key] ?? false)
                return (
                  <div key={svc.key} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 18,
                    padding: '14px 18px',
                    border: `1px solid ${ok ? svc.color + '33' : P + '1a'}`,
                    borderLeft: `3px solid ${ok ? svc.color : '#374151'}`,
                    borderRadius: 5, background: `${PF}99`,
                  }}>
                    {/* Abbr + status */}
                    <div style={{ width: 64, flexShrink: 0, paddingTop: 2 }}>
                      <div style={{ fontSize: 16, letterSpacing: 2, color: svc.color, opacity: ok ? 1 : 0.3, fontWeight: 'bold' }}>{svc.abbr}</div>
                      <div style={{ fontSize: 9, marginTop: 5, letterSpacing: 1, color: ok ? '#4ade80' : '#ef4444' }}>{ok ? '● ACTIVE' : '○ OFFLINE'}</div>
                    </div>
                    {/* Info */}
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, letterSpacing: 1, color: PG, opacity: 0.9, marginBottom: 6 }}>{svc.label}</div>
                      <div style={{ fontSize: 11, lineHeight: 1.65, color: PG, opacity: 0.65 }}>{svc.desc}</div>
                      {svc.apiVar && (
                        <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                          <span style={{ fontSize: 9, letterSpacing: 2, color: P, opacity: 0.7 }}>API KEY</span>
                          <span style={{ fontSize: 10, letterSpacing: 2, color: ok ? '#4ade80' : '#ef4444' }}>
                            {ok ? '●●●●●●●●  ●●●●●●●●  ●●●●' : 'NOT CONFIGURED'}
                          </span>
                          <span style={{ fontSize: 8, color: PG, opacity: 0.3, letterSpacing: 1 }}>({svc.apiVar})</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* ── AGENTS ── */}
          {tab === 'agents' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {AGENT_INFO.map(agent => (
                <div key={agent.key} style={{
                  padding: '16px 18px',
                  border: `1px solid ${agent.color}33`,
                  borderLeft: `3px solid ${agent.color}`,
                  borderRadius: 5, background: `${PF}99`,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                    <span style={{ width: 9, height: 9, borderRadius: '50%', background: agent.color, boxShadow: `0 0 10px ${agent.glow}`, flexShrink: 0 }} />
                    <span style={{ fontSize: 14, letterSpacing: 2, color: agent.color }}>{agent.name}</span>
                    <span style={{ fontSize: 8, letterSpacing: 2, color: agent.color, opacity: 0.5, marginLeft: 'auto', textAlign: 'right' }}>{agent.role}</span>
                  </div>
                  <div style={{ fontSize: 11, lineHeight: 1.7, color: PG, opacity: 0.7, marginBottom: 12 }}>{agent.desc}</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {agent.tools.map(t => (
                      <span key={t} style={{
                        fontSize: 8, padding: '2px 8px',
                        background: `${agent.color}18`, border: `1px solid ${agent.color}33`,
                        borderRadius: 3, color: agent.color, opacity: 0.85, letterSpacing: 0.5,
                      }}>{t}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* ── TOOLS ── */}
          {tab === 'tools' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {TOOL_MODULES.map(tool => (
                <div key={tool.name} style={{
                  padding: '14px 18px',
                  border: `1px solid ${tool.color}2a`,
                  borderLeft: `3px solid ${tool.color}`,
                  borderRadius: 5, background: `${PF}99`,
                }}>
                  <div style={{ fontSize: 12, letterSpacing: 2, color: tool.color, marginBottom: 8 }}>{tool.name}</div>
                  <div style={{ fontSize: 11, lineHeight: 1.65, color: PG, opacity: 0.68 }}>{tool.desc}</div>
                </div>
              ))}
            </div>
          )}

        </div>
      </div>
    </div>
  )
}

// ── Featured panel (popup card) ───────────────────────────────────────────────

function FeaturedPanel({ panel, onDismiss }) {
  const [progress, setProgress] = useState(100)
  const [dying,    setDying]    = useState(false)

  useEffect(() => {
    const ttl   = panel.ttl ?? 45000
    const start = Date.now()
    const t     = setInterval(() => {
      const elapsed   = Date.now() - start
      const remaining = Math.max(0, ttl - elapsed)
      setProgress((remaining / ttl) * 100)
      if (remaining < 1200) setDying(true)
      if (remaining <= 0)   { clearInterval(t); onDismiss(panel.id) }
    }, 80)
    return () => clearInterval(t)
  }, [])

  const c = panel.color || P

  return (
    <div style={{
      opacity: dying ? 0 : 1,
      transition: 'opacity 0.9s ease',
      background: `${PF}f5`,
      border: `1px solid ${c}44`,
      borderLeft: `3px solid ${c}`,
      borderRadius: 6,
      overflow: 'hidden',
      boxShadow: `0 0 40px ${c}1a, 0 10px 40px rgba(0,0,0,0.7)`,
      animation: 'slidein 0.22s ease',
      fontFamily: "'Courier New',monospace",
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px 8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: c, boxShadow: `0 0 8px ${c}`, flexShrink: 0 }} />
          <span style={{ fontSize: 9, letterSpacing: 3, color: c }}>{panel.title}</span>
        </div>
        <button
          onClick={() => onDismiss(panel.id)}
          style={{ background: 'none', border: 'none', color: c, opacity: 0.45, cursor: 'pointer', fontSize: 9, padding: 0, fontFamily: 'inherit' }}
          onMouseEnter={e => e.currentTarget.style.opacity = 0.9}
          onMouseLeave={e => e.currentTarget.style.opacity = 0.45}
        >✕</button>
      </div>
      <div style={{ padding: '0 14px 12px', fontSize: 10, lineHeight: 1.75, color: PG, opacity: 0.85, whiteSpace: 'pre-wrap' }}>
        {panel.content}
      </div>
      <div style={{ height: 2, background: `${c}22` }}>
        <div style={{ height: '100%', width: `${progress}%`, background: c, opacity: 0.55, transition: 'width 0.08s linear' }} />
      </div>
    </div>
  )
}

// ── Pipeline board ────────────────────────────────────────────────────────────

function PipelineBoard({ pipeline }) {
  if (!pipeline) return null
  const { inbox = [], proposed = [], active = [] } = pipeline

  const ColHead = ({ label, count }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px 4px', borderBottom: `1px solid ${P}0f`, flexShrink: 0 }}>
      <span style={{ fontSize: 10, letterSpacing: 3, opacity: 0.65 }}>{label}</span>
      {count > 0 && <span style={{ fontSize: 9, padding: '1px 6px', background: `${P}2a`, border: `1px solid ${P}44`, borderRadius: 8, color: P, lineHeight: '15px' }}>{count}</span>}
    </div>
  )

  const clean = name => name.replace(/\.\w+$/, '').replace(/^\d{4}-\d{2}-\d{2}[T_-][\d:._-]*Z?[-_]?/, '').replace(/[-_]/g, ' ')

  return (
    <div style={{ flexShrink: 0, borderTop: `1px solid ${P}18`, display: 'flex', height: 136, zIndex: 1 }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', borderRight: `1px solid ${P}10`, overflow: 'hidden' }}>
        <ColHead label="INBOX" count={inbox.length} />
        <div style={{ flex: 1, overflowY: 'auto', padding: '2px 12px' }}>
          {inbox.length === 0
            ? <div style={{ fontSize: 10, opacity: 0.35, paddingTop: 6, letterSpacing: 1 }}>CLEAR</div>
            : inbox.map((item, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 0', borderBottom: `1px solid ${P}0c` }}>
                <span style={{ width: 5, height: 5, borderRadius: '50%', background: (item.status === 'classified' || item.status === 'processed') ? '#4ade80' : P, flexShrink: 0, opacity: 0.85 }} />
                <span style={{ fontSize: 10, opacity: 0.8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{clean(item.filename)}</span>
              </div>
            ))}
        </div>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', borderRight: `1px solid ${P}10`, overflow: 'hidden' }}>
        <ColHead label="PROPOSED" count={proposed.length} />
        <div style={{ flex: 1, overflowY: 'auto', padding: '2px 12px' }}>
          {proposed.length === 0
            ? <div style={{ fontSize: 10, opacity: 0.35, paddingTop: 6, letterSpacing: 1 }}>NONE</div>
            : proposed.map((p, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 0', borderBottom: `1px solid ${P}0c` }}>
                <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#f59e0b', flexShrink: 0, opacity: 0.85 }} />
                <span style={{ fontSize: 10, opacity: 0.82, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.title}</span>
              </div>
            ))}
        </div>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <ColHead label="ACTIVE" count={active.length} />
        <div style={{ flex: 1, overflowY: 'auto', padding: '2px 12px' }}>
          {active.length === 0
            ? <div style={{ fontSize: 10, opacity: 0.35, paddingTop: 6, letterSpacing: 1 }}>NONE</div>
            : active.map((p, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 0', borderBottom: `1px solid ${P}0c` }}>
                <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#4ade80', flexShrink: 0, animation: 'pulse 2.5s ease-in-out infinite' }} />
                <span style={{ fontSize: 10, opacity: 0.85, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.title}</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [micDeviceId, setMicDeviceId] = useState(() => localStorage.getItem('tina_mic_device') || '')
  const [micDevices,  setMicDevices]  = useState([])

  useEffect(() => {
    const update = () => navigator.mediaDevices.enumerateDevices().then(d => setMicDevices(d.filter(x => x.kind === 'audioinput')))
    update()
    navigator.mediaDevices.addEventListener('devicechange', update)
    return () => navigator.mediaDevices.removeEventListener('devicechange', update)
  }, [])

  const {
    connected, tinaState, isRecording, activeAgent,
    lastResponse, services, pipeline, turnCount, sessionStart,
    agentStatuses, diagRunning, diagResults,
    codePreviewFiles, panels, dismissPanel,
    featuredPanels, dismissFeaturedPanel,
    morningActive, wakeWordActive,
    kaosLive, stripeLive, notificationHistory,
    emailDrafts, setEmailDrafts,
    wakeActive, convActive,
    sendMessage, stopRecording,
    enterConversation, exitConversation,
  } = useTina({ micDeviceId })

  const [input,           setInput]          = useState('')
  const [time,            setTime]           = useState(new Date())
  const [uptime,          setUptime]         = useState('00:00:00')
  const [messages,        setMessages]       = useState([
    { id: 0, role: 'system', text: 'Neural core online. All systems ready.' },
  ])
  const [showDiag,        setShowDiag]       = useState(false)
  const [showCodePreview, setShowCodePreview] = useState(false)
  const [showSystemInfo,  setShowSystemInfo] = useState(false)
  const [chatOpen,        setChatOpen]       = useState(false)
  const [activityFeed,    setActivityFeed]   = useState([])
  const [,                setTick]           = useState(0)

  const msgIdRef      = useRef(1)
  const inputRef      = useRef(null)
  const chatRef       = useRef(null)
  const prevConn      = useRef(false)
  const prevResp      = useRef(null)
  const prevStatusRef = useRef({})

  const addMessage = useCallback((role, text) => {
    setMessages(prev => [...prev, { id: msgIdRef.current++, role, text, ts: Date.now() }].slice(-80))
  }, [])

  useEffect(() => {
    const t = setInterval(() => {
      setTime(new Date())
      const ms = Date.now() - sessionStart
      const h  = Math.floor(ms / 3600000)
      const m  = Math.floor((ms % 3600000) / 60000)
      const s  = Math.floor((ms % 60000) / 1000)
      setUptime(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`)
      setTick(n => n + 1)
    }, 1000)
    return () => clearInterval(t)
  }, [sessionStart])

  useEffect(() => {
    if ( connected && !prevConn.current) addMessage('system', 'Neural link established')
    if (!connected &&  prevConn.current) addMessage('system', 'Connection lost — reconnecting…')
    prevConn.current = connected
  }, [connected, addMessage])

  useEffect(() => {
    if (lastResponse && lastResponse !== prevResp.current) {
      addMessage('tina', lastResponse)
      prevResp.current = lastResponse
    }
  }, [lastResponse, addMessage])

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight
  }, [messages.length])

  useEffect(() => {
    if (chatOpen) setTimeout(() => inputRef.current?.focus(), 60)
  }, [chatOpen])

  useEffect(() => {
    if (codePreviewFiles.length > 0) {
      setShowCodePreview(true)
      addMessage('system', `SAM wrote ${codePreviewFiles[0].path.replace(/\\/g, '/').split('/').pop()}`)
    }
  }, [codePreviewFiles.length])

  useEffect(() => {
    if (diagRunning) setShowDiag(true)
  }, [diagRunning])

  // Spacebar toggles voice — ignore when typing in an input/textarea or overlay is open
  useEffect(() => {
    const onKey = (e) => {
      if (e.code !== 'Space') return
      const tag = document.activeElement?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (!connected) return
      e.preventDefault()
      if (convActive) {
        if (isRecording) stopRecording()
        else exitConversation()
      } else {
        enterConversation()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [connected, convActive, isRecording, stopRecording, exitConversation, enterConversation])

  // Build activity feed from agent status transitions
  useEffect(() => {
    const prev = prevStatusRef.current
    const newEntries = []
    for (const [key, status] of Object.entries(agentStatuses)) {
      if (prev[key]?.status === 'running' && status.status === 'done') {
        const agent = AGENTS.find(a => a.key === key)
        newEntries.push({ id: `${key}-${Date.now()}`, name: agent?.name || key.toUpperCase(), color: agent?.color || P, ts: Date.now() })
      }
    }
    if (newEntries.length) setActivityFeed(p => [...newEntries, ...p].slice(0, 10))
    prevStatusRef.current = { ...agentStatuses }
  }, [agentStatuses])

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

  const toolPanels   = panels.filter(p => p.type !== 'agent')
  const tinaMessages = messages.filter(m => m.role === 'tina')
  const lastTinaMsg  = tinaMessages[tinaMessages.length - 1]
  const hasMessages  = messages.some(m => m.role !== 'system')

  // Ambient glow colour driven by state
  const ambientColor = isRecording
    ? 'rgba(239,68,68,0.06)'
    : activeAgent
    ? `${activeAgent.color}0a`
    : tinaState === 'speaking'
    ? 'rgba(133,183,235,0.05)'
    : 'transparent'

  const svcDots = [
    { key: 'ws', label: 'WS', ok: connected },
    { key: 'dg', label: 'DG', ok: services?.deepgram },
    { key: 'el', label: 'EL', ok: services?.elevenlabs },
    { key: 'gh', label: 'GH', ok: services?.github },
    { key: 'tv', label: 'TV', ok: services?.tavily },
    { key: 'sl', label: 'SL', ok: services?.slack },
  ]

  return (
    <div style={{
      height: '100vh', overflow: 'hidden',
      background: PB, display: 'flex', flexDirection: 'column',
      fontFamily: "'Courier New',monospace", color: PG,
      position: 'relative',
      boxShadow: `inset 0 0 120px ${ambientColor}`,
      transition: 'box-shadow 1.2s ease',
    }}>

      {/* Canvas background */}
      <BgCanvas />

      {/* Scanline texture */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0,
        background: 'repeating-linear-gradient(0deg, transparent, transparent 1px, rgba(0,0,0,0.04) 1px, rgba(0,0,0,0.04) 2px)',
      }} />

      {/* Corner brackets */}
      {[
        { top: 8, left:  8, borderTop: `1px solid ${P}55`, borderLeft:  `1px solid ${P}55` },
        { top: 8, right: 8, borderTop: `1px solid ${P}55`, borderRight: `1px solid ${P}55` },
        { bottom: 8, left:  8, borderBottom: `1px solid ${P}55`, borderLeft:  `1px solid ${P}55` },
        { bottom: 8, right: 8, borderBottom: `1px solid ${P}55`, borderRight: `1px solid ${P}55` },
      ].map((s, i) => (
        <div key={i} style={{ position: 'absolute', width: 18, height: 18, opacity: isOffline ? 0.1 : 0.5, zIndex: 1, ...s }} />
      ))}

      {/* Overlays */}
      {showCodePreview && codePreviewFiles.length > 0 && (
        <CodePreviewPanel files={codePreviewFiles} onClose={() => setShowCodePreview(false)} />
      )}
      {showDiag && Object.keys(diagResults).length > 0 && (
        <DiagOverlay results={diagResults} running={diagRunning} onClose={() => setShowDiag(false)} />
      )}
      {showSystemInfo && (
        <SystemInfoOverlay onClose={() => setShowSystemInfo(false)} services={services} connected={connected} />
      )}
      {emailDrafts && (
        <DraftsOverlay
          data={emailDrafts}
          onClose={() => setEmailDrafts(null)}
          onDismiss={() => setEmailDrafts(null)}
        />
      )}

      {/* Featured data popups */}
      {featuredPanels.length > 0 && (
        <div style={{
          position: 'fixed', top: 52, left: '50%', transform: 'translateX(-50%)',
          display: 'flex', flexDirection: 'column', gap: 8,
          zIndex: 58, width: 430, pointerEvents: 'none',
        }}>
          {featuredPanels.map(panel => (
            <div key={panel.id} style={{ pointerEvents: 'auto' }}>
              <FeaturedPanel panel={panel} onDismiss={dismissFeaturedPanel} />
            </div>
          ))}
        </div>
      )}

      {isOffline && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, background: 'rgba(8,4,15,0.94)' }}>
          <div style={{ fontSize: 26, letterSpacing: 8, color: '#E24B4A', opacity: 0.85, animation: 'blink 2s ease-in-out infinite' }}>TINA OFFLINE</div>
          <div style={{ fontSize: 8, letterSpacing: 3, color: '#E24B4A', opacity: 0.3 }}>START BACKEND — python tina.py</div>
        </div>
      )}

      {/* ── Header ── */}
      <div style={{ flexShrink: 0, zIndex: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 22px', borderBottom: `1px solid ${P}22` }}>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {svcDots.map(({ key, label, ok }) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <span style={{
                width: 5, height: 5, borderRadius: '50%', display: 'inline-block',
                background: ok === undefined ? '#374151' : ok ? '#4ade80' : '#ef4444',
                boxShadow: ok === undefined ? 'none' : ok ? '0 0 5px #4ade8088' : '0 0 5px #ef444488',
              }} />
              <span style={{ fontSize: 9, letterSpacing: 1, opacity: 0.65 }}>{label}</span>
            </div>
          ))}
          <button
            onClick={() => setShowSystemInfo(true)}
            style={{
              marginLeft: 6, padding: '3px 11px', fontSize: 8, letterSpacing: 2,
              background: 'transparent', border: `1px solid ${P}33`,
              color: PG + '77', borderRadius: 3, cursor: 'pointer',
              fontFamily: "'Courier New',monospace", transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = `${P}22`; e.currentTarget.style.color = PG; e.currentTarget.style.borderColor = `${P}88` }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = PG + '77'; e.currentTarget.style.borderColor = `${P}33` }}
          >SYS</button>

          {/* Morning routine running indicator — no button, triggered by voice */}
          {morningActive && (
            <span style={{
              padding: '3px 11px', fontSize: 8, letterSpacing: 2,
              border: '1px solid #f59e0b',
              color: '#f59e0b', borderRadius: 3,
              animation: 'pulse 1.5s ease-in-out infinite',
              fontFamily: "'Courier New',monospace",
            }}>◐ MORNING</span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Voice indicator — SPACE activates, wake word auto-activates */}
          <div
            title={
              convActive
                ? (isRecording ? 'Recording… press SPACE to stop' : 'Listening — press SPACE to speak')
                : wakeWordActive
                ? 'Wake word active — say "Tina" to start'
                : 'Press SPACE to start voice'
            }
            style={{
              padding: '5px 14px', fontSize: 10, letterSpacing: 1,
              background: isRecording ? '#ef444422' : convActive ? `${P}33` : wakeWordActive ? '#4ade8011' : 'transparent',
              border: `1px solid ${isRecording ? '#ef4444' : convActive ? P : wakeWordActive ? '#4ade8055' : P + '22'}`,
              color: isRecording ? '#ef4444' : convActive ? PG : wakeWordActive ? '#4ade80cc' : connected ? PG + '66' : PG + '22',
              borderRadius: 3,
              animation: isRecording ? 'micpulse 0.8s ease-in-out infinite' : wakeWordActive && !convActive ? 'breathe 3s ease-in-out infinite' : 'none',
              transition: 'all 0.2s', fontFamily: "'Courier New',monospace",
              userSelect: 'none',
            }}
          >
            {isRecording ? '■ REC' : convActive ? '◉ LIVE' : wakeWordActive ? '◎ WAKE' : '● SPACE'}
          </div>

          {/* CHAT button */}
          <button
            onClick={() => setChatOpen(v => !v)}
            style={{
              position: 'relative',
              padding: '5px 18px', fontSize: 10, letterSpacing: 2,
              background: chatOpen ? `${P}44` : `${P}18`,
              border: `1px solid ${chatOpen ? P : P + '44'}`,
              color: chatOpen ? PG : PG + 'bb',
              borderRadius: 3, cursor: 'pointer',
              textTransform: 'uppercase', transition: 'all 0.2s',
              fontFamily: "'Courier New',monospace",
            }}
          >
            {chatOpen ? '✕ CHAT' : 'CHAT'}
            {hasMessages && !chatOpen && (
              <span style={{
                position: 'absolute', top: -3, right: -3,
                width: 6, height: 6, borderRadius: '50%',
                background: P, border: `1px solid ${PB}`,
                animation: 'pulse 2s ease-in-out infinite',
              }} />
            )}
          </button>

          <div style={{ textAlign: 'right', fontSize: 11, letterSpacing: 1, opacity: 0.55 }}>
            <div>{time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
            <div style={{ marginTop: 1, fontSize: 9, color: isRecording ? '#ef4444' : PG + 'aa' }}>
              {isRecording ? '● REC' : cfg.label}
            </div>
          </div>
        </div>
      </div>

      {/* ── 3-column body ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', zIndex: 1 }}>

        {/* ── LEFT — Ops ── */}
        <div style={{ width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', borderRight: `1px solid ${P}18`, overflowY: 'auto' }}>

          <Section label="PIPELINE" style={{ marginTop: 4 }}>
            {[
              { label: 'INBOX',    count: pipeline?.inbox?.length ?? 0,    color: P,         pulse: (pipeline?.inbox?.length ?? 0) > 0 },
              { label: 'PROPOSED', count: pipeline?.proposed?.length ?? 0, color: '#f59e0b', pulse: false },
              { label: 'ACTIVE',   count: pipeline?.active?.length ?? 0,   color: '#4ade80', pulse: true  },
            ].map(({ label, count, color, pulse }) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 14px' }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                  background: count > 0 ? color : color + '22',
                  animation: pulse && count > 0 ? 'pulse 2s ease-in-out infinite' : 'none',
                }} />
                <span style={{ fontSize: 11, letterSpacing: 1, opacity: 0.7, flex: 1 }}>{label}</span>
                <span style={{ fontSize: 13, color: count > 0 ? color : PG, opacity: count > 0 ? 0.9 : 0.45, fontVariantNumeric: 'tabular-nums' }}>{count}</span>
              </div>
            ))}
            {pipeline?.active?.length > 0 && (
              <div style={{ padding: '2px 14px 4px' }}>
                {pipeline.active.map((proj, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '2px 0' }}>
                    <span style={{ fontSize: 10, opacity: 0.4, marginLeft: 12 }}>└</span>
                    <span style={{ fontSize: 10, opacity: 0.75, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{proj.title}</span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section label="ACTIVITY">
            {activityFeed.length === 0 ? (
              <div style={{ padding: '6px 14px', fontSize: 10, opacity: 0.45, letterSpacing: 1 }}>NO RECENT ACTIVITY</div>
            ) : activityFeed.slice(0, 7).map(entry => (
              <div key={entry.id} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '5px 14px', borderBottom: `1px solid ${P}0c` }}>
                <span style={{ width: 5, height: 5, borderRadius: '50%', background: entry.color, flexShrink: 0, opacity: 0.9 }} />
                <span style={{ fontSize: 11, color: entry.color, opacity: 0.85, letterSpacing: 0.5, flex: 1 }}>{entry.name}</span>
                <span style={{ fontSize: 9, opacity: 0.5, flexShrink: 0 }}>{relTime(entry.ts)}</span>
              </div>
            ))}
          </Section>

          {/* Notification / alert history */}
          <Section label="ALERTS" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
              {notificationHistory.length === 0 ? (
                <div style={{ padding: '6px 14px', fontSize: 10, opacity: 0.4, letterSpacing: 1 }}>NO ALERTS YET</div>
              ) : notificationHistory.slice(0, 20).map(n => (
                <div key={n.id} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '4px 14px', borderBottom: `1px solid ${P}0c` }}>
                  <span style={{ width: 4, height: 4, borderRadius: '50%', background: n.color, flexShrink: 0, boxShadow: `0 0 4px ${n.color}88` }} />
                  <span style={{ fontSize: 10, color: n.color, opacity: 0.85, letterSpacing: 0.5, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.title}</span>
                  <span style={{ fontSize: 9, opacity: 0.45, flexShrink: 0 }}>{relTime(n.ts)}</span>
                </div>
              ))}
            </div>
          </Section>

          <Section label="SESSION">
            {[
              { label: 'UPTIME',    value: uptime },
              { label: 'EXCHANGES', value: turnCount },
              { label: 'AGENTS',    value: `${AGENTS.length}` },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 14px' }}>
                <span style={{ fontSize: 10, letterSpacing: 1, opacity: 0.65 }}>{label}</span>
                <span style={{ fontSize: 12, opacity: 0.85, fontVariantNumeric: 'tabular-nums' }}>{value}</span>
              </div>
            ))}
          </Section>

          {micDevices.length > 0 && (
            <Section label="MIC">
              <div style={{ padding: '2px 14px' }}>
                <select
                  value={micDeviceId}
                  onChange={e => { setMicDeviceId(e.target.value); localStorage.setItem('tina_mic_device', e.target.value) }}
                  style={{
                    width: '100%', background: 'transparent', border: `1px solid ${P}22`, color: PG,
                    fontSize: 10, letterSpacing: 1, padding: '4px 6px', borderRadius: 3,
                    cursor: 'pointer', opacity: 0.65,
                  }}
                >
                  <option value=''>DEFAULT</option>
                  {micDevices.map(d => (
                    <option key={d.deviceId} value={d.deviceId}>
                      {(d.label || `Mic ${d.deviceId.slice(0,6)}`).toUpperCase().slice(0, 22)}
                    </option>
                  ))}
                </select>
              </div>
            </Section>
          )}
        </div>

        {/* ── CENTRE — Hero ── */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '8px 12px 14px', gap: 0 }}>

          {/* Face + ring stack */}
          <div style={{ position: 'relative', width: 320, height: 320, flexShrink: 0 }}>
            <RingCanvas state={tinaState} />
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <TinaFace state={tinaState} size={230} />
            </div>
            {/* State label overlaid on lower face area */}
            <div style={{ position: 'absolute', bottom: 30, left: 0, right: 0, textAlign: 'center', pointerEvents: 'none' }}>
              <div style={{ fontSize: 8, letterSpacing: 5, color: activeAgent ? activeAgent.color : PG, opacity: 0.9, transition: 'color 0.4s' }}>
                {dispLabel}
              </div>
              <div style={{ fontSize: 6, letterSpacing: 2, opacity: 0.5, marginTop: 2 }}>{dispSub}</div>
            </div>
          </div>

          {/* Last TINA response snippet */}
          {lastTinaMsg && (
            <div style={{
              width: '100%', maxWidth: 340, marginTop: 2,
              padding: '7px 12px',
              border: `1px solid ${P}18`, borderLeft: `2px solid ${P}44`,
              borderRadius: 3, background: `${PF}77`,
            }}>
              <div style={{ fontSize: 6, letterSpacing: 2, color: P, opacity: 0.7, marginBottom: 3 }}>LAST RESPONSE</div>
              <div style={{
                fontSize: 9, lineHeight: 1.5, color: PG, opacity: 0.8,
                overflow: 'hidden', display: '-webkit-box',
                WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
              }}>
                {lastTinaMsg.text}
              </div>
            </div>
          )}

          {/* Voice mode indicator */}
          <div style={{ height: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, marginTop: 6 }}>
            {wakeActive && !convActive && (
              <><span style={{ width: 4, height: 4, borderRadius: '50%', background: P, display: 'inline-block', animation: 'wakepulse 2.4s ease-in-out infinite' }} />
              <span style={{ fontSize: 6, letterSpacing: 2, color: P, opacity: 0.65 }}>WAKE WORD ACTIVE</span></>
            )}
            {convActive && !isRecording && (
              <><span style={{ width: 4, height: 4, borderRadius: '50%', background: '#4ade80', display: 'inline-block', animation: 'pulse 1s ease-in-out infinite' }} />
              <span style={{ fontSize: 6, letterSpacing: 2, color: '#4ade80', opacity: 0.75 }}>LISTENING…</span></>
            )}
            {isRecording && (
              <><span style={{ width: 4, height: 4, borderRadius: '50%', background: '#ef4444', display: 'inline-block', animation: 'micpulse 0.8s ease-in-out infinite' }} />
              <span style={{ fontSize: 6, letterSpacing: 2, color: '#ef4444', opacity: 0.8 }}>RECORDING</span></>
            )}
          </div>

          {/* Code preview — only shown when SAM has written files */}
          {codePreviewFiles.length > 0 && (
            <button
              onClick={() => setShowCodePreview(v => !v)}
              style={{
                marginTop: 6, padding: '4px 14px', fontSize: 8, letterSpacing: 2,
                background: `${P}22`, border: `1px solid ${P}55`,
                color: PG + 'cc', borderRadius: 3, cursor: 'pointer',
                textTransform: 'uppercase', fontFamily: "'Courier New',monospace",
              }}
            >
              CODE ({codePreviewFiles.length})
            </button>
          )}
        </div>

        {/* ── RIGHT — Team ── */}
        <div style={{ width: 300, flexShrink: 0, display: 'flex', flexDirection: 'column', borderLeft: `1px solid ${P}18`, overflow: 'hidden' }}>

          {/* Live metrics tiles */}
          {(kaosLive || stripeLive) && (
            <Section label="LIVE" style={{ flexShrink: 0 }}>
              <div style={{ padding: '4px 10px 6px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                {kaosLive && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 3 }}>
                    {[
                      { label: 'WORKSPACES', val: kaosLive.users   ?? '—' },
                      { label: 'TICKETS',    val: kaosLive.tickets  ?? '—', alert: kaosLive.tickets > 0 },
                      { label: 'ACTIVE',     val: kaosLive.active_subs ?? '—', positive: true },
                      { label: 'TRIAL',      val: kaosLive.trial_subs  ?? '—' },
                    ].map(({ label, val, alert, positive }) => (
                      <div key={label} style={{
                        background: alert ? '#f59e0b11' : positive ? '#4ade8011' : `${P}0a`,
                        border: `1px solid ${alert ? '#f59e0b33' : positive ? '#4ade8033' : P + '22'}`,
                        borderRadius: 4, padding: '5px 4px', textAlign: 'center',
                      }}>
                        <div style={{ fontSize: 13, fontWeight: 'bold', color: alert ? '#f59e0b' : positive ? '#4ade80' : PG, opacity: 0.9 }}>{val}</div>
                        <div style={{ fontSize: 7, letterSpacing: 1, color: PG, opacity: 0.5, marginTop: 1 }}>{label}</div>
                      </div>
                    ))}
                  </div>
                )}
                {stripeLive && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3 }}>
                    {[
                      { label: 'MRR',  val: `$${stripeLive.mrr != null ? stripeLive.mrr.toLocaleString('en-AU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) : '—'}`, positive: true },
                      { label: 'SUBS', val: stripeLive.active_subs ?? '—', positive: true },
                    ].map(({ label, val, positive }) => (
                      <div key={label} style={{
                        background: '#4ade8011', border: '1px solid #4ade8033',
                        borderRadius: 4, padding: '5px 4px', textAlign: 'center',
                      }}>
                        <div style={{ fontSize: 13, fontWeight: 'bold', color: '#4ade80', opacity: 0.9 }}>{val}</div>
                        <div style={{ fontSize: 7, letterSpacing: 1, color: PG, opacity: 0.5, marginTop: 1 }}>{label}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Section>
          )}

          <Section label="AGENTS" style={{ marginTop: 4, flexShrink: 0 }}>
            <div style={{ padding: '4px 10px 6px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
              {AGENTS.map(agent => (
                <AgentCard key={agent.key} agent={agent} status={agentStatuses[agent.key]} />
              ))}
            </div>
          </Section>

          <Section label="CONTEXT" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', marginBottom: 0 }}>
            {toolPanels.length === 0 ? (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ fontSize: 10, letterSpacing: 2, opacity: 0.35, textAlign: 'center', lineHeight: 2 }}>
                  TOOL RESULTS<br />APPEAR HERE
                </div>
              </div>
            ) : (
              <div style={{ flex: 1, overflowY: 'auto', padding: '4px 10px 8px', display: 'flex', flexDirection: 'column', gap: 5 }}>
                {toolPanels.map(panel => (
                  <ToolPanel key={panel.id} panel={panel} onDismiss={dismissPanel} />
                ))}
              </div>
            )}
          </Section>
        </div>
      </div>

      {/* ── Pipeline board ── */}
      <PipelineBoard pipeline={pipeline} />

      {/* ── Footer ── */}
      <div style={{ flexShrink: 0, zIndex: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '5px 22px', borderTop: `1px solid ${P}22`, fontSize: 9, letterSpacing: 2, opacity: 0.55 }}>
        <span>UPTIME {uptime}</span>
        <span>TURNS {turnCount}</span>
        {pipeline && <span>IN {pipeline.inbox.length} · ACT {pipeline.active.length}</span>}
        <span>PANELS {panels.length}</span>
        <span>{connected ? 'ONLINE' : 'OFFLINE'} · SONNET 4.6</span>
      </div>

      {/* ── Chat slide-in ── */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 380,
        background: `${PF}fa`,
        borderLeft: `1px solid ${P}44`,
        boxShadow: `-16px 0 60px rgba(0,0,0,0.8), -1px 0 0 ${P}18`,
        display: 'flex', flexDirection: 'column',
        transform: chatOpen ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.28s cubic-bezier(0.4,0,0.2,1)',
        zIndex: 60,
        fontFamily: "'Courier New', monospace",
      }}>

        <div style={{ flexShrink: 0, padding: '10px 16px', borderBottom: `1px solid ${P}22`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, letterSpacing: 3, opacity: 0.7 }}>CONVERSATION</span>
            <span style={{ fontSize: 10, opacity: 0.5 }}>{messages.filter(m => m.role !== 'system').length} messages</span>
          </div>
          <button
            onClick={() => setChatOpen(false)}
            style={{
              background: 'none', border: `1px solid ${P}33`, borderRadius: 3,
              color: PG, opacity: 0.5, cursor: 'pointer',
              fontSize: 10, letterSpacing: 2, padding: '4px 12px',
              fontFamily: "'Courier New',monospace", transition: 'opacity 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.opacity = 0.85}
            onMouseLeave={e => e.currentTarget.style.opacity = 0.45}
          >
            ✕ CLOSE
          </button>
        </div>

        <div ref={chatRef} style={{ flex: 1, overflowY: 'auto', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {messages.map(msg => {
            if (msg.role === 'system') return (
              <div key={msg.id} style={{ textAlign: 'center', fontSize: 9, letterSpacing: 1.5, color: PG, opacity: 0.4, padding: '2px 0' }}>
                — {msg.text} —
              </div>
            )
            if (msg.role === 'ky') return (
              <div key={msg.id} style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <div style={{
                  maxWidth: '86%', background: `${P}22`, border: `1px solid ${P}44`,
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
                  maxWidth: '92%', background: `${PF}dd`, border: `1px solid ${P}18`,
                  borderRadius: '8px 8px 8px 2px', padding: '6px 10px',
                  fontSize: 10, lineHeight: 1.55, color: PG, opacity: 0.8, letterSpacing: 0.2,
                }}>
                  {msg.text}
                </div>
              </div>
            )
          })}
        </div>

        <div style={{ flexShrink: 0, borderTop: `1px solid ${P}18`, padding: '8px 12px' }}>
          <form onSubmit={handleSend} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: P, opacity: 0.55, flexShrink: 0 }}>&gt;</span>
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder={connected ? 'send a message…' : 'offline…'}
              disabled={!connected || isRecording}
              style={{
                flex: 1, background: `${PF}cc`, border: `1px solid ${P}22`,
                borderRadius: 3, padding: '7px 10px', color: PG,
                fontFamily: "'Courier New',monospace", fontSize: 11, letterSpacing: 0.3,
                outline: 'none',
              }}
            />
            <button
              type="submit"
              disabled={!connected || !input.trim() || isRecording}
              style={{
                padding: '7px 16px', fontSize: 10, letterSpacing: 2,
                background: connected && input.trim() && !isRecording ? `${P}33` : 'transparent',
                border: `1px solid ${connected && input.trim() && !isRecording ? P : P + '22'}`,
                color: connected && input.trim() && !isRecording ? PG : PG + '66',
                borderRadius: 3, cursor: connected && input.trim() && !isRecording ? 'pointer' : 'not-allowed',
                textTransform: 'uppercase', fontFamily: "'Courier New',monospace",
              }}
            >
              SEND
            </button>
          </form>
        </div>
      </div>

      <style>{`
        * { box-sizing: border-box; }
        body { margin: 0; overflow: hidden; }
        @keyframes blink     { 0%,100%{opacity:0.85} 50%{opacity:0.2}  }
        @keyframes pulse     { 0%,100%{opacity:1}    50%{opacity:0.25} }
        @keyframes micpulse  { 0%,100%{box-shadow:0 0 6px #ef4444} 50%{box-shadow:0 0 22px #ef4444} }
        @keyframes wakepulse { 0%,100%{opacity:0.5}  50%{opacity:1}    }
        @keyframes slidein   { from{opacity:0;transform:translateY(-8px)} to{opacity:1;transform:translateY(0)} }
        @keyframes breathe   { 0%,100%{opacity:0.5} 50%{opacity:1} }
        ::-webkit-scrollbar { width: 2px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${P}33; border-radius: 1px; }
      `}</style>
    </div>
  )
}
