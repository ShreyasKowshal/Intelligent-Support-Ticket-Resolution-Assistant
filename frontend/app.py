"""Support-agent page: one complaint goes through FastAPI's /resolve route."""

import streamlit as st

from frontend.api_client import FrontendError, MAX_COMPLAINT_LENGTH, ResolveResult, resolve_complaint

EXAMPLES = {
    "Broadband dropouts": "My broadband drops every evening around 8 PM and I already restarted the router twice.",
    "Unexpected billing fee": "I was charged an extra fee this month and I don't know why.",
    "Mobile data failure": "Calls work but my mobile internet does not.",
    "Frustrated service outage": "This is the third day my home internet has failed. I work from home and I'm very frustrated.",
    "Unusual optical alarm": "My fiber modem shows a red optical signal alarm after a storm, and no service works.",
}


def clear_previous_result() -> None:
    """Keep a prior recommendation from appearing under a newly edited complaint."""
    st.session_state.result = None
    st.session_state.error_message = None


def show_analysis(result: ResolveResult) -> None:
    analysis = result.analysis
    st.header("1. Complaint Analysis")
    if analysis.needs_review:
        st.warning("Agent review required: verify this classification before advising the customer.")
    if analysis.severity.upper() in ("HIGH", "CRITICAL"):
        st.warning(f"{analysis.severity.title()} severity — prioritize this case.")
    left, middle, right = st.columns(3)
    left.metric("Category", analysis.category)
    middle.metric("Product", analysis.product)
    right.metric("Severity", analysis.severity.title())
    st.write("**Intent:**", analysis.intent)
    st.write("**Customer sentiment:**", analysis.sentiment.title())
    st.write("**Model self-assessed confidence:**", f"{analysis.confidence:.2f}")
    st.write("**Needs review:**", "Yes" if analysis.needs_review else "No")
    if analysis.suggested_category:
        st.write("**Suggested new category:**", analysis.suggested_category)
    st.write("**Rationale:**", analysis.rationale)


def show_tickets(result: ResolveResult) -> None:
    st.header("2. Similar Resolved Tickets")
    st.caption("Similarity scores rank matches; they are not calibrated probabilities.")
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
    if not result.kb_articles:
        st.info("No approved knowledge base articles were retrieved.")
    for article in result.kb_articles:
        with st.expander(f"{article.source_id} · {article.title} · similarity {article.similarity_score:.3f}"):
            st.write("**Category:**", article.category)
            st.write("**Guidance:**", article.content)


def show_resolution(result: ResolveResult) -> None:
    resolution = result.resolution
    st.header("4. Recommended Resolution")
    if result.insufficient_evidence:
        st.warning("Insufficient evidence: no step-by-step fix is proposed. Review this case or escalate it.")
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
    st.title("Intelligent Support Ticket Resolution Assistant")
    st.write(
        "Analyze telecom complaints, find similar approved cases and knowledge-base guidance, "
        "and review a cited resolution draft."
    )
    st.session_state.setdefault("complaint", "")
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("error_message", None)

    with st.sidebar:
        st.subheader("Try a sample complaint")
        st.caption("Selecting an example fills the box; submit it to run the real backend workflow.")
        for label, example in EXAMPLES.items():
            if st.button(label, key=f"sample_{label}", use_container_width=True):
                st.session_state.complaint = example
                st.session_state.result = None
                st.session_state.error_message = None

    st.text_area(
        "Customer complaint", key="complaint", height=170,
        placeholder="Paste the customer's raw telecom complaint here...",
        help=f"Up to {MAX_COMPLAINT_LENGTH} characters.",
        on_change=clear_previous_result,
    )
    if st.button("Analyze & Resolve", type="primary", use_container_width=True):
        st.session_state.result = None
        st.session_state.error_message = None
        try:
            with st.spinner("Analyzing the complaint and checking approved evidence..."):
                st.session_state.result = resolve_complaint(st.session_state.complaint)
        except FrontendError as exc:
            st.session_state.error_message = str(exc)

    if st.session_state.error_message:
        st.error(st.session_state.error_message)
    result = st.session_state.result
    if result is not None:
        show_analysis(result)
        show_tickets(result)
        show_kb_articles(result)
        show_resolution(result)
        show_sources_and_system(result)


if __name__ == "__main__":
    main()
