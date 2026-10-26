/* RemediGenius Community Edition — GitHub tab for the Hermes dashboard.
 * Connect a repository from the web console: GitHub consent happens on github.com (two clicks), everything else is choices on this page.
 * The key never reaches this page or this process: every step is a request to this plugin's backend (/api/plugins/rg-github), which asks the
 * desk, which holds the key. No build step: plain React elements from the dashboard SDK. */
(function () {
  "use strict";
  var SDK = window.__HERMES_PLUGIN_SDK__;
  var React = SDK.React;
  var h = React.createElement;
  var useState = SDK.hooks.useState, useEffect = SDK.hooks.useEffect, useCallback = SDK.hooks.useCallback, useRef = SDK.hooks.useRef;
  var API = "/api/plugins/rg-github";

  function get(path) { return SDK.fetchJSON(API + path); }
  function post(path, body) {
    return SDK.fetchJSON(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  }
  function errText(e) {
    var m = (e && (e.detail || e.message)) || String(e);
    try { var j = JSON.parse(m.slice(m.indexOf("{"))); if (j.detail) return j.detail; } catch (x) { /* plain text */ }
    return m;
  }
  function cls() { return Array.prototype.filter.call(arguments, Boolean).join(" "); }
  function query(name) { try { return new URLSearchParams(window.location.search).get(name); } catch (e) { return null; } }

  function Notice(props) {
    if (!props.text) return null;
    return h("div", { className: cls("rgg-notice", "rgg-notice-" + (props.tone || "info")), role: props.tone === "error" ? "alert" : "status" }, props.text);
  }
  function Button(props) {
    return h("button", { type: "button", className: cls("rgg-btn", props.kind && "rgg-btn-" + props.kind), onClick: props.onClick, disabled: props.disabled, title: props.title },
      props.children);
  }
  function Pill(props) { return h("span", { className: cls("rgg-pill", "rgg-pill-" + props.tone) }, props.children); }

  // The four user-facing states, from the desk's status.
  function stateOf(st) {
    if (!st) return { key: "loading", label: "Checking…", tone: "muted" };
    var remedy = st.remedy || "";
    if (st.state === "Disconnected") return { key: "disconnected", label: "Not connected", tone: "muted" };
    if (st.state === "Ready to create development PRs") return { key: "ready", label: "Ready to create pull requests", tone: "ok" };
    if (st.state && st.state.indexOf("Connected") === 0) return { key: st.repo ? "readonly" : "choose", label: st.repo ? "Connected: read and propose only" : "Connected: choose a repository", tone: "warn" };
    if (remedy.indexOf("not installed") >= 0) return { key: "install", label: "App created: install it", tone: "warn" };
    if (remedy.indexOf("RGGITHUB_HOME") >= 0) return { key: "unavailable", label: "Not available here", tone: "bad" };
    return { key: "blocked", label: "Blocked", tone: "bad" };
  }

  // ---------------------------------------------------------------- Connect
  function Connect(props) {
    var org = useState(""), orgValue = org[0], setOrg = org[1];
    var busy = useState(false), isBusy = busy[0], setBusy = busy[1];
    function start() {
      setBusy(true);
      post("/begin", { org: orgValue.trim(), reconnect: !!props.reconnect }).then(function (r) {
        if (r.resume) { props.onResume(r); setBusy(false); return; }
        var form = document.createElement("form");           // the browser itself posts the App definition to GitHub
        form.method = "post"; form.action = r.target; form.style.display = "none";
        var input = document.createElement("input");
        input.type = "hidden"; input.name = "manifest"; input.value = JSON.stringify(r.manifest);
        form.appendChild(input); document.body.appendChild(form); form.submit();
      }).catch(function (e) { setBusy(false); props.onError(errText(e)); });
    }
    return h("section", { className: "rgg-card" },
      h("h2", null, props.reconnect ? "Reconnect GitHub" : "Connect GitHub"),
      h("p", null, "Let RemediGenius open fixes as pull requests in one repository you choose. It takes two clicks on github.com:"),
      h("ol", { className: "rgg-steps" },
        h("li", null, h("strong", null, "Create GitHub App"), " — GitHub shows a pre-filled page; click the green button once."),
        h("li", null, h("strong", null, "Install"), " — choose ", h("em", null, "Only select repositories"), " and pick just the repository you want to use.")),
      h("ul", { className: "rgg-facts" },
        h("li", null, "You come back to this page automatically; there is nothing to copy or paste."),
        h("li", null, "It can only reach the repository you select, and it can never merge, approve, or touch your main branch. A person reviews and merges."),
        h("li", null, "You can disconnect at any time here, or on GitHub under Settings, Applications.")),
      h("label", { className: "rgg-field" }, "Organization (leave empty to use your own GitHub account)",
        h("input", { className: "rgg-input", value: orgValue, placeholder: "for example my-company", onChange: function (e) { setOrg(e.target.value); }, disabled: isBusy })),
      h("div", { className: "rgg-row" }, h(Button, { kind: "primary", onClick: start, disabled: isBusy }, isBusy ? "Opening GitHub…" : "Connect GitHub")));
  }

  // ---------------------------------------------------------------- Install (wait for GitHub)
  function Install(props) {
    var info = useState(props.initial || null), data = info[0], setData = info[1];
    var timer = useRef(null);
    var check = useCallback(function () {
      return get("/install").then(function (r) { setData(r); if (r.installed) props.onInstalled(); }).catch(function (e) { props.onError(errText(e)); });
    }, []);
    useEffect(function () {
      check();
      timer.current = window.setInterval(check, 4000);
      return function () { window.clearInterval(timer.current); };
    }, []);
    var url = data && data.install_url;
    return h("section", { className: "rgg-card" },
      h("h2", null, "Install the App on your repository"),
      h("p", null, "The App exists but is not installed yet. On the GitHub page choose ", h("em", null, "Only select repositories"), " and pick just the repository you want RemediGenius to use, then click Install."),
      h("div", { className: "rgg-row" },
        url ? h("a", { className: "rgg-btn rgg-btn-primary", href: url, target: "_blank", rel: "noopener noreferrer" }, "Open GitHub to install") : null,
        h(Button, { onClick: check }, "I installed it, check now")),
      h("p", { className: "rgg-muted rgg-small" }, "This page checks automatically every few seconds."));
  }

  // ---------------------------------------------------------------- Configure (repository, branch, reviewers)
  function Configure(props) {
    var repos = useState(null), repoList = repos[0], setRepos = repos[1];
    var repo = useState(props.status.repo || ""), repoValue = repo[0], setRepo = repo[1];
    var br = useState(null), branchInfo = br[0], setBranchInfo = br[1];
    var base = useState(props.status.base || ""), baseValue = base[0], setBase = base[1];
    var rev = useState((props.status.reviewers || []).join(", ")), reviewers = rev[0], setReviewers = rev[1];
    var busy = useState(false), isBusy = busy[0], setBusy = busy[1];
    useEffect(function () {
      get("/repos").then(function (r) {
        setRepos(r.repos || []);
        if (!repoValue && r.repos && r.repos.length === 1) setRepo(r.repos[0]);
      }).catch(function (e) { props.onError(errText(e)); });
    }, []);
    useEffect(function () {
      if (!repoValue) { setBranchInfo(null); return; }
      setBranchInfo(null);
      get("/branches?repo=" + encodeURIComponent(repoValue)).then(function (r) {
        setBranchInfo(r);
        setBase(function (current) { return current && r.branches.indexOf(current) >= 0 ? current : (r.suggested || ""); });
      }).catch(function (e) { props.onError(errText(e)); });
    }, [repoValue]);
    var names = reviewers.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
    var ready = repoValue && baseValue && names.length > 0 && !isBusy;
    function save() {
      setBusy(true);
      post("/configure", { repo: repoValue, base: baseValue, reviewers: names }).then(function (r) { setBusy(false); props.onSaved(r); })
        .catch(function (e) { setBusy(false); props.onError(errText(e)); });
    }
    return h("section", { className: "rgg-card" },
      h("h2", null, props.status.repo ? "Change repository, branch or reviewers" : "Choose the repository, branch and reviewers"),
      !repoList ? h("p", { className: "rgg-muted" }, "Loading the repositories you selected on GitHub…") :
        repoList.length === 0 ? h(Notice, { tone: "warn", text: "The App is installed on no repository. Open github.com/settings/installations, choose Configure, select a repository, then reload this page." }) :
          h("div", { className: "rgg-form" },
            h("label", { className: "rgg-field" }, "Repository",
              h("select", { className: "rgg-input", value: repoValue, onChange: function (e) { setRepo(e.target.value); } },
                [h("option", { key: "", value: "" }, "Choose…")].concat(repoList.map(function (r) { return h("option", { key: r, value: r }, r); })))),
            repoValue && branchInfo && branchInfo.branches.length === 0 ? h(Notice, { tone: "warn", text:
              "This repository has no development branch yet (only " + (branchInfo.default || "its default branch") + "). A repository administrator must create one, with their own GitHub login: " + branchInfo.admin_command }) :
              h("label", { className: "rgg-field" }, "Development branch (pull requests go here; never your production branch)",
                h("select", { className: "rgg-input", value: baseValue, disabled: !branchInfo, onChange: function (e) { setBase(e.target.value); } },
                  [h("option", { key: "", value: "" }, branchInfo ? "Choose…" : "Loading…")].concat(((branchInfo && branchInfo.branches) || []).map(function (b) {
                    return h("option", { key: b, value: b }, b); })))),
            h("label", { className: "rgg-field" }, "Human reviewers (GitHub names, or org/team, separated by commas; bots are not accepted)",
              h("input", { className: "rgg-input", value: reviewers, placeholder: "for example your-github-name", onChange: function (e) { setReviewers(e.target.value); } })),
            h("div", { className: "rgg-row" },
              h(Button, { kind: "primary", onClick: save, disabled: !ready }, isBusy ? "Checking the repository…" : "Save and check"),
              props.onCancel ? h(Button, { onClick: props.onCancel, disabled: isBusy }, "Cancel") : null)));
  }

  // ---------------------------------------------------------------- Status (what is connected, what protects it)
  function Checks(props) {
    var checks = (props.protection && props.protection.checks) || [];
    if (!checks.length) return null;
    return h("div", { className: "rgg-checks" }, h("h3", null, "Protection on GitHub"),
      h("ul", null, checks.map(function (c, i) {
        var tone = c.result === "pass" ? "ok" : c.result === "fail" ? "bad" : "warn";
        return h("li", { key: i }, h("span", { className: "rgg-dot rgg-dot-" + tone }, c.result === "pass" ? "✓" : c.result === "fail" ? "✗" : "!"), " ", c.check,
          c.detail ? h("span", { className: "rgg-muted" }, " — " + c.detail) : null);
      })));
  }
  function StatusCard(props) {
    var st = props.status, s = stateOf(st), busy = useState(""), working = busy[0], setWorking = busy[1];
    function run(name, path, body) {
      setWorking(name);
      post(path, body).then(function (r) { setWorking(""); props.onDone(name, r); }).catch(function (e) { setWorking(""); props.onError(errText(e)); });
    }
    var identity = st.identity || "not set";
    return h("section", { className: "rgg-card" },
      h("div", { className: "rgg-row rgg-between" }, h("h2", null, "Connection"), h(Pill, { tone: s.tone }, s.label)),
      h("dl", { className: "rgg-dl" },
        h("dt", null, "App identity"), h("dd", null, identity),
        h("dt", null, "Repository"), h("dd", null, st.repo || "not chosen yet"),
        h("dt", null, "Development branch"), h("dd", null, st.base || "not chosen yet"),
        h("dt", null, "Feature branches"), h("dd", null, st.branch_prefix || "feature/remedigenius/"),
        h("dt", null, "Human reviewers"), h("dd", null, (st.reviewers || []).join(", ") || "not set"),
        h("dt", null, "Can create pull requests"), h("dd", null, st.writes_enabled ? "Yes" : "No"),
        st.validation_tools ? h("dt", null, "Checks before a PR") : null,
        st.validation_tools ? h("dd", null, Object.keys(st.validation_tools).map(function (k) {
          return k + (st.validation_tools[k] ? "" : " (missing: changes touching those files are reported as not validated)");
        }).join(", ")) : null),
      st.remedy ? h(Notice, { tone: s.key === "ready" ? "info" : "warn", text: "Next step: " + st.remedy }) : null,
      h(Checks, { protection: st.protection }),
      h("div", { className: "rgg-row rgg-wrap" },
        st.repo ? h(Button, { onClick: function () { run("verify", "/verify"); }, disabled: !!working }, working === "verify" ? "Checking…" : "Check protection now") : null,
        st.repo ? h(Button, { onClick: function () { run("refresh", "/refresh"); }, disabled: !!working, title: "Re-read the development branch so fixes see your latest code" },
          working === "refresh" ? "Refreshing…" : "Refresh repository") : null,
        h(Button, { onClick: props.onChange, disabled: !!working }, "Change repository, branch or reviewers"),
        h(Button, { kind: "danger", onClick: props.onDisconnect, disabled: !!working }, "Disconnect")));
  }

  function Disconnect(props) {
    var remove = useState(true), removeInstall = remove[0], setRemove = remove[1];
    var busy = useState(false), isBusy = busy[0], setBusy = busy[1];
    function go() {
      setBusy(true);
      post("/disconnect", { keep_installation: !removeInstall }).then(function (r) { setBusy(false); props.onDone(r); })
        .catch(function (e) { setBusy(false); props.onError(errText(e)); });
    }
    return h("section", { className: "rgg-card" },
      h("h2", null, "Disconnect GitHub"),
      h("p", null, "This deletes the saved App key and settings from RemediGenius. Pull requests already opened stay on GitHub."),
      h("label", { className: "rgg-check" }, h("input", { type: "checkbox", checked: removeInstall, onChange: function (e) { setRemove(e.target.checked); } }),
        " Also uninstall the App from GitHub (recommended)"),
      h("div", { className: "rgg-row" },
        h(Button, { kind: "danger", onClick: go, disabled: isBusy }, isBusy ? "Disconnecting…" : "Disconnect"),
        h(Button, { onClick: props.onCancel, disabled: isBusy }, "Cancel")));
  }

  // ---------------------------------------------------------------- The page
  function GitHubPage() {
    var st = useState(null), status = st[0], setStatus = st[1];
    var er = useState(query("error")), error = er[0], setError = er[1];
    var nt = useState(""), note = nt[0], setNote = nt[1];
    var vw = useState(query("step") === "install" ? "install" : ""), view = vw[0], setView = vw[1];
    var load = useCallback(function () {
      return get("/status").then(setStatus).catch(function (e) { setError(errText(e)); setStatus({ state: "Blocked", remedy: errText(e) }); });
    }, []);
    useEffect(function () { load(); }, []);
    useEffect(function () {   // GitHub returns here after the install (setup URL) or the App creation (callback): drop the one-time query
      if (query("step") || query("error") || query("installation_id") || query("setup_action")) {
        try { window.history.replaceState(null, "", window.location.pathname + (query("profile") ? "?profile=" + query("profile") : "")); } catch (e) { /* ignore */ }
      }
    }, []);
    var s = stateOf(status);
    function fail(m) { setError(m); setNote(""); }
    function done(name, r) {
      setError(""); setView("");
      setNote(name === "refresh" ? "Repository refreshed from " + (r.branch || "the development branch") + "." : "Checked.");
      load();
    }
    var body;
    if (!status) body = h("p", { className: "rgg-muted" }, "Loading…");
    else if (view === "disconnect") body = h(Disconnect, { onCancel: function () { setView(""); }, onError: fail, onDone: function (r) { setView(""); setNote((r.notes || []).join(" ")); load(); } });
    else if (view === "configure" || s.key === "choose") body = h(Configure, { status: status, onError: fail, onCancel: s.key === "choose" ? null : function () { setView(""); },
      onSaved: function (r) { setError(""); setView(""); setNote(r.writes_enabled ? "Saved. Pull requests can now be created." : "Saved. Pull requests are still off: see the next step below."); load(); } });
    else if (view === "install" || s.key === "install") body = h(Install, { onError: fail, onInstalled: function () { setView(""); setNote("GitHub confirmed the installation."); load(); } });
    else if (view === "reconnect") body = h(Connect, { reconnect: true, onError: fail, onResume: function () { setView("install"); } });
    else if (s.key === "disconnected") body = h(Connect, { onError: fail, onResume: function () { setView("install"); } });
    else if (s.key === "unavailable") body = h(Notice, { tone: "error", text: status.remedy });
    else body = h("div", { className: "rgg-stack" },
      h(StatusCard, { status: status, onError: fail, onDone: done, onChange: function () { setView("configure"); }, onDisconnect: function () { setView("disconnect"); } }),
      s.key === "blocked" ? h("section", { className: "rgg-card" }, h("h2", null, "Fix the connection"),
        h("p", null, "If the App was removed or its access was revoked on GitHub, reconnect: RemediGenius checks what happened and either resumes or creates a replacement App."),
        h("div", { className: "rgg-row" }, h(Button, { kind: "primary", onClick: function () { setView("reconnect"); } }, "Reconnect GitHub"))) : null);
    return h("div", { className: "rgg-page" },
      h("header", { className: "rgg-header" },
        h("div", null, h("h1", null, "GitHub"),
          h("p", { className: "rgg-muted" }, "Connect one repository so the agent can propose fixes as pull requests into your development branch. People review and merge; the agent never does.")),
        status ? h(Pill, { tone: s.tone }, s.label) : null),
      error ? h(Notice, { tone: "error", text: error }) : null,
      note ? h(Notice, { tone: "ok", text: note }) : null,
      body);
  }

  window.__HERMES_PLUGINS__.register("rg-github", GitHubPage);
})();
