"use strict";

/* ============ Session helpers ============ */

const Session = {
  get token() { return sessionStorage.getItem("anya_token"); },
  set token(v) { v ? sessionStorage.setItem("anya_token", v) : sessionStorage.removeItem("anya_token"); },
  get serverUrl() { return localStorage.getItem("anya_server_url") || ""; },
  set serverUrl(v) { localStorage.setItem("anya_server_url", v); },
  get username() { return sessionStorage.getItem("anya_username") || ""; },
  set username(v) { v ? sessionStorage.setItem("anya_username", v) : sessionStorage.removeItem("anya_username"); },
  clear() {
    sessionStorage.removeItem("anya_token");
    sessionStorage.removeItem("anya_username");
  },
};

function apiUrl(path) {
  return Session.serverUrl.replace(/\/+$/, "") + path;
}

async function api(path, { method = "GET", body = null, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) headers["Authorization"] = "Bearer " + Session.token;

  const res = await fetch(apiUrl(path), {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    Session.clear();
    showLogin("Session expired — please log in again.");
    throw new Error("Unauthorized");
  }

  let data = null;
  try { data = await res.json(); } catch (_) { /* no body */ }

  if (!res.ok) {
    const message = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
}

/* ============ Toast ============ */

let toastTimer = null;
function toast(message, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

/* ============ Login flow ============ */

const loginScreen = document.getElementById("login-screen");
const appRoot = document.getElementById("app");

function showLogin(errorMessage) {
  appRoot.classList.add("hidden");
  loginScreen.classList.remove("hidden");
  document.getElementById("server-url").value = Session.serverUrl;
  const errEl = document.getElementById("login-error");
  errEl.textContent = errorMessage || "";
}

function showApp() {
  loginScreen.classList.add("hidden");
  appRoot.classList.remove("hidden");
  document.getElementById("who-am-i").textContent = Session.username;
  startPolling();
  refreshCurrentView();
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const serverUrl = document.getElementById("server-url").value.trim();
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const btn = document.getElementById("login-btn");
  const errEl = document.getElementById("login-error");

  if (!serverUrl) { errEl.textContent = "Server URL is required."; return; }
  Session.serverUrl = serverUrl;

  btn.disabled = true;
  btn.textContent = "connecting…";
  errEl.textContent = "";

  try {
    const data = await api("/api/auth/login", { method: "POST", auth: false, body: { username, password } });
    Session.token = data.token;
    Session.username = username;
    showApp();
  } catch (err) {
    errEl.textContent = err.message || "Could not connect.";
  } finally {
    btn.disabled = false;
    btn.textContent = "connect";
  }
});

document.getElementById("logout-btn").addEventListener("click", () => {
  Session.clear();
  stopPolling();
  showLogin();
});

/* ============ Nav / view switching ============ */

const views = ["overview", "queue", "controls", "users", "commands", "logs", "broadcast"];
let activeView = "overview";

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});

function setView(name) {
  activeView = name;
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
  refreshCurrentView();
}

document.querySelectorAll("[data-refresh]").forEach((btn) => {
  btn.addEventListener("click", () => refreshView(btn.dataset.refresh));
});

function refreshCurrentView() { refreshView(activeView); }

function refreshView(name) {
  const handlers = {
    overview: loadOverview,
    queue: loadQueue,
    users: loadUsers,
    commands: () => loadCommands(true),
    logs: loadLogs,
  };
  if (handlers[name]) handlers[name]().catch((err) => toast(err.message, true));
}

/* ============ Overview ============ */

