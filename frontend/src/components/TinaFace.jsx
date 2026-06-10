import { useRef, useCallback, useEffect } from 'react'

const P  = '#8B5CF6'
const PG = '#A78BFA'

export const STATE_CFG = {
  listening:   { label: 'LISTENING',   sub: 'Awaiting input',        speeds: [18, 24, 30], opacities: [0.25, 0.18, 0.12], glow: 0.4  },
  thinking:    { label: 'PROCESSING',  sub: 'Analysing request...',  speeds: [6,  9,  12], opacities: [0.6,  0.45, 0.3 ], glow: 0.7  },
  speaking:    { label: 'RESPONDING',  sub: 'Transmitting...',       speeds: [4,  6,  8 ], opacities: [0.8,  0.6,  0.4 ], glow: 1.0  },
  standby:     { label: 'STANDBY',     sub: 'System idle',           speeds: [30, 40, 50], opacities: [0.1,  0.07, 0.05], glow: 0.15 },
  offline:     { label: 'OFFLINE',     sub: 'No connection',         speeds: [40, 55, 70], opacities: [0.08, 0.05, 0.03], glow: 0.08 },
  diagnostics: { label: 'DIAGNOSTICS', sub: 'Running system scan',   speeds: [3,  5,  7 ], opacities: [0.7,  0.55, 0.35], glow: 0.6  },
}

