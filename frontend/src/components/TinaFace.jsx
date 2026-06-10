import { useRef, useCallback, useEffect } from 'react'

const P  = '#8B5CF6'
const PG = '#A78BFA'

// Target values per state — lerped toward each frame
export const STATE_CFG = {
  listening:   { label: 'READY',        sub: 'Awaiting input',       speeds: [20, 26, 34], opacities: [0.28, 0.18, 0.11], glow: 0.38, breathAmp: 0.018, breathSpeed: 0.5  },
  thinking:    { label: 'PROCESSING',  sub: 'Analysing request...', speeds: [6,  9,  13], opacities: [0.6,  0.42, 0.26], glow: 0.65, breathAmp: 0.030, breathSpeed: 1.2  },
  speaking:    { label: 'RESPONDING',  sub: 'Transmitting...',      speeds: [4,  6,  9 ], opacities: [0.78, 0.55, 0.34], glow: 0.85, breathAmp: 0.040, breathSpeed: 1.8  },
  standby:     { label: 'STANDBY',     sub: 'System idle',          speeds: [38, 52, 68], opacities: [0.09, 0.06, 0.04], glow: 0.13, breathAmp: 0.010, breathSpeed: 0.3  },
  offline:     { label: 'OFFLINE',     sub: 'No connection',        speeds: [55, 70, 90], opacities: [0.05, 0.04, 0.03], glow: 0.07, breathAmp: 0.005, breathSpeed: 0.2  },
  diagnostics: { label: 'DIAGNOSTICS', sub: 'Running system scan',  speeds: [4,  6,  9 ], opacities: [0.65, 0.48, 0.30], glow: 0.58, breathAmp: 0.025, breathSpeed: 1.0  },
}

