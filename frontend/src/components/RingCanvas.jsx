import { useEffect, useRef } from 'react'

const RINGS = [
  { r: 148, spd: 0.003,  dash: [12, 10], base: 'rgba(55,138,221,',  w: 1.5 },
  { r: 133, spd: -0.006, dash: [5, 14],  base: 'rgba(29,158,117,',  w: 1   },
  { r: 116, spd: 0.011,  dash: [3, 10],  base: 'rgba(55,138,221,',  w: 0.5 },
  { r: 96,  spd: -0.017, dash: [8, 6],   base: 'rgba(133,183,235,', w: 1   },
  { r: 74,  spd: 0.024,  dash: [4, 8],   base: 'rgba(29,158,117,',  w: 0.5 },
]
const BASE_ALPHA = [0.5, 0.4, 0.3, 0.35, 0.5]

const STATE_PARAMS = {
  speaking: { alpha: 1.4, speed: 2.2, pulse: 0.08, base: 'rgba(133,183,235,' },
  thinking: { alpha: 1.1, speed: 1.5, pulse: 0.04, base: 'rgba(55,138,221,'  },
  standby:  { alpha: 0.3, speed: 0.4, pulse: 0,    base: 'rgba(55,138,221,'  },
  offline:  { alpha: 0.15,speed: 0.2, pulse: 0,    base: 'rgba(226,75,74,'   },
  listening:{ alpha: 0.8, speed: 1,   pulse: 0.02, base: 'rgba(55,138,221,'  },
}

export default function RingCanvas({ state }) {
  const canvasRef = useRef(null)
  const stateRef  = useRef(state)

  useEffect(() => { stateRef.current = state }, [state])

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const dots = RINGS.map(() => ({
      a1: Math.random() * Math.PI * 2,
      a2: Math.random() * Math.PI * 2,
    }))

    let curAlpha = 1, curSpeed = 1, curPulse = 0, wavePhase = 0, rafId

    function draw(ts) {
      const t = ts * 0.001
      wavePhase += 0.05
      const s = stateRef.current
      const p = STATE_PARAMS[s] ?? STATE_PARAMS.listening

      curAlpha += (p.alpha - curAlpha) * 0.04
      curSpeed += (p.speed - curSpeed) * 0.03
      curPulse += (p.pulse - curPulse) * 0.05

      const cx = 160, cy = 160
      ctx.clearRect(0, 0, 320, 320)

      const sw = s === 'speaking' ? Math.sin(wavePhase) * 0.06 : 0
      const freq = s === 'speaking' ? 12 : s === 'thinking' ? 6 : 3
      const pulse = 1 + curPulse * Math.sin(t * freq) + sw

      RINGS.forEach((ring, ri) => {
        const angle = ring.spd * t * 60 * curSpeed
        const r     = ring.r * pulse * (1 + sw * (ri % 2 === 0 ? 1 : -1) * 0.5)
        const alpha = (BASE_ALPHA[ri] * curAlpha).toFixed(2)
        const col   = p.base + alpha + ')'

        ctx.save()
        ctx.translate(cx, cy)
        ctx.rotate(angle)
        ctx.beginPath()
        ctx.arc(0, 0, r, 0, Math.PI * 2)
        ctx.setLineDash(ring.dash)
        ctx.strokeStyle = col
        ctx.lineWidth = ring.w * (s === 'speaking' ? 1.5 + Math.abs(sw) * 4 : 1)
        ctx.stroke()
        ctx.restore()

        const da = dots[ri].a1 + angle
        ctx.beginPath()
        ctx.arc(cx + Math.cos(da) * r, cy + Math.sin(da) * r, s === 'speaking' ? 4 : 3, 0, Math.PI * 2)
        ctx.fillStyle = p.base + '0.9)'
        ctx.fill()

        if (ri < 3) {
          const da2 = dots[ri].a2 - angle
          ctx.beginPath()
          ctx.arc(cx + Math.cos(da2) * r, cy + Math.sin(da2) * r, 2, 0, Math.PI * 2)
          ctx.fillStyle = p.base + '0.5)'
          ctx.fill()
        }
      })

      const glowR = 44 * pulse
      const glowA = (s === 'speaking' ? 0.5 + Math.abs(sw) * 2 : s === 'thinking' ? 0.35 : s === 'standby' ? 0.08 : 0.15).toFixed(2)
      ctx.beginPath()
      ctx.arc(cx, cy, glowR, 0, Math.PI * 2)
      ctx.strokeStyle = p.base + glowA + ')'
      ctx.lineWidth = s === 'speaking' ? 22 + Math.abs(sw) * 30 : 18
      ctx.setLineDash([])
      ctx.stroke()

      if (s === 'speaking') {
        for (let i = 0; i < 3; i++) {
          ctx.beginPath()
          ctx.arc(cx, cy, glowR + 10 + i * 8 + Math.abs(sw) * 15, 0, Math.PI * 2)
          ctx.strokeStyle = p.base + (0.08 - i * 0.02).toFixed(2) + ')'
          ctx.lineWidth = 4 - i
          ctx.stroke()
        }
      }

      rafId = requestAnimationFrame(draw)
    }

    rafId = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(rafId)
  }, [])

  return (
    <canvas
      ref={canvasRef}
      width={320}
      height={320}
      style={{ position: 'absolute', top: 0, left: 0 }}
    />
  )
}
