"use strict";
(() => {
  const API = "https://samuga-news-bot-production.up.railway.app";
  const HISTORY_KEY = "samuga-ai-page-history-v1";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const store = {
    get(key){ try { return sessionStorage.getItem(key); } catch { return null; } },
    set(key,value){ try { sessionStorage.setItem(key,value); } catch {} },
    remove(key){ try { sessionStorage.removeItem(key); } catch {} }
  };
  const lang = () => {
    try { return localStorage.getItem("samuga-lang") === "dv" ? "dv" : "en"; }
    catch { return "en"; }
  };
  async function apiFetch(path, options = {}) {
    let lastError = null;
    for (const url of [path, `${API}${path}`]) {
      try {
        const response = await fetch(url, options);
        if (response.ok) return response;
        lastError = new Error(`HTTP ${response.status}`);
      } catch (error) { lastError = error; }
    }
    throw lastError || new Error("Samuga AI is unavailable");
  }
  function addMessage(text, type = "bot", persist = true) {
    const box = $("#aiPageMessages");
    if (!box) return null;
    const node = document.createElement("div");
    node.className = `ai-page-message ${type}`;
    node.textContent = String(text || "");
    box.appendChild(node);
    box.scrollTop = box.scrollHeight;
    if (persist) saveHistory();
    return node;
  }
  function saveHistory() {
    const rows = $$(".ai-page-message", $("#aiPageMessages"))
      .filter(node => !node.dataset.transient)
      .slice(-60)
      .map(node => ({type: node.classList.contains("user") ? "user" : "bot", text: node.textContent || ""}));
    store.set(HISTORY_KEY, JSON.stringify(rows));
  }
  function restoreHistory() {
    const box = $("#aiPageMessages");
    if (!box) return;
    let rows = [];
    try { rows = JSON.parse(store.get(HISTORY_KEY) || "[]"); } catch {}
    if (Array.isArray(rows) && rows.length) {
      box.innerHTML = "";
      rows.slice(-60).forEach(row => addMessage(row.text, row.type === "user" ? "user" : "bot", false));
    }
    box.scrollTop = box.scrollHeight;
  }
  function clearChat() {
    store.remove(HISTORY_KEY);
    const box = $("#aiPageMessages");
    if (!box) return;
    box.innerHTML = "";
    addMessage(lang() === "dv" ? "ސަމުގާ މީޑިއާގައި ޝާއިއުކުރެވިފައިވާ ޚަބަރެއް ގެ މައްޗަށް ސުވާލެއް ކުރޭ." : "Ask me about stories published by Samuga Media.", "bot", true);
  }
  function setBusy(busy, message = "") {
    const send = $("#aiPageSend");
    const input = $("#aiPageInput");
    const status = $("#aiPageStatus");
    if (send) send.disabled = busy;
    if (input) input.disabled = busy;
    if (status) status.textContent = message;
  }
  async function submitMessage(message) {
    const clean = String(message || "").trim();
    if (!clean) return;
    addMessage(clean, "user");
    setBusy(true, lang() === "dv" ? "ސަމުގާ AI ބަލަނީ…" : "Samuga AI is checking…");
    const wait = addMessage(lang() === "dv" ? "ބަލަނީ…" : "Checking…", "bot", false);
    if (wait) wait.dataset.transient = "true";
    try {
      const response = await apiFetch("/api/chat", {
        method: "POST",
        headers: {"Content-Type":"application/json","Accept":"application/json"},
        body: JSON.stringify({message: clean, lang: lang(), surface: "dedicated-page"})
      });
      const data = await response.json();
      wait?.remove();
      addMessage(data.reply || (lang() === "dv" ? "މިހާރު ޖަވާބެއް ނުފެނުނު." : "I could not find an answer right now."), "bot");
      setBusy(false, "");
    } catch (error) {
      wait?.remove();
      const node = addMessage(lang() === "dv" ? "ކަނެކްޝަން މައްސަލައެއް. އަލުން ޖައްސަވާ." : "Connection issue. Please try again.", "bot");
      node?.classList.add("error");
      setBusy(false, "");
    }
    $("#aiPageInput")?.focus();
  }
  function updateLanguage() {
    const dv = lang() === "dv";
    const title = $("#aiPageTitle");
    const intro = $("#aiPageIntro");
    const input = $("#aiPageInput");
    const send = $("#aiPageSend");
    if (title) title.textContent = dv ? "ސަމުގާ AI އަށް އަހާ" : "Ask Samuga AI";
    if (intro) intro.textContent = dv ? "ސަމުގާ މީޑިއާގައި ޝާއިއުކުރެވިފައިވާ ޚަބަރުތަކާ ބެހޭ ސުވާލުތައް ކުރޭ." : "Ask questions about stories and information published by Samuga Media.";
    if (input) input.placeholder = dv ? "ޚަބަރެއް ގެ މައްޗަށް ސުވާލެއް…" : "Ask about the news…";
    if (send) send.textContent = dv ? "ފޮނުވާ" : "Send";
  }
  document.addEventListener("DOMContentLoaded", () => {
    restoreHistory();
    updateLanguage();
    const form = $("#aiPageForm");
    const input = $("#aiPageInput");
    form?.addEventListener("submit", event => {
      event.preventDefault();
      const message = input?.value || "";
      if (input) input.value = "";
      submitMessage(message);
    });
    input?.addEventListener("input", () => {
      input.style.height = "auto";
      input.style.height = `${Math.min(input.scrollHeight,130)}px`;
    });
    input?.addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form?.requestSubmit();
      }
    });
    $("#aiClearChat")?.addEventListener("click", clearChat);
    $$("[data-ai-prompt]").forEach(button => button.addEventListener("click", () => {
      if (input) input.value = button.dataset.aiPrompt || button.textContent || "";
      form?.requestSubmit();
    }));
    document.addEventListener("samuga:languagechange", updateLanguage);
    window.setTimeout(() => input?.focus(), 120);
  });
})();
