import React, { useEffect, useRef, useState } from 'react'
import { startSession, stopSession, sendChunk, uploadVideo, renderVideo } from './api'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const LANGS = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'Hindi' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'ja', label: 'Japanese' },
]

export default function App() {
  const videoRef = useRef(null)
  const audioRef = useRef(null)
  const streamRef = useRef(null)
  const audioRecorderRef = useRef(null)
  const videoRecorderRef = useRef(null)
  const videoChunksRef = useRef([])
  const audioStreamRef = useRef(null)
  const videoStreamRef = useRef(null)
  const sessionIdRef = useRef('')
  const runningRef = useRef(false)
  const audioFlushTimerRef = useRef(null)
  // WebAudio WAV capture
  const audioCtxRef = useRef(null)
  const sourceNodeRef = useRef(null)
  const scriptNodeRef = useRef(null)
  const wavSampleRateRef = useRef(48000)
  const pcmChunksRef = useRef([]) // array of Float32Array
  const pcmLengthRef = useRef(0)

  const [sessionId, setSessionId] = useState('')
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState('Idle')
  const [sourceLang, setSourceLang] = useState('en')
  const [targetLang, setTargetLang] = useState('hi')
  const [lastText, setLastText] = useState('')
  const [lastTranslated, setLastTranslated] = useState('')
  const [finalUrl, setFinalUrl] = useState('')
  const [srtUrl, setSrtUrl] = useState('')

  const audioQueueRef = useRef([])
  const playingRef = useRef(false)

  useEffect(() => {
    return () => {
      // cleanup
      if (audioRecorderRef.current && audioRecorderRef.current.state !== 'inactive') {
        audioRecorderRef.current.stop()
      }
      if (videoRecorderRef.current && videoRecorderRef.current.state !== 'inactive') {
        videoRecorderRef.current.stop()
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop())
      }
    }
  }, [audioRecorderRef, videoRecorderRef, streamRef])

  // Helper: merge Float32 chunks into a single Float32Array
  const mergeFloat32 = (chunks, totalLen) => {
    const out = new Float32Array(totalLen)
    let offset = 0
    for (const c of chunks) {
      out.set(c, offset)
      offset += c.length
    }
    return out
  }

  // Helper: Convert Float32 mono PCM [-1,1] to 16-bit PCM WAV Blob
  const floatTo16BitPCM = (float32) => {
    const buffer = new ArrayBuffer(float32.length * 2)
    const view = new DataView(buffer)
    let offset = 0
    for (let i = 0; i < float32.length; i++, offset += 2) {
      let s = Math.max(-1, Math.min(1, float32[i]))
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true)
    }
    return buffer
  }

  const encodeWAV = (samplesFloat32, sampleRate) => {
    const pcm16 = floatTo16BitPCM(samplesFloat32)
    const wavBuffer = new ArrayBuffer(44 + pcm16.byteLength)
    const view = new DataView(wavBuffer)
    // RIFF header
    const writeString = (view, offset, str) => { for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i)) }
    writeString(view, 0, 'RIFF')
    view.setUint32(4, 36 + pcm16.byteLength, true)
    writeString(view, 8, 'WAVE')
    // fmt chunk
    writeString(view, 12, 'fmt ')
    view.setUint32(16, 16, true) // PCM chunk size
    view.setUint16(20, 1, true)  // PCM format
    view.setUint16(22, 1, true)  // mono
    view.setUint32(24, sampleRate, true)
    view.setUint32(28, sampleRate * 2, true) // byte rate (mono 16-bit)
    view.setUint16(32, 2, true) // block align
    view.setUint16(34, 16, true) // bits per sample
    // data chunk
    writeString(view, 36, 'data')
    view.setUint32(40, pcm16.byteLength, true)
    // Copy PCM
    new Uint8Array(wavBuffer, 44).set(new Uint8Array(pcm16))
    return new Blob([wavBuffer], { type: 'audio/wav' })
  }

  const sendAudioBlob = async (blob) => {
    const clientTs = Date.now()
    console.log('[chunk] sending audio chunk to backend', { size: blob.size, type: blob.type, sessionId: sessionIdRef.current })
    try {
      setStatus('Translating...')
      const resp = await sendChunk({
        blob,
        clientTs,
        sourceLang,
        targetLang,
        sessionId: sessionIdRef.current || sessionId || ''
      })
      console.log('[chunk] resp', resp)
      setLastText(resp.text || '')
      setLastTranslated(resp.translated_text || '')
      if (!resp || !resp.audio_b64) {
        console.log('[chunk] no audio returned (likely silence), skipping playback')
        setStatus('No speech detected')
        return
      }
      const audioBytes = atob(resp.audio_b64)
      const arr = new Uint8Array(audioBytes.length)
      for (let i = 0; i < audioBytes.length; i++) arr[i] = audioBytes.charCodeAt(i)
      const outBlob = new Blob([arr], { type: resp.mime || 'audio/mpeg' })
      if (outBlob.size === 0) {
        console.warn('[chunk] empty audio blob, skipping')
        setStatus('Empty audio')
        return
      }
      console.log('[chunk] enqueuing dubbed audio', { size: outBlob.size, type: outBlob.type })
      audioQueueRef.current.push({ blob: outBlob, clientTs: resp.client_ts })
      playQueue()
      setStatus('Ready')
    } catch (err) {
      console.error('[chunk] error sending/receiving', err)
      setStatus('Error (chunk)')
    }
  }

  const pickSupportedMime = (candidates = []) => {
    for (const m of candidates) {
      if (!m) return undefined
      if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) {
        return m
      }
    }
    return undefined
  }

  const ensureStream = async () => {
    if (!streamRef.current) {
      console.log('[media] requesting user media (video+audio)')
      const fullStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
      streamRef.current = fullStream

      // Split into dedicated streams for recorders
      const aTrack = fullStream.getAudioTracks()[0]
      const vTrack = fullStream.getVideoTracks()[0]
      audioStreamRef.current = new MediaStream(aTrack ? [aTrack] : [])
      videoStreamRef.current = new MediaStream(vTrack ? [vTrack] : [])

      if (videoRef.current) {
        // Show full stream for live preview (muted to avoid echo)
        videoRef.current.srcObject = fullStream
        videoRef.current.muted = true
        await videoRef.current.play().catch(() => {})
      }
      console.log('[media] streams ready', {
        audioTracks: fullStream.getAudioTracks().length,
        videoTracks: fullStream.getVideoTracks().length,
      })
    }
    return streamRef.current
  }

  const playQueue = async () => {
    if (playingRef.current) return
    playingRef.current = true
    while (audioQueueRef.current.length > 0) {
      const { blob } = audioQueueRef.current.shift()
      const url = URL.createObjectURL(blob)
      audioRef.current.src = url
      await audioRef.current.play()
      await new Promise(res => audioRef.current.onended = () => res())
      URL.revokeObjectURL(url)
    }
    playingRef.current = false
  }

  const onStart = async () => {
    try {
      await ensureStream()
      const { session_id } = await startSession()
      setSessionId(session_id)
      sessionIdRef.current = session_id
      // Reset any previous outputs
      setFinalUrl('')
      setSrtUrl('')

      // Audio capture via WebAudio -> WAV chunks
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext
        const audioCtx = new AudioCtx()
        audioCtxRef.current = audioCtx
        wavSampleRateRef.current = audioCtx.sampleRate || 48000
        const source = audioCtx.createMediaStreamSource(audioStreamRef.current)
        sourceNodeRef.current = source
        const proc = audioCtx.createScriptProcessor(4096, 1, 1)
        scriptNodeRef.current = proc
        proc.onaudioprocess = async (e) => {
          if (!runningRef.current) return
          const inBuf = e.inputBuffer.getChannelData(0)
          // Copy to avoid referencing the internal buffer
          pcmChunksRef.current.push(new Float32Array(inBuf))
          pcmLengthRef.current += inBuf.length
          const sr = wavSampleRateRef.current
          if (pcmLengthRef.current >= sr * 2) { // ~2s
            const merged = mergeFloat32(pcmChunksRef.current, pcmLengthRef.current)
            // Reset buffers before async work
            pcmChunksRef.current = []
            pcmLengthRef.current = 0
            const wavBlob = encodeWAV(merged, sr)
            await sendAudioBlob(wavBlob)
          }
        }
        source.connect(proc)
        proc.connect(audioCtx.destination) // required by some browsers
        console.log('[rec] audio WebAudio started, sr=', wavSampleRateRef.current)
      } catch (err) {
        console.error('[rec] WebAudio init failed', err)
        throw err
      }

      // Video recording (whole session, upload on stop)
      const videoMime = pickSupportedMime([
        'video/webm;codecs=vp9',
        'video/webm;codecs=vp8',
        'video/webm'
      ])
      console.log('[rec] video mime selected:', videoMime)
      let videoRec
      try {
        videoRec = videoMime ? new MediaRecorder(videoStreamRef.current, { mimeType: videoMime }) : new MediaRecorder(videoStreamRef.current)
      } catch (err) {
        console.error('[rec] create video MediaRecorder failed, retry without options', err)
        videoRec = new MediaRecorder(videoStreamRef.current)
      }
      videoRecorderRef.current = videoRec
      videoChunksRef.current = []
      videoRec.onstart = () => console.log('[rec] video started')
      videoRec.onstop = () => console.log('[rec] video stopped')
      videoRec.onpause = () => console.log('[rec] video paused')
      videoRec.onresume = () => console.log('[rec] video resumed')
      videoRec.onerror = (e) => console.error('[rec] video error', e)
      videoRec.ondataavailable = (e) => { if (e.data && e.data.size > 0) videoChunksRef.current.push(e.data) }

      console.log('[rec] about to start recorders', { audio: 'webaudio', videoState: videoRec.state })
      try {
        videoRec.start() // continuous video until stop
        console.log('[rec] video.start() called, state:', videoRec.state)
      } catch (err) {
        console.error('[rec] video start failed', err)
        throw err
      }
      // Set running BEFORE starting recorders
      runningRef.current = true
      setRunning(true)
      setStatus('Running')
      console.log('[rec] both recorders started successfully')
    } catch (e) {
      console.error(e)
      setStatus('Error starting')
    }
  }

  const onStop = async () => {
    try {
      setStatus('Stopping...')
      runningRef.current = false
      setRunning(false)
      if (audioFlushTimerRef.current) { clearInterval(audioFlushTimerRef.current); audioFlushTimerRef.current = null }
      // Stop WebAudio
      try {
        if (scriptNodeRef.current) { scriptNodeRef.current.disconnect(); scriptNodeRef.current.onaudioprocess = null; scriptNodeRef.current = null }
        if (sourceNodeRef.current) { sourceNodeRef.current.disconnect(); sourceNodeRef.current = null }
        if (audioCtxRef.current) { await audioCtxRef.current.close(); audioCtxRef.current = null }
      } catch {}

      let uploadResp = null
      let renderResp = null
      if (videoRecorderRef.current) {
        const videoRec = videoRecorderRef.current
        await new Promise(res => {
          videoRec.onstop = () => res()
          if (videoRec.state !== 'inactive') videoRec.stop()
        })
        const videoBlob = new Blob(videoChunksRef.current, { type: 'video/webm' })
        videoChunksRef.current = []
        if (sessionId) {
          setStatus('Uploading video...')
          uploadResp = await uploadVideo({ blob: videoBlob, sessionId, filename: 'session.webm' })
          setStatus('Rendering final video (merge audio + captions)...')
          // Trigger backend render BEFORE stopping the session (session holds segments)
          renderResp = await renderVideo({ sessionId, burnSubs: true })
          // Build absolute URLs for convenience
          if (renderResp?.final_url) setFinalUrl(`${API_BASE}${renderResp.final_url}`)
          if (renderResp?.srt_url) setSrtUrl(`${API_BASE}${renderResp.srt_url}`)
        }
      }

      // Now safe to stop session
      if (sessionIdRef.current) await stopSession(sessionIdRef.current)
      setSessionId('')
      sessionIdRef.current = ''
      if (renderResp?.final_url) {
        setStatus('Final video ready!')
      } else if (uploadResp?.saved) {
        setStatus(`Saved raw video: ${uploadResp.saved}`)
      } else {
        setStatus('Stopped')
      }
    } catch (e) {
      console.error(e)
      setStatus('Error stopping')
    }
  }

  return (
    <div className="container">
      <h1>Real-Time Video Translation & Dubbing</h1>
      <div className="controls">
        <label>
          Source:
          <select value={sourceLang} onChange={e => setSourceLang(e.target.value)}>
            {LANGS.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </label>
        <label>
          Target:
          <select value={targetLang} onChange={e => setTargetLang(e.target.value)}>
            {LANGS.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </label>
        {!running ? (
          <button onClick={onStart}>Start Translation</button>
        ) : (
          <button className="danger" onClick={onStop}>Stop</button>
        )}
      </div>

      <div className="preview">
        <video ref={videoRef} playsInline muted></video>
        <audio ref={audioRef} />
      </div>

      <div className="status">Status: {status}</div>
      <div className="status">ASR: {lastText || '—'}</div>
      <div className="status">Translation: {lastTranslated || '—'}</div>
      <p className="hint">Best-effort sync: audio chunks are played as they arrive.</p>
      {finalUrl && (
        <div className="outputs">
          <div><a href={finalUrl} target="_blank" rel="noreferrer">Download Final MP4 (dubbed + burned captions)</a></div>
          {srtUrl && <div><a href={srtUrl} target="_blank" rel="noreferrer">Download SRT</a></div>}
        </div>
      )}
    </div>
  )
}
