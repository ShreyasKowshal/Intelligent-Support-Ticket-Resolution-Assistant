import type { FormEvent } from 'react'
import type { BackendState } from '../hooks/useBackendStatus'
import { characterCount, MAX_COMPLAINT_LENGTH } from '../utils/display'

interface Props {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  onRetry: () => void
  state: BackendState
  loading: boolean
  error: string | null
}

export function ComplaintForm({ value, onChange, onSubmit, onRetry, state, loading, error }: Props) {
  const length = characterCount(value)
  const tooLong = length > MAX_COMPLAINT_LENGTH
  const empty = !value.trim()
  const submit = (event: FormEvent) => { event.preventDefault(); if (!empty && !tooLong && state === 'ready' && !loading) onSubmit() }
  return <section aria-labelledby="complaint-title" className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
    <h2 id="complaint-title" className="text-xl font-bold tracking-tight text-navy-950">Customer complaint</h2>
    <p className="mt-2 text-sm text-slate-600">Enter the customer’s telecom complaint.</p>
    <form onSubmit={submit} className="mt-5">
      <label htmlFor="complaint" className="mb-2 block text-sm font-semibold text-navy-950">Complaint text</label>
      <textarea id="complaint" value={value} onChange={event => onChange(event.target.value)}
        placeholder="Paste the customer's raw telecom complaint here..." rows={10}
        aria-describedby="complaint-count complaint-validation" aria-invalid={tooLong}
        className="w-full resize-y rounded-xl border border-slate-300 bg-slate-50 p-4 text-sm leading-6 text-navy-950 placeholder:text-slate-500 focus:border-mint-700 focus:bg-white" />
      <div id="complaint-count" aria-live="polite" className={`mt-1 text-right text-xs ${tooLong ? 'text-red-700' : 'text-slate-600'}`}>
        {length} / {MAX_COMPLAINT_LENGTH} characters
      </div>
      <div id="complaint-validation" role={tooLong ? 'alert' : undefined} className="mt-1 min-h-5 text-sm text-red-700">
        {tooLong ? `Complaint must be ${MAX_COMPLAINT_LENGTH} characters or fewer.` : ''}
      </div>
      <button type="submit" disabled={empty || tooLong || state !== 'ready' || loading}
        className="mt-3 w-full rounded-xl bg-emerald-700 px-5 py-3.5 text-sm font-bold text-white shadow-sm hover:bg-emerald-800 disabled:cursor-not-allowed disabled:bg-slate-400">
        {loading ? 'Analyzing complaint…' : 'Analyze & Resolve'}
      </button>
    </form>
    {state === 'starting' && <p className="mt-4 text-sm text-slate-600">The backend is waking. Submission will be available when it is ready.</p>}
    {state === 'unavailable' && <button type="button" onClick={onRetry} className="mt-4 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-navy-950 hover:bg-slate-50">Retry backend connection</button>}
    {error && <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
  </section>
}
