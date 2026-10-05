import type { ResolveResponse } from '../types/api'
import { displayValue } from '../utils/display'

export function EvidencePanel({ result }: { result: ResolveResponse }) {
  return <section aria-labelledby="evidence-title" className="mt-8">
    <h2 id="evidence-title" className="mb-4 text-lg font-bold text-navy-950">Retrieved evidence</h2>
    {result.insufficient_evidence && <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Candidate matches only — verify relevance before using this guidance.</p>}
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
        <h3 className="text-lg font-bold text-navy-950">Similar resolved tickets</h3>
        <p className="mt-1 text-xs text-slate-600">Similarity scores rank retrieved matches.</p>
        {result.tickets.length === 0 && <p className="mt-5 text-sm text-slate-600">No approved resolved tickets were retrieved.</p>}
        <div className="mt-4 space-y-3">{result.tickets.map(ticket => <details key={ticket.source_id} className="min-w-0 rounded-xl border border-slate-200 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-navy-950">{ticket.source_id} · similarity {ticket.similarity_score.toFixed(3)}</summary>
          <dl className="mt-3 space-y-2 break-words text-sm leading-6 text-slate-600">
            <div><dt className="inline font-semibold text-navy-950">Complaint: </dt><dd className="inline">{ticket.complaint}</dd></div>
            <div><dt className="inline font-semibold text-navy-950">Product: </dt><dd className="inline">{displayValue(ticket.product)}</dd></div>
            <div><dt className="inline font-semibold text-navy-950">Category: </dt><dd className="inline">{displayValue(ticket.category)}</dd></div>
            <div><dt className="inline font-semibold text-navy-950">Historical resolution: </dt><dd className="inline">{ticket.resolution}</dd></div>
          </dl>
        </details>)}</div>
      </div>
      <div className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
        <h3 className="text-lg font-bold text-navy-950">Relevant KB articles</h3>
        <p className="mt-1 text-xs text-slate-600">Similarity scores rank retrieved matches.</p>
        {result.kb_articles.length === 0 && <p className="mt-5 text-sm text-slate-600">No approved knowledge base articles were retrieved.</p>}
        <div className="mt-4 space-y-3">{result.kb_articles.map(article => <details key={article.source_id} className="min-w-0 rounded-xl border border-slate-200 p-4">
          <summary className="cursor-pointer break-words text-sm font-semibold text-navy-950">{article.source_id} · {article.title} · similarity {article.similarity_score.toFixed(3)}</summary>
          <dl className="mt-3 space-y-2 break-words text-sm leading-6 text-slate-600">
            <div><dt className="inline font-semibold text-navy-950">Category: </dt><dd className="inline">{displayValue(article.category)}</dd></div>
            <div><dt className="inline font-semibold text-navy-950">Guidance: </dt><dd className="inline">{article.content}</dd></div>
          </dl>
        </details>)}</div>
      </div>
    </div>
  </section>
}
