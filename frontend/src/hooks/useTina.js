import { useState, useEffect, useCallback, useRef } from 'react'

const WS_URL = 'ws://localhost:8000/ws'
const RECONNECT_MS = 3000

function getMimeType() {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
  return types.find(t => MediaRecorder.isTypeSupported(t)) ?? ''
}

export function useTina() {
  const [connected,    setConnected]   = useState(false)
  const [tinaState,    setTinaState]   = useState('offline')
  const [isRecording,  setIsRecording] = useState(false)
  const [activeAgent,  setActiveAgent] = useState(null)
  const [conversation, setConversation] = useState([
    { role: 'tina', text: 'all systems online. ready when you are.' },
  ])
  const [stats,        setStats]        = useState({ facts: 0, sessions: 0, tools: 5 })
  const [voice,        setVoice]        = useState('Daniel')
  const [user,         setUser]         = useState({ name: 'Kai', location: '—' })
  const [lastTool,     setLastTool]     = useState({ name: '—', time: '—' })
  const [alert,        setAlert]        = useState(null)
  const [lastResponse, setLastResponse] = useState(null)
  const [services,     setServices]     = useState(null)
  const [diagRunning,       setDiagRunning]       = useState(false)
  const [diagResults,       setDiagResults]       = useState({})
  const [turnCount,         setTurnCount]         = useState(0)
  const [sessionStart]                            = useState(Date.now())
  const [codePreviewFiles,  setCodePreviewFiles]  = useState([])
  const [panels,            setPanels]            = useState([])
  const [activityLogVisible, setActivityLogVisible] = useState(true)
  const [agentStatuses, setAgentStatuses] = useState({
    tina:     { status: 'offline', tool: null, color: '#8B5CF6', glow: '#A78BFA' },
    research: { status: 'idle',    tool: null, color: '#06b6d4', glow: '#67e8f9' },
    coding:   { status: 'idle',    tool: null, color: '#10b981', glow: '#6ee7b7', label: 'Sam' },
    email:    { status: 'idle',    tool: null, color: '#f59e0b', glow: '#fcd34d', label: 'Tristan' },
  })

  const activeAgentKeyRef     = useRef(null)
  const backgroundAgentKeyRef = useRef(null)

  const TOOL_LABELS = {
    vault_search: 'VAULT SEARCH', vault_read: 'VAULT READ',
    list_events: 'CALENDAR', create_event: 'CREATE EVENT',
    update_event: 'UPDATE EVENT', delete_event: 'DELETE EVENT',
    check_availability: 'CHECK AVAIL',
    get_weather: 'WEATHER',
    search: 'WEB SEARCH', wikipedia: 'WIKIPEDIA', news: 'NEWS FEED',
    github_list_repos: 'GITHUB REPOS', github_get_repo: 'GITHUB REPO',
    github_list_issues: 'GITHUB ISSUES', github_create_issue: 'CREATE ISSUE',
    github_list_prs: 'GITHUB PRS', github_read_file: 'GITHUB FILE',
    delegate_to_agent: 'DELEGATING',
  }

  // Auto-expire panels whose TTL has elapsed
  useEffect(() => {
    const t = setInterval(() => {
      const now = Date.now()
      setPanels(prev => prev.filter(p => p.ttl === Infinity || now - p.ts < p.ttl))
    }, 1000)
    return () => clearInterval(t)
  }, [])

  const dismissPanel = useCallback((id) => {
    setPanels(prev => prev.filter(p => p.id !== id))
  }, [])

  // Poll service health every 30s
  useEffect(() => {
    const check = () =>
      fetch('http://localhost:8000/api/status')
        .then(r => r.json())
        .then(setServices)
        .catch(() => setServices(null))
    check()
    const t = setInterval(check, 30000)
    return () => clearInterval(t)
  }, [])

  const wsRef            = useRef(null)
  const alertTimerRef    = useRef(null)
  const mediaRef         = useRef(null)
  const chunksRef        = useRef([])
  const audioCtxRef      = useRef(null)
  const nextStartTimeRef = useRef(0)

  const showAlert = useCallback((msg, type = 'tool') => {
    if (alertTimerRef.current) clearTimeout(alertTimerRef.current)
    setAlert({ msg, type })
    alertTimerRef.current = setTimeout(() => setAlert(null), 3000)
  }, [])

  const addLine = useCallback((role, text) => {
    setConversation(prev => [...prev, { role, text }].slice(-3))
  }, [])

  const getAudioCtx = useCallback(() => {
    if (!audioCtxRef.current || audioCtxRef.current.state === 'closed')
      audioCtxRef.current = new AudioContext()
    return audioCtxRef.current
  }, [])

  const scheduleChunk = useCallback(async (base64data) => {
    try {
      const ctx = getAudioCtx()
      if (ctx.state === 'suspended') await ctx.resume()
      const bytes   = Uint8Array.from(atob(base64data), c => c.charCodeAt(0))
      const decoded = await ctx.decodeAudioData(bytes.buffer)
      const src     = ctx.createBufferSource()
      src.buffer    = decoded
      src.connect(ctx.destination)
      const startAt = Math.max(ctx.currentTime, nextStartTimeRef.current)
      src.start(startAt)
      nextStartTimeRef.current = startAt + decoded.duration
    } catch (e) {
      console.error('Audio chunk error:', e)
    }
  }, [getAudioCtx])

  const connect = useCallback(() => {
    if (wsRef.current) return
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      nextStartTimeRef.current = 0
      showAlert('tina online', 'tool')
    }

    ws.onmessage = async e => {
      const data = JSON.parse(e.data)
      switch (data.type) {
        case 'state':
          setTinaState(data.state)
          if (data.state === 'listening') {
            setActiveAgent(null)
            activeAgentKeyRef.current = backgroundAgentKeyRef.current
            setAgentStatuses(prev => ({
              ...prev,
              tina: { ...prev.tina, status: 'listening', tool: null },
              research: prev.research.status === 'running' ? prev.research : { ...prev.research, status: 'idle', tool: null },
              coding:   prev.coding.status   === 'running' ? prev.coding   : { ...prev.coding,   status: 'idle', tool: null },
            }))
          } else {
            setAgentStatuses(prev => ({ ...prev, tina: { ...prev.tina, status: data.state, tool: prev.tina.tool } }))
          }
          break
        case 'agent_active': {
          const key = data.agent?.toLowerCase()
          activeAgentKeyRef.current = key
          setActiveAgent({ name: data.agent, color: data.color, glow: data.glow })
          setAgentStatuses(prev => ({
            ...prev,
            tina: { ...prev.tina, tool: 'DELEGATING' },
            [key]: prev[key] ? { ...prev[key], status: 'active', tool: 'STARTING...' } : prev[key],
          }))
          break
        }
        case 'agent_background_start': {
          const key = data.key || data.agent?.toLowerCase()
          activeAgentKeyRef.current     = key
          backgroundAgentKeyRef.current = key
          setAgentStatuses(prev => ({
            ...prev,
            [key]: prev[key] ? { ...prev[key], status: 'running', tool: 'RUNNING...' } : prev[key],
          }))
          setPanels(prev => [
            ...prev.filter(p => p.id !== `agent-${key}`),
            { id: `agent-${key}`, name: key, type: 'agent', display: data.agent, color: data.color, glow: data.glow, text: 'Starting…', ttl: Infinity, ts: Date.now(), side: 'activity' },
          ])
          break
        }
        case 'agent_background_done': {
          const key = data.agent?.toLowerCase()
          activeAgentKeyRef.current     = null
          backgroundAgentKeyRef.current = null
          setAgentStatuses(prev => ({
            ...prev,
            [key]: prev[key] ? { ...prev[key], status: 'idle', tool: null } : prev[key],
          }))
          setPanels(prev => prev.filter(p => p.id !== `agent-${key}`))
          if (data.summary) setLastResponse(`${data.display} finished:\n\n${data.summary}`)
          break
        }
        case 'agent_done':
          setActiveAgent(null)
          activeAgentKeyRef.current = null
          setAgentStatuses(prev => ({
            ...prev,
            tina: { ...prev.tina, tool: null },
            research: { ...prev.research, status: 'idle', tool: null },
            coding:   { ...prev.coding,   status: 'idle', tool: null },
          }))
          break
        case 'heard':
          addLine('kai', data.text)
          setLastResponse(null)
          setTurnCount(c => c + 1)
          break
        case 'response':
          addLine('tina', data.text)
          if (data.text && data.text.length > 100) setLastResponse(data.text)
          setAgentStatuses(prev => ({ ...prev, tina: { ...prev.tina, tool: null } }))
          break
        case 'audio_chunk':
          await scheduleChunk(data.data)
          break
        case 'audio_end': {
          const ctx = audioCtxRef.current
          const delay = ctx ? Math.max(0, nextStartTimeRef.current - ctx.currentTime) : 0
          setTimeout(() => {
            nextStartTimeRef.current = 0
            if (wsRef.current?.readyState === WebSocket.OPEN)
              wsRef.current.send(JSON.stringify({ type: 'audio_done' }))
          }, delay * 1000 + 150)
          break
        }
        case 'tool': {
          const label = TOOL_LABELS[data.name] ?? data.name.toUpperCase()
          setLastTool({ name: data.name, time: data.time ?? '—' })
          showAlert('tool: ' + data.name)
          const key = activeAgentKeyRef.current
          if (key) {
            setAgentStatuses(prev => prev[key]
              ? { ...prev, [key]: { ...prev[key], tool: label } }
              : prev
            )
            setPanels(prev => prev.map(p =>
              p.id === `agent-${key}` ? { ...p, text: label } : p
            ))
          } else {
            setAgentStatuses(prev => ({ ...prev, tina: { ...prev.tina, tool: label } }))
          }
          break
        }
        case 'code_preview':
          setCodePreviewFiles(prev => [
            { path: data.path, content: data.content, ts: Date.now() },
            ...prev.filter(f => f.path !== data.path),
          ].slice(0, 20))
          break
        case 'tool_result': {
          const pid = `${data.name}-panel`
          setPanels(prev => [
            { id: pid, name: data.name, type: data.panel_type, text: data.text, ttl: data.ttl, ts: Date.now(), side: 'info' },
            ...prev.filter(p => p.id !== pid),
          ])
          break
        }
        case 'diag_start':
          setDiagRunning(true)
          setDiagResults(Object.fromEntries((data.checks || []).map(id => [id, { status: 'running', label: id, detail: '' }])))
          break
        case 'diag_update':
          setDiagResults(prev => ({ ...prev, [data.id]: { status: data.status, label: data.label, detail: data.detail } }))
          break
        case 'diag_complete':
          setDiagRunning(false)
          break
        case 'prefs':
          if (data.data?.activity_log !== undefined)
            setActivityLogVisible(data.data.activity_log)
          break
        case 'ui_pref':
          if (data.key === 'activity_log') setActivityLogVisible(data.value)
          break
        case 'system':
          if (data.voice)              setVoice(data.voice)
          if (data.user)               setUser(u => ({ ...u, name: data.user }))
          if (data.facts !== undefined)    setStats(s => ({ ...s, facts: data.facts }))
          if (data.sessions !== undefined) setStats(s => ({ ...s, sessions: data.sessions }))
          if (data.tools !== undefined)    setStats(s => ({ ...s, tools: data.tools }))
          break
      }
    }

    ws.onclose = () => {
      wsRef.current = null
      setConnected(false)
      setTinaState('offline')
      showAlert('tina offline', 'offline')
      setTimeout(connect, RECONNECT_MS)
    }

    ws.onerror = () => ws.close()
  }, [showAlert, addLine, scheduleChunk])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  const unlockAudio = useCallback(() => {
    const ctx = getAudioCtx()
    if (ctx.state === 'suspended') ctx.resume()
  }, [getAudioCtx])

  const sendMessage = useCallback(text => {
    unlockAudio()
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify({ type: 'message', text }))
  }, [unlockAudio])

  const startRecording = useCallback(async () => {
    unlockAudio()
    if (mediaRef.current || !wsRef.current) return
    try {
      const stream   = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = getMimeType()
      const rec      = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      chunksRef.current = []

      rec.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      rec.onstop = () => {
        const type = mimeType || 'audio/webm'
        const blob = new Blob(chunksRef.current, { type })
        blob.arrayBuffer().then(buf => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            // Tell backend the exact MIME type before sending binary
            wsRef.current.send(JSON.stringify({ type: 'audio_meta', mimeType: type }))
            wsRef.current.send(buf)
          }
        })
        stream.getTracks().forEach(t => t.stop())
      }

      rec.start()
      mediaRef.current = rec
      setIsRecording(true)
    } catch (e) {
      console.error('Mic error:', e)
    }
  }, [])

  const stopRecording = useCallback(() => {
    if (!mediaRef.current) return
    mediaRef.current.stop()
    mediaRef.current = null
    setIsRecording(false)
  }, [])

  return {
    connected, tinaState, isRecording, activeAgent, conversation,
    stats, voice, user, lastTool, alert, lastResponse,
    services, turnCount, sessionStart, agentStatuses,
    diagRunning, diagResults, codePreviewFiles,
    panels, dismissPanel, activityLogVisible,
    sendMessage, startRecording, stopRecording,
  }
}
