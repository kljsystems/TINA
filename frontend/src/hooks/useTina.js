import { useState, useEffect, useCallback, useRef } from 'react'

const WS_URL       = 'ws://localhost:8000/ws'
const RECONNECT_MS = 3000
const WAKE_WORDS   = ['hey tina', 'tina', 'ok tina']
const SILENCE_RMS    = 10    // time-domain RMS below this = silence (0–128 range)
const SILENCE_MS     = 7000  // 7s continuous silence after speech → stop recording
const MIN_SPEECH_MS  = 1200  // must have spoken for at least 1.2s before cutoff can trigger
const NO_SPEECH_MS   = 9000  // 9s no speech at all → exit conversation mode

function getMimeType() {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
  return types.find(t => MediaRecorder.isTypeSupported(t)) ?? ''
}

export function useTina({ micDeviceId } = {}) {
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
  const [pipeline,     setPipeline]     = useState(null)
  const [diagRunning,       setDiagRunning]       = useState(false)
  const [diagResults,       setDiagResults]       = useState({})
  const [turnCount,         setTurnCount]         = useState(0)
  const [sessionStart]                            = useState(Date.now())
  const [codePreviewFiles,  setCodePreviewFiles]  = useState([])
  const [panels,            setPanels]            = useState([])
  const [featuredPanels,    setFeaturedPanels]    = useState([])
  const [morningActive,     setMorningActive]     = useState(false)
  const [wakeWordActive,      setWakeWordActive]      = useState(false)
  const [kaosLive,            setKaosLive]            = useState(null)
  const [stripeLive,          setStripeLive]          = useState(null)
  const [notificationHistory, setNotificationHistory] = useState(() => {
    try {
      const stored = localStorage.getItem('tina_alerts')
      return stored ? JSON.parse(stored) : []
    } catch { return [] }
  })
  const [activityLogVisible,  setActivityLogVisible]  = useState(true)
  const [agentStatuses, setAgentStatuses] = useState({
    tina:      { status: 'offline', tool: null, color: '#8B5CF6', glow: '#A78BFA' },
    research:  { status: 'idle',    tool: null, color: '#06b6d4', glow: '#67e8f9',  label: 'Charlie' },
    coding:    { status: 'idle',    tool: null, color: '#10b981', glow: '#6ee7b7',  label: 'Sam'     },
    email:     { status: 'idle',    tool: null, color: '#f59e0b', glow: '#fcd34d',  label: 'Tristan' },
    data:      { status: 'idle',    tool: null, color: '#a78bfa', glow: '#c4b5fd',  label: 'Connor'  },
    marketing: { status: 'idle',    tool: null, color: '#ec4899', glow: '#f9a8d4',  label: 'Wade'    },
    website:   { status: 'idle',    tool: null, color: '#0ea5e9', glow: '#7dd3fc',  label: 'Jamie'   },
  })

  // Wake word + conversation mode state
  const [wakeActive, setWakeActive] = useState(false)
  const [convActive, setConvActive] = useState(false)

  const activeAgentKeyRef     = useRef(null)
  const backgroundAgentKeyRef = useRef(null)
  const wakeActiveRef         = useRef(false)
  const convActiveRef         = useRef(false)
  const recognitionRef        = useRef(null)
  const vadRef                = useRef(null)
  const noSpeechRef           = useRef(null)

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

  const dismissFeaturedPanel = useCallback((id) => {
    setFeaturedPanels(prev => prev.filter(p => p.id !== id))
  }, [])

  // Persist alert history to localStorage so it survives page refreshes
  useEffect(() => {
    try {
      localStorage.setItem('tina_alerts', JSON.stringify(notificationHistory.slice(0, 30)))
    } catch {}
  }, [notificationHistory])

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

  // Poll pipeline state every 30s
  useEffect(() => {
    const check = () =>
      fetch('http://localhost:8000/api/pipeline')
        .then(r => r.json())
        .then(setPipeline)
        .catch(() => {})
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

  // All cross-referencing callbacks live here to avoid circular useCallback deps.
  // Updated each render so async callers always get the latest version.
  const cb = useRef({})

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
      audioCtxRef.current = new AudioContext({ sampleRate: 44100, latencyHint: 'playback' })
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

  const unlockAudio = useCallback(() => {
    const ctx = getAudioCtx()
    if (ctx.state === 'suspended') ctx.resume()
  }, [getAudioCtx])

  const sendMessage = useCallback(text => {
    unlockAudio()
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify({ type: 'message', text }))
  }, [unlockAudio])

  // Stop any in-progress recording (manual or VAD) and clear VAD timers
  const stopRecording = useCallback(() => {
    clearInterval(vadRef.current)
    clearTimeout(noSpeechRef.current)
    vadRef.current    = null
    noSpeechRef.current = null
    if (!mediaRef.current) return
    mediaRef.current.stop()
    mediaRef.current = null
    setIsRecording(false)
  }, [])

  // Manual hold-to-talk recording (no VAD)
  const startRecording = useCallback(async () => {
    unlockAudio()
    if (mediaRef.current || !wsRef.current) return
    try {
      const stream   = await navigator.mediaDevices.getUserMedia({ audio: micDeviceId ? { deviceId: { exact: micDeviceId } } : true })
      const mimeType = getMimeType()
      const rec      = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      chunksRef.current = []

      rec.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      rec.onstop = () => {
        const type = mimeType || 'audio/webm'
        const blob = new Blob(chunksRef.current, { type })
        blob.arrayBuffer().then(buf => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
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
  }, [unlockAudio])

  // Define cross-referencing functions on cb.current (updated each render)
  cb.current.stopWakeWord = () => {
    wakeActiveRef.current = false
    setWakeActive(false)
    if (recognitionRef.current) {
      try { recognitionRef.current.abort() } catch {}
      recognitionRef.current = null
    }
  }

  cb.current.exitConversation = () => {
    convActiveRef.current = false
    setConvActive(false)
    clearInterval(vadRef.current)
    clearTimeout(noSpeechRef.current)
    vadRef.current      = null
    noSpeechRef.current = null
    if (mediaRef.current) {
      try { mediaRef.current.stop() } catch {}
      mediaRef.current = null
    }
    setIsRecording(false)
    // Return to wake word mode after a short pause
    setTimeout(() => cb.current.startWakeWord(), 400)
  }

  cb.current.startVADRecording = async () => {
    unlockAudio()
    if (mediaRef.current || !wsRef.current || !convActiveRef.current) return
    try {
      const stream   = await navigator.mediaDevices.getUserMedia({ audio: micDeviceId ? { deviceId: { exact: micDeviceId } } : true })
      const mimeType = getMimeType()
      const rec      = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      chunksRef.current = []

      // Silence detection via time-domain RMS
      const audioCtx   = getAudioCtx()
      const source     = audioCtx.createMediaStreamSource(stream)
      const analyser   = audioCtx.createAnalyser()
      analyser.fftSize = 512
      source.connect(analyser)
      const buf        = new Uint8Array(analyser.frequencyBinCount)

      let hasSpeech    = false
      let speechStart  = null   // when speech first began
      let silenceStart = null

      // If user never speaks, exit conversation after NO_SPEECH_MS
      noSpeechRef.current = setTimeout(() => {
        if (!hasSpeech) cb.current.exitConversation()
      }, NO_SPEECH_MS)

      vadRef.current = setInterval(() => {
        analyser.getByteTimeDomainData(buf)
        const rms = Math.sqrt(buf.reduce((s, v) => s + (v - 128) ** 2, 0) / buf.length)

        if (rms > SILENCE_RMS) {
          // Speech detected
          if (!speechStart) speechStart = Date.now()
          hasSpeech    = true
          silenceStart = null
          clearTimeout(noSpeechRef.current)
          noSpeechRef.current = null
        } else if (hasSpeech && speechStart && Date.now() - speechStart > MIN_SPEECH_MS) {
          // Only start silence countdown after MIN_SPEECH_MS of actual speech
          if (!silenceStart) {
            silenceStart = Date.now()
          } else if (Date.now() - silenceStart > SILENCE_MS) {
            clearInterval(vadRef.current)
            vadRef.current = null
            if (mediaRef.current) {
              mediaRef.current.stop()
              mediaRef.current = null
              setIsRecording(false)
            }
          }
        }
      }, 80)

      rec.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      rec.onstop = () => {
        clearInterval(vadRef.current)
        clearTimeout(noSpeechRef.current)
        vadRef.current      = null
        noSpeechRef.current = null
        const type = mimeType || 'audio/webm'
        const blob = new Blob(chunksRef.current, { type })
        blob.arrayBuffer().then(arrayBuf => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'audio_meta', mimeType: type }))
            wsRef.current.send(arrayBuf)
          }
        })
        stream.getTracks().forEach(t => t.stop())
      }

      rec.start()
      mediaRef.current = rec
      setIsRecording(true)
    } catch (e) {
      console.error('VAD mic error:', e)
    }
  }

  cb.current.enterConversation = () => {
    cb.current.stopWakeWord()
    convActiveRef.current = true
    setConvActive(true)
    setTimeout(() => cb.current.startVADRecording(), 300)
  }

  cb.current.startWakeWord = () => {
    if (wakeActiveRef.current) return
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return  // Firefox — fall back to manual button

    wakeActiveRef.current = true
    setWakeActive(true)

    const tryStart = () => {
      if (!wakeActiveRef.current) return

      const recognition = new SR()
      recognition.continuous      = false   // fresh instance each cycle — more reliable than reusing
      recognition.interimResults  = false   // final results only — much more accurate
      recognition.lang            = 'en-AU' // Australian English to match Ky's accent
      recognition.maxAlternatives = 5       // check multiple recognition candidates

      recognitionRef.current = recognition

      recognition.onresult = (e) => {
        for (let i = 0; i < e.results.length; i++) {
          for (let j = 0; j < e.results[i].length; j++) {
            const t = e.results[i][j].transcript.toLowerCase().trim()
            // Match "tina" or common mishearings (Gina, Dina, Tena, Teena)
            if (/\b(tina|teena|tena|gina|dina|kina)\b/.test(t)) {
              recognitionRef.current = null
              wakeActiveRef.current  = false
              setWakeActive(false)
              setTimeout(() => cb.current.enterConversation(), 400)
              return
            }
          }
        }
      }

      // Restart with a fresh instance on end — avoids stale-state bugs in Chrome
      recognition.onend = () => {
        if (wakeActiveRef.current) setTimeout(tryStart, 150)
      }

      recognition.onerror = (e) => {
        if (e.error === 'not-allowed') {
          wakeActiveRef.current = false
          setWakeActive(false)
          return
        }
        // network/aborted/no-speech errors — just restart
        if (wakeActiveRef.current) setTimeout(tryStart, 500)
      }

      try { recognition.start() } catch { if (wakeActiveRef.current) setTimeout(tryStart, 500) }
    }

    tryStart()
  }

  // Stable wrappers for components to call
  const enterConversation = useCallback(() => cb.current.enterConversation(), [])
  const exitConversation  = useCallback(() => cb.current.exitConversation(),  [])
  const startWakeWord     = useCallback(() => cb.current.startWakeWord(),     [])

  const connect = useCallback(() => {
    if (wsRef.current) return
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      nextStartTimeRef.current = 0
      showAlert('tina online', 'tool')
      // Start wake word detection automatically on connect
      setTimeout(() => cb.current.startWakeWord(), 800)
    }

    ws.onmessage = async e => {
      const data = JSON.parse(e.data)
      switch (data.type) {
        case 'state':
          setTinaState(data.state)
          if (data.state === 'listening') {
            setActiveAgent(null)
            activeAgentKeyRef.current = backgroundAgentKeyRef.current
            setAgentStatuses(prev => {
              const next = { ...prev, tina: { ...prev.tina, status: 'listening', tool: null } }
              for (const key of Object.keys(next)) {
                if (key !== 'tina' && next[key].status !== 'running') {
                  next[key] = { ...next[key], status: 'idle', tool: null }
                }
              }
              return next
            })
            // VAD is started in audio_end (after audio finishes), not here —
            // the backend sends 'listening' before the browser has finished playing.
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
          // Notify TINA so she knows the agent completed and can chain the next task
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            const note = `[SYSTEM:agent_done] agent=${data.agent} display=${data.display} task_complete=true`
            wsRef.current.send(JSON.stringify({ type: 'message', text: note }))
          }
          break
        }
        case 'agent_done':
          setActiveAgent(null)
          activeAgentKeyRef.current = null
          setAgentStatuses(prev => {
            const next = { ...prev, tina: { ...prev.tina, tool: null } }
            for (const key of Object.keys(next)) {
              if (key !== 'tina') next[key] = { ...next[key], status: 'idle', tool: null }
            }
            return next
          })
          break
        case 'heard':
          addLine('kai', data.text)
          setLastResponse(null)
          setTurnCount(c => c + 1)
          // Entering conversation via button (not wake word) still sets convActive
          if (!convActiveRef.current) {
            convActiveRef.current = true
            setConvActive(true)
          }
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
            // Audio is fully done playing — safe to start listening now
            if (convActiveRef.current && !mediaRef.current) {
              setTimeout(() => cb.current.startVADRecording(), 500)
            }
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
        case 'featured_panel':
          setFeaturedPanels(prev => [...prev, { ...data }].slice(0, 6))
          setNotificationHistory(prev => [{
            id: data.id, title: data.title, color: data.color || '#8B5CF6',
            ts: data.ts || Date.now(),
          }, ...prev].slice(0, 30))
          break
        case 'kaos_live':
          setKaosLive({ ...data })
          break
        case 'stripe_live':
          setStripeLive({ ...data })
          break
        case 'morning_routine_start':
          setMorningActive(true)
          break
        case 'morning_routine_end':
          setMorningActive(false)
          break
        case 'wake_word_ready':
          setWakeWordActive(true)
          break
        case 'wake_word_detected':
          if (!convActiveRef.current) {
            enterConversation()
          }
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
      // Stop wake word + conversation on disconnect
      cb.current.stopWakeWord?.()
      convActiveRef.current = false
      setConvActive(false)
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

  return {
    connected, tinaState, isRecording, activeAgent, conversation,
    stats, voice, user, lastTool, alert, lastResponse,
    services, pipeline, turnCount, sessionStart, agentStatuses,
    diagRunning, diagResults, codePreviewFiles,
    panels, dismissPanel, featuredPanels, dismissFeaturedPanel,
    morningActive, wakeWordActive,
    kaosLive, stripeLive, notificationHistory,
    activityLogVisible,
    wakeActive, convActive,
    sendMessage, startRecording, stopRecording,
    enterConversation, exitConversation, startWakeWord,
  }
}
