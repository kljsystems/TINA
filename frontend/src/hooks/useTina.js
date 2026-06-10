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
  const [turnCount,    setTurnCount]    = useState(0)
  const [sessionStart]                  = useState(Date.now())
  const [agentStatuses, setAgentStatuses] = useState({
    tina:     { status: 'offline', tool: null, color: '#8B5CF6', glow: '#A78BFA' },
    research: { status: 'idle',    tool: null, color: '#06b6d4', glow: '#67e8f9' },
    coding:   { status: 'idle',    tool: null, color: '#10b981', glow: '#6ee7b7' },
  })

  const activeAgentKeyRef = useRef(null)

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
            activeAgentKeyRef.current = null
            setAgentStatuses(prev => ({
              ...prev,
              tina: { ...prev.tina, status: 'listening', tool: null },
              research: { ...prev.research, status: 'idle', tool: null },
              coding:   { ...prev.coding,   status: 'idle', tool: null },
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
          } else {
            setAgentStatuses(prev => ({ ...prev, tina: { ...prev.tina, tool: label } }))
          }
          break
        }
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

  const sendMessage = useCallback(text => {
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify({ type: 'message', text }))
  }, [])

  const startRecording = useCallback(async () => {
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
    sendMessage, startRecording, stopRecording,
  }
}
