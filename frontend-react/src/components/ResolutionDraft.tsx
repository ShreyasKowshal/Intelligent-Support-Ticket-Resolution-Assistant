import type { ResolveResponse, SourceId } from '../types/api'
import { displayValue } from '../utils/display'

function CitationChips({ ids }: { ids: SourceId[] }) {
  if (!ids.length) return null
  return <div aria-label="Citations" className="mt-2 flex flex-wrap gap-1.5">
    {ids.map(id => <span key={id} className="rounded-md bg-mint-50 px-2 py-1 text-xs font-semibold text-mint-700">{id}</span>)}
  </div>
}

export function ResolutionDraft({ result, loading }: { result: ResolveResponse | null; loading: boolean }) {
  const state = result?.non_actionable ? 'Clarification needed' : result?.insufficient_evidence ? 'Insufficient evidence' : result ? 'Ready for agent review' : 'Awaiting complaint'
  const ready = result && !result.non_actionable && !result.insufficient_evidence
  return <section aria-labelledby="draft-title" aria-busy={loading} className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <h2 id="draft-title" className="text-xl font-bold tracking-tight text-navy-950">Resolution draft</h2>
      <span className={`rounded-full px-3 py-1.5 text-xs font-semibold ${ready ? 'bg-mint-50 text-mint-700' : result ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-slate-600'}`}>{state}</span>
    </div>
    {!result && <div className="mt-6 flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 text-center">
      <div aria-hidden="true" className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-white text-2xl text-mint-700 shadow-sm">✦</div>
      <h3 className="font-semibold text-navy-950">{loading ? 'Checking approved evidence' : 'Ready when you are'}</h3>
      <p className="mt-2 max-w-sm text-sm leading-6 text-slate-600">{loading ? 'Analyzing the complaint and preparing a cited draft…' : 'Enter a customer complaint to see its analysis, approved evidence, and a resolution draft for review.'}</p>
    </div>}
    {result && <div className="mt-6">
      <div className="mb-3 text-xs font-bold tracking-widest text-slate-500">COMPLAINT ANALYSIS</div>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {([['Category', result.analysis.category], ['Product', result.analysis.product], ['Severity', result.analysis.severity], ['Sentiment', result.analysis.sentiment]] as const).map(([label, value]) =>
          <div key={label} className="min-w-0 rounded-xl bg-slate-50 p-3">
            <div className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</div>
            <div className="mt-2 break-words text-sm font-semibold text-navy-950">{displayValue(value)}</div>
          </div>)}
      </div>
      <div className="mt-4 text-sm text-slate-600"><span className="font-semibold text-navy-950">Intent:</span> {result.analysis.intent}</div>
      <details className="mt-2 rounded-lg border border-slate-200 p-3 text-sm text-slate-600">
        <summary className="cursor-pointer font-semibold text-navy-950">Analysis details</summary>
        <dl className="mt-3 grid gap-2 sm:grid-cols-2">
          <div><dt className="font-semibold">Model self-assessed confidence</dt><dd>{result.analysis.confidence.toFixed(2)}</dd></div>
          <div><dt className="font-semibold">Needs review</dt><dd>{result.analysis.needs_review ? 'Yes' : 'No'}</dd></div>
          {result.analysis.suggested_category && <div><dt className="font-semibold">Suggested new category</dt><dd>{displayValue(result.analysis.suggested_category)}</dd></div>}
          <div className="sm:col-span-2"><dt className="font-semibold">Rationale</dt><dd>{result.analysis.rationale}</dd></div>
        </dl>
      </details>
      {result.non_actionable ? <div className="mt-5 rounded-xl border-l-4 border-slate-400 bg-slate-50 p-4 text-sm leading-6 text-navy-950">
        <h3 className="font-bold">{result.resolution.problem_summary}</h3>
        <p className="mt-2">{result.resolution.escalation_recommendation}</p>
        <p className="mt-2 text-slate-600">{result.resolution.confidence_or_evidence_note}</p>
      </div> : <>
        <div className="mt-5 rounded-xl border-l-4 border-emerald-500 bg-mint-50 p-4">
          <div className="text-xs font-bold uppercase tracking-wider text-mint-700">Problem summary</div>
          <p className="mt-1 text-sm leading-6 text-navy-950">{result.resolution.problem_summary}</p>
        </div>
        {result.insufficient_evidence ? <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <h3 className="font-bold">Insufficient approved evidence</h3>
          <p className="mt-1">No reliable resolution was generated. Review this case or escalate it.</p>
        </div> : <div className="mt-6">
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">Resolution steps</h3>
          <ol className="mt-2 divide-y divide-slate-200">
            {result.resolution.resolution_steps.map(step => <li key={step.step_number} className="flex gap-4 py-4">
              <span aria-label={`Step ${step.step_number}`} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-mint-50 text-sm font-bold text-mint-700">{step.step_number}</span>
              <div className="min-w-0 pt-1"><p className="text-sm leading-6 text-navy-950">{step.action}</p><CitationChips ids={step.source_ids} /></div>
            </li>)}
          </ol>
        </div>}
        <div className="mt-5 grid gap-4 border-t border-slate-200 pt-5 text-sm leading-6 text-slate-600 sm:grid-cols-2">
          <div><h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Escalation recommendation</h3><p className="mt-1">{result.resolution.escalation_recommendation}</p></div>
          <div><h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Evidence note</h3><p className="mt-1">{result.resolution.confidence_or_evidence_note}</p></div>
        </div>
        {result.source_ids.length > 0 && <div className="mt-5"><h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Sources used</h3><CitationChips ids={result.source_ids} /></div>}
      </>}
      {result.analysis.needs_review && <p className="mt-5 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Agent review required: verify this classification before advising the customer.</p>}
      {['HIGH', 'CRITICAL'].includes(result.analysis.severity) && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{displayValue(result.analysis.severity)} severity — prioritize this case.</p>}
    </div>}
    <p className="mt-5 border-t border-slate-200 pt-4 text-sm font-medium text-slate-600">Review the generated resolution and cited sources before using it with a customer.</p>
  </section>
}
