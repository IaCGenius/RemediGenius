/* RemediGenius Community Edition — Knowledge tab for the Hermes dashboard.
 * One Open Knowledge Format (OKF) bundle per installation. Reviewed organization concepts change the desk's
 * priorities; drafts from the agent or from document import wait here for a person. No build step: plain React
 * elements from the dashboard SDK; every request goes to this plugin's backend (/api/plugins/rg-knowledge). */
(function () {
  "use strict";
  var SDK = window.__HERMES_PLUGIN_SDK__;
  var React = SDK.React;
  var h = React.createElement;
  var useState = SDK.hooks.useState, useEffect = SDK.hooks.useEffect, useMemo = SDK.hooks.useMemo,
      useRef = SDK.hooks.useRef, useCallback = SDK.hooks.useCallback;
  var API = "/api/plugins/rg-knowledge";
  var TABS = ["Overview", "Browse", "Review", "Add", "Import", "Graph"];
  var TYPE_COLORS = {
    "Application": "#2f7fd8", "Account": "#7c5cd6", "Team": "#1f9d74", "Risk Exception": "#d0453a",
    "Security Goal": "#d98a1c", "Policy": "#3d8c99", "Runbook": "#5f8f2f", "Architecture": "#8a6d3b",
    "Reference": "#7d8590", "Note": "#9a6fb0", "Playbook": "#c2577f", "Source Guide": "#4f6fb0", "Guide": "#3f9fa8"
  };

  // ---------------------------------------------------------------- helpers
  function get(path) { return SDK.fetchJSON(API + path); }
  function post(path, body) {
    return SDK.fetchJSON(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  }
  function errText(e) {
    var m = (e && (e.detail || e.message)) || String(e);
    try { var j = JSON.parse(m.slice(m.indexOf("{"))); if (j.detail) return j.detail; } catch (x) { /* plain text */ }
    return m.replace(/^Error:\s*/, "");
  }
  function cls() { return Array.prototype.filter.call(arguments, Boolean).join(" "); }
  function store(key, value) {
    try { if (value === undefined) return window.localStorage.getItem("rgk." + key); window.localStorage.setItem("rgk." + key, value); }
    catch (e) { return null; }
  }
  function applied(r) {
    var x = r && r.rescored;
    if (!x || x.error) return x && x.error ? " The board updates at the next scan." : "";
    return " Board updated now: " + x.changed_priority + " of " + x.findings + " findings changed priority.";
  }
  function typeColor(t) { return TYPE_COLORS[t] || "#8b949e"; }
  function trustLabel(t) { return t === "human-reviewed" ? "Reviewed" : t === "machine-confirmed" ? "Machine-confirmed" : "Unreviewed"; }

  function Badge(props) {
    return h("span", { className: cls("rgk-badge", props.tone && "rgk-" + props.tone), title: props.title, style: props.style }, props.children);
  }
  function TypeBadge(props) {
    return h("span", { className: "rgk-badge rgk-type", style: { borderColor: typeColor(props.type), color: typeColor(props.type) } }, props.type || "?");
  }
  function TrustBadges(props) {
    var c = props.c || {};
    return h(React.Fragment, null,
      h(Badge, { tone: c.trust === "human-reviewed" ? "ok" : c.trust === "machine-confirmed" ? "info" : "muted",
                 title: "OKF trust tier, from the `verified` field" }, trustLabel(c.trust)),
      c.status && c.status !== "stable" ? h(Badge, { tone: c.status === "draft" ? "warn" : "muted" }, c.status) : null,
      c.stale ? h(Badge, { tone: "warn", title: "stale_after has passed" }, "stale") : null,
      c.shipped || (c.path || "").indexOf("remedigenius/") === 0 ? h(Badge, { tone: "muted", title: "Shipped with RemediGenius-CE; refreshed on every start" }, "shipped") : null);
  }
  function Button(props) {
    return h("button", { type: "button", className: cls("rgk-btn", props.kind && "rgk-btn-" + props.kind), onClick: props.onClick,
                         disabled: props.disabled, title: props.title }, props.children);
  }
  function Notice(props) {
    if (!props.text) return null;
    return h("div", { className: cls("rgk-notice", "rgk-notice-" + (props.tone || "info")), role: props.tone === "error" ? "alert" : "status" }, props.text);
  }
  function Empty(props) { return h("div", { className: "rgk-empty" }, props.children); }

  // ---------------------------------------------------------------- safe markdown (escape first, then a small subset)
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function inline(text) {
    var out = esc(text);
    out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|[\s(])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
    out = out.replace(/\[\^([^\]]+)\]/g, '<sup class="rgk-fn">[$1]</sup>');
    out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (_, label, href) {
      var raw = href.replace(/&amp;/g, "&");
      if (/^https?:\/\//i.test(raw)) return '<a href="' + esc(raw) + '" target="_blank" rel="noopener noreferrer">' + label + "</a>";
      if (/^[a-z][a-z0-9+.-]*:/i.test(raw)) return label;
      return '<a href="#" data-rgk-link="' + esc(raw) + '">' + label + "</a>";
    });
    return out;
  }
  function markdown(md) {
    var lines = String(md || "").replace(/\r\n/g, "\n").split("\n"), html = [], i = 0;
    while (i < lines.length) {
      var line = lines[i];
      if (/^```/.test(line)) {
        var code = []; i++;
        while (i < lines.length && !/^```/.test(lines[i])) { code.push(lines[i]); i++; }
        html.push("<pre><code>" + esc(code.join("\n")) + "</code></pre>"); i++; continue;
      }
      var head = /^(#{1,4})\s+(.*)$/.exec(line);
      if (head) { var n = Math.min(head[1].length + 2, 6); html.push("<h" + n + ">" + inline(head[2]) + "</h" + n + ">"); i++; continue; }
      if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
        var cells = function (l) { return l.trim().replace(/^\||\|$/g, "").split("|").map(function (c) { return c.trim(); }); };
        var t = "<table><thead><tr>" + cells(line).map(function (c) { return "<th>" + inline(c) + "</th>"; }).join("") + "</tr></thead><tbody>";
        i += 2;
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
          t += "<tr>" + cells(lines[i]).map(function (c) { return "<td>" + inline(c) + "</td>"; }).join("") + "</tr>"; i++;
        }
        html.push('<div class="rgk-table">' + t + "</tbody></table></div>"); continue;
      }
      if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
        var ordered = /^\s*\d+\./.test(line), items = [];
        while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
          var item = lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ""); i++;
          while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*]|\d+\.)\s+/.test(lines[i])) { item += " " + lines[i].trim(); i++; }
          items.push("<li>" + inline(item) + "</li>");
        }
        html.push((ordered ? "<ol>" : "<ul>") + items.join("") + (ordered ? "</ol>" : "</ul>")); continue;
      }
      if (/^>\s?/.test(line)) {
        var quote = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) { quote.push(lines[i].replace(/^>\s?/, "")); i++; }
        html.push("<blockquote>" + inline(quote.join(" ")) + "</blockquote>"); continue;
      }
      if (/^\[\^[^\]]+\]:/.test(line)) { html.push('<p class="rgk-footnote">' + inline(line) + "</p>"); i++; continue; }
      if (!line.trim()) { i++; continue; }
      var para = [line]; i++;
      while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|\s*([-*]|\d+\.)\s|>|\s*\|)/.test(lines[i])) { para.push(lines[i]); i++; }
      html.push("<p>" + inline(para.join(" ")) + "</p>");
    }
    return html.join("\n");
  }
  function resolveLink(from, target) {
    target = target.split("#")[0];
    if (!target) return null;
    var parts = target.charAt(0) === "/" ? [] : (from || "").split("/").slice(0, -1);
    target.replace(/^\//, "").split("/").forEach(function (p) {
      if (!p || p === ".") return;
      if (p === "..") parts.pop(); else parts.push(p);
    });
    return parts.join("/");
  }
  function Markdown(props) {
    var onClick = function (e) {
      var a = e.target.closest ? e.target.closest("a[data-rgk-link]") : null;
      if (!a) return;
      e.preventDefault();
      var path = resolveLink(props.from, a.getAttribute("data-rgk-link"));
      if (path && props.onOpen) props.onOpen(path);
    };
    return h("div", { className: "rgk-md", onClick: onClick, dangerouslySetInnerHTML: { __html: markdown(props.text) } });
  }

  // ---------------------------------------------------------------- overview
  function Overview(props) {
    var o = props.status && props.status.overview;
    var _v = useState(null), check = _v[0], setCheck = _v[1];
    var _l = useState([]), log = _l[0], setLog = _l[1];
    var _k = useState({}), kinds = _k[0], setKinds = _k[1];
    useEffect(function () {
      get("/log").then(setLog).catch(function () {});
      get("/kinds").then(setKinds).catch(function () {});
    }, [props.version]);
    if (!o) return h(Empty, null, "Loading…");
    var applied = o.applied || {};
    var stat = function (label, value, hint, onClick) {
      return h("button", { type: "button", className: "rgk-stat", onClick: onClick, title: hint }, h("div", { className: "rgk-stat-value" }, value), h("div", { className: "rgk-stat-label" }, label));
    };
    var gapAction = function (g) {
      if (/review queue/i.test(g)) return ["Review", null];
      if (/map to an application/i.test(g)) return ["Add", "Application"];
      if (/Account concept/i.test(g)) return ["Add", "Account"];
      if (/Team concepts/i.test(g)) return ["Add", "Team"];
      if (/expired/i.test(g)) return ["Add", "Risk Exception"];
      if (/application/i.test(g)) return ["Add", "Application"];
      return ["Browse", null];
    };
    return h("div", { className: "rgk-stack" },
      h("div", { className: "rgk-stats" },
        stat("organization concepts", o.organization, "Concepts your organization added (the shipped guides are not counted)", function () { props.go("Browse"); }),
        stat("reviewed by a person", o.human_reviewed, "OKF trust tier human-reviewed", function () { props.go("Browse"); }),
        stat("changing priorities", (applied.applications || 0) + (applied.accounts || 0) + (applied.exceptions || 0) + (applied.goals || 0),
             (applied.applications || 0) + " applications · " + (applied.accounts || 0) + " accounts · " + (applied.exceptions || 0) + " risk exceptions · " + (applied.goals || 0) + " goals"),
        stat("drafts to review", o.review_queue, "From the agent and from document import", function () { props.go("Review"); }),
        stat("stale", (o.stale || []).length, "Past their stale_after date: ask the owner to re-review", function () { props.go("Browse"); })),
      h("section", { className: "rgk-card" },
        h("h3", null, "What the desk is missing"),
        (o.gaps || []).length ? h("ul", { className: "rgk-gaps" }, o.gaps.map(function (g, n) {
          var act = gapAction(g);
          return h("li", { key: n }, h("span", null, g), h(Button, { kind: "link", onClick: function () { props.go(act[0], act[1]); } },
            act[0] === "Add" ? "Add " + act[1] : act[0] === "Review" ? "Open review" : "Browse"));
        })) : h("p", { className: "rgk-muted" }, "No gaps found in the last scan. Add knowledge whenever something changes.")),
      h("section", { className: "rgk-card" },
        h("h3", null, "How knowledge changes triage"),
        h("p", { className: "rgk-muted" }, "Only concepts a person reviewed change scores. Every effect is cited with the concept path in the finding's reasons, so the desk's ranking stays explainable."),
        h("div", { className: "rgk-table" }, h("table", null,
          h("thead", null, h("tr", null, h("th", null, "Type"), h("th", null, "Effect"), h("th", null, ""))),
          h("tbody", null, Object.keys(kinds).filter(function (k) { return k !== "Reference"; }).map(function (k) {
            return h("tr", { key: k },
              h("td", null, h(TypeBadge, { type: k })),
              h("td", null, kinds[k].effect, kinds[k].affects_triage ? h(Badge, { tone: "info", style: { marginLeft: 6 } }, "changes priority") : null),
              h("td", null, h(Button, { kind: "link", onClick: function () { props.go("Add", k); } }, "Add")));
          }))))),
      h("section", { className: "rgk-card" },
        h("div", { className: "rgk-row" }, h("h3", null, "Bundle health"),
          h(Button, { onClick: function () { setCheck("…"); get("/validate").then(setCheck).catch(function (e) { setCheck({ error: errText(e) }); }); } }, "Check the bundle")),
        h("p", { className: "rgk-muted" }, "Open Knowledge Format v0.2 · ", h("code", null, o.bundle), " · ", o.concepts, " concepts (", o.shipped, " shipped with RemediGenius-CE)"),
        check === "…" ? h("p", null, "Checking…") : check && check.error ? h(Notice, { tone: "error", text: check.error }) : check ? h("div", null,
          h("p", null, check.errors ? check.errors + " errors, " : "No errors, ", (check.issues.length - check.errors) + " warnings."),
          h("ul", { className: "rgk-issues" }, check.issues.slice(0, 30).map(function (i, n) {
            return h("li", { key: n }, h(Badge, { tone: i.level === "error" ? "bad" : "warn" }, i.level), " ",
              h("a", { href: "#", onClick: function (e) { e.preventDefault(); props.open(i.path); } }, i.path), ": ", i.message);
          }))) : null),
      h("section", { className: "rgk-card" },
        h("h3", null, "Recent changes"),
        log.length ? h("ul", { className: "rgk-log" }, log.slice(0, 12).map(function (e, n) {
          return h("li", { key: n }, h("span", { className: "rgk-muted" }, e.date), " ", h(Markdown, { text: e.text, onOpen: props.open }));
        })) : h("p", { className: "rgk-muted" }, "Nothing yet.")));
  }

  // ---------------------------------------------------------------- browse
  function ConceptView(props) {
    var c = props.concept;
    var _e = useState(false), editing = _e[0], setEditing = _e[1];
    var _t = useState(""), text = _t[0], setText = _t[1];
    var _m = useState(null), msg = _m[0], setMsg = _m[1];
    var _b = useState(false), busy = _b[0], setBusy = _b[1];
    useEffect(function () { setEditing(false); setMsg(null); }, [c && c.path]);
    if (!c) return h(Empty, null, "Choose a concept on the left, or search.");
    var act = function (path, body, done) {
      setBusy(true); setMsg(null);
      post(path, Object.assign({ path: c.path, reviewer: props.reviewer }, body)).then(function (r) {
        setBusy(false); setMsg({ tone: "ok", text: done + applied(r) }); props.changed(r && r.path);
      }).catch(function (e) { setBusy(false); setMsg({ tone: "error", text: errText(e) }); });
    };
    var ext = (c.meta && c.meta.remedigenius) || null;
    var shipped = c.shipped;
    return h("div", { className: "rgk-stack" },
      h("div", { className: "rgk-row rgk-wrap" }, h(TypeBadge, { type: c.type }), h(TrustBadges, { c: c }),
        c.affects_triage ? h(Badge, { tone: "info" }, "changes priority") : null),
      h("h2", { className: "rgk-title" }, c.title),
      c.description ? h("p", { className: "rgk-lead" }, c.description) : null,
      h("p", { className: "rgk-muted rgk-small" }, h("code", null, c.path),
        c.generated && c.generated.by ? " · written by " + c.generated.by + (c.generated.at ? " " + String(c.generated.at).slice(0, 10) : "") : "",
        (c.verified || []).length ? " · reviewed by " + c.verified.map(function (v) { return v.by.replace(/^human:/, "") + " " + String(v.at || "").slice(0, 10); }).join(", ") : ""),
      c.effect ? h(Notice, { tone: "info", text: "Effect: " + c.effect + (c.affects_triage && c.trust !== "human-reviewed" ? " Not applied until a person marks it reviewed." : "") }) : null,
      ext ? h("dl", { className: "rgk-settings" }, Object.keys(ext).map(function (k) {
        var v = ext[k];
        return h(React.Fragment, { key: k }, h("dt", null, k.replace(/_/g, " ")), h("dd", null, typeof v === "object" ? Object.keys(v).map(function (x) { return Array.isArray(v) ? v[x] : x + "=" + v[x]; }).join(", ") : String(v)));
      })) : null,
      (c.meta && c.meta.sources || []).length ? h("div", { className: "rgk-sources" }, h("strong", null, "Sources: "),
        c.meta.sources.map(function (s, n) {
          var r = String(s.resource || "");
          return h("span", { key: n }, n ? " · " : "", /^https?:\/\//.test(r) ? h("a", { href: r, target: "_blank", rel: "noopener noreferrer" }, s.title || r)
            : r.charAt(0) === "/" ? h("a", { href: "#", onClick: function (e) { e.preventDefault(); props.open(r.slice(1)); } }, s.title || r) : (s.title || r));
        })) : null,
      editing ? h("div", { className: "rgk-stack" },
          h("label", { className: "rgk-label" }, "OKF source (frontmatter and markdown). Saving records you as the editor."),
          h("textarea", { className: "rgk-editor", value: text, onChange: function (e) { setText(e.target.value); }, spellCheck: false }),
          h("div", { className: "rgk-row" },
            h(Button, { kind: "primary", disabled: busy, onClick: function () { act("/concept/edit", { content: text, verify: true }, "Saved and marked reviewed."); } }, "Save as reviewed"),
            h(Button, { disabled: busy, onClick: function () { act("/concept/edit", { content: text, verify: false }, "Saved (not reviewed)."); } }, "Save without review"),
            h(Button, { kind: "ghost", onClick: function () { setEditing(false); } }, "Cancel")))
        : h(Markdown, { text: c.body, from: c.path, onOpen: props.open }),
      (c.links || []).length || (c.backlinks || []).length ? h("div", { className: "rgk-links" },
        h("div", null, h("strong", null, "Links to: "), (c.links || []).map(function (l, n) {
          return h("a", { key: n, href: "#", className: "rgk-chip", onClick: function (e) { e.preventDefault(); props.open(l); } }, l);
        })),
        h("div", null, h("strong", null, "Linked from: "), (c.backlinks || []).length ? c.backlinks.map(function (l, n) {
          return h("a", { key: n, href: "#", className: "rgk-chip", onClick: function (e) { e.preventDefault(); props.open(l); } }, l);
        }) : h("span", { className: "rgk-muted" }, "nothing yet"))) : null,
      h(Notice, { tone: msg && msg.tone, text: msg && msg.text }),
      shipped ? h("p", { className: "rgk-muted rgk-small" }, "Shipped with RemediGenius-CE and refreshed on every start. To add to it, create your own Policy, Runbook or Note that links here.")
        : !editing ? h("div", { className: "rgk-row rgk-wrap" },
          c.trust !== "human-reviewed" || c.status === "draft" || c.stale ? h(Button, { kind: "primary", disabled: busy, onClick: function () { act("/concept/verify", {}, "Marked reviewed by " + props.reviewer + "."); } },
            c.stale ? "Re-review (still correct)" : "Mark reviewed") : null,
          h(Button, { disabled: busy, onClick: function () { setText(c.raw || ""); setEditing(true); } }, "Edit"),
          c.status !== "deprecated" ? h(Button, { disabled: busy, onClick: function () {
            var reason = window.prompt("Why is this no longer current? (kept for history and links)");
            if (reason !== null) act("/concept/deprecate", { reason: reason }, "Deprecated.");
          } }, "Deprecate") : null,
          h(Button, { kind: "danger", disabled: busy, onClick: function () {
            if (window.confirm("Move " + c.path + " to the knowledge trash? It stops applying immediately; the file is kept."))
              act("/concept/remove", {}, "Moved to the knowledge trash.");
          } }, "Move to trash")) : null);
  }

  function Browse(props) {
    var _c = useState([]), list = _c[0], setList = _c[1];
    var _q = useState(""), q = _q[0], setQ = _q[1];
    var _h = useState(null), hits = _h[0], setHits = _h[1];
    var _t = useState(""), type = _t[0], setType = _t[1];
    var _s = useState(store("shipped") === "1"), shipped = _s[0], setShipped = _s[1];
    var _x = useState(null), concept = _x[0], setConcept = _x[1];
    var _e = useState(null), err = _e[0], setErr = _e[1];
    useEffect(function () { get("/concepts").then(setList).catch(function (e) { setErr(errText(e)); }); }, [props.version]);
    useEffect(function () {
      if (!props.selected) { setConcept(null); return; }
      get("/concept?path=" + encodeURIComponent(props.selected)).then(function (c) { setConcept(c); setErr(null); })
        .catch(function (e) { setConcept(null); setErr(errText(e)); });
    }, [props.selected, props.version]);
    useEffect(function () {
      if (!q.trim()) { setHits(null); return; }
      var t = setTimeout(function () { get("/search?q=" + encodeURIComponent(q)).then(setHits).catch(function () {}); }, 250);
      return function () { clearTimeout(t); };
    }, [q]);
    var rows = (hits || list).filter(function (c) {
      return (shipped || c.path.indexOf("remedigenius/") !== 0 || hits) && (!type || c.type === type);
    });
    var types = Array.from(new Set(list.map(function (c) { return c.type; }))).sort();
    var groups = {};
    rows.forEach(function (c) { var f = hits ? "Search results" : c.path.split("/").slice(0, -1).join("/") || "(root)"; (groups[f] = groups[f] || []).push(c); });
    return h("div", { className: "rgk-split" },
      h("aside", { className: "rgk-side" },
        h("input", { className: "rgk-input", placeholder: "Search titles, tags and text", value: q, onChange: function (e) { setQ(e.target.value); }, "aria-label": "Search knowledge" }),
        h("div", { className: "rgk-row rgk-wrap" },
          h("select", { className: "rgk-input", value: type, onChange: function (e) { setType(e.target.value); }, "aria-label": "Type" },
            h("option", { value: "" }, "All types"), types.map(function (t) { return h("option", { key: t, value: t }, t); })),
          h("label", { className: "rgk-check" }, h("input", { type: "checkbox", checked: shipped, onChange: function (e) { setShipped(e.target.checked); store("shipped", e.target.checked ? "1" : "0"); } }), " shipped guides")),
        err ? h(Notice, { tone: "error", text: err }) : null,
        rows.length ? Object.keys(groups).sort().map(function (g) {
          return h("div", { key: g, className: "rgk-group" }, h("div", { className: "rgk-group-title" }, g),
            groups[g].map(function (c) {
              return h("button", { key: c.path, type: "button", className: cls("rgk-item", props.selected === c.path && "rgk-active"), onClick: function () { props.open(c.path); } },
                h("span", { className: "rgk-dot", style: { background: typeColor(c.type) } }),
                h("span", { className: "rgk-item-title" }, c.title),
                c.trust === "human-reviewed" ? h("span", { className: "rgk-tick", title: "reviewed" }, "✓") : null,
                c.stale ? h("span", { className: "rgk-warn-dot", title: "stale" }, "!") : null);
            }));
        }) : h(Empty, null, list.length ? "No concept matches." : "No organization knowledge yet. Use Add or Import, or tick 'shipped guides'.")),
      h("main", { className: "rgk-main" }, h(ConceptView, { concept: concept, reviewer: props.reviewer, open: props.open, changed: function (p) { props.changed(p); } })));
  }

  // ---------------------------------------------------------------- review queue
  function Review(props) {
    var _q = useState(null), queue = _q[0], setQueue = _q[1];
    var _s = useState(null), sel = _s[0], setSel = _s[1];
    var _i = useState(null), item = _i[0], setItem = _i[1];
    var _t = useState(""), text = _t[0], setText = _t[1];
    var _p = useState(""), target = _p[0], setTarget = _p[1];
    var _m = useState(null), msg = _m[0], setMsg = _m[1];
    var _b = useState(false), busy = _b[0], setBusy = _b[1];
    var load = function () { get("/review").then(function (r) { setQueue(r.drafts || []); }).catch(function (e) { setMsg({ tone: "error", text: errText(e) }); }); };
    useEffect(load, [props.version]);
    useEffect(function () {
      setItem(null);
      if (!sel) return;
      get("/review/item?file=" + encodeURIComponent(sel)).then(function (r) { setItem(r); setText(r.raw || ""); setTarget(r.target || ""); })
        .catch(function (e) { setMsg({ tone: "error", text: errText(e) }); });
    }, [sel]);
    var decide = function (approve, replace) {
      setBusy(true); setMsg(null);
      var body = { file: sel, reviewer: props.reviewer };
      if (approve) { body.path = target; body.replace = !!replace; if (item && text !== item.raw) body.content = text; }
      post(approve ? "/review/approve" : "/review/reject", body).then(function (r) {
        setBusy(false); setSel(null);
        setMsg({ tone: "ok", text: approve ? "Approved: " + r.path + " is now reviewed knowledge." + applied(r) : "Rejected; the draft is kept in the .rejected folder." });
        load(); props.changed(approve ? r.path : null);
      }).catch(function (e) { setBusy(false); setMsg({ tone: "error", text: errText(e) }); });
    };
    if (!queue) return h(Empty, null, "Loading…");
    return h("div", { className: "rgk-split" },
      h("aside", { className: "rgk-side" },
        h("p", { className: "rgk-muted rgk-small" }, "Drafts from the agent (it writes them when you tell it something) and from document import. Nothing here changes priorities until you approve it."),
        queue.length ? queue.map(function (d) {
          return h("button", { key: d.file, type: "button", className: cls("rgk-item", sel === d.file && "rgk-active"), onClick: function () { setSel(d.file); setMsg(null); } },
            h("span", { className: "rgk-dot", style: { background: typeColor(d.type) } }),
            h("span", { className: "rgk-item-title" }, d.title || d.name, h("span", { className: "rgk-muted rgk-small rgk-block" }, (d.type || "unreadable") + " · " + ((d.generated && d.generated.by) || "unknown author"))),
            d.affects_triage ? h("span", { className: "rgk-tick", title: "changes priorities once approved" }, "⚑") : null);
        }) : h(Empty, null, "The review queue is empty.")),
      h("main", { className: "rgk-main" },
        h(Notice, { tone: msg && msg.tone, text: msg && msg.text }),
        !sel ? h(Empty, null, queue.length ? "Choose a draft to review." : "When the agent learns something from you, or you import a document and draft with AI, the drafts appear here.")
          : !item ? h(Empty, null, "Loading…") : item.error ? h("div", { className: "rgk-stack" },
            h(Notice, { tone: "error", text: "This draft is not valid OKF: " + item.error }),
            h("textarea", { className: "rgk-editor", value: text, onChange: function (e) { setText(e.target.value); }, spellCheck: false }),
            h("div", { className: "rgk-row" },
              h(Button, { kind: "primary", disabled: busy, onClick: function () { decide(true, false); } }, "Approve the corrected text"),
              h(Button, { kind: "danger", disabled: busy, onClick: function () { decide(false); } }, "Reject")))
          : h("div", { className: "rgk-stack" },
            h("div", { className: "rgk-row rgk-wrap" }, h(TypeBadge, { type: item.meta.type }), h(Badge, { tone: "warn" }, "draft"),
              item.affects_triage ? h(Badge, { tone: "info" }, "changes priority once approved") : null),
            h("h2", { className: "rgk-title" }, item.meta.title || "(no title)"),
            item.meta.description ? h("p", { className: "rgk-lead" }, item.meta.description) : null,
            h(Notice, { tone: "info", text: "Effect once approved: " + item.effect }),
            item.meta.type === "Risk Exception" && !((item.meta.remedigenius || {}).resource) ? h(Notice, { tone: "warn",
              text: "This exception names no resource: it accepts the risk for every finding that matches " +
                [(item.meta.remedigenius || {}).control_id, (item.meta.remedigenius || {}).finding_type].filter(Boolean).join(" / ") +
                ((item.meta.remedigenius || {}).account_id ? " in account " + item.meta.remedigenius.account_id : " in every account") +
                ". Add a resource (Edit before approving) unless that is intended." }) : null,
            item.meta.remedigenius ? h("dl", { className: "rgk-settings" }, Object.keys(item.meta.remedigenius).map(function (k) {
              var v = item.meta.remedigenius[k];
              return h(React.Fragment, { key: k }, h("dt", null, k.replace(/_/g, " ")), h("dd", null, typeof v === "object" ? JSON.stringify(v) : String(v)));
            })) : null,
            h(Markdown, { text: item.body, from: target, onOpen: props.open }),
            h("details", null, h("summary", null, "Edit before approving"),
              h("textarea", { className: "rgk-editor", value: text, onChange: function (e) { setText(e.target.value); }, spellCheck: false })),
            h("label", { className: "rgk-label" }, "Save as ", h("input", { className: "rgk-input rgk-mono", value: target, onChange: function (e) { setTarget(e.target.value); }, "aria-label": "Concept path" })),
            item.target_exists && target === item.target ? h(Notice, { tone: "warn", text: target + " already exists. Approve and replace it, or choose another path." }) : null,
            h("div", { className: "rgk-row rgk-wrap" },
              h(Button, { kind: "primary", disabled: busy, onClick: function () { decide(true, item.target_exists && target === item.target); } },
                item.target_exists && target === item.target ? "Approve and replace" : "Approve as " + props.reviewer),
              h(Button, { kind: "danger", disabled: busy, onClick: function () { decide(false); } }, "Reject")),
            h("p", { className: "rgk-muted rgk-small" }, "Approving records you as the reviewer (OKF trust tier human-reviewed)."))));
  }

  // ---------------------------------------------------------------- add (wizard)
  function Field(props) {
    var f = props.f, v = props.value == null ? "" : props.value, set = function (x) { props.onChange(f.name, x); };
    var input;
    if (f.kind === "text") input = h("textarea", { className: "rgk-input rgk-textarea", value: v, onChange: function (e) { set(e.target.value); } });
    else if (f.kind === "criticality") input = h("select", { className: "rgk-input", value: v, onChange: function (e) { set(e.target.value); } },
      h("option", { value: "" }, "Choose…"),
      [["mission_critical", "Mission critical — an outage or breach stops the business"], ["business_critical", "Business critical — significant impact"],
       ["non_critical", "Non-critical — limited impact"], ["test_development", "Test or development — lowers priority"]].map(function (o) { return h("option", { key: o[0], value: o[0] }, o[1]); }));
    else if (f.kind === "choice") input = h("select", { className: "rgk-input", value: v, onChange: function (e) { set(e.target.value); } },
      h("option", { value: "" }, "Choose…"), (f.choices || []).map(function (o) { return h("option", { key: o, value: o }, o); }));
    else if (f.kind === "team") input = h(React.Fragment, null,
      h("input", { className: "rgk-input", list: "rgk-teams", value: v, placeholder: "Team name", onChange: function (e) { set(e.target.value); } }),
      h("datalist", { id: "rgk-teams" }, (props.teams || []).map(function (t) { return h("option", { key: t.path, value: t.title }); })));
    else input = h("input", { className: "rgk-input", type: f.kind === "date" ? "date" : f.kind === "number" ? "number" : "text", value: v,
                              placeholder: f.kind === "tags" ? "app=payments, env=prod" : "", onChange: function (e) { set(e.target.value); } });
    return h("label", { className: "rgk-field" }, h("span", { className: "rgk-label" }, f.label, f.required ? h("span", { className: "rgk-req" }, " *") : null), input,
      f.help ? h("span", { className: "rgk-muted rgk-small" }, f.help) : null);
  }

  function preview(kind, v) {
    var crit = { mission_critical: "mission critical (+15)", business_critical: "business critical (+10)", non_critical: "non-critical (0)", test_development: "test/development (−10)" }[v.criticality] || "?";
    if (kind === "Application") return "Resources tagged " + (v.match_tags || "?") + " will be scored as " + crit + (v.owner ? ", with owner " + v.owner : "") + ".";
    if (kind === "Account") return "Every finding in account " + (v.account_id || "?") + " will be scored as " + crit + " (unless an application is more specific).";
    if (kind === "Risk Exception") return "Findings matching " + [v.control_id && "control " + v.control_id, v.finding_type && "type " + v.finding_type, v.resource && "resource " + v.resource].filter(Boolean).join(" and ") + (v.account_id ? " in account " + v.account_id : "") + " will count as accepted risk until " + (v.expires || "?") + ", then return to the queue.";
    if (kind === "Security Goal") return "Findings on " + ([v.resource_types, v.categories, v.signals].filter(Boolean).join(" / ") || "?") + " get +" + (v.points || 5) + " points, cited with this goal.";
    if (kind === "Team") return "Applications and accounts can name this team as owner; findings will show it.";
    return "Context for the desk's answers and fix proposals; scores do not change.";
  }

  function Add(props) {
    var _k = useState(null), kinds = _k[0], setKinds = _k[1];
    var _s = useState(props.kind || null), kind = _s[0], setKind = _s[1];
    var _v = useState({}), values = _v[0], setValues = _v[1];
    var _t = useState([]), teams = _t[0], setTeams = _t[1];
    var _m = useState(null), msg = _m[0], setMsg = _m[1];
    var _b = useState(false), busy = _b[0], setBusy = _b[1];
    useEffect(function () { get("/kinds").then(setKinds).catch(function (e) { setMsg({ tone: "error", text: errText(e) }); }); }, []);
    useEffect(function () { get("/concepts").then(function (l) { setTeams(l.filter(function (c) { return c.type === "Team"; })); }).catch(function () {}); }, [props.version]);
    useEffect(function () { if (props.kind) { setKind(props.kind); setValues({}); setMsg(null); } }, [props.kind]);
    if (!kinds) return h(Empty, null, "Loading…");
    if (!kind) return h("div", { className: "rgk-stack" },
      h("p", { className: "rgk-lead" }, "What do you want to tell the desk? Concepts you add here are recorded as reviewed by you."),
      h("div", { className: "rgk-kinds" }, Object.keys(kinds).filter(function (k) { return kinds[k].fields.length; }).map(function (k) {
        return h("button", { key: k, type: "button", className: "rgk-kind", onClick: function () { setKind(k); setValues({}); setMsg(null); } },
          h("div", { className: "rgk-row" }, h(TypeBadge, { type: k }), kinds[k].affects_triage ? h(Badge, { tone: "info" }, "changes priority") : null),
          h("p", null, kinds[k].effect));
      })));
    var spec = kinds[kind];
    var onChange = function (name, value) { setValues(function (v) { var n = Object.assign({}, v); n[name] = value; return n; }); };
    var save = function (replace) {
      setBusy(true); setMsg(null);
      post("/concept/save", { kind: kind, fields: values, reviewer: props.reviewer, replace: !!replace }).then(function (r) {
        setBusy(false); setMsg({ tone: "ok", text: "Saved " + r.path + " as reviewed knowledge." + applied(r), path: r.path }); props.changed(r.path);
      }).catch(function (e) { setBusy(false); setMsg({ tone: "error", text: errText(e), exists: /already exists/.test(errText(e)) }); });
    };
    return h("div", { className: "rgk-stack rgk-narrow" },
      h("div", { className: "rgk-row" }, h(Button, { kind: "link", onClick: function () { setKind(null); } }, "← All types"), h(TypeBadge, { type: kind })),
      h("p", { className: "rgk-muted" }, spec.effect),
      h("div", { className: "rgk-form" }, spec.fields.map(function (f) { return h(Field, { key: f.name, f: f, value: values[f.name], onChange: onChange, teams: teams }); })),
      h(Notice, { tone: "info", text: "Preview: " + preview(kind, values) }),
      h(Notice, { tone: msg && msg.tone, text: msg && msg.text }),
      h("div", { className: "rgk-row" },
        h(Button, { kind: "primary", disabled: busy, onClick: function () { save(false); } }, "Save as " + props.reviewer),
        msg && msg.exists ? h(Button, { kind: "danger", disabled: busy, onClick: function () { save(true); } }, "Replace the existing concept") : null,
        msg && msg.path ? h(Button, { onClick: function () { props.open(msg.path); } }, "Open it") : null,
        msg && msg.path ? h(Button, { kind: "ghost", onClick: function () { setValues({}); setMsg(null); } }, "Add another") : null));
  }

  // ---------------------------------------------------------------- import
  function Import(props) {
    var _c = useState(null), conv = _c[0], setConv = _c[1];
    var _f = useState(null), file = _f[0], setFile = _f[1];
    var _t = useState(""), title = _t[0], setTitle = _t[1];
    var _r = useState(null), result = _r[0], setResult = _r[1];
    var _m = useState(null), msg = _m[0], setMsg = _m[1];
    var _b = useState(false), busy = _b[0], setBusy = _b[1];
    var _x = useState([]), refs = _x[0], setRefs = _x[1];
    var _e = useState(null), est = _e[0], setEst = _e[1];
    var _d = useState(null), drafted = _d[0], setDrafted = _d[1];
    var _o = useState(""), focus = _o[0], setFocus = _o[1];
    var poll = useRef(null);
    var loadConv = function () { get("/converter").then(setConv).catch(function () {}); };
    useEffect(function () { loadConv(); return function () { clearInterval(poll.current); }; }, []);
    useEffect(function () { get("/concepts").then(function (l) { setRefs(l.filter(function (c) { return c.type === "Reference"; })); }).catch(function () {}); }, [props.version]);
    useEffect(function () {
      clearInterval(poll.current);
      if (conv && conv.state === "running") poll.current = setInterval(loadConv, 4000);
    }, [conv && conv.state]);
    var upload = function () {
      if (!file) return;
      setBusy(true); setMsg(null); setResult(null); setEst(null); setDrafted(null);
      var reader = new FileReader();
      reader.onload = function () {
        var data = String(reader.result).split(",")[1] || "";
        post("/import", { name: file.name, data: data, title: title, reviewer: props.reviewer }).then(function (r) {
          setBusy(false); setResult(r); if (r.estimate) setEst(Object.assign({ path: r.path }, r.estimate)); props.changed(null);
        }).catch(function (e) { setBusy(false); setMsg({ tone: "error", text: errText(e) }); });
      };
      reader.onerror = function () { setBusy(false); setMsg({ tone: "error", text: "Could not read the file." }); };
      reader.readAsDataURL(file);
    };
    var estimate = function (path) {
      setEst(null); setDrafted(null); setMsg(null);
      get("/ai/estimate?path=" + encodeURIComponent(path)).then(function (e) { setEst(Object.assign({ path: path }, e)); }).catch(function (e) { setMsg({ tone: "error", text: errText(e) }); });
    };
    var draft = function () {
      setBusy(true); setMsg(null);
      post("/ai/draft", { path: est.path, confirm: true, reviewer: props.reviewer, focus: focus }).then(function (r) {
        setBusy(false); setDrafted(r); props.changed(null);
      }).catch(function (e) { setBusy(false); setMsg({ tone: "error", text: errText(e) }); });
    };
    var installed = conv && conv.installed;
    return h("div", { className: "rgk-stack rgk-narrow" },
      h("section", { className: "rgk-card" },
        h("h3", null, "Import a document"),
        h("p", { className: "rgk-muted" }, "PDF, Word, PowerPoint, Excel, Markdown, text or CSV becomes a Reference concept the desk can read and cite. A Markdown file that is already an OKF concept, or a .zip of a bundle, goes to the review queue."),
        conv && !installed ? h("div", { className: "rgk-notice rgk-notice-warn" },
          conv.state === "running" ? "Installing the document converter (markitdown)… this takes a few minutes the first time."
            : h(React.Fragment, null, "PDF and Office files need the open-source converter markitdown (MIT, Microsoft, " + conv.size_note + "). Markdown, text and CSV work without it. ",
              h(Button, { kind: "primary", onClick: function () { post("/converter/install").then(setConv).catch(function (e) { setMsg({ tone: "error", text: errText(e) }); }); } }, "Install converter")),
          conv.state === "failed" ? h("pre", { className: "rgk-log-box" }, conv.log) : null) : null,
        h("div", { className: "rgk-form" },
          h("label", { className: "rgk-field" }, h("span", { className: "rgk-label" }, "File (up to 15 MB)"),
            h("input", { type: "file", accept: ".pdf,.docx,.pptx,.xlsx,.md,.markdown,.txt,.csv,.zip", onChange: function (e) { setFile(e.target.files[0] || null); } })),
          h("label", { className: "rgk-field" }, h("span", { className: "rgk-label" }, "Title (optional)"),
            h("input", { className: "rgk-input", value: title, onChange: function (e) { setTitle(e.target.value); } }))),
        h("div", { className: "rgk-row" }, h(Button, { kind: "primary", disabled: busy || !file, onClick: upload }, busy && !est ? "Importing…" : "Import")),
        result && result.path ? h(Notice, { tone: "ok", text: (result.existing ? "Already imported (same file) as " : "Imported as ") + result.path + " (" + (result.characters || 0).toLocaleString() + " characters" + (result.truncated ? ", truncated" : "") + ")." }) : null,
        result && result.queued ? h(Notice, { tone: "ok", text: result.note + ". Open Review to approve." }) : null),
      est ? h("section", { className: "rgk-card" },
        h("h3", null, "Draft concepts with AI (optional)"),
        h("p", null, "The model reads ", h("code", null, est.path), " and proposes concepts (applications, teams, policies, …). Drafts go to the review queue; nothing applies until you approve it."),
        h("div", { className: "rgk-notice rgk-notice-warn" },
          "This spends model tokens: about ", h("strong", null, est.input_tokens.toLocaleString(), " input"), " and up to ", h("strong", null, est.max_output_tokens.toLocaleString(), " output"),
          " tokens on ", h("strong", null, est.model), ". ", est.truncated ? "Only the first part of the document is sent. " : "", "Nothing is sent until you click the button."),
        h("label", { className: "rgk-field" }, h("span", { className: "rgk-label" }, "Focus (optional)"),
          h("input", { className: "rgk-input", value: focus, placeholder: "for example: owners and criticality of payment systems", onChange: function (e) { setFocus(e.target.value); } })),
        h("div", { className: "rgk-row" },
          h(Button, { kind: "primary", disabled: busy, onClick: draft }, busy ? "Drafting… (the model is reading)" : "Draft with AI and spend tokens"),
          h(Button, { kind: "ghost", onClick: function () { setEst(null); } }, "Not now")),
        drafted ? h("div", null,
          h(Notice, { tone: drafted.drafts.length ? "ok" : "info", text: drafted.drafts.length ? drafted.drafts.length + " draft(s) are in the review queue." : (drafted.note || "No concepts found.") }),
          drafted.usage ? h("p", { className: "rgk-muted rgk-small" }, "Used " + (drafted.usage.input_tokens || 0).toLocaleString() + " input and " + (drafted.usage.output_tokens || 0).toLocaleString() + " output tokens on " + drafted.model + (drafted.usage.cost_usd ? " (≈ $" + drafted.usage.cost_usd.toFixed(4) + ")" : "") + ".") : null,
          drafted.drafts.length ? h(Button, { kind: "primary", onClick: function () { props.go("Review"); } }, "Review the drafts") : null) : null) : null,
      h(Notice, { tone: msg && msg.tone, text: msg && msg.text }),
      h("section", { className: "rgk-card" },
        h("h3", null, "Imported references"),
        refs.length ? h("ul", { className: "rgk-refs" }, refs.map(function (r) {
          return h("li", { key: r.path }, h("a", { href: "#", onClick: function (e) { e.preventDefault(); props.open(r.path); } }, r.title),
            h("span", { className: "rgk-muted rgk-small" }, " " + r.description + " "),
            h(Button, { kind: "link", onClick: function () { estimate(r.path); } }, "Draft with AI…"));
        })) : h("p", { className: "rgk-muted" }, "None yet.")));
  }

  // ---------------------------------------------------------------- graph
  // Fruchterman–Reingold: nodes repel (k²/d), links attract (d²/k), a cooling temperature caps each move.
  function layout(nodes, edges, w, hgt) {
    var index = {}, n = nodes.length, padX = 140, padY = 30;
    nodes.forEach(function (d, i) {
      var a = 2.399963 * i, r = Math.sqrt((i + 0.5) / Math.max(n, 1)) * Math.min(w, hgt) * 0.45;  // sunflower start: no overlaps
      d.x = w / 2 + r * Math.cos(a); d.y = hgt / 2 + r * Math.sin(a); index[d.id] = d;
    });
    var links = edges.map(function (e) { return { s: index[e.source], t: index[e.target] }; }).filter(function (l) { return l.s && l.t; });
    var k = Math.sqrt(((w - 2 * padX) * (hgt - 2 * padY)) / Math.max(n, 1)) * 1.05, temp = w / 8;
    for (var step = 0; step < 400; step++) {
      nodes.forEach(function (d) { d.dx = 0; d.dy = 0; });
      for (var i = 0; i < n; i++) {
        for (var j = i + 1; j < n; j++) {
          var u = nodes[i], v = nodes[j], ex = u.x - v.x, ey = u.y - v.y, dist = Math.max(Math.sqrt(ex * ex + ey * ey), 0.5), f = (k * k) / dist;
          u.dx += ex / dist * f; u.dy += ey / dist * f; v.dx -= ex / dist * f; v.dy -= ey / dist * f;
        }
      }
      links.forEach(function (l) {
        var ex = l.s.x - l.t.x, ey = l.s.y - l.t.y, dist = Math.max(Math.sqrt(ex * ex + ey * ey), 0.5), f = (dist * dist) / k;
        l.s.dx -= ex / dist * f; l.s.dy -= ey / dist * f; l.t.dx += ex / dist * f; l.t.dy += ey / dist * f;
      });
      nodes.forEach(function (d) {
        d.dx += (w / 2 - d.x) * 0.012; d.dy += (hgt / 2 - d.y) * 0.012;  // weak gravity keeps islands on screen
        var len = Math.max(Math.sqrt(d.dx * d.dx + d.dy * d.dy), 0.01), move = Math.min(len, temp);
        d.x = Math.max(padX, Math.min(w - padX, d.x + d.dx / len * move));
        d.y = Math.max(padY, Math.min(hgt - padY, d.y + d.dy / len * move));
      });
      temp = Math.max(temp * 0.985, 1);
    }
    return links;
  }

  function Graph(props) {
    var _g = useState(null), data = _g[0], setData = _g[1];
    var _s = useState(store("graphShipped") !== "0"), shipped = _s[0], setShipped = _s[1];
    var _h = useState(null), hover = _h[0], setHover = _h[1];
    var _e = useState(null), err = _e[0], setErr = _e[1];
    useEffect(function () { get("/graph").then(setData).catch(function (e) { setErr(errText(e)); }); }, [props.version]);
    var W = 1100, H = 680;
    var view = useMemo(function () {
      if (!data) return null;
      var nodes = data.nodes.filter(function (d) { return shipped || d.id.indexOf("remedigenius/") !== 0; }).map(function (d) { return Object.assign({}, d); });
      var ids = {}; nodes.forEach(function (d) { ids[d.id] = true; });
      var edges = data.edges.filter(function (e) { return ids[e.source] && ids[e.target]; });
      var degree = {}; edges.forEach(function (e) { degree[e.source] = (degree[e.source] || 0) + 1; degree[e.target] = (degree[e.target] || 0) + 1; });
      var links = layout(nodes, edges, W, H);
      return { nodes: nodes, links: links, degree: degree };
    }, [data, shipped]);
    if (err) return h(Notice, { tone: "error", text: err });
    if (!view) return h(Empty, null, "Loading…");
    var near = {};
    if (hover) view.links.forEach(function (l) { if (l.s.id === hover) near[l.t.id] = true; if (l.t.id === hover) near[l.s.id] = true; });
    var types = Array.from(new Set(view.nodes.map(function (d) { return d.type; }))).sort();
    return h("div", { className: "rgk-stack" },
      h("div", { className: "rgk-row rgk-wrap" },
        h("label", { className: "rgk-check" }, h("input", { type: "checkbox", checked: shipped, onChange: function (e) { setShipped(e.target.checked); store("graphShipped", e.target.checked ? "1" : "0"); } }), " include shipped guides and playbooks"),
        h("span", { className: "rgk-muted rgk-small" }, view.nodes.length + " concepts · " + view.links.length + " links · solid ring = reviewed, dashed = unreviewed · click a node to open it")),
      h("div", { className: "rgk-legend" }, types.map(function (t) { return h("span", { key: t }, h("span", { className: "rgk-dot", style: { background: typeColor(t) } }), t); })),
      view.nodes.length ? h("svg", { className: "rgk-graph", viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Knowledge graph" },
        h("g", null, view.links.map(function (l, n) {
          var on = hover && (l.s.id === hover || l.t.id === hover);
          return h("line", { key: n, x1: l.s.x, y1: l.s.y, x2: l.t.x, y2: l.t.y, className: cls("rgk-edge", on && "rgk-edge-on", hover && !on && "rgk-dim") });
        })),
        h("g", null, view.nodes.map(function (d) {
          var r = 6 + Math.min(10, (view.degree[d.id] || 0) * 1.2), dim = hover && hover !== d.id && !near[d.id];
          return h("g", { key: d.id, className: cls("rgk-node", dim && "rgk-dim"), transform: "translate(" + d.x + "," + d.y + ")", tabIndex: 0, role: "button",
                          "aria-label": d.title + " (" + d.type + ")",
                          onMouseEnter: function () { setHover(d.id); }, onMouseLeave: function () { setHover(null); },
                          onFocus: function () { setHover(d.id); }, onBlur: function () { setHover(null); },
                          onClick: function () { props.open(d.id); }, onKeyDown: function (e) { if (e.key === "Enter") props.open(d.id); } },
            h("circle", { r: r, fill: typeColor(d.type), className: cls(d.trust === "human-reviewed" ? "rgk-ring" : "rgk-ring-dashed", d.stale && "rgk-ring-stale") }),
            (hover === d.id || near[d.id] || (!hover && (view.nodes.length <= 16 || r >= 12))) ? h("text", { x: r + 4, y: 4, className: "rgk-label-svg" }, d.title.length > 34 ? d.title.slice(0, 33) + "…" : d.title) : null);
        }))) : h(Empty, null, "No concepts to draw. Tick 'include shipped guides' or add knowledge."));
  }

  // ---------------------------------------------------------------- page
  function KnowledgePage() {
    var initial = (window.location.hash || "").replace(/^#/, "").split(":");
    var _t = useState(TABS.indexOf(initial[0]) >= 0 ? initial[0] : "Overview"), tab = _t[0], setTab = _t[1];
    var _s = useState(initial[0] === "Browse" && initial[1] ? decodeURIComponent(initial.slice(1).join(":")) : null), selected = _s[0], setSelected = _s[1];
    var _k = useState(null), addKind = _k[0], setAddKind = _k[1];
    var _st = useState(null), status = _st[0], setStatus = _st[1];
    var _v = useState(0), version = _v[0], setVersion = _v[1];
    var _e = useState(null), err = _e[0], setErr = _e[1];
    var _r = useState(store("reviewer") || ""), reviewer = _r[0], setReviewer = _r[1];
    useEffect(function () {
      get("/status").then(function (s) { setStatus(s); setErr(null); if (!store("reviewer")) setReviewer(s.reviewer); })
        .catch(function (e) { setErr(errText(e)); });
    }, [version]);
    useEffect(function () {
      var hash = tab + (tab === "Browse" && selected ? ":" + encodeURIComponent(selected) : "");
      if (window.history && window.history.replaceState) window.history.replaceState(null, "", "#" + hash);
    }, [tab, selected]);
    var go = useCallback(function (t, kind) { setTab(t); if (t === "Add") setAddKind(kind || null); }, []);
    var open = useCallback(function (path) { setSelected(path); setTab("Browse"); }, []);
    var changed = useCallback(function (path) { setVersion(function (v) { return v + 1; }); if (path) setSelected(path); }, []);
    var who = reviewer || (status && status.reviewer) || "owner";
    var queue = status && status.overview ? status.overview.review_queue : 0;
    return h("div", { className: "rgk-page" },
      h("header", { className: "rgk-header" },
        h("div", null,
          h("h1", null, "Knowledge"),
          h("p", { className: "rgk-muted" }, "What the security desk knows about your organization, in Open Knowledge Format. Reviewed concepts change priorities; the agent cites them.")),
        h("label", { className: "rgk-reviewer", title: "Recorded as human:<name> when you approve or add knowledge" }, "Reviewer ",
          h("input", { className: "rgk-input", value: who, onChange: function (e) { setReviewer(e.target.value); store("reviewer", e.target.value); }, "aria-label": "Reviewer name" }))),
      h("nav", { className: "rgk-tabs", role: "tablist" }, TABS.map(function (t) {
        return h("button", { key: t, type: "button", role: "tab", "aria-selected": tab === t, className: cls("rgk-tab", tab === t && "rgk-tab-on"), onClick: function () { go(t); } },
          t, t === "Review" && queue ? h("span", { className: "rgk-count" }, queue) : null);
      })),
      err ? h(Notice, { tone: "error", text: "The knowledge service is not available: " + err }) : null,
      tab === "Overview" ? h(Overview, { status: status, version: version, go: go, open: open }) : null,
      tab === "Browse" ? h(Browse, { selected: selected, open: open, reviewer: who, version: version, changed: changed }) : null,
      tab === "Review" ? h(Review, { reviewer: who, version: version, changed: changed, open: open }) : null,
      tab === "Add" ? h(Add, { kind: addKind, reviewer: who, version: version, changed: changed, open: open }) : null,
      tab === "Import" ? h(Import, { reviewer: who, version: version, changed: changed, open: open, go: go }) : null,
      tab === "Graph" ? h(Graph, { version: version, open: open }) : null);
  }

  window.__HERMES_PLUGINS__.register("rg-knowledge", KnowledgePage);
})();
