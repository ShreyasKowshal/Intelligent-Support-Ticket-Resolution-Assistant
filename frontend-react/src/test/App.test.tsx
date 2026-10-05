import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'
import { ApiRequestError, getHealth, getReadiness, resolveComplaint } from '../services/api'
import type { ResolveResponse } from '../types/api'

vi.mock('../services/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../services/api')>()
  return { ...original, getHealth: vi.fn(), getReadiness: vi.fn(), resolveComplaint: vi.fn() }
})

const health = vi.mocked(getHealth)
const readiness = vi.mocked(getReadiness)
const resolve = vi.mocked(resolveComplaint)
const complaint = 'My broadband keeps disconnecting every evening.'

const normal: ResolveResponse = {
  analysis: {
    intent: 'restore broadband', category: 'broadband_connectivity', product: 'broadband',
    severity: 'HIGH', sentiment: 'FRUSTRATED', confidence: 0.8, needs_review: false,
    rationale: 'Repeated failures', suggested_category: null,
  },
  tickets: [{ source_id: 'T-001', complaint: 'Broadband fails', product: 'broadband',
    category: 'broadband_connectivity', resolution: 'Check the line.', similarity_score: 0.78 }],
  kb_articles: [{ source_id: 'KB-001', title: 'Connection checks', content: 'Use approved line checks.',
    category: 'broadband_connectivity', similarity_score: 0.71 }],
  resolution: { problem_summary: 'Recurring drops', resolution_steps: [{ step_number: 1,
    action: 'Check the line status.', source_ids: ['KB-001'] }],
    escalation_recommendation: 'Escalate if persistent.', confidence_or_evidence_note: 'Based on approved guidance.',
    sources_used: ['KB-001'], insufficient_evidence: false },
  source_ids: ['KB-001'], insufficient_evidence: false, non_actionable: false, latency_ms: 123.4,
}

async function readyApp() {
  render(<App />)
  await screen.findByText('Backend ready')
}

async function submit(text = complaint) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Complaint text'), text)
  await user.click(screen.getByRole('button', { name: 'Analyze & Resolve' }))
}

beforeEach(() => {
  vi.clearAllMocks()
  health.mockResolvedValue({ status: 'ok' })
  readiness.mockResolvedValue({ statusCode: 200, body: {
    status: 'ready', database: true, search_index: true, embedding_model: true, gemini_configured: true,
  } })
  resolve.mockResolvedValue(normal)
})
afterEach(() => cleanup())

