"""A live multiline input using Streamlit's supported Components v2 API.

Native st.text_area commits on blur or Ctrl+Enter, so its value cannot drive a
counter or disabled button while the customer is still typing.
"""

from collections.abc import Callable

import streamlit as st


HTML = '<textarea aria-label="Customer complaint" placeholder="Paste the customer\'s raw telecom complaint here..."></textarea>'
CSS = """
        textarea {
            box-sizing: border-box;
            display: block;
            width: 100%;
            height: 170px;
            padding: 0.75rem;
            resize: vertical;
            border: 1px solid var(--st-border-color, #888);
            border-radius: 0.5rem;
            background: var(--st-secondary-background-color, transparent);
            color: var(--st-text-color, inherit);
            font: inherit;
        }
        textarea:focus { outline: 2px solid var(--st-primary-color, #f63366); }
    """
JS = """
        export default function({ parentElement, data, setStateValue }) {
            const input = parentElement.querySelector('textarea');
            if (!input.dataset.initialized) {
                input.value = data.value ?? '';
                input.dataset.initialized = 'true';
            }
            input.oninput = () => setStateValue('value', input.value);
            return () => { input.oninput = null; };
        }
    """


def complaint_text_area(on_change: Callable[[], None]) -> str:
    """Return the single complaint value; each input event updates component state."""
    # Registration belongs to the active script run, including AppTest reruns.
    complaint_input = st.components.v2.component(
        "live_complaint_input", html=HTML, css=CSS, js=JS,
    )
    current = st.session_state.get("complaint_input", {}).get("value", "")
    result = complaint_input(
        data={"value": current}, default={"value": current}, key="complaint_input",
        on_value_change=on_change, height=180,
    )
    return result.value or ""
