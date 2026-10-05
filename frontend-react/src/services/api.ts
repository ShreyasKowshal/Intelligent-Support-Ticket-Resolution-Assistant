import type { ApiErrorResponse, HealthResponse, ReadinessResponse, ResolveResponse, ResolutionStep } from '../types/api'

// In development Vite proxies these paths to VITE_API_BASE_URL, avoiding local CORS changes.
// In a production build the browser calls the configured API origin directly.
const baseUrl = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/$/, '')

const safeErrors: Record<string, string> = {
  validation_error: 'Please check the complaint and try again.',
  missing_configuration: 'The AI service is not configured. Ask an administrator to check the backend.',
  provider_error: 'The AI provider is unavailable right now. Please try again later.',
  provider_timeout: 'The AI provider timed out. Please try again later.',
  provider_rate_limit: 'The AI provider is busy. Please try again later.',
  invalid_analysis: 'The AI analysis could not be validated. Please try again.',
  grounding_error: 'The draft failed citation checks. No recommendation was shown.',
  search_unavailable: 'Semantic search is unavailable right now. Please try again later.',
  storage_unavailable: 'The support database is unavailable right now.',
}

export class ApiRequestError extends Error {
  constructor(message: string, readonly connectionFailed = false) { super(message) }
}

function endpoint(path: string): string { return `${baseUrl}${path}` }

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(endpoint('/health'), { signal })
  if (!response.ok) throw new ApiRequestError('Backend health is unavailable.')
  return response.json() as Promise<HealthResponse>
}

export async function getReadiness(signal?: AbortSignal): Promise<{ statusCode: number; body: ReadinessResponse | null }> {
  const response = await fetch(endpoint('/ready'), { signal })
  if (response.status !== 200 && response.status !== 503) return { statusCode: response.status, body: null }
  try {
    return { statusCode: response.status, body: await response.json() as ReadinessResponse }
  } catch {
    return { statusCode: response.status, body: null }
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string')
}
function textFields(value: unknown, fields: string[]): boolean {
  return record(value) && fields.every(field => typeof value[field] === 'string')
}

function isResolveResponse(value: unknown): value is ResolveResponse {
  if (!record(value) || !record(value.analysis) || !record(value.resolution)) return false
  const { analysis, resolution } = value
  if (!textFields(analysis, ['intent', 'category', 'product', 'severity', 'sentiment', 'rationale']) ||
      typeof analysis.confidence !== 'number' || !Number.isFinite(analysis.confidence) ||
      typeof analysis.needs_review !== 'boolean' ||
      !(analysis.suggested_category === null || typeof analysis.suggested_category === 'string')) return false
  if (!Array.isArray(value.tickets) || !value.tickets.every(ticket =>
    textFields(ticket, ['source_id', 'complaint', 'product', 'category', 'resolution']) &&
    Number.isFinite(ticket.similarity_score))) return false
  if (!Array.isArray(value.kb_articles) || !value.kb_articles.every(article =>
    textFields(article, ['source_id', 'title', 'content', 'category']) &&
    Number.isFinite(article.similarity_score))) return false
  if (!textFields(resolution, ['problem_summary', 'escalation_recommendation', 'confidence_or_evidence_note']) ||
      !strings(resolution.sources_used) || !strings(value.source_ids) ||
      typeof resolution.insufficient_evidence !== 'boolean' ||
      !Array.isArray(resolution.resolution_steps) ||
      !resolution.resolution_steps.every(step => record(step) &&
        Number.isInteger(step.step_number) && typeof step.action === 'string' && strings(step.source_ids)) ||
      typeof value.non_actionable !== 'boolean' ||
      typeof value.insufficient_evidence !== 'boolean' ||
      !Number.isFinite(value.latency_ms)) return false
  const sourceIds = value.source_ids as string[]
  const steps = resolution.resolution_steps as ResolutionStep[]
  if (value.insufficient_evidence !== resolution.insufficient_evidence ||
      sourceIds.join('\0') !== resolution.sources_used.join('\0')) return false
  if (value.insufficient_evidence) {
    if (steps.length !== 0 || sourceIds.length !== 0) return false
  } else if (steps.length === 0 || steps.some(step =>
    step.source_ids.length === 0 || step.source_ids.some(id => !sourceIds.includes(id)))) return false
  return !value.non_actionable || (value.insufficient_evidence && value.tickets.length === 0 && value.kb_articles.length === 0)
}

export async function resolveComplaint(complaint: string): Promise<ResolveResponse> {
  let response: Response
  try {
    response = await fetch(endpoint('/resolve'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ complaint: complaint.trim() }),
      signal: AbortSignal.timeout(90_000),
    })
  } catch (error) {
    if (error instanceof Error && (error.name === 'TimeoutError' || error.name === 'AbortError')) {
      throw new ApiRequestError('The analysis request timed out. Please try again.')
    }
    throw new ApiRequestError('Backend is starting. Please wait until the status changes to Ready.', true)
  }
  if (!response.ok) {
    let code = ''
    try { code = ((await response.json()) as ApiErrorResponse).error?.code ?? '' } catch { /* No safe code available. */ }
    throw new ApiRequestError(safeErrors[code] ?? 'The backend returned an unexpected error. Please try again or check service status.')
  }
  let body: unknown
  try { body = await response.json() } catch { throw new ApiRequestError('The backend returned an invalid response. Please try again.') }
  if (!isResolveResponse(body)) throw new ApiRequestError('The backend returned an invalid response. Please try again.')
  return body
}