describe('support workspace', () => {
  it('renders the initial dashboard and empty draft', async () => {
    await readyApp()
    expect(screen.getByText('Support Resolution Assistant')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Intelligent Support Ticket Resolution Assistant')
    expect(screen.getByText('Enter the customer’s telecom complaint.')).toBeInTheDocument()
    expect(screen.getByText('Review the generated resolution and cited sources before using it with a customer.')).toBeInTheDocument()
    expect(screen.getByText('Ready when you are')).toBeInTheDocument()
  })

  it('accepts textarea input and updates the character count', async () => {
    await readyApp()
    fireEvent.change(screen.getByLabelText('Complaint text'), { target: { value: 'No signal.' } })
    expect(screen.getByLabelText('Complaint text')).toHaveValue('No signal.')
    expect(screen.getByText('10 / 3000 characters')).toBeInTheDocument()
  })

  it('accepts exactly 3000 characters and rejects 3001 without truncating', async () => {
    await readyApp()
    const input = screen.getByLabelText('Complaint text')
    fireEvent.change(input, { target: { value: 'a'.repeat(3000) } })
    expect(screen.getByRole('button', { name: 'Analyze & Resolve' })).toBeEnabled()
    fireEvent.change(input, { target: { value: 'a'.repeat(3001) } })
    expect(input).toHaveValue('a'.repeat(3001))
    expect(screen.getByText('3001 / 3000 characters')).toBeInTheDocument()
    expect(screen.getByText('Complaint must be 3000 characters or fewer.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyze & Resolve' })).toBeDisabled()
  })

  it('disables submission for empty or whitespace input', async () => {
    await readyApp()
    expect(screen.getByRole('button', { name: 'Analyze & Resolve' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Complaint text'), { target: { value: '   ' } })
    expect(screen.getByRole('button', { name: 'Analyze & Resolve' })).toBeDisabled()
    expect(resolve).not.toHaveBeenCalled()
  })

  it('shows loading and disables duplicate submission', async () => {
    let finish!: (value: ResolveResponse) => void
    resolve.mockReturnValue(new Promise(resolvePromise => { finish = resolvePromise }))
    await readyApp()
    await submit()
    expect(screen.getByRole('button', { name: 'Analyzing complaint…' })).toBeDisabled()
    expect(screen.getByText('Checking approved evidence')).toBeInTheDocument()
    finish(normal)
    await screen.findByText('Recurring drops')
    expect(resolve).toHaveBeenCalledTimes(1)
  })

  it('submits the complaint to /resolve service and shows the summary', async () => {
    await readyApp()
    await submit()
    expect(resolve).toHaveBeenCalledWith(complaint)
    expect(await screen.findByText('Recurring drops')).toBeInTheDocument()
    expect(screen.getByText('Ready for agent review')).toBeInTheDocument()
  })

  it('renders the four analysis cards and intent', async () => {
    await readyApp(); await submit()
    expect((await screen.findAllByText('Broadband Connectivity')).length).toBeGreaterThan(0)
    expect(screen.getByText('Frustrated')).toBeInTheDocument()
    expect(screen.getByText(/restore broadband/)).toBeInTheDocument()
  })

  it('renders cited numbered steps, source IDs, escalation, and evidence note', async () => {
    await readyApp(); await submit()
    expect(await screen.findByText('Check the line status.')).toBeInTheDocument()
    expect(screen.getByLabelText('Step 1')).toBeInTheDocument()
    expect(within(screen.getAllByLabelText('Citations')[0]).getByText('KB-001')).toBeInTheDocument()
    expect(screen.getByText('Escalate if persistent.')).toBeInTheDocument()
    expect(screen.getByText('Based on approved guidance.')).toBeInTheDocument()
    expect(screen.getAllByText('Review the generated resolution and cited sources before using it with a customer.')).toHaveLength(1)
  })

  it('shows real ticket evidence and similarity', async () => {
    await readyApp(); await submit()
    const tickets = screen.getByText('Similar resolved tickets').closest('div.rounded-2xl')!
    expect(await within(tickets as HTMLElement).findByText(/T-001 · similarity 0.780/)).toBeInTheDocument()
    expect(within(tickets as HTMLElement).getByText('Similarity scores rank retrieved matches.')).toBeInTheDocument()
  })

  it('shows real KB evidence and source ID', async () => {
    await readyApp(); await submit()
    expect(await screen.findByText(/KB-001 · Connection checks · similarity 0.710/)).toBeInTheDocument()
  })

  it('starts every retrieved evidence accordion closed and opens selected evidence on request', async () => {
    await readyApp(); await submit()
    const evidence = (await screen.findByRole('heading', { name: 'Retrieved evidence' })).closest('section')!
    const accordions = evidence.querySelectorAll('details')
    expect(accordions).toHaveLength(2)
    accordions.forEach(accordion => expect(accordion.open).toBe(false))
    await userEvent.click(screen.getByText(/T-001 · similarity 0.780/))
    expect(accordions[0].open).toBe(true)
    expect(accordions[1].open).toBe(false)
    expect(within(accordions[0]).getByText('Check the line.')).toBeVisible()
    const system = screen.getByText('System information').closest('details')!
    expect(system.open).toBe(false)
    await userEvent.click(screen.getByText('System information'))
    expect(within(system).getByText('Backend processing time:', { exact: false })).toBeVisible()
  })

  it('shows backend clarification without fabricated evidence for non-actionable input', async () => {
    resolve.mockResolvedValue({ ...normal, tickets: [], kb_articles: [], source_ids: [],
      insufficient_evidence: true, non_actionable: true,
      resolution: { problem_summary: 'No clear telecom issue was identified.', resolution_steps: [],
        escalation_recommendation: 'Please describe the telecom service problem you need help with.',
        confidence_or_evidence_note: 'Retrieval was skipped.', sources_used: [], insufficient_evidence: true } })
    await readyApp(); await submit('I watched a movie yesterday.')
    expect(await screen.findByText('Clarification needed')).toBeInTheDocument()
    expect(screen.getByText('Please describe the telecom service problem you need help with.')).toBeInTheDocument()
    expect(screen.queryByText('Similar resolved tickets')).not.toBeInTheDocument()
    expect(screen.queryByText('Resolution steps')).not.toBeInTheDocument()
  })

  it.each([
    ['I forgot my Gmail password.', 'Please enter a telecom account or service problem.'],
    ['forgot my wifi password 😢🥵 and cannot log in', 'Do you mean the Wi-Fi network password for your router, or the password for your telecom account?'],
  ])('renders backend clarification without evidence for %s', async (input, clarification) => {
    resolve.mockResolvedValue({ ...normal, tickets: [], kb_articles: [], source_ids: [],
      insufficient_evidence: true, non_actionable: true,
      analysis: { ...normal.analysis, category: 'other', product: 'other', needs_review: true },
      resolution: { problem_summary: 'Clarification needed.', resolution_steps: [],
        escalation_recommendation: clarification, confidence_or_evidence_note: 'Retrieval was skipped.',
        sources_used: [], insufficient_evidence: true } })
    await readyApp(); await submit(input)
    expect(await screen.findByText(clarification)).toBeInTheDocument()
    expect(screen.queryByText('Similar resolved tickets')).not.toBeInTheDocument()
    expect(screen.queryByText('Relevant KB articles')).not.toBeInTheDocument()
    expect(screen.queryByText('Resolution steps')).not.toBeInTheDocument()
  })

  it('handles insufficient evidence without showing steps', async () => {
    resolve.mockResolvedValue({ ...normal, source_ids: [], insufficient_evidence: true,
      resolution: { ...normal.resolution, resolution_steps: [], sources_used: [],
        insufficient_evidence: true, confidence_or_evidence_note: 'Approved evidence is insufficient.' } })
    await readyApp(); await submit()
    expect(await screen.findByText('Insufficient approved evidence')).toBeInTheDocument()
    expect(screen.getByText('Approved evidence is insufficient.')).toBeInTheDocument()
    expect(screen.queryByText('Check the line status.')).not.toBeInTheDocument()
    expect(screen.getByText(/Candidate matches only/)).toBeInTheDocument()
  })

  it('shows a safe API error without losing the complaint', async () => {
    resolve.mockRejectedValue(new ApiRequestError('The AI provider is unavailable right now. Please try again later.'))
    await readyApp(); await submit()
    expect(await screen.findByRole('alert')).toHaveTextContent('The AI provider is unavailable')
    expect(screen.getByLabelText('Complaint text')).toHaveValue(complaint)
  })

  it('shows backend-ready status and dependency information', async () => {
    await readyApp()
    expect(screen.getByRole('status')).toHaveTextContent('Backend ready')
    expect(readiness).toHaveBeenCalled()
    const system = screen.getByText('System information').closest('details')!
    expect(system.open).toBe(false)
    await userEvent.click(screen.getByText('System information'))
    expect(system.open).toBe(true)
    expect(within(system).getByText('Gemini configured:', { exact: false })).toBeVisible()
  })

  it('shows backend-unavailable state and offers retry', async () => {
    readiness.mockResolvedValue({ statusCode: 503, body: { status: 'not_ready', database: false,
      search_index: false, embedding_model: false, gemini_configured: false } })
    render(<App />)
    expect(await screen.findByText('Backend unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyze & Resolve' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Retry backend connection' })).toBeInTheDocument()
  })

  it('retries an unavailable backend and returns to ready', async () => {
    readiness.mockResolvedValueOnce({ statusCode: 404, body: null })
    render(<App />)
    await screen.findByText('Backend unavailable')
    await userEvent.click(screen.getByRole('button', { name: 'Retry backend connection' }))
    expect(await screen.findByText('Backend ready')).toBeInTheDocument()
  })

  it('returns to waking state after a connection failure', async () => {
    resolve.mockRejectedValue(new ApiRequestError('Backend is starting. Please wait until the status changes to Ready.', true))
    await readyApp(); await submit()
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend is starting')
    await waitFor(() => expect(readiness).toHaveBeenCalledTimes(2))
  })
})
