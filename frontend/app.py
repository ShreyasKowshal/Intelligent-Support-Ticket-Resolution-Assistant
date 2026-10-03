"""Support-agent page: one complaint goes through FastAPI's /resolve route."""

from hashlib import sha256
from time import monotonic

import streamlit as st

from frontend import live_complaint
from frontend.api_client import (
    BackendConnectionError, FrontendError, MAX_COMPLAINT_LENGTH, ResolveResult,
    check_backend_health, check_backend_readiness, resolve_complaint,
)

RETRY_INTERVAL_SECONDS = 5
RETRY_WINDOW_SECONDS = 120
STATUS_LABELS = {
    "starting": ("🟡 Starting backend...", "starting"),
    "ready": ("🟢 Backend ready", "ready"),
    "unavailable": ("🔴 Backend unavailable", "unavailable"),
}


def start_backend_check() -> None:
    """Start a bounded /health wake and /ready verification window."""
    st.session_state.backend_state = "starting"
    st.session_state.backend_stage = "wake"
    st.session_state.backend_started_at = monotonic()
    st.session_state.backend_next_check_at = 0.0


def poll_backend_status() -> bool:
    """Return whether the two-stage check reached ready or unavailable."""
    if st.session_state.backend_state != "starting":
        return False
    now = monotonic()
    if now - st.session_state.backend_started_at >= RETRY_WINDOW_SECONDS:
        st.session_state.backend_state = "unavailable"
        return True
    if now < st.session_state.backend_next_check_at:
        return False
    if st.session_state.backend_stage == "wake":
        health = check_backend_health()
        if health == "unavailable":
            st.session_state.backend_state = "unavailable"
            return True
        if health == "starting":
            st.session_state.backend_next_check_at = now + RETRY_INTERVAL_SECONDS
            return False
        st.session_state.backend_stage = "ready"
    state = check_backend_readiness()
    if state == "ready" or state == "unavailable":
        st.session_state.backend_state = state
        return True
    if monotonic() - st.session_state.backend_started_at >= RETRY_WINDOW_SECONDS:
        st.session_state.backend_state = "unavailable"
        return True
    st.session_state.backend_next_check_at = now + RETRY_INTERVAL_SECONDS
    return False


def show_backend_status() -> None:
    if poll_backend_status():
        # The submit button is outside this fragment and needs a full rerun.
        st.rerun()
    label, style = STATUS_LABELS[st.session_state.backend_state]
    st.markdown(
        f'<div class="backend-status {style}">{label}</div>', unsafe_allow_html=True,
    )
    if st.session_state.backend_state == "unavailable":
        if st.button("Retry backend connection", key="retry_backend_connection"):
            start_backend_check()
            st.rerun()


def clear_previous_result() -> None:
    """Keep a prior recommendation from appearing under a newly edited complaint."""
    st.session_state.result = None
    st.session_state.error_message = None
    st.session_state.result_input_fingerprint = None


def complaint_fingerprint(complaint: str) -> str:
    return sha256(complaint.encode("utf-8")).hexdigest()


def show_analysis(result: ResolveResult) -> None:
    analysis = result.analysis
    st.header("1. Complaint Analysis")
    if analysis.needs_review and not result.non_actionable:
        st.warning("Agent review required: verify this classification before advising the customer.")
    if analysis.severity.upper() in ("HIGH", "CRITICAL") and not result.non_actionable:
        st.warning(f"{analysis.severity.title()} severity — prioritize this case.")
    left, middle, right, sentiment = st.columns(4)
    left.metric("Category", analysis.category)
    middle.metric("Product", analysis.product)
    right.metric("Severity", analysis.severity.title())
    sentiment.metric("Sentiment", analysis.sentiment.title())
    st.write("**Intent:**", analysis.intent)
    confidence, review = st.columns(2)
    confidence.metric("Model self-assessed confidence", f"{analysis.confidence:.2f}")
    review.metric("Needs review", "Yes" if analysis.needs_review else "No")
    if analysis.suggested_category:
        st.write("**Suggested new category:**", analysis.suggested_category)
    st.write("**Rationale:**", analysis.rationale)


def show_tickets(result: ResolveResult) -> None:
    st.header("2. Similar Resolved Tickets")
    st.caption("Similarity scores rank matches; they are not calibrated probabilities.")
    if result.insufficient_evidence and result.tickets:
        st.info("Candidate matches only — this evidence did not support a reliable resolution.")
    if not result.tickets:
        st.info("No approved resolved tickets were retrieved.")
    for ticket in result.tickets:
        with st.expander(f"{ticket.source_id} · similarity {ticket.similarity_score:.3f}"):
            st.write("**Complaint:**", ticket.complaint)
            st.write("**Product:**", ticket.product)
            st.write("**Category:**", ticket.category)
            st.write("**Historical resolution:**", ticket.resolution)


