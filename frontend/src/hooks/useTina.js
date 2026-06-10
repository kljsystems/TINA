import { useState, useEffect, useCallback, useRef } from 'react'

const WS_URL = 'ws://localhost:8000/ws'
const RECONNECT_MS = 3000

export function useTina() {
  const [connected, setConnected] = useState(false)
  const [tinaState, setTinaState] = useState('offline')
  const [conversation, setConversation] = useState([
    { role: 'tina', text: 'all systems online. ready when you are.' },
  ])
  const [stats, setStats] = useState({ facts: 0, sessions: 0, tools: 5 })
  const [voice, setVoice] = useState('Daniel')
  const [user, setUser] = useState({ name: 'Kai', location: '—' })
  const [lastTool, setLastTool] = useState({ name: '—', time: '—' })
  const [alert, setAlert] = useState(null)

  const wsRef = useRef(null)
  const alertTimerRef = useRef(null)

  const showAlert = useCallback((msg, type = 'tool') => {
    if (alertTimerRef.current) clearTimeout(alertTimerRef.current)
    setAlert({ msg, type })
    alertTimerRef.current = setTimeout(() => setAlert(null), 3000)
  }, [])

  const addLine = useCallback((role, text) => {
    setConversation(prev => [...prev, { role, text }].slice(-3))
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current) return
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      showAlert('tina online', 'tool')
    }

    ws.onmessage = e => {
      const data = JSON.parse(e.data)
      switch (data.type) {
        case 'state':
          setTinaState(data.state)
          break
        case 'heard':
          addLine('kai', data.text)
          break
        case 'response':
          addLine('tina', data.text)
          break
        case 'tool':
          setLastTool({ name: data.name, time: data.time ?? '—' })
          showAlert('tool: ' + data.name)
          break
        case 'system':
          if (data.voice) setVoice(data.voice)
          if (data.user) setUser(u => ({ ...u, name: data.user }))
          if (data.facts !== undefined) setStats(s => ({ ...s, facts: data.facts }))
          if (data.sessions !== undefined) setStats(s => ({ ...s, sessions: data.sessions }))
          if (data.tools !== undefined) setStats(s => ({ ...s, tools: data.tools }))
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
  }, [showAlert, addLine])

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
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'message', text }))
    }
  }, [])

  return { connected, tinaState, conversation, stats, voice, user, lastTool, alert, sendMessage }
}
