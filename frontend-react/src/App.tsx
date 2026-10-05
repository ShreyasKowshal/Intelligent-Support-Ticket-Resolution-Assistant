import { useRef, useState } from 'react'
import { BackendStatus } from './components/BackendStatus'
import { ComplaintForm } from './components/ComplaintForm'
import { EvidencePanel } from './components/EvidencePanel'
import { ResolutionDraft } from './components/ResolutionDraft'
import { SystemInfo } from './components/SystemInfo'
import { useBackendStatus } from './hooks/useBackendStatus'
import { ApiRequestError, resolveComplaint } from './services/api'
import type { ResolveResponse } from './types/api'

export default function App() {
  const [complaint, setComplaint] = useState('')
  const [result, setResult] = useState<ResolveResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const requestId = useRef(0)
  const backend = useBackendStatus()

  const changeComplaint = (value: string) => {
    requestId.current += 1
    setComplaint(value); setResult(null); setError(null); setLoading(false)
  }
  const submit = async () => {
    const thisRequest = ++requestId.current
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const response = await resolveComplaint(complaint)
      if (requestId.current === thisRequest) setResult(response)
    }
    catch (reason) {
      if (requestId.current === thisRequest) {
        setError(reason instanceof ApiRequestError ? reason.message : 'The request could not be completed. Please try again.')
        if (reason instanceof ApiRequestError && reason.connectionFailed) backend.retry()
      }
    }
    finally { if (requestId.current === thisRequest) setLoading(false) }
  }

  return <div className="min-h-screen bg-[#f3f5f6]">
    <header className="bg-navy-950 text-white">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-4 px-5 py-5 sm:px-8">
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-700 text-xl font-bold">T</span>
          <span className="max-w-xl text-sm font-bold leading-5 sm:text-base">Support Resolution Assistant</span>
        </div>
        <BackendStatus state={backend.state} />
      </div>
    </header>
    <main className="mx-auto max-w-[1440px] px-5 pb-12 pt-10 sm:px-8 sm:pt-14">
      <div className="mb-9">
        <p className="text-xs font-bold tracking-[0.16em] text-emerald-700">TELECOM SUPPORT WORKSPACE</p>
        <h1 className="mt-3 max-w-4xl text-3xl font-bold tracking-tight text-navy-950 sm:text-4xl">Intelligent Support Ticket Resolution Assistant</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600 sm:text-base">Analyze telecom complaints, retrieve similar resolved tickets and knowledge-base articles, and review a cited resolution draft.</p>
      </div>
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(300px,0.85fr)_minmax(0,1.5fr)]">
        <ComplaintForm value={complaint} onChange={changeComplaint} onSubmit={submit} onRetry={backend.retry} state={backend.state} loading={loading} error={error} />
        <ResolutionDraft result={result} loading={loading} />
      </div>
      {result && !result.non_actionable && <EvidencePanel result={result} />}
      <SystemInfo health={backend.health} readiness={backend.readiness} result={result} />
    </main>
  </div>
}