def show_kb_articles(result: ResolveResult) -> None:
    st.header("3. Relevant Knowledge Base Articles")
    st.caption("Similarity scores rank matches; they are not calibrated probabilities.")
    if result.insufficient_evidence and result.kb_articles:
        st.info("Candidate matches only — verify relevance before using this guidance.")
    if not result.kb_articles:
        st.info("No approved knowledge base articles were retrieved.")
    for article in result.kb_articles:
        with st.expander(f"{article.source_id} · {article.title} · similarity {article.similarity_score:.3f}"):
            st.write("**Category:**", article.category)
            st.write("**Guidance:**", article.content)


def show_resolution(result: ResolveResult) -> None:
    resolution = result.resolution
    st.header("4. Resolution Draft")
    if result.insufficient_evidence:
        st.warning("Insufficient evidence: no reliable resolution was generated. Review this case or escalate it.")
        st.warning("Agent review required: gather approved guidance before advising the customer.")
    else:
        st.warning("Agent review required: verify every step against current KB guidance before advising the customer.")
    st.write("**Problem summary:**", resolution.problem_summary)
    if not result.insufficient_evidence:
        for step in resolution.resolution_steps:
            st.write(f"{step.step_number}. {step.action}")
            st.caption("Citations: " + ", ".join(step.source_ids))
    st.write("**Escalation recommendation:**", resolution.escalation_recommendation)
    st.write("**Evidence note:**", resolution.confidence_or_evidence_note)


def show_sources_and_system(result: ResolveResult) -> None:
    st.header("5. Sources Used")
    if result.source_ids:
        st.write(", ".join(result.source_ids))
    else:
        st.info("No sources were cited because the evidence was insufficient.")
    st.header("6. System Information")
    st.caption(f"Backend processing time: {result.latency_ms:,.0f} ms")


def main() -> None:
    st.set_page_config(page_title="Intelligent Support Ticket Resolution Assistant", page_icon="🎧", layout="wide")
    st.markdown("""
        <style>
        .backend-status { color: inherit; font-size: .8rem; font-weight: 600;
            line-height: 1.35; padding: .2rem 0; text-align: right; white-space: nowrap; }
        </style>
    """, unsafe_allow_html=True)
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("error_message", None)
    st.session_state.setdefault("result_input_fingerprint", None)
    st.session_state.setdefault("last_submitted_complaint", "")
    st.session_state.setdefault("last_submit_id", None)
    st.session_state.setdefault("submission_ack", 0)
    if "backend_state" not in st.session_state or "backend_stage" not in st.session_state:
        start_backend_check()

    @st.fragment(run_every=RETRY_INTERVAL_SECONDS if st.session_state.backend_state == "starting" else None)
    def backend_status_panel() -> None:
        show_backend_status()

    _, status_column = st.columns([5, 2], vertical_alignment="top")
    with status_column:
        backend_status_panel()
    st.title("Intelligent Support Ticket Resolution Assistant")
    st.caption("Analyze telecom complaints and review cited guidance from approved support evidence.")

    with st.container(border=True):
        st.subheader("Customer complaint")
        submission = live_complaint.complaint_input(
            ready=st.session_state.backend_state == "ready",
            initial_value=st.session_state.last_submitted_complaint,
            ack=st.session_state.submission_ack,
        )
        if isinstance(submission, dict) and submission.get("id") != st.session_state.last_submit_id:
            st.session_state.last_submit_id = submission.get("id")
            complaint = submission.get("complaint")
            clear_previous_result()
            try:
                if st.session_state.backend_state != "ready":
                    raise FrontendError("Backend is starting. Please wait until the status changes to Ready.")
                if not isinstance(complaint, str) or not complaint.strip():
                    raise FrontendError("Enter a customer complaint before continuing.")
                if len(complaint) > MAX_COMPLAINT_LENGTH:
                    raise FrontendError(f"Complaint must be {MAX_COMPLAINT_LENGTH} characters or fewer.")
                st.session_state.last_submitted_complaint = complaint
                with st.spinner("Analyzing the complaint and checking approved evidence..."):
                    st.session_state.result = resolve_complaint(complaint)
                    st.session_state.result_input_fingerprint = complaint_fingerprint(complaint)
            except BackendConnectionError as exc:
                st.session_state.error_message = str(exc)
                start_backend_check()
            except FrontendError as exc:
                st.session_state.error_message = str(exc)
            finally:
                st.session_state.submission_ack += 1
                st.rerun()

    if st.session_state.error_message:
        st.error(st.session_state.error_message)
    result = st.session_state.result
    if result is not None:
        with st.container(border=True):
            show_analysis(result)
        if result.non_actionable:
            with st.container(border=True):
                st.info("No clear telecom issue was identified. Please enter a customer complaint describing the problem.")
                st.markdown("Please provide the affected telecom service, what is not working, and when the issue occurs.")
                st.caption("Retrieval and resolution drafting were intentionally skipped for this input.")
                st.subheader("System Information")
                st.caption(f"Backend processing time: {result.latency_ms:,.0f} ms")
        else:
            ticket_column, kb_column = st.columns(2, gap="large")
            with ticket_column, st.container(border=True):
                show_tickets(result)
            with kb_column, st.container(border=True):
                show_kb_articles(result)
            with st.container(border=True):
                show_resolution(result)
            with st.container(border=True):
                show_sources_and_system(result)


if __name__ == "__main__":
    main()
