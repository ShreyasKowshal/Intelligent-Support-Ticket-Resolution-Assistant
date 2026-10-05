import type { BackendState } from '../hooks/useBackendStatus'

const labels: Record<BackendState, string> = {
  starting: 'Waking backend', ready: 'Backend ready', unavailable: 'Backend unavailable',
}
const colors: Record<BackendState, string> = {
  starting: 'bg-amber-300', ready: 'bg-emerald-400', unavailable: 'bg-rose-400',
}

export function BackendStatus({ state }: { state: BackendState }) {
  return <div role="status" aria-live="polite" className="inline-flex items-center gap-2 rounded-full bg-navy-800 px-3 py-2 text-xs font-semibold text-white sm:text-sm">
    <span aria-hidden="true" className={`h-2 w-2 rounded-full ${colors[state]}`} />{labels[state]}
  </div>
}
