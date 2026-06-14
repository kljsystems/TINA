import { useRef, useCallback, useEffect } from 'react'

const P  = '#8B5CF6'
const PG = '#A78BFA'

export const STATE_CFG = {
  listening:   { label: 'READY',       sub: 'Awaiting input',      irisScale: 0.82, pupilSize: 0.30, ringSpeed: 0.28, glow: 0.50, pulseAmp: 0.04, scanAmp: 0,   breathSpeed: 0.5  },
  thinking:    { label: 'PROCESSING',  sub: 'Analysing request',   irisScale: 1.00, pupilSize: 0.50, ringSpeed: 1.50, glow: 0.80, pulseAmp: 0.09, scanAmp: 1.0, breathSpeed: 1.3  },
  speaking:    { label: 'RESPONDING',  sub: 'Transmitting...',     irisScale: 1.00, pupilSize: 0.38, ringSpeed: 0.60, glow: 0.92, pulseAmp: 0.13, scanAmp: 0,   breathSpeed: 1.9  },
  standby:     { label: 'STANDBY',     sub: 'System idle',         irisScale: 0.55, pupilSize: 0.22, ringSpeed: 0.07, glow: 0.18, pulseAmp: 0.01, scanAmp: 0,   breathSpeed: 0.25 },
  offline:     { label: 'OFFLINE',     sub: 'No connection',       irisScale: 0.35, pupilSize: 0.16, ringSpeed: 0.02, glow: 0.06, pulseAmp: 0,    scanAmp: 0,   breathSpeed: 0.15 },
  diagnostics: { label: 'DIAGNOSTICS', sub: 'Running system scan', irisScale: 1.00, pupilSize: 0.55, ringSpeed: 2.20, glow: 0.84, pulseAmp: 0.16, scanAmp: 0.8, breathSpeed: 1.1  },
}

function lerp(a, b, t) { return a + (b - a) * t }

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