function fmtUptime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function fmtDuration(seconds) {
  seconds = Math.max(0, Math.floor(seconds || 0));
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

async function loadOverview() {
  const data = await api("/api/overview");
  document.getElementById("status-dot").classList.toggle("live", data.voice_engine_online);
  document.getElementById("login-pulse").classList.toggle("live", data.voice_engine_online);
  document.getElementById("stat-voice").textContent = data.voice_engine_online ? "online" : "offline";
  document.getElementById("stat-plays").textContent = data.total_plays;
  document.getElementById("stat-queue").textContent = data.queue_length;
  document.getElementById("stat-uptime").textContent = fmtUptime(data.uptime_seconds);

  const tracksEl = document.getElementById("top-tracks");
  tracksEl.innerHTML = "";
  if (!data.top_tracks.length) {
    tracksEl.innerHTML = `<li class="empty-note">No plays recorded yet.</li>`;
  } else {
    data.top_tracks.forEach(([title, count]) => {
      const li = document.createElement("li");
      li.innerHTML = `<span>${escapeHtml(title)}</span><span class="rank-count">${count} plays</span>`;
      tracksEl.appendChild(li);
    });
  }

  const usersEl = document.getElementById("top-users");
  usersEl.innerHTML = "";
  if (!data.top_users.length) {
    usersEl.innerHTML = `<li class="empty-note">No activity recorded yet.</li>`;
  } else {
    data.top_users.forEach(([userId, count]) => {
      const li = document.createElement("li");
      li.innerHTML = `<span>${escapeHtml(userId)}</span><span class="rank-count">${count} plays</span>`;
      usersEl.appendChild(li);
    });
  }
}

/* ============ Queue / now playing ============ */

async function loadQueue() {
  const data = await api("/api/queue");
  const card = document.getElementById("now-playing-card");

  if (!data.now_playing) {
    card.innerHTML = `<p class="empty-note">Nothing is playing right now.</p>`;
  } else {
    const t = data.now_playing;
    const pct = t.duration_seconds ? Math.min(100, (t.elapsed_seconds / t.duration_seconds) * 100) : 0;
    card.innerHTML = `
      <p class="np-title">${escapeHtml(t.title)}</p>
      <p class="np-meta">${escapeHtml(t.artist || "")} · requested by ${escapeHtml(t.requested_by_name)}</p>
      <div class="np-bar-track"><div class="np-bar-fill" style="width:${pct}%"></div></div>
      <div class="np-time"><span>${fmtDuration(t.elapsed_seconds)}</span><span>${fmtDuration(t.duration_seconds)}</span></div>
      <div class="np-badges">
        <span class="np-badge">${t.is_paused ? "paused" : "playing"}</span>
        <span class="np-badge">vol ${t.volume}%</span>
        <span class="np-badge">loop: ${t.loop_mode.toLowerCase()}</span>
      </div>`;
  }

  const list = document.getElementById("queue-list");
  list.innerHTML = "";
  if (!data.pending.length) {
    list.innerHTML = `<li class="empty-note" style="border:none;background:none;padding:4px 0;">Queue is empty.</li>`;
  } else {
    data.pending.forEach((track, i) => {
      const li = document.createElement("li");
      li.innerHTML = `<span><span class="queue-pos">${i + 1}.</span>${escapeHtml(track.title)}</span><span class="rank-count">${fmtDuration(track.duration_seconds)}</span>`;
      list.appendChild(li);
    });
  }
}

/* ============ Controls ============ */

document.querySelectorAll(".control-btn[data-action]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const action = btn.dataset.action;
    if (action === "stop" && !confirm("Stop playback and clear the queue?")) return;
    try {
      await api(`/api/control/${action}`, { method: "POST" });
      toast(`${action} sent.`);
      loadQueue().catch(() => {});
    } catch (err) {
      toast(err.message, true);
    }
  });
});

const volumeSlider = document.getElementById("volume-slider");
const volumeValue = document.getElementById("volume-value");
volumeSlider.addEventListener("input", () => { volumeValue.textContent = volumeSlider.value + "%"; });
document.getElementById("volume-apply").addEventListener("click", async () => {
  try {
    await api("/api/control/volume", { method: "POST", body: { volume: Number(volumeSlider.value) } });
    toast("Volume updated.");
  } catch (err) { toast(err.message, true); }
});

document.querySelectorAll(".chip[data-loop]").forEach((chip) => {
  chip.addEventListener("click", async () => {
    document.querySelectorAll(".chip[data-loop]").forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    try {
      await api("/api/control/loop", { method: "POST", body: { mode: chip.dataset.loop } });
      toast(`Loop set to ${chip.dataset.loop}.`);
    } catch (err) { toast(err.message, true); }
  });
});

