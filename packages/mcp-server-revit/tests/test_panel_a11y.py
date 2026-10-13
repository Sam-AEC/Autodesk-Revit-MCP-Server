"""Static accessibility / layout / behaviour guards for the dockable panel (panel/).

The panel runs inside WebView2 in Revit, so these are string-level checks plus a
node stub-DOM harness that run anywhere. Anything needing a live WebView2 is
verified by hand (see the PR description).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PANEL = Path(__file__).resolve().parents[3] / "panel"
CSS = (PANEL / "styles.css").read_text(encoding="utf-8")
HTML = (PANEL / "index.html").read_text(encoding="utf-8")
JS = (PANEL / "app.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------- contrast


def _rgba(value: str):
    value = value.strip()
    if value.startswith("#"):
        h = value[1:]
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
    m = re.match(r"rgba?\(([^)]*)\)", value)
    parts = [p.strip() for p in m.group(1).split(",")]
    a = float(parts[3]) if len(parts) > 3 else 1.0
    return (float(parts[0]), float(parts[1]), float(parts[2]), a)


def _over(fg, bg):
    r, g, b, a = fg
    return tuple(c * a + k * (1 - a) for c, k in zip((r, g, b), bg[:3])) + (1.0,)


def _lum(c) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def ratio(fg, bg) -> float:
    a, b = _lum(_over(fg, bg)), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _block(selector_re: str) -> str:
    m = re.search(selector_re + r"\s*\{(.*?)\n\}", CSS, re.S | re.M)
    assert m, selector_re
    return m.group(1)


def _tokens(block: str) -> dict:
    return dict(re.findall(r"(--amb-[\w-]+):\s*([^;]+);", block))


def themes() -> dict:
    light = _tokens(_block(r"^:root"))
    dark = {**light, **_tokens(_block(r'^:root\[data-theme="dark"\]'))}
    return {"light": light, "dark": dark}


def _primary_bg(t: dict) -> str:
    """Background the primary button actually paints (first rule of button.primary)."""
    m = re.search(
        r"^button\.primary\s*\{[^}]*?background:\s*var\((--amb-[\w-]+)\)", CSS, re.M
    )
    assert m
    return t[m.group(1)]


# (foreground token, background token or 'PRIMARY', minimum ratio, what it is)
PAIRS = [
    ("ink", "bg", 4.5, "body text"),
    ("ink", "surface", 4.5, "card text"),
    ("ink-muted", "bg", 4.5, "secondary text on app bg"),
    ("ink-muted", "surface", 4.5, "secondary text on card"),
    ("ink-muted", "surface-raised", 4.5, "status pill text"),
    ("on-brand", "PRIMARY", 4.5, "primary button label"),
    ("brand-strong", "surface", 4.5, "brand text"),
    ("success", "surface", 4.5, "setup ready text"),
    ("danger", "surface", 4.5, "setup blocked text / error message"),
    ("rail-ink", "rail", 4.5, "nav label"),
    ("brand", "surface", 3.0, "focus ring / graphics"),
    ("info", "surface-raised", 4.5, "mode chip: Look only"),
    ("pending", "surface-raised", 4.5, "mode chip: Ask me first"),
    ("ink", "surface-raised", 4.5, "mode chip: Auto"),
    ("warning", "surface", 4.5, "look-only / auto note in chat cards"),
    ("ink", "danger-wash", 4.5, "chat error text on its wash"),
    ("brand-strong", "surface", 4.5, "chat link text"),
]
LIGHT_BADGES = ("danger", "warning", "info", "success", "pending", "idle")


def measure():
    out = []
    for name, t in themes().items():
        base = _rgba(t["--amb-surface"])
        for fg, bg, minimum, what in PAIRS:
            bgv = _primary_bg(t) if bg == "PRIMARY" else t[f"--amb-{bg}"]
            fgv = t[f"--amb-{fg}"]
            out.append(
                (
                    name,
                    what,
                    fgv,
                    bgv,
                    ratio(_rgba(fgv), _over(_rgba(bgv), base)),
                    minimum,
                )
            )
        if name == "light":
            for kind in LIGHT_BADGES:
                bgv = t[f"--amb-{kind}"]
                out.append(
                    (
                        name,
                        f"{kind} badge",
                        "#FFFFFF",
                        bgv,
                        ratio(_rgba("#FFFFFF"), _rgba(bgv)),
                        4.5,
                    )
                )
    return out


@pytest.mark.parametrize("row", measure(), ids=lambda r: f"{r[0]}-{r[1]}")
def test_contrast_meets_wcag_aa(row):
    theme, what, fg, bg, got, minimum = row
    assert got >= minimum, f"{theme} {what}: {fg} on {bg} = {got:.2f}:1 < {minimum}:1"


def test_dark_badges_meet_aa():
    surface = _rgba(themes()["dark"]["--amb-surface"])
    rules = re.findall(
        r'^:root\[data-theme="dark"\] \.badge\.\w+\s*\{\s*background:\s*(rgba\([^)]*\));[^}]*?color:\s*(#\w+);',
        CSS,
        re.M,
    )
    assert len(rules) == 6
    for bg, fg in rules:
        assert ratio(_rgba(fg), _over(_rgba(bg), surface)) >= 4.5, (fg, bg)


# ------------------------------------------------------------------ layout


def test_narrow_layout_rules():
    assert re.search(r"@media\s*\(max-width:\s*\d+px\)", CSS), (
        "no narrow-width media query"
    )
    body = _block(r"^body")
    assert "min-width: 320px" not in body, "body min-width forces horizontal scroll"
    assert "overflow-wrap" in CSS


def test_active_view_scrolls_inside_a_bounded_row():
    """A long plan list must scroll inside the view, not push the top bar away."""
    app = _block(r"\.app")
    assert "display: flex" in app and "flex-direction: column" in app
    assert "height: 100vh" in app
    view = re.search(r"\.app > \.view\.is-active\s*\{([^}]*)\}", CSS)
    assert view, "active view is not given the remaining height"
    assert "flex: 1 1 auto" in view.group(1) and "min-height: 0" in view.group(1)
    assert "overflow: auto" in view.group(1)
    assert "grid-auto-rows: auto" not in app
    assert "overflow: hidden" in _block(r"^body")


def test_status_pill_keeps_port_visible_when_narrow():
    body = _block(r"\.status-pill")
    assert "white-space: nowrap" not in body
    assert "text-overflow: ellipsis" not in CSS.split(".status-pill > span:last-child")[1].split("}")[0]


# ------------------------------------------------------------------- plans


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    return node


HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
class HTMLElement {}
function el(id) {
  const e = new HTMLElement();
  Object.assign(e, { id, dataset: {}, children: [], _html: '', hidden: false, disabled: false, value: 'all',
    classList: { toggle(){}, add(){}, remove(){} }, style: {}, handlers: {},
    setAttribute(){}, removeAttribute(){}, appendChild(c){ this.children.push(c); return c; },
    append(){}, replaceChildren(){}, replaceWith(){}, remove(){},
    addEventListener(t, f){ (this.handlers[t] = this.handlers[t] || []).push(f); },
    querySelector(){ return el('q'); }, querySelectorAll(){ return []; },
    lastElementChild: el0(), selectedOptions: [], options: [] });
  Object.defineProperty(e, 'innerHTML', {
    set(v){ this._html = v; if (v === '') this.children = []; },
    get(){ return this._html + this.children.map((c) => c.innerHTML).join(''); } });
  Object.defineProperty(e, 'textContent', { set(v){ this._t = v; }, get(){ return this._t || ''; } });
  return e;
}
function el0() { return { textContent: '' }; }
const els = {};
const buttons = [];
global.HTMLElement = HTMLElement;
global.document = {
  getElementById: (id) => els[id] || (els[id] = el(id)),
  createElement: () => el('new'),
  querySelectorAll: (sel) => (sel.includes('data-action') ? buttons : []),
  querySelector: () => el('q'),
  body: el('body'), documentElement: { dataset: {} },
};
const sent = [];
global.window = { chrome: { webview: {
  postMessage: (m) => sent.push(JSON.parse(m)),
  addEventListener: (t, f) => { global.__onmsg = f; } } } };
global.sent = sent; global.els = els; global.buttons = buttons;
(0, eval)(src);
function host(extra) { __onmsg({ data: Object.assign({ type: 'host.status', serverRunning: true, activeDocument: 'm.rvt' }, extra) }); }
function plans(list) { __onmsg({ data: { type: 'plans.updated', result: { plans: list } } }); }
function fire(type, dataset) {
  const t = new HTMLElement(); t.dataset = dataset; t.checked = dataset.checked === 'true';
  (document.body.handlers[type] || []).forEach((h) => h({ target: t }));
}
global.host = host; global.plans = plans; global.fire = fire;
"""