function useRAF(cb) {
  const rafRef  = useRef()
  const prevRef = useRef()
  useEffect(() => {
    const loop = t => {
      if (prevRef.current) cb(t - prevRef.current, t)
      prevRef.current = t
      rafRef.current  = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(rafRef.current)
  }, [cb])
}

export default function TinaFace({ state, size = 420, ringColor = '#A78BFA', glowColor = '#8B5CF6' }) {
  const canvasRef = useRef()
  const angles    = useRef([0, 0, 0])
  const wave      = useRef(0)
  const cfg       = STATE_CFG[state] ?? STATE_CFG.listening
  const sc        = size / 320  // scale factor

  useRAF(useCallback((delta, time) => {
    const c = canvasRef.current
    if (!c) return
    const ctx = c.getContext('2d')
    const cx = c.width / 2, cy = c.height / 2

    ctx.clearRect(0, 0, c.width, c.height)

    // Three arcs
    ;[90, 115, 140].map(r => r * sc).forEach((r, i) => {
      angles.current[i] += (1 / cfg.speeds[i]) * (delta / 1000) * Math.PI * 2 * (i % 2 === 0 ? 1 : -1)
      const a   = angles.current[i]
      const gap = [0.35, 0.28, 0.22][i]

      ctx.beginPath()
      ctx.arc(cx, cy, r, a + gap, a + Math.PI * 2 - gap)
      ctx.strokeStyle = ringColor
      ctx.globalAlpha = cfg.opacities[i]
      ctx.lineWidth   = i === 0 ? 2.5 : 2
      ctx.shadowColor = glowColor
      ctx.shadowBlur  = 14
      ctx.stroke()

      for (const ang of [a + gap, a + Math.PI * 2 - gap]) {
        ctx.beginPath()
        ctx.arc(cx + Math.cos(ang) * r, cy + Math.sin(ang) * r, 3.5 * sc, 0, Math.PI * 2)
        ctx.fillStyle   = ringColor
        ctx.globalAlpha = cfg.opacities[i] * 1.5
        ctx.shadowBlur  = 10
        ctx.fill()
      }
    })

    ctx.globalAlpha = 1
    ctx.shadowBlur  = 0

    // Speaking — outer wave ring
    if (state === 'speaking') {
      wave.current += delta * 0.005
      const wr = 165 * sc
      ctx.beginPath()
      for (let s = 0; s <= 80; s++) {
        const th  = (s / 80) * Math.PI * 2
        const amp = 9 * sc * Math.sin(s * 0.4 + wave.current) * Math.sin(s * 0.15 + wave.current * 0.7)
        const x   = cx + Math.cos(th) * (wr + amp)
        const y   = cy + Math.sin(th) * (wr + amp)
        s === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
      }
      ctx.closePath()
      ctx.strokeStyle = ringColor
      ctx.globalAlpha = 0.5
      ctx.lineWidth   = 1.5
      ctx.shadowColor = glowColor
      ctx.shadowBlur  = 10
      ctx.stroke()
      ctx.globalAlpha = 1
      ctx.shadowBlur  = 0
    }

    // Diagnostics — rotating sweep
    if (state === 'diagnostics') {
      const sr = 145 * sc
      const sa = ((time * 0.001) % 1) * Math.PI * 2
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.arc(cx, cy, sr, sa - 0.5, sa)
      ctx.closePath()
      ctx.fillStyle   = ringColor
      ctx.globalAlpha = 0.12
      ctx.fill()
      ctx.globalAlpha = 1
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.lineTo(cx + Math.cos(sa) * sr, cy + Math.sin(sa) * sr)
      ctx.strokeStyle = ringColor
      ctx.globalAlpha = 0.6
      ctx.lineWidth   = 1
      ctx.shadowColor = ringColor
      ctx.shadowBlur  = 8
      ctx.stroke()
      ctx.globalAlpha = 1
      ctx.shadowBlur  = 0
    }

    // Thinking — orbiting particles
    if (state === 'thinking') {
      const pr0 = 70 * sc
      for (let p = 0; p < 6; p++) {
        const pa = time * 0.0015 + (p / 6) * Math.PI * 2
        const pr = pr0 + Math.sin(time * 0.002 + p) * 12 * sc
        ctx.beginPath()
        ctx.arc(cx + Math.cos(pa) * pr, cy + Math.sin(pa) * pr, 3 * sc, 0, Math.PI * 2)
        ctx.fillStyle   = ringColor
        ctx.globalAlpha = 0.6 + 0.4 * Math.sin(time * 0.003 + p)
        ctx.shadowColor = ringColor
        ctx.shadowBlur  = 10
        ctx.fill()
        ctx.globalAlpha = 1
        ctx.shadowBlur  = 0
      }
    }

    // Centre glow — parse glowColor to rgba
    const cR   = 40 * sc * (cfg.glow + 0.02 * Math.sin(time * 0.003))
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, cR * 1.2)
    grad.addColorStop(0,   glowColor + Math.round(cfg.glow * 255).toString(16).padStart(2,'0'))
    grad.addColorStop(0.4, glowColor + Math.round(cfg.glow * 0.7 * 255).toString(16).padStart(2,'0'))
    grad.addColorStop(1,   glowColor + '00')
    ctx.beginPath()
    ctx.arc(cx, cy, cR, 0, Math.PI * 2)
    ctx.fillStyle   = grad
    ctx.shadowColor = glowColor
    ctx.shadowBlur  = 30 * cfg.glow
    ctx.fill()
    ctx.shadowBlur  = 0

    // Tick marks
    for (let t = 0; t < 36; t++) {
      const ta = (t / 36) * Math.PI * 2
      const m  = t % 9 === 0
      const r1 = (m ? 52 : 54) * sc
      const r2 = (m ? 62 : 58) * sc
      ctx.beginPath()
      ctx.moveTo(cx + Math.cos(ta) * r1, cy + Math.sin(ta) * r1)
      ctx.lineTo(cx + Math.cos(ta) * r2, cy + Math.sin(ta) * r2)
      ctx.strokeStyle = ringColor
      ctx.globalAlpha = m ? 0.5 : 0.2
      ctx.lineWidth   = m ? 1.5 : 0.75
      ctx.stroke()
      ctx.globalAlpha = 1
    }
  }, [state, sc, ringColor, glowColor]))

  return (
    <canvas ref={canvasRef} width={size} height={size} style={{ display: 'block' }} />
  )
}