document.getElementById("remove-apply").addEventListener("click", async () => {
  const position = Number(document.getElementById("remove-position").value);
  if (!position || position < 1) { toast("Enter a valid queue position.", true); return; }
  try {
    const data = await api("/api/control/remove", { method: "POST", body: { position } });
    toast(`Removed "${data.removed.title}".`);
    loadQueue().catch(() => {});
  } catch (err) { toast(err.message, true); }
});

document.getElementById("restart-btn").addEventListener("click", async () => {
  if (!confirm("Restart the bot now? It will briefly go offline.")) return;
  try {
    await api("/api/restart", { method: "POST" });
    toast("Restart triggered.");
  } catch (err) { toast(err.message, true); }
});

/* ============ Users ============ */

async function loadUsers() {
  const data = await api("/api/users");
  const tbody = document.querySelector("#users-table tbody");
  tbody.innerHTML = "";
  if (!data.users.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-note">No users recorded yet.</td></tr>`;
    return;
  }
  data.users.forEach((u) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="primary">${escapeHtml(u.full_name || "—")}</td>
      <td>${u.username ? "@" + escapeHtml(u.username) : "—"}</td>
      <td>${u.user_id}</td>
      <td>${u.command_count}</td>
      <td>${fmtTimestamp(u.first_seen)}</td>
      <td>${fmtTimestamp(u.last_seen)}</td>`;
    tbody.appendChild(tr);
  });
}

/* ============ Commands / audit log ============ */

let commandsOffset = 0;
const COMMANDS_PAGE_SIZE = 100;

async function loadCommands(reset) {
  if (reset) commandsOffset = 0;
  const data = await api(`/api/commands?limit=${COMMANDS_PAGE_SIZE}&offset=${commandsOffset}`);
  const tbody = document.querySelector("#commands-table tbody");
  if (reset) tbody.innerHTML = "";

  if (reset && !data.entries.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-note">No commands recorded yet.</td></tr>`;
  }

  data.entries.forEach((e) => {
    const tr = document.createElement("tr");
    const who = e.full_name || e.username || (e.user_id ?? "—");
    tr.innerHTML = `
      <td>${fmtTimestamp(e.timestamp)}</td>
      <td>${escapeHtml(e.source)}</td>
      <td class="primary">${escapeHtml(String(who))}</td>
      <td>${escapeHtml(e.command)}</td>`;
    tbody.appendChild(tr);
  });

  commandsOffset += data.entries.length;
}

document.getElementById("commands-more").addEventListener("click", () => {
  loadCommands(false).catch((err) => toast(err.message, true));
});

/* ============ Logs ============ */

async function loadLogs() {
  const data = await api("/api/logs?lines=300");
  const view = document.getElementById("log-view");
  view.textContent = data.lines.length ? data.lines.join("\n") : "No logs yet.";
  view.scrollTop = view.scrollHeight;
}

/* ============ Broadcast ============ */

document.getElementById("broadcast-send").addEventListener("click", async () => {
  const text = document.getElementById("broadcast-text").value.trim();
  const statusEl = document.getElementById("broadcast-status");
  if (!text) { statusEl.textContent = "Message can't be empty."; return; }
  if (!confirm("Send this message to the group now?")) return;
  try {
    await api("/api/broadcast", { method: "POST", body: { message: text } });
    statusEl.textContent = "";
    document.getElementById("broadcast-text").value = "";
    toast("Broadcast sent.");
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

/* ============ Polling ============ */

let pollTimer = null;
function startPolling() {
  stopPolling();
  pollTimer = setInterval(() => {
    if (activeView === "overview") loadOverview().catch(() => {});
    if (activeView === "queue") loadQueue().catch(() => {});
  }, 6000);
}
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

/* ============ Utils ============ */

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtTimestamp(unixSeconds) {
  if (!unixSeconds) return "—";
  const d = new Date(unixSeconds * 1000);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/* ============ Boot ============ */

(function boot() {
  if (Session.token && Session.username) {
    showApp();
  } else {
    showLogin();
  }
})();