def _run(body: str):
    script = HARNESS + body
    res = subprocess.run(
        [_node(), "-e", script, str(PANEL / "app.js")],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


PLAN_LIST = (
    "[{plan_id:'p1',state:'pending',actions:[{tool:'a'}]},"
    "{plan_id:'p2',state:'pending',actions:[{tool:'b'}]},"
    "{plan_id:'p3',state:'executed',actions:[{tool:'c'}]},"
    "{plan_id:'p4',state:'rolled_back',actions:[{tool:'d'}]},"
    "{plan_id:'p5',state:'rejected',actions:[{tool:'e'}]},"
    "{plan_id:'p6',state:'approved',actions:[{tool:'f'}]}]"
)


def test_finished_plans_have_no_decision_buttons():
    got = _run(
        f"""
host(); plans({PLAN_LIST});
const h = els['plan-list'].innerHTML;
const out = {{}};
for (const id of ['p1','p2','p3','p4','p5','p6']) {{
  out[id] = {{ approve: h.includes('data-plan="' + id + '"') && new RegExp('data-plan="' + id + '"[^>]*data-decision="approve"').test(h),
              reject: new RegExp('data-plan="' + id + '"[^>]*data-decision="reject"').test(h) }};
}}
console.log(JSON.stringify(out));
"""
    )
    assert got["p1"]["approve"] and got["p1"]["reject"]
    assert got["p2"]["approve"] and got["p2"]["reject"]
    for finished in ("p3", "p4", "p5", "p6"):
        assert not got[finished]["approve"], f"{finished} still shows Approve"
        assert not got[finished]["reject"], f"{finished} still shows Reject"


def test_review_block_only_for_pending_plans():
    got = _run(
        f"""
host(); plans({PLAN_LIST});
const h = els['plan-list'].innerHTML;
const cards = h.split('class="item-head"').slice(1);
console.log(JSON.stringify(cards.map((c) => ({{ review: c.includes('class="plan-review"'),
  badge: c.includes('class="badge ') }}))));
"""
    )
    assert [c["review"] for c in got] == [True, True, False, False, False, False]
    assert all(c["badge"] for c in got)


def test_approve_selected_sends_one_plan_approve_per_checked_plan():
    got = _run(
        f"""
host(); plans({PLAN_LIST});
const h = els['plan-list'].innerHTML;
const checkboxes = (h.match(/data-select-plan="[^"]+"/g) || []);
sent.length = 0;
fire('change', {{ selectPlan: 'p2', checked: 'true' }});
fire('click', {{ action: 'approve-selected' }});
console.log(JSON.stringify({{ checkboxes, sent }}));
"""
    )
    assert got["checkboxes"] == ['data-select-plan="p1"', 'data-select-plan="p2"']
    assert got["sent"] == [{"type": "plan.approve", "planId": "p2", "planHash": ""}]


def test_approve_selected_with_nothing_selected_sends_nothing():
    got = _run(
        f"""
host(); plans({PLAN_LIST});
sent.length = 0;
fire('click', {{ action: 'approve-selected' }});
console.log(JSON.stringify(sent));
"""
    )
    assert got == []


def test_approve_selected_ignores_plans_that_finished_since_selection():
    got = _run(
        """
host();
plans([{plan_id:'p1',state:'pending',actions:[{tool:'a'}]}]);
fire('change', { selectPlan: 'p1', checked: 'true' });
plans([{plan_id:'p1',state:'executed',actions:[{tool:'a'}]}]);
sent.length = 0;
fire('click', { action: 'approve-selected' });
console.log(JSON.stringify(sent));
"""
    )
    assert got == []


def test_unhandled_host_message_is_not_sent():
    # The add-in (BridgePanel.xaml.cs) has no `plans.approveSelected` case, so
    # sending it was a silent no-op: the bug this guards against.
    assert "plans.approveSelected" not in JS


# ------------------------------------------------------------ focus / aria


def test_visible_focus_ring_survives_forced_colors():
    assert re.search(r":focus-visible\s*\{[^}]*outline:\s*2px solid", CSS, re.S)
    assert "outline: none" not in CSS


def test_form_controls_have_accessible_names():
    for ident in (
        "auto-minutes",
        "approval-mode",
        "severity-filter",
    ):
        tag = re.search(r'<(?:input|select)\b[^>]*\bid="%s"[^>]*>' % ident, HTML)
        assert tag, ident
        wrapped = re.search(
            r"<label[^>]*>[^<]*<(?:input|select)\b[^>]*\bid=\"%s\"" % ident, HTML
        )
        assert "aria-label" in tag.group(0) or wrapped, (
            f"{ident} has no accessible name"
        )


def test_chat_controls_are_named_in_the_chat_renderer():
    """The chat form is built by panel/chat.js, so its names are checked there."""
    chat_js = (PANEL / "chat.js").read_text(encoding="utf-8")
    assert 'id="chat-root"' in HTML
    assert 'feed.id = "chat-feed"' in chat_js
    assert 'feed.setAttribute("role", "log")' in chat_js
    assert 'input.id = "chat-input"' in chat_js
    assert 'input.setAttribute("aria-label", "Message to the agent")' in chat_js
    assert 'provider.id = "chat-provider"' in chat_js
    assert 'provider.setAttribute("aria-label", "Agent")' in chat_js
    assert 'reset.id = "chat-reset"' in chat_js
    assert 'reset.setAttribute("aria-label", "Start a new conversation")' in chat_js
    assert 'send.setAttribute("aria-label", "Send message")' in chat_js


def test_icon_buttons_and_landmarks_are_named():
    assert re.search(r"<main\b[^>]*aria-label=", HTML) or "<main" in HTML
    assert re.search(r'<nav\b|<aside class="rail" aria-label="Primary"', HTML)
    assert re.search(r'id="plan-list"[^>]*aria-label=', HTML)
