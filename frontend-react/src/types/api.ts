// Mirrors backend/app/api_models.py, analysis.py, and rag.py.
export type SourceId = string
export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type Sentiment = 'POSITIVE' | 'NEUTRAL' | 'FRUSTRATED' | 'ANGRY'

export interface ComplaintAnalysis {
  intent: string
  category: string
  product: string
  severity: Severity
  sentiment: Sentiment
  confidence: number
  needs_review: boolean
  rationale: string
  suggested_category: string | null
}

export interface TicketResult {
  source_id: SourceId
  complaint: string
  product: string
  category: string
  resolution: string
  similarity_score: number
}

export interface KBResult {
  source_id: SourceId
  title: string
  content: string
  category: string
  similarity_score: number
}

export interface ResolutionStep {
  step_number: number
  action: string
  source_ids: SourceId[]
}

export interface Resolution {
  problem_summary: string
  resolution_steps: ResolutionStep[]
  escalation_recommendation: string
  confidence_or_evidence_note: string
  sources_used: SourceId[]
  insufficient_evidence: boolean
}

export interface ResolveResponse {
  analysis: ComplaintAnalysis
  tickets: TicketResult[]
  kb_articles: KBResult[]
  resolution: Resolution
  source_ids: SourceId[]
  insufficient_evidence: boolean
  non_actionable: boolean
  latency_ms: number
}

export type NonActionableResponse = ResolveResponse & { non_actionable: true; insufficient_evidence: true }
export type InsufficientEvidenceResponse = ResolveResponse & { non_actionable: false; insufficient_evidence: true }

export interface HealthResponse { status: string }
export interface ReadinessResponse {
  status: string
  database: boolean
  search_index: boolean
  embedding_model: boolean
  gemini_configured: boolean
}

export interface ApiErrorResponse {
  error: { code: string; message: string; fields?: string[] | null }
}