function useRAF(cb) {
  const rafRef  = useRef()
  const prevRef = useRef()
  useEffect(() => {
    const loop = t => {
      if (prevRef.current !== undefined) cb(t - prevRef.current, t)
      prevRef.current = t
      rafRef.current  = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(rafRef.current)
  }, [cb])
}

function lerp(a, b, t) { return a + (b - a) * t }
function lerpArr(a, b, t) { return a.map((v, i) => lerp(v, b[i], t)) }

export default function TinaFace({ state, size = 420, ringColor = '#A78BFA', glowColor = '#8B5CF6' }) {
  const canvasRef = useRef()
  const angles    = useRef([0, 0, 0])
  const wave      = useRef(0)
  const time      = useRef(0)

  // Lerped live values
  const live = useRef({
    speeds:     [...STATE_CFG.listening.speeds],
    opacities:  [...STATE_CFG.listening.opacities],
    glow:       STATE_CFG.listening.glow,
    breathAmp:  STATE_CFG.listening.breathAmp,
    breathSpeed:STATE_CFG.listening.breathSpeed,
  })

  const sc  = size / 320
  const cfg = STATE_CFG[state] ?? STATE_CFG.listening

  useRAF(useCallback((delta, t) => {
    const c = canvasRef.current
    if (!c) return
    const ctx = c.getContext('2d')
    const cx  = c.width / 2
    const cy  = c.height / 2
    const dt  = delta / 1000

    time.current += dt
    wave.current += delta * 0.0022

    // Lerp live values toward current state target
    const α   = Math.min(1, dt * 3)   // transition speed
    const lv  = live.current
    lv.speeds     = lerpArr(lv.speeds,     cfg.speeds,     α)
    lv.opacities  = lerpArr(lv.opacities,  cfg.opacities,  α)
    lv.glow       = lerp(lv.glow,          cfg.glow,        α)
    lv.breathAmp  = lerp(lv.breathAmp,     cfg.breathAmp,   α)
    lv.breathSpeed= lerp(lv.breathSpeed,   cfg.breathSpeed, α)

    ctx.clearRect(0, 0, c.width, c.height)

    // ── Three orbital rings ───────────────────────────────────────────────────
    const baseRadii = [90, 115, 140]

    baseRadii.map(r => r * sc).forEach((baseR, i) => {
      // Organic breathing — compound oscillation
      const breathe = 1
        + lv.breathAmp * Math.sin(time.current * lv.breathSpeed + i * 1.3)
        + lv.breathAmp * 0.3 * Math.sin(time.current * lv.breathSpeed * 1.7 + i * 0.7)
      const r = baseR * breathe

      angles.current[i] += (1 / lv.speeds[i]) * dt * Math.PI * 2 * (i % 2 === 0 ? 1 : -1)
      const a   = angles.current[i]

      // Gap also breathes slightly
      const gap = ([0.35, 0.28, 0.22][i]) * (1 + 0.06 * Math.sin(time.current * lv.breathSpeed * 0.8 + i))

      ctx.beginPath()
      ctx.arc(cx, cy, r, a + gap, a + Math.PI * 2 - gap)
      ctx.strokeStyle = ringColor
      ctx.globalAlpha = lv.opacities[i]
      ctx.lineWidth   = i === 0 ? 2.5 * sc : 2 * sc
      ctx.shadowColor = glowColor
      ctx.shadowBlur  = 18
      ctx.stroke()

      // Endpoint dots — pulse with breathing
      const dotR = (3.5 + 0.6 * Math.sin(time.current * lv.breathSpeed * 1.5 + i)) * sc
      for (const ang of [a + gap, a + Math.PI * 2 - gap]) {
        ctx.beginPath()
        ctx.arc(cx + Math.cos(ang) * r, cy + Math.sin(ang) * r, dotR, 0, Math.PI * 2)
        ctx.fillStyle   = ringColor
        ctx.globalAlpha = lv.opacities[i] * 1.8
        ctx.shadowBlur  = 14
        ctx.fill()
      }

      ctx.globalAlpha = 1
      ctx.shadowBlur  = 0
    })

    // ── Speaking — layered waveform rings ────────────────────────────────────
    if (state === 'speaking') {
      const waveConfigs = [
        { r: 165, amp: 5,   freq1: 0.42, freq2: 0.16, speed: 1.0, alpha: 0.45 },
        { r: 174, amp: 3,   freq1: 0.38, freq2: 0.22, speed: 1.3, alpha: 0.20 },
        { r: 156, amp: 3.5, freq1: 0.55, freq2: 0.12, speed: 0.7, alpha: 0.15 },
      ]
      waveConfigs.forEach(({ r, amp, freq1, freq2, speed, alpha }) => {
        const wr = r * sc
        const a  = amp * sc * (1 + 0.25 * Math.sin(time.current * 3.5))
        ctx.beginPath()
        for (let s = 0; s <= 80; s++) {
          const th = (s / 80) * Math.PI * 2
          const displacement = a
            * Math.sin(s * freq1 + wave.current * speed)
            * Math.sin(s * freq2 + wave.current * speed * 0.6)
          const x = cx + Math.cos(th) * (wr + displacement)
          const y = cy + Math.sin(th) * (wr + displacement)
          s === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
        }
        ctx.closePath()
        ctx.strokeStyle = ringColor
        ctx.globalAlpha = alpha
        ctx.lineWidth   = 1.5
        ctx.shadowColor = glowColor
        ctx.shadowBlur  = 12
        ctx.stroke()
        ctx.globalAlpha = 1
        ctx.shadowBlur  = 0
      })
    }

    // ── Thinking — orbiting particles with trails ─────────────────────────────
    if (state === 'thinking') {
      const orbitR  = 70 * sc
      const pCount  = 8
      for (let p = 0; p < pCount; p++) {
        // Accelerating orbit — particles speed up over time with oscillation
        const speed = 0.0018 + 0.0006 * Math.sin(time.current * 0.8 + p)
        const pa    = time.current * speed * Math.PI * 2 * 60 + (p / pCount) * Math.PI * 2
        const pr    = orbitR + Math.sin(time.current * 2.1 + p * 1.3) * 14 * sc

        // Trail — draw fading copies behind each particle
        for (let tr = 4; tr >= 0; tr--) {
          const trailOffset = tr * 0.08
          const trailAngle  = pa - trailOffset * (i => i % 2 === 0 ? 1 : -1)(p)
          const trailR      = orbitR + Math.sin(time.current * 2.1 - trailOffset + p * 1.3) * 14 * sc
          ctx.beginPath()
          ctx.arc(
            cx + Math.cos(trailAngle) * trailR,
            cy + Math.sin(trailAngle) * trailR,
            (3 - tr * 0.4) * sc, 0, Math.PI * 2
          )
          ctx.fillStyle   = ringColor
          ctx.globalAlpha = (0.65 + 0.35 * Math.sin(time.current * 2.5 + p)) * (1 - tr * 0.18)
          ctx.shadowColor = ringColor
          ctx.shadowBlur  = tr === 0 ? 12 : 4
          ctx.fill()
          ctx.globalAlpha = 1
          ctx.shadowBlur  = 0
        }
      }
    }

    // ── Diagnostics — rotating sweep ─────────────────────────────────────────
    if (state === 'diagnostics') {
      const sr = 145 * sc
      const sa = (time.current % 1) * Math.PI * 2 * 1.2
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.arc(cx, cy, sr, sa - 0.6, sa)
      ctx.closePath()
      ctx.fillStyle   = ringColor
      ctx.globalAlpha = 0.14
      ctx.fill()
      ctx.globalAlpha = 1

      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.lineTo(cx + Math.cos(sa) * sr, cy + Math.sin(sa) * sr)
      ctx.strokeStyle = ringColor
      ctx.globalAlpha = 0.7
      ctx.lineWidth   = 1.5
      ctx.shadowColor = ringColor
      ctx.shadowBlur  = 10
      ctx.stroke()
      ctx.globalAlpha = 1
      ctx.shadowBlur  = 0
    }

    // ── Centre glow — heartbeat pulse ────────────────────────────────────────
    const heartbeat = 1
      + 0.04 * Math.sin(time.current * 1.4)
      + 0.015 * Math.sin(time.current * 2.8)
      + (state === 'speaking' ? 0.05 * Math.sin(time.current * 5.0) : 0)
    const cR   = 40 * sc * lv.glow * heartbeat
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, cR * 1.4)
    const gh   = Math.round(lv.glow * 255).toString(16).padStart(2, '0')
    const gh2  = Math.round(lv.glow * 0.6 * 255).toString(16).padStart(2, '0')
    grad.addColorStop(0,   glowColor + gh)
    grad.addColorStop(0.4, glowColor + gh2)
    grad.addColorStop(1,   glowColor + '00')
    ctx.beginPath()
    ctx.arc(cx, cy, cR, 0, Math.PI * 2)
    ctx.fillStyle   = grad
    ctx.shadowColor = glowColor
    ctx.shadowBlur  = 35 * lv.glow
    ctx.fill()
    ctx.shadowBlur  = 0

    // ── Tick marks ───────────────────────────────────────────────────────────
    for (let tk = 0; tk < 36; tk++) {
      const ta = (tk / 36) * Math.PI * 2
      const major = tk % 9 === 0
      const r1 = (major ? 52 : 54) * sc
      const r2 = (major ? 62 : 58) * sc
      ctx.beginPath()
      ctx.moveTo(cx + Math.cos(ta) * r1, cy + Math.sin(ta) * r1)
      ctx.lineTo(cx + Math.cos(ta) * r2, cy + Math.sin(ta) * r2)
      ctx.strokeStyle = ringColor
      ctx.globalAlpha = major ? 0.5 : 0.2
      ctx.lineWidth   = major ? 1.5 : 0.75
      ctx.stroke()
      ctx.globalAlpha = 1
    }
  }, [state, sc, ringColor, glowColor, cfg]))

  return (
    <canvas ref={canvasRef} width={size} height={size} style={{ display: 'block' }} />
  )
}
