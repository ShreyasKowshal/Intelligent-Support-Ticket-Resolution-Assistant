import { useCallback, useEffect, useRef, useState } from 'react'
import { getHealth, getReadiness } from '../services/api'
import type { ReadinessResponse } from '../types/api'

export type BackendState = 'starting' | 'ready' | 'unavailable'
const RETRY_INTERVAL_MS = 5_000
const RETRY_WINDOW_MS = 180_000

export function useBackendStatus() {
  const [state, setState] = useState<BackendState>('starting')
  const [health, setHealth] = useState<'ok' | 'unknown'>('unknown')
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null)
  const [attempt, setAttempt] = useState(0)
  const startedAt = useRef(Date.now())

  const retry = useCallback(() => {
    startedAt.current = Date.now()
    setHealth('unknown')
    setReadiness(null)
    setState('starting')
    setAttempt(current => current + 1)
  }, [])

  useEffect(() => {
    if (state !== 'starting') return
    let active = true
    const check = async () => {
      if (Date.now() - startedAt.current >= RETRY_WINDOW_MS) {
        if (active) setState('unavailable')
        return
      }
      try {
        const [healthResult, readyResult] = await Promise.allSettled([
          getHealth(AbortSignal.timeout(3_000)), getReadiness(AbortSignal.timeout(3_000)),
        ])
        if (!active) return
        setHealth(healthResult.status === 'fulfilled' && healthResult.value.status === 'ok' ? 'ok' : 'unknown')
        if (readyResult.status !== 'fulfilled') return
        const { statusCode, body } = readyResult.value
        setReadiness(body)
        if ([401, 403, 404, 405].includes(statusCode) || body?.gemini_configured === false) {
          setState('unavailable')
        } else if (statusCode === 200 && body?.status === 'ready' &&
          body.database === true && body.search_index === true &&
          body.embedding_model === true && body.gemini_configured === true) {
          setState('ready')
        }
      } catch { /* Remain in waking state until the retry window expires. */ }
    }
    void check()
    const timer = window.setInterval(() => { void check() }, RETRY_INTERVAL_MS)
    return () => { active = false; window.clearInterval(timer) }
  }, [attempt, state])

  return { state, health, readiness, retry }
}
