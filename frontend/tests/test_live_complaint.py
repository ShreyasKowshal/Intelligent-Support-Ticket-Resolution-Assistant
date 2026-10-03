"""Check the component boundary; browser behavior is also verified manually."""

from types import SimpleNamespace

from frontend import live_complaint


def test_input_events_update_only_local_feedback():
    js = live_complaint.JS
    assert "input.oninput = update" in js
    assert "Array.from(input.value).length" in js
    assert "counter.textContent" in js
    assert "validation.hidden = !tooLong" in js
    assert "!input.value.trim()" in js
    assert "!data.ready" in js
    assert "setStateValue" not in js
    assert "fetch(" not in js


def test_only_button_click_sends_current_complaint_to_python():
    js = live_complaint.JS
    click_handler = js.split("button.onclick = () => {", 1)[1]
    assert "const complaint = input.value" in click_handler
    assert "if (button.disabled) return" in click_handler
    assert "setTriggerValue('submit', { complaint, id: crypto.randomUUID() })" in click_handler
    assert "input.dataset.pending = 'true'" in click_handler


def test_component_receives_ready_state_and_shared_length(monkeypatch):
    captured = {}

    def register(name, *, html, css, js):
        captured.update(name=name, html=html, css=css, js=js)

        def mount(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(submit=None)

        return mount

    monkeypatch.setattr(live_complaint.st.components.v2, "component", register)
    assert live_complaint.complaint_input(ready=True, initial_value="draft", ack=2) is None
    assert captured["data"] == {
        "ready": True, "max_length": 3000, "initial_value": "draft", "ack": 2,
    }
    assert captured["key"] == "complaint_input"
    assert callable(captured["on_submit_change"])
