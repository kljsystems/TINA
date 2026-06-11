import { useRef, useCallback, useEffect } from 'react'

const P  = '#8B5CF6'
const PG = '#A78BFA'

// Target values per state — lerped toward each frame
export const STATE_CFG = {
  listening:   { label: 'READY',       sub: 'Awaiting input',      rotSpeed: 0.18, nodeGlow: 0.42, connAlpha: 0.16, pulseAmp: 0.06, speakAmp: 0,   thinkAmp: 0,   glow: 0.38, breathSpeed: 0.5  },
  thinking:    { label: 'PROCESSING',  sub: 'Analysing request',   rotSpeed: 0.90, nodeGlow: 0.74, connAlpha: 0.38, pulseAmp: 0.22, speakAmp: 0,   thinkAmp: 1.0, glow: 0.65, breathSpeed: 1.2  },
  speaking:    { label: 'RESPONDING',  sub: 'Transmitting...',     rotSpeed: 0.38, nodeGlow: 0.88, connAlpha: 0.44, pulseAmp: 0.28, speakAmp: 1.0, thinkAmp: 0,   glow: 0.85, breathSpeed: 1.8  },
  standby:     { label: 'STANDBY',     sub: 'System idle',         rotSpeed: 0.06, nodeGlow: 0.14, connAlpha: 0.05, pulseAmp: 0.02, speakAmp: 0,   thinkAmp: 0,   glow: 0.13, breathSpeed: 0.3  },
  offline:     { label: 'OFFLINE',     sub: 'No connection',       rotSpeed: 0.03, nodeGlow: 0.07, connAlpha: 0.02, pulseAmp: 0,   speakAmp: 0,   thinkAmp: 0,   glow: 0.07, breathSpeed: 0.2  },
  diagnostics: { label: 'DIAGNOSTICS', sub: 'Running system scan', rotSpeed: 0.65, nodeGlow: 0.62, connAlpha: 0.30, pulseAmp: 0.18, speakAmp: 0.3, thinkAmp: 0.5, glow: 0.58, breathSpeed: 1.0  },
}

// ── Sphere geometry (seeded random to stay stable across renders) ─────────────

function seededRand(seed) {
  let s = seed
  return () => { s = (s * 16807 + 0) % 2147483647; return (s - 1) / 2147483646 }
}

