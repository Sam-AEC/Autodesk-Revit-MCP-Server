/* AEC Model Bridge - chat UI for the side panel (vanilla JS, classic script, offline).
 *
 * Stage 1: NON-STREAMING. The host sends a whole `chat.response` / `chat.error`.
 *
 * SAFETY MODEL (all model output is untrusted):
 *  - Markdown is parsed by streaming-markdown (vendor/smd.min.js), which only builds DOM
 *    with createElement/createTextNode. Raw HTML in model text is never parsed as HTML: it
 *    arrives as plain text.
 *  - The renderer is wrapped (createMarkdownStream) to: drop images (no network fetch or
 *    tracking pixel), allow-list link schemes (http, https, mailto), never let the model set
 *    a free-form class or numeric attribute, allow-list the code-fence language, cap nesting
 *    depth, and show control / bidi / format characters as visible \uXXXX escapes (same
 *    rule as visibleText() in app.js).
 *  - Syntax highlighting output is rebuilt node by node from an inert parse, keeping only
 *    text and span.hljs-*.
 *  - Nothing in this file assigns to innerHTML / outerHTML / insertAdjacentHTML or calls
 *    document.write. A static test (tests/test_panel_chat_static.py) enforces that.
 *  - The panel makes no network requests. Links are handed to the host as `link.open`.
 */