export default function TinaFace({ state = 'listening', size = 320 }) {
  const canvasRef  = useRef()
  const time       = useRef(0)
  const scanX      = useRef(-1.2)
  const ringAngles = useRef([0, 0, 0, 0])

  const live = useRef({
    irisScale:   STATE_CFG.listening.irisScale,
    pupilSize:   STATE_CFG.listening.pupilSize,
    ringSpeed:   STATE_CFG.listening.ringSpeed,
    glow:        STATE_CFG.listening.glow,
    pulseAmp:    STATE_CFG.listening.pulseAmp,
    scanAmp:     STATE_CFG.listening.scanAmp,
    breathSpeed: STATE_CFG.listening.breathSpeed,
  })

  const cfg = STATE_CFG[state] ?? STATE_CFG.listening
  const sc  = size / 320

  useRAF(useCallback((deltaMs) => {
    const c = canvasRef.current
    if (!c) return
    const ctx = c.getContext('2d')
    const cx  = c.width  / 2
    const cy  = c.height / 2
    const dt  = Math.min(deltaMs / 1000, 0.05)

    time.current += dt

    const α  = Math.min(1, dt * 2.8)
    const lv = live.current
    lv.irisScale   = lerp(lv.irisScale,   cfg.irisScale,   α)
    lv.pupilSize   = lerp(lv.pupilSize,   cfg.pupilSize,   α)
    lv.ringSpeed   = lerp(lv.ringSpeed,   cfg.ringSpeed,   α)
    lv.glow        = lerp(lv.glow,        cfg.glow,        α)
    lv.pulseAmp    = lerp(lv.pulseAmp,    cfg.pulseAmp,    α)
    lv.scanAmp     = lerp(lv.scanAmp,     cfg.scanAmp,     α)
    lv.breathSpeed = lerp(lv.breathSpeed, cfg.breathSpeed, α)

    if (lv.scanAmp > 0.05) {
      scanX.current += dt * lv.ringSpeed * 1.6
      if (scanX.current > 1.2) scanX.current = -1.2
    }

    const ra = ringAngles.current
    ra[0] += dt * lv.ringSpeed * 0.70
    ra[1] -= dt * lv.ringSpeed * 0.45
    ra[2] += dt * lv.ringSpeed * 0.28
    ra[3] -= dt * lv.ringSpeed * 0.16

    ctx.clearRect(0, 0, c.width, c.height)

    const breathe  = 1 + lv.pulseAmp * Math.sin(time.current * lv.breathSpeed * 2.4)
    const irisR    = 88 * sc * lv.irisScale

    // ── Outer segmented rings ─────────────────────────────────────────────────
    const RINGS = [
      { ri: 0, r: 148, dashes: 52, gapFrac: 0.10, alpha: 0.10, lw: 0.7 },
      { ri: 1, r: 134, dashes: 28, gapFrac: 0.18, alpha: 0.18, lw: 0.9 },
      { ri: 2, r: 120, dashes: 18, gapFrac: 0.26, alpha: 0.28, lw: 1.1 },
      { ri: 3, r: 108, dashes: 12, gapFrac: 0.34, alpha: 0.38, lw: 1.0 },
    ]

    RINGS.forEach(({ ri, r, dashes, gapFrac, alpha, lw }) => {
      const angle  = ra[ri]
      const arcLen = (Math.PI * 2) / dashes
      const gapLen = arcLen * gapFrac
      ctx.lineWidth   = lw * sc
      ctx.strokeStyle = PG
      ctx.shadowColor = P
      ctx.shadowBlur  = 5 * lv.glow
      for (let i = 0; i < dashes; i++) {
        const a0 = angle + i * arcLen
        const a1 = a0 + arcLen - gapLen
        ctx.globalAlpha = alpha * lv.glow * breathe
        ctx.beginPath()
        ctx.arc(cx, cy, r * sc * breathe, a0, a1)
        ctx.stroke()
      }
    })
    ctx.globalAlpha = 1
    ctx.shadowBlur  = 0

    // ── Iris ambient fill ─────────────────────────────────────────────────────
    const irisGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, irisR)
    irisGrad.addColorStop(0,   P + '00')
    irisGrad.addColorStop(0.6, P + Math.round(lv.glow * 0.07 * 255).toString(16).padStart(2, '0'))
    irisGrad.addColorStop(1,   P + Math.round(lv.glow * 0.22 * 255).toString(16).padStart(2, '0'))
    ctx.beginPath()
    ctx.arc(cx, cy, irisR, 0, Math.PI * 2)
    ctx.fillStyle   = irisGrad
    ctx.globalAlpha = 0.9
    ctx.fill()
    ctx.globalAlpha = 1

    // ── Iris concentric rings ─────────────────────────────────────────────────
    const IRIS = [
      { rFrac: 1.00, lw: 1.0, alpha: 0.20, color: PG },
      { rFrac: 0.78, lw: 0.8, alpha: 0.28, color: PG },
      { rFrac: 0.58, lw: 0.7, alpha: 0.36, color: P  },
      { rFrac: 0.40, lw: 0.6, alpha: 0.44, color: P  },
    ]
    IRIS.forEach(({ rFrac, lw, alpha, color }) => {
      ctx.beginPath()
      ctx.arc(cx, cy, irisR * rFrac, 0, Math.PI * 2)
      ctx.lineWidth   = lw * sc
      ctx.strokeStyle = color
      ctx.globalAlpha = alpha * lv.glow
      ctx.shadowColor = P
      ctx.shadowBlur  = 5
      ctx.stroke()
      ctx.shadowBlur  = 0
      ctx.globalAlpha = 1
    })

    // ── Scan line (thinking / diagnostics) ────────────────────────────────────
    if (lv.scanAmp > 0.05) {
      ctx.save()
      ctx.beginPath()
      ctx.arc(cx, cy, irisR, 0, Math.PI * 2)
      ctx.clip()

      const sx = cx + scanX.current * irisR
      const sg = ctx.createLinearGradient(sx - 22 * sc, 0, sx + 22 * sc, 0)
      sg.addColorStop(0,   P + '00')
      sg.addColorStop(0.5, P + 'cc')
      sg.addColorStop(1,   P + '00')
      ctx.fillStyle   = sg
      ctx.globalAlpha = lv.scanAmp * 0.55
      ctx.fillRect(sx - 22 * sc, cy - irisR, 44 * sc, irisR * 2)
      ctx.globalAlpha = 1
      ctx.restore()
    }

    // ── Pupil ─────────────────────────────────────────────────────────────────
    const pupilR = irisR * lv.pupilSize
    const pupilG = ctx.createRadialGradient(cx, cy, 0, cx, cy, pupilR)
    pupilG.addColorStop(0,   '#000000')
    pupilG.addColorStop(0.65, '#0a0318')
    pupilG.addColorStop(1,   P + '44')
    ctx.beginPath()
    ctx.arc(cx, cy, pupilR, 0, Math.PI * 2)
    ctx.fillStyle = pupilG
    ctx.fill()

    // Pupil glow ring
    ctx.beginPath()
    ctx.arc(cx, cy, pupilR, 0, Math.PI * 2)
    ctx.lineWidth   = 1.3 * sc
    ctx.strokeStyle = P
    ctx.globalAlpha = 0.7 * lv.glow
    ctx.shadowColor = PG
    ctx.shadowBlur  = 14 * lv.glow
    ctx.stroke()
    ctx.shadowBlur  = 0
    ctx.globalAlpha = 1

    // Specular highlight
    const hx = cx - irisR * 0.28
    const hy = cy - irisR * 0.32
    const hg = ctx.createRadialGradient(hx, hy, 0, hx, hy, 6 * sc)
    hg.addColorStop(0, '#ffffffcc')
    hg.addColorStop(1, '#ffffff00')
    ctx.beginPath()
    ctx.arc(hx, hy, 6 * sc, 0, Math.PI * 2)
    ctx.fillStyle   = hg
    ctx.globalAlpha = 0.20 * lv.glow
    ctx.fill()
    ctx.globalAlpha = 1

    // ── Centre ambient glow ───────────────────────────────────────────────────
    const ag = ctx.createRadialGradient(cx, cy, 0, cx, cy, 80 * sc)
    ag.addColorStop(0, P + Math.round(lv.glow * 0.20 * 255).toString(16).padStart(2, '0'))
    ag.addColorStop(1, P + '00')
    ctx.beginPath()
    ctx.arc(cx, cy, 80 * sc, 0, Math.PI * 2)
    ctx.fillStyle   = ag
    ctx.shadowColor = P
    ctx.shadowBlur  = 20 * lv.glow
    ctx.fill()
    ctx.shadowBlur  = 0

  }, [state, sc, cfg]))

  return <canvas ref={canvasRef} width={size} height={size} style={{ display: 'block' }} />
}
