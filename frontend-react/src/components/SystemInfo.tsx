import type { ReadinessResponse, ResolveResponse } from '../types/api'

export function SystemInfo({ health, readiness, result }: { health: 'ok' | 'unknown'; readiness: ReadinessResponse | null; result: ResolveResponse | null }) {
  return <details className="mt-8 rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
    <summary className="cursor-pointer font-semibold text-navy-950">System information</summary>
    <dl className="mt-3 grid gap-2 sm:grid-cols-2">
      <div><dt className="inline font-semibold">Health: </dt><dd className="inline">{health === 'ok' ? 'Responding' : 'Unknown'}</dd></div>
      <div><dt className="inline font-semibold">Readiness: </dt><dd className="inline">{readiness?.status ?? 'Checking'}</dd></div>
      {readiness && <>
        <div><dt className="inline font-semibold">Database: </dt><dd className="inline">{readiness.database ? 'Ready' : 'Not ready'}</dd></div>
        <div><dt className="inline font-semibold">Search index: </dt><dd className="inline">{readiness.search_index ? 'Ready' : 'Not ready'}</dd></div>
        <div><dt className="inline font-semibold">Embedding model: </dt><dd className="inline">{readiness.embedding_model ? 'Ready' : 'Not ready'}</dd></div>
        <div><dt className="inline font-semibold">Gemini configured: </dt><dd className="inline">{readiness.gemini_configured ? 'Yes' : 'No'}</dd></div>
      </>}
      {result && <div><dt className="inline font-semibold">Backend processing time: </dt><dd className="inline">{result.latency_ms.toFixed(0)} ms</dd></div>}
    </dl>
  </details>
}
