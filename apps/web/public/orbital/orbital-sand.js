import { vertex, fragment } from './shaders.js'

/** Mount once on an empty decorative backdrop. Call destroy() on unmount. */
export function createOrbitalSand(host, options = {}) {
  if (!(host instanceof HTMLElement) || host.childNodes.length) {
    throw new TypeError('Use an empty HTMLElement for the Orbital backdrop.')
  }
  const settings = {
    intensity: 1.25,
    speed: 0.85,
    paused: false,
    reducedMotion: false,
    flat: false,
    renderer: 'auto',
    ...options,
  }
  function validate(next) {
    for (const [key, min, max] of [
      ['intensity', 0.4, 1.6],
      ['speed', 0.25, 1.5],
    ]) {
      if (!Number.isFinite(next[key]) || next[key] < min || next[key] > max)
        throw new RangeError(`${key} must be between ${min} and ${max}`)
    }
  }
  validate(settings)
  const originalClass = host.className,
    originalAria = host.getAttribute('aria-hidden')
  host.classList.add('oc-backdrop')
  host.setAttribute('aria-hidden', 'true')
  const poster = document.createElement('div')
  poster.className = 'oc-sand-poster'
  const canvas = document.createElement('canvas')
  canvas.className = 'oc-sand-canvas'
  host.append(poster, canvas)
  const preference = matchMedia('(prefers-reduced-motion: reduce)')
  const listeners = new AbortController()
  let gl,
    program,
    buffer,
    uniforms,
    raf = 0,
    previous = 0,
    time = 0,
    frames = 0,
    lost = true,
    destroyed = false
  let width = 0,
    height = 0
  function disposeGraphics() {
    if (gl) {
      if (buffer) gl.deleteBuffer(buffer)
      if (program) gl.deleteProgram(program)
    }
    program = null
    buffer = null
  }
  function compile(type, source) {
    const shader = gl.createShader(type)
    gl.shaderSource(shader, source)
    gl.compileShader(shader)
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      gl.deleteShader(shader)
      throw new Error('Shader compilation failed')
    }
    return shader
  }
  function initialize() {
    disposeGraphics()
    gl = canvas.getContext('webgl2', {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
    })
    if (!gl) throw new Error('WebGL 2 unavailable')
    const shaders = []
    try {
      shaders.push(compile(gl.VERTEX_SHADER, vertex))
      shaders.push(compile(gl.FRAGMENT_SHADER, fragment))
      program = gl.createProgram()
      shaders.forEach((s) => gl.attachShader(program, s))
      gl.linkProgram(program)
      if (!gl.getProgramParameter(program, gl.LINK_STATUS))
        throw new Error('Shader linking failed')
    } finally {
      shaders.forEach((s) => gl.deleteShader(s))
    }
    gl.useProgram(program)
    buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
      gl.STATIC_DRAW,
    )
    const a = gl.getAttribLocation(program, 'a')
    gl.enableVertexAttribArray(a)
    gl.vertexAttribPointer(a, 2, gl.FLOAT, false, 0, 0)
    uniforms = Object.fromEntries(
      ['resolution', 'cssSize', 'time', 'intensity'].map((k) => [
        k,
        gl.getUniformLocation(program, k),
      ]),
    )
    lost = false
  }
  function state() {
    const reduced = preference.matches || settings.reducedMotion
    const running =
      !destroyed &&
      !lost &&
      !settings.paused &&
      !settings.flat &&
      !reduced &&
      !document.hidden &&
      width > 0 &&
      height > 0
    return {
      ...settings,
      renderer: lost ? 'poster' : 'webgl2',
      reduced,
      running,
      destroyed,
    }
  }
  function draw() {
    if (lost || destroyed || width <= 0 || height <= 0) return
    const ratio = Math.min(devicePixelRatio || 1, 1.5)
    const w = Math.max(1, Math.round(width * ratio)),
      h = Math.max(1, Math.round(height * ratio))
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w
      canvas.height = h
      gl.viewport(0, 0, w, h)
    }
    gl.uniform2f(uniforms.resolution, w, h)
    gl.uniform2f(uniforms.cssSize, width, height)
    gl.uniform1f(uniforms.time, time)
    gl.uniform1f(uniforms.intensity, settings.flat ? 0 : settings.intensity)
    gl.drawArrays(gl.TRIANGLES, 0, 6)
    host.dataset.time = time.toFixed(3)
    host.dataset.frames = String(++frames)
  }
  function tick(now) {
    raf = 0
    if (!state().running) {
      previous = 0
      return
    }
    if (!previous) previous = now
    const delta = now - previous
    if (delta >= 1000 / 24) {
      time += (Math.min(delta, 100) / 1000) * settings.speed
      previous = now
      draw()
    }
    raf = requestAnimationFrame(tick)
  }
  function sync() {
    if (destroyed) return
    cancelAnimationFrame(raf)
    raf = 0
    previous = 0
    const rect = host.getBoundingClientRect()
    width = rect.width
    height = rect.height
    const current = state()
    canvas.hidden = lost
    host.dataset.flat = String(settings.flat)
    host.dataset.renderer = current.renderer
    host.dataset.motion = current.running ? 'running' : 'still'
    draw()
    host.dispatchEvent(
      new CustomEvent('orbital-sand-change', { detail: current }),
    )
    if (current.running) raf = requestAnimationFrame(tick)
  }
  const listen = (target, event, handler) =>
    target.addEventListener(event, handler, { signal: listeners.signal })
  listen(preference, 'change', sync)
  listen(document, 'visibilitychange', sync)
  listen(window, 'resize', sync)
  listen(canvas, 'webglcontextlost', (event) => {
    event.preventDefault()
    lost = true
    sync()
  })
  listen(canvas, 'webglcontextrestored', () => {
    try {
      initialize()
    } catch {
      lost = true
      disposeGraphics()
    }
    sync()
  })
  const observer = new ResizeObserver(sync)
  observer.observe(host)
  try {
    if (settings.renderer === 'poster')
      throw new Error('Requested still renderer')
    initialize()
  } catch {
    lost = true
    disposeGraphics()
  }
  sync()
  return {
    get state() {
      return state()
    },
    setOptions(next = {}) {
      if (destroyed) return
      // Renderer selection is initialization-only; unknown options are ignored.
      const allowed = Object.fromEntries(
        Object.entries(next).filter(([k]) =>
          ['intensity', 'speed', 'paused', 'reducedMotion', 'flat'].includes(k),
        ),
      )
      validate({ ...settings, ...allowed })
      Object.assign(settings, allowed)
      sync()
    },
    pause() {
      this.setOptions({ paused: true })
    },
    resume() {
      this.setOptions({ paused: false })
    },
    destroy() {
      if (destroyed) return
      destroyed = true
      cancelAnimationFrame(raf)
      observer.disconnect()
      listeners.abort()
      disposeGraphics()
      canvas.remove()
      poster.remove()
      host.className = originalClass
      if (originalAria === null) host.removeAttribute('aria-hidden')
      else host.setAttribute('aria-hidden', originalAria)
      for (const key of ['time', 'frames', 'flat', 'renderer', 'motion'])
        delete host.dataset[key]
    },
  }
}