function buildGeometry() {
  const rand = seededRand(42)
  const goldenAngle = Math.PI * (3 - Math.sqrt(5))
  const N = 72

  // Fibonacci sphere distribution
  const nodes = Array.from({ length: N }, (_, i) => {
    const y = 1 - (i / (N - 1)) * 2
    const r = Math.sqrt(Math.max(0, 1 - y * y))
    const t = goldenAngle * i
    return { x: Math.cos(t) * r, y, z: Math.sin(t) * r, phase: rand() * Math.PI * 2, isEye: false }
  })

  // Two eye nodes — slightly above equator, facing forward
  const rawEyes = [
    { x: -0.42, y: 0.36, z: 0.84 },
    { x:  0.42, y: 0.36, z: 0.84 },
  ]
  rawEyes.forEach(e => {
    const len = Math.sqrt(e.x ** 2 + e.y ** 2 + e.z ** 2)
    nodes.push({ x: e.x / len, y: e.y / len, z: e.z / len, phase: rand() * Math.PI * 2, isEye: true })
  })

  // Nearest-neighbour connections (k=3 per node, deduplicated)
  const seen = new Set()
  const connections = []
  nodes.forEach((n, i) => {
    nodes
      .map((m, j) => ({ j, d: (n.x - m.x) ** 2 + (n.y - m.y) ** 2 + (n.z - m.z) ** 2 }))
      .filter(({ j }) => j !== i)
      .sort((a, b) => a.d - b.d)
      .slice(0, 3)
      .forEach(({ j }) => {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`
        if (!seen.has(key)) { seen.add(key); connections.push([i, j]) }
      })
  })

  return { nodes, connections }
}

// Geometry is fixed — computed once at module load, no rerenders
const GEOMETRY = buildGeometry()

// ── RAF helper ────────────────────────────────────────────────────────────────

function useRAF(cb) {
  const rafRef  = useRef()
  const prevRef = useRef()
  useEffect(() => {
    const loop = t => {
      if (prevRef.current !== undefined) cb(t - prevRef.current)
      prevRef.current = t
      rafRef.current  = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(rafRef.current)
  }, [cb])
}

function lerp(a, b, t) { return a + (b - a) * t }

// ── Component ─────────────────────────────────────────────────────────────────

export default function TinaFace({ state = 'listening', size = 420, ringColor = PG, glowColor = P }) {
  const canvasRef  = useRef()
  const rotY       = useRef(0)
  const wavePhase  = useRef(0)
  const time       = useRef(0)

  const { nodes, connections } = GEOMETRY

  const live = useRef({
    rotSpeed:    STATE_CFG.listening.rotSpeed,
    nodeGlow:    STATE_CFG.listening.nodeGlow,
    connAlpha:   STATE_CFG.listening.connAlpha,
    pulseAmp:    STATE_CFG.listening.pulseAmp,
    speakAmp:    STATE_CFG.listening.speakAmp,
    thinkAmp:    STATE_CFG.listening.thinkAmp,
    glow:        STATE_CFG.listening.glow,
    breathSpeed: STATE_CFG.listening.breathSpeed,
  })

  const sc  = size / 320
  const cfg = STATE_CFG[state] ?? STATE_CFG.listening

  useRAF(useCallback((deltaMs) => {
    const c = canvasRef.current
    if (!c) return
    const ctx = c.getContext('2d')
    const cx  = c.width  / 2
    const cy  = c.height / 2
    const dt  = Math.min(deltaMs / 1000, 0.05)

    time.current      += dt
    wavePhase.current += dt * (0.9 + live.current.speakAmp * 1.6)

    // Lerp live values toward current state target
    const α  = Math.min(1, dt * 3)
    const lv = live.current
    lv.rotSpeed    = lerp(lv.rotSpeed,    cfg.rotSpeed,    α)
    lv.nodeGlow    = lerp(lv.nodeGlow,    cfg.nodeGlow,    α)
    lv.connAlpha   = lerp(lv.connAlpha,   cfg.connAlpha,   α)
    lv.pulseAmp    = lerp(lv.pulseAmp,    cfg.pulseAmp,    α)
    lv.speakAmp    = lerp(lv.speakAmp,    cfg.speakAmp,    α)
    lv.thinkAmp    = lerp(lv.thinkAmp,    cfg.thinkAmp,    α)
    lv.glow        = lerp(lv.glow,        cfg.glow,        α)
    lv.breathSpeed = lerp(lv.breathSpeed, cfg.breathSpeed, α)

    rotY.current += lv.rotSpeed * dt

    // X-axis tilt — organic sway + thinking wobble
    const rotX = Math.sin(time.current * 0.38) * 0.15
               + lv.thinkAmp * Math.sin(time.current * 1.85) * 0.28

    const cosY = Math.cos(rotY.current), sinY = Math.sin(rotY.current)
    const cosX = Math.cos(rotX),         sinX = Math.sin(rotX)

    const sr = 116 * sc  // sphere radius in pixels

    // ── Project all nodes ─────────────────────────────────────────────────────
    const projected = nodes.map(n => {
      // Rotate around Y axis
      const x1 =  n.x * cosY - n.z * sinY
      const z1 =  n.x * sinY + n.z * cosY
      // Rotate around X axis
      const y2 =  n.y * cosX - z1 * sinX
      const z2 =  n.y * sinX + z1 * cosX

      // Soft perspective projection
      const persp = 2.8
      const fov   = persp / (persp + z2 + 1)
      const px    = cx + x1 * sr * persp * fov
      const py    = cy - y2 * sr * persp * fov

      // Depth: 0 = furthest back, 1 = closest front
      const depth = (z2 + 1) / 2

      // Speaking wave: latitude bands ripple bottom→top
      const speakWave = lv.speakAmp > 0.01
        ? Math.max(0, Math.sin(wavePhase.current * 2.4 - n.y * Math.PI * 2.6))
        : 0

      // Thinking scan: a plane sweeps left→right through the sphere
      const scanX     = Math.sin(time.current * 2.2)
      const scanBoost = lv.thinkAmp * Math.max(0, 1 - Math.abs(x1 - scanX * 0.85) / 0.20) * 0.75

      return { px, py, depth, speakWave, scanBoost, n }
    })

    ctx.clearRect(0, 0, c.width, c.height)

    // ── Connections ───────────────────────────────────────────────────────────
    ctx.lineWidth = 0.85 * sc
    connections.forEach(([i, j]) => {
      const a = projected[i]
      const b = projected[j]
      const avgDepth = (a.depth + b.depth) / 2
      if (avgDepth < 0.08) return

      const speakBoost = (a.speakWave + b.speakWave) * 0.5
      const thinkBoost = (a.scanBoost + b.scanBoost) * 0.5
      const alpha = lv.connAlpha * avgDepth * (0.45 + 0.55 * avgDepth)
                  + speakBoost * 0.13 * lv.speakAmp
                  + thinkBoost * 0.10

      if (alpha < 0.005) return

      ctx.beginPath()
      ctx.moveTo(a.px, a.py)
      ctx.lineTo(b.px, b.py)
      ctx.strokeStyle = ringColor
      ctx.globalAlpha = Math.min(0.85, alpha)
      ctx.shadowColor = glowColor
      ctx.shadowBlur  = avgDepth > 0.72 && (speakBoost > 0.35 || thinkBoost > 0.3) ? 7 : 0
      ctx.stroke()
    })
    ctx.globalAlpha = 1
    ctx.shadowBlur  = 0

    // ── Nodes (back → front) ──────────────────────────────────────────────────
    const sorted = [...projected].sort((a, b) => a.depth - b.depth)

    sorted.forEach(({ px, py, depth, speakWave, scanBoost, n }) => {
      const pulse     = 1 + lv.pulseAmp * Math.sin(time.current * lv.breathSpeed * 2.3 + n.phase)
      const speakMult = 1 + speakWave * 0.7 * lv.speakAmp
      const thinkMult = 1 + scanBoost * 0.6
      const eyeMult   = n.isEye ? 2.6 : 1.0

      const baseR = 3.0 * sc
      const r     = baseR * (0.32 + 0.68 * depth) * pulse * speakMult * eyeMult
      const alpha = lv.nodeGlow * (0.15 + 0.85 * depth) * pulse * speakMult * thinkMult
                  * (n.isEye ? 1.5 : 1.0)

      ctx.beginPath()
      ctx.arc(px, py, r, 0, Math.PI * 2)
      ctx.fillStyle   = ringColor
      ctx.globalAlpha = Math.min(0.98, alpha)
      ctx.shadowColor = glowColor
      ctx.shadowBlur  = depth > 0.62
        ? (n.isEye ? 18 : 9) * depth * (1 + speakWave * lv.speakAmp)
        : 0
      ctx.fill()
    })
    ctx.globalAlpha = 1
    ctx.shadowBlur  = 0

    // ── Centre glow ───────────────────────────────────────────────────────────
    const heartbeat = 1
      + 0.035 * Math.sin(time.current * 1.4)
      + 0.012 * Math.sin(time.current * 2.85)
      + (lv.speakAmp > 0.1 ? 0.048 * Math.sin(time.current * 5.1) : 0)

    const cR   = 34 * sc * lv.glow * heartbeat
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, cR * 1.6)
    const hex  = v => Math.round(Math.min(1, v) * 255).toString(16).padStart(2, '0')
    grad.addColorStop(0,    glowColor + hex(lv.glow))
    grad.addColorStop(0.45, glowColor + hex(lv.glow * 0.48))
    grad.addColorStop(1,    glowColor + '00')

    ctx.beginPath()
    ctx.arc(cx, cy, cR, 0, Math.PI * 2)
    ctx.fillStyle   = grad
    ctx.shadowColor = glowColor
    ctx.shadowBlur  = 28 * lv.glow
    ctx.fill()
    ctx.shadowBlur  = 0

  }, [state, sc, ringColor, glowColor, cfg]))

  return (
    <canvas ref={canvasRef} width={size} height={size} style={{ display: 'block' }} />
  )
}
