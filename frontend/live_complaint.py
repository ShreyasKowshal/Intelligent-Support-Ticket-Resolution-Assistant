"""Client-side complaint editing; only an explicit submit reaches Python."""

import streamlit as st

from frontend.api_client import MAX_COMPLAINT_LENGTH

HTML = """
<textarea aria-label="Customer complaint" placeholder="Paste the customer's raw telecom complaint here..."></textarea>
<div class="counter" aria-live="polite">0 / 3000 characters</div>
<div class="validation" role="alert" hidden></div>
<button type="button" disabled>Analyze &amp; Resolve</button>
"""

CSS = """
textarea {
    box-sizing: border-box; display: block; width: 100%; height: 170px;
    padding: .75rem; resize: vertical; border: 1px solid var(--st-border-color, #888);
    border-radius: .5rem; background: var(--st-secondary-background-color, transparent);
    color: var(--st-text-color, inherit); font: inherit;
}
textarea:focus { outline: 2px solid var(--st-primary-color, #f63366); }
.counter { margin: .4rem 0 .8rem; color: var(--st-text-color, inherit); opacity: .7; font-size: .8rem; }
.validation { margin: -.3rem 0 .7rem; color: #c73636; font-size: .85rem; }
.validation[hidden] { display: none; }
button {
    box-sizing: border-box; width: 100%; min-height: 2.5rem; border: 0; border-radius: .5rem;
    background: var(--st-primary-color, #f63366); color: white; font: inherit;
    font-weight: 600; cursor: pointer;
}
button:disabled { opacity: .45; cursor: not-allowed; }
"""

JS = """
export default function({ parentElement, data, setTriggerValue }) {
    const input = parentElement.querySelector('textarea');
    const counter = parentElement.querySelector('.counter');
    const validation = parentElement.querySelector('.validation');
    const button = parentElement.querySelector('button');
    const acknowledgement = String(data.ack);

    if (!input.dataset.initialized) {
        input.value = data.initial_value ?? '';
        input.dataset.initialized = 'true';
        input.dataset.ack = acknowledgement;
    } else if (input.dataset.ack !== acknowledgement) {
        input.dataset.ack = acknowledgement;
        input.dataset.pending = '';
        input.disabled = false;
    }

    function update() {
        const length = Array.from(input.value).length;
        const tooLong = length > data.max_length;
        counter.textContent = `${length} / ${data.max_length} characters`;
        validation.textContent = tooLong ? `Complaint must be ${data.max_length} characters or fewer.` : '';
        validation.hidden = !tooLong;
        button.disabled = !data.ready || !input.value.trim() || tooLong || input.dataset.pending === 'true';
    }

    input.oninput = update;
    button.onclick = () => {
        update();
        if (button.disabled) return;
        const complaint = input.value;
        input.dataset.pending = 'true';
        input.disabled = true;
        update();
        setTriggerValue('submit', { complaint, id: crypto.randomUUID() });
    };
    update();
    return () => { input.oninput = null; button.onclick = null; };
}
"""


def complaint_input(*, ready: bool, initial_value: str, ack: int):
    """Render one input with local feedback and a one-shot submit event."""
    component = st.components.v2.component(
        "complaint_input", html=HTML, css=CSS, js=JS,
    )
    result = component(
        data={
            "ready": ready, "max_length": MAX_COMPLAINT_LENGTH,
            "initial_value": initial_value, "ack": ack,
        },
        key="complaint_input", on_submit_change=lambda: None, height=245,
    )
    return result.submit