(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  // Messages above this size are cut for display (the copy button still copies the full text).
  const MAX_MESSAGE_CHARS = 200000;
  const MAX_INPUT_CHARS = 8000;

  /* ---------- helpers ---------- */

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function icon(id, cls) {
    const s = document.createElementNS(SVG_NS, "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("aria-hidden", "true");
    s.setAttribute("focusable", "false");
    s.setAttribute("class", "i " + (cls || ""));
    const u = document.createElementNS(SVG_NS, "use");
    u.setAttribute("href", "#" + id);
    s.appendChild(u);
    return s;
  }

  // Control (Cc), format (Cf, incl. bidi + zero width), line/para separators, surrogates,
  // private use, unassigned -> visible escapes. keepNl keeps \n and \t.
  const UNSAFE_CH = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}\p{Cs}\p{Co}\p{Cn}]/gu;
  const UNSAFE_TEST = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}\p{Cs}\p{Co}\p{Cn}\s]/u;
  function visibleText(value, keepNl) {
    return String(value).replace(UNSAFE_CH, (ch) => {
      if (keepNl && (ch === "\n" || ch === "\t")) return ch;
      const code = ch.codePointAt(0);
      const hex = code.toString(16).padStart(code <= 0xff ? 2 : code <= 0xffff ? 4 : 8, "0");
      return (code <= 0xff ? "\\x" : code <= 0xffff ? "\\u" : "\\U") + hex;
    });
  }

  function stringify(value) {
    try {
      const t = JSON.stringify(value === undefined ? null : value, null, 2);
      return visibleText(t === undefined ? String(value) : t, true);
    } catch (e) {
      return "(not displayable)";
    }
  }

  function inline(value, max) {
    let s;
    try {
      s = typeof value === "string" ? value : JSON.stringify(value);
    } catch (e) {
      s = "(not displayable)";
    }
    if (s === undefined) s = String(value);
    if (max && s.length > max) s = s.slice(0, max - 1) + "…";
    return visibleText(s);
  }

  const SAFE_LINK_PROTOCOLS = new Set(["https:", "http:", "mailto:"]);
  // Returns a normalised URL string or null. javascript:, data:, file:, vbscript:, blob:,
  // relative and credential-bearing URLs are all rejected.
  function safeUrl(raw) {
    const s = String(raw).trim();
    if (!s || s.length > 2048 || UNSAFE_TEST.test(s)) return null;
    let u;
    try { u = new URL(s); } catch (e) { return null; }
    if (!SAFE_LINK_PROTOCOLS.has(u.protocol)) return null;
    if (u.username || u.password) return null;
    return u.href;
  }

  const prefersReducedMotion = () =>
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- clipboard ---------- */

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(() => legacyCopy(text));
    }
    return legacyCopy(text);
  }
  function legacyCopy(text) {
    return new Promise((resolve, reject) => {
      const ta = el("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.className = "copy-scratch"; // positioned off-screen by chat.css (no inline style: CSP)
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { /* ignore */ }
      ta.remove();
      ok ? resolve() : reject(new Error("copy failed"));
    });
  }

  /* ---------- safe syntax highlighting ---------- */

  const MAX_HIGHLIGHT = 20000;
  const LANG_OK = /^[a-z0-9+#_-]{1,20}$/i;

  function highlightInto(codeEl, text, lang) {
    if (!window.hljs || !lang || !LANG_OK.test(lang) || !hljs.getLanguage(lang) || text.length > MAX_HIGHLIGHT) {
      return;
    }
    let html;
    try { html = hljs.highlight(text, { language: lang, ignoreIllegals: true }).value; } catch (e) { return; }
    // Inert parse (DOMParser documents run no scripts and load no resources), then copy ONLY
    // text nodes and span.hljs-* into live DOM. highlight.js escapes the code text itself.
    const doc = new DOMParser().parseFromString("<body>" + html, "text/html");
    const out = document.createDocumentFragment();
    (function walk(src, dst) {
      for (const n of src.childNodes) {
        if (n.nodeType === 3) {
          dst.appendChild(document.createTextNode(n.nodeValue));
        } else if (n.nodeType === 1 && n.tagName === "SPAN") {
          const cls = (n.getAttribute("class") || "")
            .split(/\s+/).filter((c) => /^hljs-[a-z_-]{1,30}$/.test(c)).join(" ");
          const s = el("span", cls);
          walk(n, s);
          dst.appendChild(s);
        }
      }
    })(doc.body, out);
    codeEl.replaceChildren(out);
  }

  /* ---------- hardened streaming-markdown renderer ---------- */

  function createMarkdownStream(container) {
    const base = smd.default_renderer(container);
    const data = base.data;
    const cur = () => data.nodes[data.index];
    const codeInfo = new WeakMap(); // code element -> {lang, label}

    function pushNode(parent, node) { data.nodes[++data.index] = parent.appendChild(node); }

    // DoS guard: ">>>>...x" x2000 nests 2000 blockquotes and crashed the renderer process in
    // Chromium. Beyond MAX_DEPTH new nodes are attached flat at that depth.
    const MAX_DEPTH = 12;
    const renderer = {
      data,
      add_token(d, type) {
        const idx = data.index;
        let saved = null;
        if (idx >= MAX_DEPTH) { saved = data.nodes[idx]; data.nodes[idx] = data.nodes[MAX_DEPTH - 1]; }
        try { addToken(d, type); } finally { if (saved) data.nodes[idx] = saved; }
      },
      end_token() {
        const node = cur();
        const info = codeInfo.get(node);
        if (info && info.lang) highlightInto(node, node.textContent, info.lang);
        if (node.tagName === "A") finishLink(node);
        data.index -= 1;
      },
      add_text(d, text) {
        const t = String(text).replace(/\r\n?/g, "\n");
        cur().appendChild(document.createTextNode(visibleText(t, true)));
      },
      set_attr: setAttr,
    };

    function addToken(d, type) {
      const parent = cur();
      switch (type) {
        case smd.IMAGE: {
          // Never create <img>: no remote fetch, no tracking pixel.
          const s = el("span", "md-image");
          s.title = "Image blocked";
          pushNode(parent, s);
          return;
        }
        case smd.CODE_BLOCK:
        case smd.CODE_FENCE: {
          const wrap = el("div", "codeblock");
          const head = el("div", "codeblock-head");
          const label = el("span", "codeblock-lang", "code");
          const btn = el("button", "copy-btn");
          btn.type = "button";
          btn.setAttribute("aria-label", "Copy code");
          btn.append(icon("i-copy"), el("span", "copy-label", "Copy"));
          head.append(label, btn);
          const pre = el("pre");
          pre.tabIndex = 0; // keyboard-scrollable region
          pre.setAttribute("role", "region");
          pre.setAttribute("aria-label", "Code");
          const code = el("code");
          pre.appendChild(code);
          wrap.append(head, pre);
          parent.appendChild(wrap);
          codeInfo.set(code, { lang: "", label });
          data.nodes[++data.index] = pre.appendChild(code);
          return;
        }
        case smd.TABLE: {
          const wrap = el("div", "table-wrap");
          wrap.tabIndex = 0;
          wrap.setAttribute("role", "region");
          wrap.setAttribute("aria-label", "Table");
          parent.appendChild(wrap);
          data.nodes[data.index] = parent; // keep stack consistent for the default impl
          const t = el("table");
          data.nodes[++data.index] = wrap.appendChild(t);
          return;
        }
        case smd.EQUATION_BLOCK:
        case smd.EQUATION_INLINE:
          pushNode(parent, el("span", "md-math"));
          return;
      }
      smd.default_add_token(d, type);
    }

    function setAttr(d, type, value) {
      const node = cur();
      switch (type) {
        case smd.HREF: {
          const url = safeUrl(value);
          if (node.tagName === "A") {
            if (url) { node.dataset.href = url; node.title = url; } else { node.dataset.blocked = "1"; node.title = "Link blocked"; }
          }
          return;
        }
        case smd.SRC: return; // images are never loaded
        case smd.LANG: {
          const lang = String(value).replace(/^language-/, "").trim().toLowerCase();
          const info = codeInfo.get(node);
          if (info && LANG_OK.test(lang)) {
            info.lang = lang;
            info.label.textContent = lang;
          }
          return;
        }
        case smd.START: {
          if (/^\d{1,6}$/.test(value)) node.setAttribute("start", value);
          return;
        }
        case smd.CHECKED: node.setAttribute("checked", ""); return;
      }
    }

    function finishLink(a) {
      // Links are inert; clicks are routed through the host (link.open) so the panel itself
      // never navigates. The destination is shown to the user (title + link note on click).
      if (a.dataset.href) {
        a.setAttribute("href", a.dataset.href); // keyboard focus + status bar; click is intercepted
        a.setAttribute("rel", "noopener noreferrer nofollow");
      } else {
        a.removeAttribute("href");
        a.classList.add("link-blocked");
      }
    }

    const parser = smd.parser(renderer);
    let carry = "";
    return {
      write(chunk) {
        let s = carry + String(chunk);
        carry = "";
        // do not split a surrogate pair across chunks
        const last = s.charCodeAt(s.length - 1);
        if (last >= 0xd800 && last <= 0xdbff) { carry = s.slice(-1); s = s.slice(0, -1); }
        smd.parser_write(parser, s);
      },
      end() {
        if (carry) { smd.parser_write(parser, carry); carry = ""; }
        smd.parser_end(parser);
      },
    };
  }

  /* ---------- proposal facts (computed from the real actions) ---------- */

  // Argument names that identify the elements an action touches.
  const ELEMENT_KEYS = /^(element_?ids?|element_?uids?|elements|ids|uids|unique_?ids?)$/i;

  function summarizeActions(actions) {
    const list = Array.isArray(actions) ? actions : [];
    const toolCounts = new Map();
    const elements = new Set();
    let actionsWithScope = 0;
    let beforeCaptured = 0;
    list.forEach((a) => {
      const tool = visibleText(a && a.tool != null ? a.tool : "(unnamed tool)");
      toolCounts.set(tool, (toolCounts.get(tool) || 0) + 1);
      const args = a && a.arguments && typeof a.arguments === "object" ? a.arguments : {};
      let named = false;
      Object.keys(args).forEach((k) => {
        if (!ELEMENT_KEYS.test(k)) return;
        const v = args[k];
        const vals = Array.isArray(v) ? v : [v];
        vals.forEach((x) => {
          if (typeof x === "string" || typeof x === "number") { elements.add(String(x)); named = true; }
        });
      });
      if (named) actionsWithScope++;
      const before = a && a.before;
      if (before && typeof before === "object" && Object.keys(before).length > 0) beforeCaptured++;
    });
    return {
      count: list.length,
      tools: Array.from(toolCounts, ([tool, n]) => ({ tool, n })),
      elementCount: elements.size,
      scopeKnown: list.length > 0 && actionsWithScope === list.length,
      scopePartial: actionsWithScope > 0 && actionsWithScope < list.length,
      beforeCaptured,
    };
  }

  function scopeText(s) {
    if (s.elementCount === 0) return "Not stated in the actions";
    const n = s.elementCount + (s.elementCount === 1 ? " element" : " elements");
    return s.scopeKnown ? n : "At least " + n + " (some actions do not name their elements)";
  }

  function beforeText(s) {
    if (s.count === 0) return "Nothing to compare";
    if (s.beforeCaptured === 0) return "Not captured for these changes";
    if (s.beforeCaptured === s.count) return "Captured for all " + s.count;
    return "Captured for " + s.beforeCaptured + " of " + s.count;
  }

  const UNDO_NOTE = "Undo: Ctrl+Z in Revit, once per step. One-step undo for the whole set is not built yet.";
  const MODE_INFO = {
    look_only: {
      label: "Look only",
      text: "Look only: the assistant reads the model and cannot change it. Change in settings.",
    },
    ask_first: {
      label: "Ask me first",
      text: "",
    },
    auto: {
      label: "Auto",
      text: "Auto: approvals are skipped. Not recommended. Change in settings.",
    },
    dev: {
      label: "Dev",
      text: "Dev is on for this workspace: assistants can make changes without approval until you switch it off in Settings. Actions are logged.",
    },
  };

  /* ---------- mount ---------- */

  function mount(root, opts) {
    opts = opts || {};
    const postToHost = opts.postToHost || function () {};
    const onReview = opts.onReview || function () {};
    const state = {
      approvalMode: null, // null (unknown) | look_only | ask_first | auto | dev
      disabled: false,
      pending: [],        // assistant shells waiting for a whole response, oldest first
      unseen: 0,
      nextId: 1,
    };
    const proposals = new Map(); // planId -> {card, ...}

    root.classList.add("chat");
    root.replaceChildren();

    const banner = el("div", "mode-banner");
    banner.setAttribute("role", "status");
    banner.hidden = true;

    const feedWrap = el("div", "feed-wrap");
    const feed = el("div", "feed");
    feed.id = "chat-feed";
    feed.setAttribute("role", "log");
    feed.setAttribute("aria-label", "Conversation");
    feed.setAttribute("aria-live", "polite");
    feed.tabIndex = 0;
    const empty = buildEmpty();
    feedWrap.append(feed);

    const pill = el("button", "jump-pill");
    pill.type = "button";
    pill.hidden = true;
    pill.append(icon("i-down"), el("span", "jump-label", "Jump to latest"));
    feedWrap.append(pill);

    const sr = el("div", "sr-only");
    sr.id = "sr-status";
    sr.setAttribute("role", "status");
    sr.setAttribute("aria-live", "polite");

    const linkNote = buildLinkNote();
    const composer = buildComposer();
    root.append(banner, feedWrap, linkNote.box, composer.form, sr);
    feed.append(empty);

    /* --- scrolling --- */
    const NEAR = 48;
    const atBottom = () => feed.scrollHeight - feed.scrollTop - feed.clientHeight <= NEAR;
    let stick = true;
    function scrollToEnd(force) {
      if (force || stick) {
        feed.scrollTop = feed.scrollHeight;
      } else {
        state.unseen++;
      }
      updatePill();
    }
    function updatePill() {
      pill.hidden = atBottom();
      pill.querySelector(".jump-label").textContent = state.unseen > 0 ? "New content below" : "Jump to latest";
    }
    feed.addEventListener("scroll", () => {
      stick = atBottom();
      if (stick) state.unseen = 0;
      updatePill();
    }, { passive: true });
    pill.addEventListener("click", () => {
      stick = true; state.unseen = 0;
      feed.scrollTo({ top: feed.scrollHeight, behavior: prefersReducedMotion() ? "auto" : "smooth" });
      composer.input.focus({ preventScroll: true });
    });

    /* --- link + copy delegation (the panel must never navigate away) --- */
    root.addEventListener("click", (e) => {
      const a = e.target.closest("a");
      if (a && root.contains(a)) {
        e.preventDefault();
        if (a.dataset.href) openLink(a.dataset.href);
        return;
      }
      const cp = e.target.closest(".copy-btn");
      if (cp) {
        const block = cp.closest(".codeblock");
        flashCopied(cp, copyText(block.querySelector("code").textContent), "Copied code");
      }
    });
    // Belt and braces: middle-click / drag-drop of links
    root.addEventListener("auxclick", (e) => { if (e.target.closest("a")) e.preventDefault(); });
    root.addEventListener("dragstart", (e) => { if (e.target.closest && e.target.closest("a")) e.preventDefault(); });

    function openLink(url) {
      // The add-in host has no link.open handler yet (UNVERIFIED until it does), so the URL
      // is also shown as selectable, copyable text. The message is harmless if ignored.
      postToHost("link.open", { url });
      linkNote.show(url);
    }

    function buildLinkNote() {
      const box = el("div", "link-note");
      box.setAttribute("role", "status");
      box.hidden = true;
      const label = el("span", "link-note-label", "Link (copy it into your browser if it does not open):");
      const urlEl = el("code", "link-note-url");
      const copy = el("button", "act-btn");
      copy.type = "button";
      copy.setAttribute("aria-label", "Copy link");
      copy.append(icon("i-copy"), el("span", "copy-label", "Copy"));
      const close = el("button", "act-btn");
      close.type = "button";
      close.setAttribute("aria-label", "Dismiss link");
      close.textContent = "Dismiss";
      box.append(label, urlEl, copy, close);
      let current = "";
      copy.addEventListener("click", () => flashCopied(copy, copyText(current), "Copied link"));
      close.addEventListener("click", () => { box.hidden = true; });
      return {
        box,
        show(url) {
          current = url;
          urlEl.textContent = visibleText(url);
          box.hidden = false;
        },
      };
    }

    function flashCopied(btn, promise, announce) {
      const label = btn.querySelector(".copy-label");
      const before = label ? label.textContent : "";
      promise.then(() => {
        btn.classList.add("is-done");
        if (label) label.textContent = "Copied";
        sr.textContent = announce;
      }).catch(() => {
        if (label) label.textContent = "Copy failed";
        sr.textContent = "Copy failed";
      }).finally(() => {
        setTimeout(() => {
          btn.classList.remove("is-done");
          if (label) label.textContent = before;
        }, 1600);
      });
    }

    /* --- empty state --- */
    function buildEmpty() {
      const e = el("section", "chat-empty");
      e.setAttribute("aria-labelledby", "chat-empty-title");
      const mark = el("div", "chat-empty-mark");
      const svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("width", "44"); svg.setAttribute("height", "44");
      svg.setAttribute("aria-hidden", "true");
      const use = document.createElementNS(SVG_NS, "use");
      use.setAttribute("href", "#brand-mark");
      svg.appendChild(use); mark.appendChild(svg);
      const h = el("h2", "chat-empty-title", "Ask about the active model");
      h.id = "chat-empty-title";
      const p = el("p", "chat-empty-sub", "Try one of these, or type your own question:");
      const list = el("ul", "prompt-list");
      [
        ["Model health", "Summarise the model health: warnings, duplicate instances and unplaced rooms."],
        ["Missing data", "Which doors on Level 2 have no Fire Rating value? Group them by door type."],
        ["Coordination", "List the clashes in the last Navisworks issue set that are still unassigned."],
      ].forEach(([title, text]) => {
        const li = el("li");
        const b = el("button", "prompt-card");
        b.type = "button";
        b.dataset.prompt = text;
        b.append(el("span", "prompt-title", title), el("span", "prompt-text", text));
        li.appendChild(b);
        list.appendChild(li);
      });
      e.append(mark, h, p, list);
      e.addEventListener("click", (ev) => {
        const b = ev.target.closest(".prompt-card");
        if (b) { composer.input.value = b.dataset.prompt; composer.grow(); composer.input.focus(); composer.sync(); }
      });
      return e;
    }
    function hideEmpty() { if (empty.isConnected) empty.remove(); }

    /* --- composer --- */
    function buildComposer() {
      const form = el("form", "composer");
      form.autocomplete = "off";
      const input = el("textarea", "composer-input");
      input.rows = 1;
      input.name = "message";
      input.id = "chat-input";
      input.placeholder = "Ask about the active model";
      input.setAttribute("aria-label", "Message to the agent");
      input.setAttribute("enterkeyhint", "send");
      input.maxLength = MAX_INPUT_CHARS;

      const row = el("div", "composer-row");

      const provider = el("select", "provider");
      provider.id = "chat-provider";
      provider.setAttribute("aria-label", "Agent");
      [["claude", "Claude"], ["codex", "Codex"]].forEach(([v, t]) => {
        const o = el("option", null, t); o.value = v; provider.appendChild(o);
      });

      const reset = el("button", "new-btn");
      reset.id = "chat-reset";
      reset.type = "button";
      reset.setAttribute("aria-label", "Start a new conversation");
      reset.title = "New conversation";
      reset.append(icon("i-new"), el("span", null, "New"));

      const send = el("button", "send-btn");
      send.type = "submit";
      send.setAttribute("aria-label", "Send message");
      send.title = "Send (Enter)";
      send.disabled = true;
      send.appendChild(icon("i-send"));

      const rowEnd = el("div", "row-end");
      rowEnd.append(reset, send);
      row.append(provider, rowEnd);
      const hint = el("p", "composer-hint");
      hint.id = "composer-hint";
      hint.textContent = "Enter to send, Shift+Enter for a new line";
      input.setAttribute("aria-describedby", "composer-hint");
      form.append(input, row, hint);

      function grow() {
        input.style.height = "auto";
        const max = 8 * 20 + 16;
        input.style.height = Math.min(input.scrollHeight, max) + "px";
        input.style.overflowY = input.scrollHeight > max ? "auto" : "hidden";
      }
      function sync() {
        send.disabled = state.disabled || !input.value.trim();
      }
      input.addEventListener("input", () => { grow(); sync(); });
      input.addEventListener("keydown", (e) => {
        // isComposing / keyCode 229: an IME is confirming a candidate, not sending.
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
          e.preventDefault();
          if (!send.disabled) form.requestSubmit();
        }
      });
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text || state.disabled) return;
        input.value = "";
        grow(); sync();
        api.send(text, provider.value);
      });
      reset.addEventListener("click", () => api.reset());
      return { form, input, grow, sync, provider, send, reset };
    }

    /* --- messages --- */
    function userMessage(text) {
      hideEmpty();
      const m = el("article", "msg user");
      m.setAttribute("aria-label", "You");
      const body = el("div", "bubble");
      body.textContent = visibleText(text, true); // plain text, pre-wrap in CSS
      m.append(body);
      feed.append(m);
      stick = true; state.unseen = 0;
      scrollToEnd(true);
      return m;
    }

    function assistantShell() {
      hideEmpty();
      const m = el("article", "msg assistant");
      m.setAttribute("aria-label", "Assistant");
      const meta = el("div", "meta");
      const svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("width", "16"); svg.setAttribute("height", "16"); svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("class", "mini-mark");
      const use = document.createElementNS(SVG_NS, "use"); use.setAttribute("href", "#brand-mark");
      svg.appendChild(use);
      meta.append(svg, el("span", "who", "Assistant"));
      const body = el("div", "assistant-body");
      m.append(meta, body);
      feed.append(m);
      return { m, body };
    }

    function actionsBar(msgEl, getText) {
      const bar = el("div", "msg-actions");
      const b = el("button", "act-btn");
      b.type = "button";
      b.setAttribute("aria-label", "Copy message");
      b.append(icon("i-copy"), el("span", "copy-label", "Copy"));
      b.addEventListener("click", () => flashCopied(b, copyText(getText()), "Copied message"));
      bar.appendChild(b);
      msgEl.appendChild(bar);
    }

    function beginPending() {
      const shell = assistantShell();
      shell.m.classList.add("pending");
      shell.m.setAttribute("aria-busy", "true");
      shell.body.appendChild(el("p", "pending-text", "Thinking…"));
      state.pending.push(shell);
      scrollToEnd(true);
      return shell;
    }

    // Fill a shell (pending or fresh) with a whole markdown message.
    function fillAssistant(shell, text, isError) {
      shell.m.classList.remove("pending");
      shell.m.removeAttribute("aria-busy");
      shell.body.replaceChildren();
      const full = String(text);
      if (isError) {
        shell.m.classList.add("error");
        shell.body.appendChild(el("p", "error-text", "Error: " + visibleText(full)));
      } else {
        const shown = full.length > MAX_MESSAGE_CHARS ? full.slice(0, MAX_MESSAGE_CHARS) : full;
        const mdEl = el("div", "md");
        shell.body.appendChild(mdEl);
        const md = createMarkdownStream(mdEl);
        md.write(shown);
        md.end();
        if (shown.length < full.length) {
          const kb = (n) => Math.round(n / 1000) + " KB";
          shell.body.appendChild(el("p", "truncated-note",
            "Message shortened for display: showing the first " + kb(shown.length) + " of " + kb(full.length) +
            ". Copy gives the full text."));
        }
      }
      actionsBar(shell.m, () => full);
      sr.textContent = isError ? "Error from the assistant" : "Assistant replied";
      scrollToEnd(false);
    }

    function takeShell() {
      return state.pending.shift() || assistantShell();
    }

    /* --- proposed changes (chat cards; approval happens only in the Plans view) --- */
    function buildProposalCard(plan) {
      const sum = summarizeActions(plan.actions);
      const c = el("section", "proposal");
      c.dataset.planId = String(plan.id);
      c.setAttribute("aria-label", "Proposed changes");
      const head = el("div", "proposal-head");
      const title = el("h3", "proposal-title", sum.count + (sum.count === 1 ? " proposed change" : " proposed changes"));
      const badge = el("span", "badge pending", "Pending");
      head.append(icon("i-shield"), title, badge);

      const facts = el("dl", "facts");
      const fact = (k, v) => {
        facts.append(el("dt", null, k), el("dd", null, v));
      };
      fact("Tools", sum.tools.map((t) => t.tool + (t.n > 1 ? " ×" + t.n : "")).join(", ") || "None");
      fact("Scope", scopeText(sum));
      fact("Before values", beforeText(sum));

      const list = el("ol", "proposal-actions");
      const shownActions = (plan.actions || []).slice(0, 3);
      shownActions.forEach((a) => {
        const li = el("li");
        li.append(el("code", "tool-name", visibleText(a && a.tool != null ? a.tool : "(unnamed tool)")));
        const args = a && a.arguments !== undefined ? a.arguments : {};
        li.append(el("span", "action-args", inline(args, 140)));
        list.appendChild(li);
      });
      const more = (plan.actions || []).length - shownActions.length;
      const moreEl = more > 0 ? el("p", "proposal-more", "and " + more + " more. Open the review to see every change.") : null;

      const hash = el("p", "proposal-hash",
        "Plan " + visibleText(String(plan.id)) + " · hash " + visibleText(String(plan.hash || "").slice(0, 10)));
      const lock = el("p", "proposal-lock");
      lock.id = "lock-" + String(plan.id).replace(/[^A-Za-z0-9_-]/g, "_");
      const undo = el("p", "proposal-undo", UNDO_NOTE);

      const btns = el("div", "proposal-btns");
      const review = el("button", "primary review-btn");
      review.type = "button";
      review.textContent = "Review " + sum.count + (sum.count === 1 ? " change" : " changes");
      review.addEventListener("click", () => onReview(String(plan.id)));
      btns.appendChild(review);

      c.append(head, facts, list);
      if (moreEl) c.appendChild(moreEl);
      c.append(hash, lock, undo, btns);
      return { card: c, badge, lock, review, btns, planId: String(plan.id), settled: false };
    }

    function refreshProposalLock(rec) {
      if (rec.settled) { rec.lock.hidden = true; return; }
      const mode = state.approvalMode;
      let text = "";
      if (mode === "look_only") {
        text = "Look only: these changes cannot be approved. Change the mode in settings to approve changes.";
      } else if (mode === "auto") {
        text = "Auto mode: approvals are skipped by the hub. Not recommended.";
      } else if (mode === "dev") {
        text = "Dev is on: approvals are skipped until you switch it off in Settings.";
      }
      rec.lock.textContent = text;
      rec.lock.hidden = !text;
      rec.card.classList.toggle("is-locked", mode === "look_only");
      rec.review.setAttribute("aria-describedby", text ? rec.lock.id : "");
      if (!text) rec.review.removeAttribute("aria-describedby");
    }

    function settleProposal(rec, label, kind) {
      rec.settled = true;
      rec.badge.className = "badge " + kind;
      rec.badge.textContent = label;
      rec.btns.remove();
      refreshProposalLock(rec);
    }

    // plans: [{id, hash, status, actions:[{tool, arguments, before}]}] - the Plans view data.
    function setProposals(plans) {
      const seen = new Set();
      (plans || []).forEach((p) => {
        const id = String(p.id);
        seen.add(id);
        let rec = proposals.get(id);
        if (!rec) {
          if (p.status !== "pending") return;
          rec = buildProposalCard(p);
          proposals.set(id, rec);
          hideEmpty();
          feed.append(rec.card);
          refreshProposalLock(rec);
          sr.textContent = "Proposed changes are waiting for review";
          scrollToEnd(false);
          // A card taller than the feed would otherwise show only its bottom: start at its top.
          if (stick && rec.card.offsetHeight > feed.clientHeight - 24) {
            feed.scrollTop = Math.max(0, rec.card.offsetTop - 12);
            updatePill();
          }
        } else if (!rec.settled && p.status !== "pending") {
          const label = String(p.status).replace(/_/g, " ");
          settleProposal(rec, visibleText(label), p.status === "rejected" ? "error" : p.status === "rolled_back" ? "idle" : "success");
        }
      });
      proposals.forEach((rec, id) => {
        if (!seen.has(id) && !rec.settled) settleProposal(rec, "No longer pending", "idle");
      });
    }

    function setApprovalMode(mode) {
      state.approvalMode = Object.prototype.hasOwnProperty.call(MODE_INFO, mode) ? mode : null;
      root.dataset.approvalMode = state.approvalMode || "unknown";
      const info = state.approvalMode ? MODE_INFO[state.approvalMode] : null;
      banner.hidden = !(info && info.text);
      banner.textContent = info ? info.text : "";
      banner.classList.toggle("is-warning", state.approvalMode === "auto" || state.approvalMode === "dev");
      proposals.forEach(refreshProposalLock);
    }

    function setDisabled(disabled, why) {
      state.disabled = !!disabled;
      composer.input.disabled = state.disabled;
      composer.provider.disabled = false;
      composer.input.placeholder = state.disabled && why ? why : "Ask about the active model";
      composer.sync();
    }

    function focusProposal(planId) {
      const rec = proposals.get(String(planId));
      if (!rec) return false;
      rec.card.scrollIntoView({ block: "nearest" });
      return true;
    }

    /* --- public API --- */
    const api = {
      el: root, state, composer,
      send(text, provider) {
        userMessage(text);
        beginPending();
        postToHost("chat.message", { message: text, provider: provider || "claude" });
      },
      reset() {
        postToHost("chat.reset");
        state.pending.length = 0;
        proposals.clear();
        feed.replaceChildren(empty);
        state.unseen = 0; stick = true; updatePill();
        linkNote.box.hidden = true;
        composer.input.focus();
      },
      userMessage,
      setApprovalMode,
      setDisabled,
      setProposals,
      focusProposal,
      addAssistantMessage(text) { fillAssistant(takeShell(), String(text), false); },
      addError(text) { fillAssistant(takeShell(), String(text), true); },
      /* Host -> panel messages the chat understands. Returns true when handled. */
      onHostMessage(data) {
        if (!data || typeof data.type !== "string") return false;
        switch (data.type) {
          case "chat.response":
            api.addAssistantMessage(data.message == null || data.message === "" ? "(empty response)" : data.message);
            return true;
          case "chat.error":
            api.addError(data.message || "Unknown error");
            return true;
        }
        return false;
      },
    };
    return api;
  }

  window.AMBChat = { mount, createMarkdownStream, visibleText, safeUrl, summarizeActions, MAX_MESSAGE_CHARS };
})();
