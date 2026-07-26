"use strict";

const API = "https://samuga-news-bot-production.up.railway.app";
const TOKEN_KEY = "samuga-newsroom-token";
const RECOVERY_KEY = "samuga-newsroom-recovery-v2";
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]));
const attr = value => esc(value).replace(/`/g, "&#096;");

let token = localStorage.getItem(TOKEN_KEY) || "";
let user = null;
let currentArticles = [];
let currentMedia = [];
let editorLang = "en";
let coverType = "image";
let mediaItems = [];
let mediaPickerTarget = "cover";
let dirty = false;
let recoveryTimer = null;
let mediaSearchTimer = null;

const TITLES = {home:"Overview",articles:"Articles",editor:"Article editor",media:"Media library",ads:"Advertisements",site:"Website settings",users:"Newsroom users",activity:"Activity log"};
const PUBLISH_ROLES = new Set(["editor","admin","super_admin"]);
const ADMIN_ROLES = new Set(["admin","super_admin"]);

window.addEventListener("DOMContentLoaded", init);
window.addEventListener("beforeunload", event => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });

function init() {
  wireStaticEvents();
  if (token) authenticateExisting();
  else showLogin();
}

function wireStaticEvents() {
  $("#loginForm")?.addEventListener("submit", login);
  $("#logoutBtn")?.addEventListener("click", logout);
  $("#themeToggle")?.addEventListener("click", toggleTheme);
  $("#mobileSidebar")?.addEventListener("click", () => $("#sidebar")?.classList.toggle("open"));
  $$(".side-link").forEach(button => button.addEventListener("click", () => openView(button.dataset.view)));
  $$('[data-view-jump]').forEach(button => button.addEventListener("click", () => openView(button.dataset.viewJump)));
  $$('[data-open-editor]').forEach(button => button.addEventListener("click", () => openNewEditor()));
  $$('[data-close-dialog]').forEach(button => button.addEventListener("click", () => $("#" + button.dataset.closeDialog)?.close()));

  $("#articleSearch")?.addEventListener("input", debounce(loadArticles, 350));
  $("#articleStatus")?.addEventListener("change", loadArticles);
  $("#articleForm")?.addEventListener("submit", event => { event.preventDefault(); saveArticle(false); });
  $("#saveDraftBtn")?.addEventListener("click", () => saveArticle(true));
  $("#previewBtn")?.addEventListener("click", showPreview);
  $("#revisionsBtn")?.addEventListener("click", loadRevisions);
  $("#shareNowBtn")?.addEventListener("click", shareArticleNow);
  $("#articlePublishStatus")?.addEventListener("change", updateScheduleVisibility);
  $("#addMediaBtn")?.addEventListener("click", () => { mediaItems.push({type:"image",url:"",poster:"",caption:"",position:""}); renderMediaItems(); markDirty(); });
  $$('[data-editor-lang]').forEach(button => button.addEventListener("click", () => setEditorLanguage(button.dataset.editorLang)));
  $$('[data-cover-type]').forEach(button => button.addEventListener("click", () => setCoverType(button.dataset.coverType)));
  $$('[data-open-media-picker]').forEach(button => button.addEventListener("click", () => openMediaPicker(button.dataset.openMediaPicker)));
  $("#coverUrl")?.addEventListener("input", () => { renderCoverPreview(); markDirty(); });
  $("#videoPosterUrl")?.addEventListener("input", markDirty);
  $("#coverUpload")?.addEventListener("change", event => handleCoverUpload(event.target.files?.[0]));
  $("#videoPosterUpload")?.addEventListener("change", event => handlePosterUpload(event.target.files?.[0]));

  $("#articleForm")?.addEventListener("input", onEditorInput);
  $("#articleForm")?.addEventListener("change", onEditorInput);
  $("#restoreRecoveryBtn")?.addEventListener("click", restoreRecovery);
  $("#discardRecoveryBtn")?.addEventListener("click", discardRecovery);

  $("#libraryUpload")?.addEventListener("change", event => uploadLibraryFiles(event.target.files));
  $("#mediaSearch")?.addEventListener("input", () => { clearTimeout(mediaSearchTimer); mediaSearchTimer = setTimeout(loadMediaLibrary, 300); });
  $("#mediaTypeFilter")?.addEventListener("change", loadMediaLibrary);

  $("#newAdBtn")?.addEventListener("click", () => openAdDialog());
  $("#adForm")?.addEventListener("submit", saveAd);
  $("#adUpload")?.addEventListener("change", async event => {
    const file = event.target.files?.[0]; if (!file) return;
    try { const data = await uploadFile(file); if (data.type !== "image") throw new Error("Advertisement banners must be images."); $("#adImage").value = data.url; toast("Banner uploaded"); }
    catch (error) { toast(error.message, true); }
    finally { event.target.value = ""; }
  });

  $("#siteSettingsForm")?.addEventListener("submit", saveSiteSettings);
  $("#newUserBtn")?.addEventListener("click", () => openUserDialog());
  $("#userForm")?.addEventListener("submit", saveUser);
  $("#refreshAuditBtn")?.addEventListener("click", loadAudit);
}

async function authenticateExisting() {
  try {
    const data = await api("/api/admin/me");
    user = data.user;
    showApp();
  } catch {
    logout(false);
  }
}

async function login(event) {
  event.preventDefault();
  $("#loginError").textContent = "";
  const button = event.submitter || $("#loginForm button[type=submit]");
  button.disabled = true;
  try {
    const data = await api("/api/admin/login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({email: $("#loginEmail").value.trim(), password: $("#loginPassword").value})
    });
    token = data.token;
    user = data.user;
    localStorage.setItem(TOKEN_KEY, token);
    showApp();
  } catch (error) {
    $("#loginError").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function showLogin() {
  $("#loginScreen").hidden = false;
  $("#appShell").hidden = true;
}

function showApp() {
  $("#loginScreen").hidden = true;
  $("#appShell").hidden = false;
  $("#profileName").textContent = user?.name || "Newsroom user";
  $("#profileRole").textContent = String(user?.role || "newsroom").replaceAll("_", " ");
  $$(".admin-only").forEach(el => el.hidden = !ADMIN_ROLES.has(user?.role));
  configureRoleControls();
  loadAuthors();
  openView("home");
}

function logout(showMessage = true) {
  token = ""; user = null; localStorage.removeItem(TOKEN_KEY);
  if (showMessage) toast("Signed out");
  showLogin();
}

function configureRoleControls() {
  const canPublish = PUBLISH_ROLES.has(user?.role);
  const select = $("#articlePublishStatus");
  if (select) {
    [...select.options].forEach(option => {
      if (["posted","scheduled","hidden"].includes(option.value)) option.disabled = !canPublish;
    });
  }
  $("#sharePanel").hidden = !canPublish;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const auth = options.auth !== false;
  if (auth && token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(API + path, {...options, headers, cache:"no-store"});
  let data = {};
  try { data = await response.json(); } catch { data = {}; }
  if (response.status === 401 && auth) { logout(false); throw new Error("Your session expired. Sign in again."); }
  if (!response.ok || data.ok === false) {
    const error = new Error(data.detail ? `${data.error || "Request failed"} ${data.detail}` : (data.error || `Request failed (${response.status})`));
    error.status = response.status;
    throw error;
  }
  return data;
}

function openView(name) {
  if (!TITLES[name]) name = "home";
  if (["ads","site","users","activity"].includes(name) && !ADMIN_ROLES.has(user?.role)) name = "home";
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".side-link").forEach(button => button.classList.toggle("active", button.dataset.view === name));
  $("#viewTitle").textContent = TITLES[name];
  $("#sidebar")?.classList.remove("open");
  if (name === "home") loadDashboard();
  if (name === "articles") loadArticles();
  if (name === "media") loadMediaLibrary();
  if (name === "ads") loadAds();
  if (name === "site") loadSiteSettings();
  if (name === "users") loadUsers();
  if (name === "activity") loadAudit();
}

async function loadDashboard() {
  try {
    const [statsData, articlesData] = await Promise.all([
      api("/api/admin/dashboard"),
      api("/api/admin/articles?limit=7")
    ]);
    const stats = statsData.stats || {};
    $("#statPublished").textContent = stats.published ?? 0;
    $("#statDrafts").textContent = stats.drafts ?? 0;
    $("#statReview").textContent = stats.review ?? 0;
    $("#statScheduled").textContent = stats.scheduled ?? 0;
    $("#statToday").textContent = stats.today ?? 0;
    $("#statFailures").textContent = stats.failures ?? 0;
    renderArticles(articlesData.articles || [], $("#recentArticles"), true);
  } catch (error) { toast(error.message, true); }
}

async function loadArticles() {
  const q = encodeURIComponent($("#articleSearch")?.value.trim() || "");
  const status = encodeURIComponent($("#articleStatus")?.value || "");
  try {
    const data = await api(`/api/admin/articles?limit=150&q=${q}&status=${status}`);
    currentArticles = data.articles || [];
    renderArticles(currentArticles, $("#articleList"));
  } catch (error) { toast(error.message, true); }
}

function renderArticles(articles, container, compact = false) {
  if (!container) return;
  const head = `<div class="table-row header"><span>Article</span><span>Status</span><span>Category</span><span>Updated</span><span></span></div>`;
  if (!articles.length) { container.innerHTML = `<div class="empty-panel">No articles found.</div>`; return; }
  container.innerHTML = head + articles.map(article => {
    const status = article.status || "draft";
    const time = status === "scheduled" && article.scheduled_at ? `For ${shortDateTime(article.scheduled_at)}` : shortDateTime(article.updated_at || article.posted_at);
    return `<div class="table-row">
      <div class="article-cell"><strong>${esc(article.title || "Untitled")}</strong><span>${esc(article.author_name || article.created_by || "Samuga Newsroom")} · ${esc(article.lang?.toUpperCase() || "EN")}${socialBadges(article.social_status)}</span></div>
      <span class="status-pill ${esc(status)}">${esc(status)}</span>
      <span>${esc(article.category || "LOCAL")}</span>
      <span>${esc(time)}</span>
      <div class="row-actions"><button data-edit-article="${attr(article.id)}">Edit</button>${isPublicStatus(status) ? `<button data-view-public="${attr(article.id)}">View</button>` : ""}</div>
    </div>`;
  }).join("");
  $$('[data-edit-article]', container).forEach(button => button.addEventListener("click", () => openArticle(button.dataset.editArticle)));
  $$('[data-view-public]', container).forEach(button => button.addEventListener("click", () => window.open(`/article?id=${encodeURIComponent(button.dataset.viewPublic)}`, "_blank", "noopener")));
}

function socialBadges(status) {
  if (!status || typeof status !== "object" || !Object.keys(status).length) return "";
  const badges = Object.entries(status).map(([platform, value]) => `<span class="social-badge ${value?.ok ? "ok" : "failed"}">${esc(platform)}</span>`).join("");
  return `<span class="social-badges">${badges}</span>`;
}

function isPublicStatus(status) { return ["posted","published","social_posted","queued"].includes(status); }

async function openArticle(id) {
  try {
    const data = await api(`/api/admin/article?id=${encodeURIComponent(id)}`);
    fillEditor(data.article || {});
    openView("editor");
  } catch (error) { toast(error.message, true); }
}

function openNewEditor() {
  resetEditor();
  openView("editor");
  showRecoveryAvailability();
  setTimeout(() => $("#articleTitle")?.focus(), 50);
}

function resetEditor() {
  $("#articleForm")?.reset();
  $("#articleId").value = "";
  mediaItems = [];
  setEditorLanguage("en");
  setCoverType("image");
  $("#articlePublishStatus").value = "draft";
  $("#articleCategory").value = "LOCAL";
  $("#saveState").textContent = "Not saved";
  $("#revisionsBtn").hidden = true;
  $("#shareNowBtn").hidden = true;
  $("#socialStatusSummary").textContent = "";
  renderMediaItems(); renderCoverPreview(); updateScheduleVisibility(); updateWordStats();
  dirty = false;
}

function fillEditor(article) {
  resetEditor();
  $("#articleId").value = article.id || "";
  $("#articleTitle").value = article.title || "";
  $("#articleExcerpt").value = article.excerpt || article.summary || "";
  $("#articleBody").value = article.body || "";
  $("#articleCategory").value = article.category || "LOCAL";
  $("#articlePublishStatus").value = ["draft","review","posted","scheduled","hidden"].includes(article.status) ? article.status : "draft";
  $("#articleFeatured").checked = !!article.featured;
  $("#articleBreaking").checked = !!article.breaking;
  $("#articleAuthor").value = article.author_id || user?.author_id || "";
  $("#coverCaption").value = article.cover_caption || "";
  $("#socialCaption").value = article.social_caption || "";
  $("#scheduledAt").value = toLocalInput(article.scheduled_at);
  const targets = article.share_targets || {};
  $("#shareTelegram").checked = !!targets.telegram;
  $("#shareFacebook").checked = !!targets.facebook;
  $("#shareX").checked = !!targets.x;
  mediaItems = Array.isArray(article.media_items) ? article.media_items.map(item => ({...item})) : [];
  if (article.cover_video) { setCoverType("video"); $("#coverUrl").value = article.cover_video; $("#videoPosterUrl").value = article.video_poster || ""; }
  else { setCoverType("image"); $("#coverUrl").value = article.cover_image || ""; }
  setEditorLanguage(article.lang || "en");
  renderMediaItems(); renderCoverPreview(); updateScheduleVisibility(); updateWordStats();
  $("#revisionsBtn").hidden = !article.id;
  $("#shareNowBtn").hidden = !(article.id && isPublicStatus(article.status) && PUBLISH_ROLES.has(user?.role));
  renderSocialSummary(article.social_status || {});
  $("#saveState").textContent = article.updated_at ? `Saved ${shortDateTime(article.updated_at)}` : "Saved";
  dirty = false;
  showRecoveryAvailability(article.id);
}

function setEditorLanguage(lang) {
  editorLang = lang === "dv" ? "dv" : "en";
  $$('[data-editor-lang]').forEach(button => button.classList.toggle("active", button.dataset.editorLang === editorLang));
  $(".editor-panel")?.classList.toggle("dv-mode", editorLang === "dv");
  $("#articleTitle").dir = editorLang === "dv" ? "rtl" : "ltr";
  $("#articleExcerpt").dir = editorLang === "dv" ? "rtl" : "ltr";
  $("#articleBody").dir = editorLang === "dv" ? "rtl" : "ltr";
  markDirty();
}

function setCoverType(type) {
  coverType = type === "video" ? "video" : "image";
  $$('[data-cover-type]').forEach(button => button.classList.toggle("active", button.dataset.coverType === coverType));
  $("#videoPosterRow").hidden = coverType !== "video";
  renderCoverPreview();
}

function updateScheduleVisibility() {
  const scheduled = $("#articlePublishStatus")?.value === "scheduled";
  $("#scheduleRow").hidden = !scheduled;
  if (scheduled && !$("#scheduledAt").value) {
    const date = new Date(Date.now() + 60 * 60 * 1000);
    date.setMinutes(Math.ceil(date.getMinutes() / 5) * 5, 0, 0);
    $("#scheduledAt").value = toLocalInput(date.toISOString());
  }
}

function onEditorInput() { markDirty(); updateWordStats(); scheduleRecovery(); }
function markDirty() { dirty = true; if ($("#saveState")) $("#saveState").textContent = "Unsaved changes"; }
function updateWordStats() {
  const text = $("#articleBody")?.value.trim() || "";
  const words = text ? text.split(/\s+/).filter(Boolean).length : 0;
  const mins = Math.max(1, Math.ceil(words / (editorLang === "dv" ? 170 : 220)));
  $("#wordCount").textContent = `${words} words`;
  $("#readingEstimate").textContent = `${mins} min read`;
}

function scheduleRecovery() {
  clearTimeout(recoveryTimer);
  recoveryTimer = setTimeout(() => {
    const payload = articlePayload(false, true);
    if (!payload.title && !payload.body) return;
    localStorage.setItem(RECOVERY_KEY, JSON.stringify({...payload, saved_at: new Date().toISOString()}));
    $("#saveState").textContent = "Recovered in browser";
  }, 900);
}

function readRecovery() {
  try { const data = JSON.parse(localStorage.getItem(RECOVERY_KEY) || "null"); return data && typeof data === "object" ? data : null; }
  catch { return null; }
}

function showRecoveryAvailability(currentId = "") {
  const recovery = readRecovery();
  const useful = recovery && (recovery.title || recovery.body) && (!currentId || recovery.id === currentId || !recovery.id);
  $("#recoveryBanner").hidden = !useful;
}

function restoreRecovery() {
  const data = readRecovery(); if (!data) return;
  fillEditor({...data, id:data.id || "", excerpt:data.excerpt || "", media_items:data.media_items || [], share_targets:data.share || {}});
  dirty = true; $("#saveState").textContent = "Recovery restored — save when ready";
  $("#recoveryBanner").hidden = true;
  toast("Recovery draft restored");
}
function discardRecovery() { localStorage.removeItem(RECOVERY_KEY); $("#recoveryBanner").hidden = true; toast("Recovery draft discarded"); }

function articlePayload(forceDraft = false, recoveryOnly = false) {
  const selectedStatus = forceDraft ? "draft" : $("#articlePublishStatus").value;
  let scheduledAt = null;
  if (selectedStatus === "scheduled" && $("#scheduledAt").value) scheduledAt = new Date($("#scheduledAt").value).toISOString();
  return {
    id: $("#articleId").value || null,
    title: $("#articleTitle").value.trim(), excerpt: $("#articleExcerpt").value.trim(), body: $("#articleBody").value.trim(),
    lang: editorLang, category: $("#articleCategory").value, status: selectedStatus,
    scheduled_at: scheduledAt, featured: $("#articleFeatured").checked, breaking: $("#articleBreaking").checked,
    author_id: $("#articleAuthor").value,
    cover_image: coverType === "image" ? $("#coverUrl").value.trim() : null,
    cover_video: coverType === "video" ? $("#coverUrl").value.trim() : null,
    video_poster: coverType === "video" ? $("#videoPosterUrl").value.trim() : null,
    cover_caption: $("#coverCaption").value.trim(), media_items: mediaItems.filter(item => item.url),
    social_caption: $("#socialCaption").value.trim(),
    share: {telegram: $("#shareTelegram").checked, facebook: $("#shareFacebook").checked, x: $("#shareX").checked},
    recovery_only: recoveryOnly
  };
}

async function saveArticle(forceDraft) {
  const payload = articlePayload(forceDraft);
  if (!payload.title || !payload.body) { toast("Headline and body are required.", true); return; }
  $("#publishBtn").disabled = true; $("#saveDraftBtn").disabled = true; $("#saveState").textContent = "Saving…";
  try {
    const data = await api("/api/admin/article", {method:"POST", body:JSON.stringify(payload)});
    $("#articleId").value = data.article.id;
    $("#articlePublishStatus").value = data.article.status;
    $("#revisionsBtn").hidden = false;
    $("#shareNowBtn").hidden = !(isPublicStatus(data.article.status) && PUBLISH_ROLES.has(user?.role));
    renderSocialSummary(data.social_status || {});
    dirty = false; localStorage.removeItem(RECOVERY_KEY); $("#recoveryBanner").hidden = true;
    $("#saveState").textContent = "Saved";
    toast(data.message || "Article saved");
    if (data.share_results && Object.keys(data.share_results).length) {
      const failed = Object.values(data.share_results).some(value => !value.ok);
      toast(Object.entries(data.share_results).map(([name,value]) => `${name}: ${value.ok ? "done" : "failed"}`).join(" · "), failed);
    }
    await loadDashboard();
  } catch (error) { $("#saveState").textContent = "Save failed"; toast(error.message, true); }
  finally { $("#publishBtn").disabled = false; $("#saveDraftBtn").disabled = false; }
}

async function shareArticleNow() {
  const id = $("#articleId").value;
  const platforms = ["telegram","facebook","x"].filter(name => $("#share" + (name === "x" ? "X" : name[0].toUpperCase() + name.slice(1))).checked);
  if (!id || !platforms.length) { toast("Choose at least one platform.", true); return; }
  const button = $("#shareNowBtn"); button.disabled = true; button.textContent = "Sharing…";
  try {
    const data = await api("/api/admin/share", {method:"POST", body:JSON.stringify({id, platforms, caption:$("#socialCaption").value.trim()})});
    renderSocialSummary(data.social_status || {});
    const failed = Object.values(data.results || {}).some(value => !value.ok);
    toast(Object.entries(data.results || {}).map(([name,value]) => `${name}: ${value.ok ? "done" : "failed"}`).join(" · "), failed);
  } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; button.textContent = "Share selected now"; }
}

function renderSocialSummary(status) {
  const target = $("#socialStatusSummary"); if (!target) return;
  const entries = Object.entries(status || {});
  target.innerHTML = entries.length ? entries.map(([name,value]) => `<span class="social-badge ${value?.ok ? "ok" : "failed"}" title="${attr(value?.message || "")}">${esc(name)}</span>`).join("") : `<span class="optional-text">Not shared</span>`;
}

function renderCoverPreview() {
  const box = $("#coverPreview"); if (!box) return;
  const url = $("#coverUrl")?.value.trim();
  if (!url) { box.innerHTML = "<span>No cover selected</span>"; return; }
  box.innerHTML = coverType === "video" ? `<video src="${attr(url)}" poster="${attr($("#videoPosterUrl")?.value || "")}" controls playsinline preload="metadata"></video>` : `<img src="${attr(url)}" alt="Cover preview">`;
}

async function handleCoverUpload(file) {
  if (!file) return;
  try { const data = await uploadFile(file, true); coverType = data.type; setCoverType(data.type); $("#coverUrl").value = data.url; renderCoverPreview(); markDirty(); toast("Cover uploaded"); }
  catch (error) { toast(error.message, true); }
  finally { $("#coverUpload").value = ""; }
}
async function handlePosterUpload(file) {
  if (!file) return;
  try { const data = await uploadFile(file, true); if (data.type !== "image") throw new Error("Video thumbnails must be images."); $("#videoPosterUrl").value = data.url; renderCoverPreview(); markDirty(); toast("Thumbnail uploaded"); }
  catch (error) { toast(error.message, true); }
  finally { $("#videoPosterUpload").value = ""; }
}

function uploadFile(file, showProgress = false) {
  return new Promise((resolve, reject) => {
    const form = new FormData(); form.append("file", file);
    const xhr = new XMLHttpRequest(); xhr.open("POST", API + "/api/admin/upload"); xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    const progress = $("#uploadProgress");
    if (showProgress && progress) progress.hidden = false;
    xhr.upload.onprogress = event => { if (event.lengthComputable && progress) progress.querySelector("span").style.width = `${Math.max(4, event.loaded / event.total * 100)}%`; };
    xhr.onload = () => {
      if (progress) { progress.hidden = true; progress.querySelector("span").style.width = "35%"; }
      let data = {}; try { data = JSON.parse(xhr.responseText || "{}"); } catch {}
      if (xhr.status === 401) { logout(false); reject(new Error("Your session expired.")); return; }
      if (xhr.status < 200 || xhr.status >= 300 || data.ok === false) reject(new Error(data.error || `Upload failed (${xhr.status})`));
      else resolve(data);
    };
    xhr.onerror = () => { if (progress) progress.hidden = true; reject(new Error("Upload connection failed.")); };
    xhr.send(form);
  });
}

function renderMediaItems() {
  const list = $("#inlineMediaList"); if (!list) return;
  if (!mediaItems.length) { list.innerHTML = `<div class="empty-panel">No inline media added.</div>`; return; }
  list.innerHTML = mediaItems.map((item,index) => `<div class="inline-media-item">
    <input data-media-url="${index}" value="${attr(item.url || "")}" placeholder="Image or video URL">
    <label class="mini-upload">Upload<input type="file" data-media-upload="${index}" accept="image/*,video/mp4,video/webm,video/quicktime" hidden></label>
    <select data-media-type="${index}"><option value="image" ${item.type !== "video" ? "selected" : ""}>Image</option><option value="video" ${item.type === "video" ? "selected" : ""}>Video</option></select>
    <input data-media-position="${index}" type="number" min="1" value="${attr(item.position || "")}" placeholder="After ¶">
    <button type="button" class="remove-media" data-remove-media="${index}">×</button>
    <input class="media-caption-input" data-media-caption="${index}" value="${attr(item.caption || "")}" placeholder="Caption (optional)">
  </div>`).join("");
  $$('[data-remove-media]', list).forEach(button => button.addEventListener("click", () => { mediaItems.splice(+button.dataset.removeMedia, 1); renderMediaItems(); markDirty(); }));
  $$('[data-media-url]', list).forEach(input => input.addEventListener("input", () => { mediaItems[+input.dataset.mediaUrl].url = input.value; markDirty(); }));
  $$('[data-media-type]', list).forEach(select => select.addEventListener("change", () => { mediaItems[+select.dataset.mediaType].type = select.value; markDirty(); }));
  $$('[data-media-position]', list).forEach(input => input.addEventListener("input", () => { mediaItems[+input.dataset.mediaPosition].position = input.value; markDirty(); }));
  $$('[data-media-caption]', list).forEach(input => input.addEventListener("input", () => { mediaItems[+input.dataset.mediaCaption].caption = input.value; markDirty(); }));
  $$('[data-media-upload]', list).forEach(input => input.addEventListener("change", async () => {
    const file = input.files?.[0], index = +input.dataset.mediaUpload; if (!file) return;
    try { const data = await uploadFile(file, true); mediaItems[index].url = data.url; mediaItems[index].type = data.type; renderMediaItems(); markDirty(); toast("Media uploaded"); }
    catch (error) { toast(error.message, true); }
  }));
}

async function loadAuthors() {
  try {
    const data = await api("/api/admin/authors");
    $("#articleAuthor").innerHTML = (data.authors || []).map(author => `<option value="${attr(author.author_id)}">${esc(author.name)} — ${esc(author.role || "Reporter")}</option>`).join("");
    if (user?.author_id) $("#articleAuthor").value = user.author_id;
  } catch (error) { toast(error.message, true); }
}

function showPreview() {
  const payload = articlePayload(false, true);
  const paragraphs = payload.body.split(/\n\s*\n+/).filter(Boolean);
  const cover = payload.cover_video ? `<div class="preview-cover"><video src="${attr(payload.cover_video)}" poster="${attr(payload.video_poster || "")}" controls playsinline></video></div>` : payload.cover_image ? `<div class="preview-cover"><img src="${attr(payload.cover_image)}" alt=""></div>` : "";
  let body = "";
  paragraphs.forEach((paragraph,index) => {
    body += `<p>${esc(paragraph)}</p>`;
    payload.media_items.filter(item => Number(item.position || 0) === index + 1).forEach(item => body += previewMedia(item));
  });
  payload.media_items.filter(item => !item.position || Number(item.position) > paragraphs.length).forEach(item => body += previewMedia(item));
  $("#previewCanvas").innerHTML = `<article class="preview-article" dir="${payload.lang === "dv" ? "rtl" : "ltr"}">${cover}<span class="preview-meta">${esc(payload.category)} · Samuga Media</span><h1>${esc(payload.title || "Untitled article")}</h1>${payload.excerpt ? `<p class="subhead">${esc(payload.excerpt)}</p>` : ""}<div class="preview-body">${body || "<p>Article body appears here.</p>"}</div></article>`;
  $("#previewDialog").showModal();
}
function previewMedia(item) { const visual = item.type === "video" ? `<video src="${attr(item.url)}" poster="${attr(item.poster || "")}" controls playsinline></video>` : `<img src="${attr(item.url)}" alt="${attr(item.caption || "")}">`; return `<figure>${visual}${item.caption ? `<figcaption>${esc(item.caption)}</figcaption>` : ""}</figure>`; }

async function loadRevisions() {
  const id = $("#articleId").value; if (!id) return;
  $("#revisionList").innerHTML = `<div class="empty-panel">Loading history…</div>`;
  $("#revisionsDialog").showModal();
  try {
    const data = await api(`/api/admin/revisions?id=${encodeURIComponent(id)}`);
    const revisions = data.revisions || [];
    $("#revisionList").innerHTML = revisions.length ? revisions.map(revision => `<div class="revision-item"><div><strong>Revision ${revision.revision_no}</strong><span>${esc(shortDateTime(revision.created_at))} · ${esc(revision.created_email || "System")}</span><span>${esc(revision.snapshot?.title || "Untitled")}</span></div><button data-load-revision="${revision.id}">Load version</button></div>`).join("") : `<div class="empty-panel">No revisions recorded yet.</div>`;
    $$('[data-load-revision]', $("#revisionList")).forEach(button => button.addEventListener("click", () => {
      const revision = revisions.find(item => String(item.id) === button.dataset.loadRevision); if (!revision) return;
      const snapshot = revision.snapshot || {};
      fillEditor({...snapshot, id, excerpt:snapshot.excerpt || "", media_items:snapshot.media_items || [], share_targets:snapshot.share_targets || {}, updated_at:null});
      dirty = true; $("#saveState").textContent = `Revision ${revision.revision_no} loaded — save to restore`;
      $("#revisionsDialog").close(); toast("Revision loaded into editor");
    }));
  } catch (error) { $("#revisionList").innerHTML = `<div class="empty-panel">${esc(error.message)}</div>`; }
}

async function loadMediaLibrary() {
  const q = encodeURIComponent($("#mediaSearch")?.value.trim() || "");
  const type = encodeURIComponent($("#mediaTypeFilter")?.value || "");
  try { const data = await api(`/api/admin/media?q=${q}&type=${type}`); currentMedia = data.media || []; renderMediaLibrary($("#mediaLibrary"), currentMedia, false); }
  catch (error) { toast(error.message, true); }
}

function renderMediaLibrary(container, items, picker = false) {
  if (!container) return;
  if (!items.length) { container.innerHTML = `<div class="empty-panel">No uploaded media found.</div>`; return; }
  container.innerHTML = items.map(item => `<article class="media-card"><div class="media-thumb">${item.type === "video" ? `<video src="${attr(item.url)}" muted preload="metadata"></video>` : `<img src="${attr(item.url)}" alt="${attr(item.name || "")}" loading="lazy">`}</div><div class="media-info"><strong>${esc(item.name || "Uploaded media")}</strong><span>${esc(formatBytes(item.size_bytes))} · ${esc(shortDate(item.created_at))}</span></div><div class="media-actions">${picker ? `<button data-pick-media="${item.id}">Use media</button>` : `<button data-use-cover="${item.id}">Use as cover</button><button data-add-inline="${item.id}">Add inline</button>${ADMIN_ROLES.has(user?.role) ? `<button data-delete-media="${item.id}">Delete</button>` : ""}`}</div></article>`).join("");
  $$('[data-pick-media]', container).forEach(button => button.addEventListener("click", () => chooseMedia(items.find(item => String(item.id) === button.dataset.pickMedia))));
  $$('[data-use-cover]', container).forEach(button => button.addEventListener("click", () => { const item = items.find(x => String(x.id) === button.dataset.useCover); useMediaAsCover(item); openView("editor"); }));
  $$('[data-add-inline]', container).forEach(button => button.addEventListener("click", () => { const item = items.find(x => String(x.id) === button.dataset.addInline); addMediaInline(item); openView("editor"); }));
  $$('[data-delete-media]', container).forEach(button => button.addEventListener("click", () => deleteMedia(button.dataset.deleteMedia)));
}

async function uploadLibraryFiles(fileList) {
  const files = [...(fileList || [])]; if (!files.length) return;
  for (const file of files) {
    try { await uploadFile(file, true); toast(`${file.name} uploaded`); }
    catch (error) { toast(`${file.name}: ${error.message}`, true); }
  }
  $("#libraryUpload").value = ""; loadMediaLibrary();
}

async function openMediaPicker(target) {
  mediaPickerTarget = target === "inline" ? "inline" : "cover";
  $("#mediaPickerGrid").innerHTML = `<div class="empty-panel">Loading media…</div>`;
  $("#mediaPickerDialog").showModal();
  try { const data = await api("/api/admin/media"); renderMediaLibrary($("#mediaPickerGrid"), data.media || [], true); }
  catch (error) { $("#mediaPickerGrid").innerHTML = `<div class="empty-panel">${esc(error.message)}</div>`; }
}
function chooseMedia(item) { if (!item) return; if (mediaPickerTarget === "cover") useMediaAsCover(item); else addMediaInline(item); $("#mediaPickerDialog").close(); }
function useMediaAsCover(item) { if (!item) return; setCoverType(item.type); $("#coverUrl").value = item.url; renderCoverPreview(); markDirty(); toast("Cover selected"); }
function addMediaInline(item) { if (!item) return; mediaItems.push({type:item.type,url:item.url,poster:"",caption:"",position:""}); renderMediaItems(); markDirty(); toast("Media added to article"); }
async function deleteMedia(id) {
  if (!confirm("Remove this item from the media library? Live article files are kept safely.")) return;
  try { const data = await api("/api/admin/media/delete", {method:"POST", body:JSON.stringify({id})}); toast(data.kept_for_article ? "Removed from library; file kept because an article uses it." : "Media deleted"); loadMediaLibrary(); }
  catch (error) { toast(error.message, true); }
}

async function loadSiteSettings() {
  try {
    const data = await api("/api/admin/site-settings"), settings = data.settings || {};
    $("#siteTaglineEn").value = settings.tagline_en || ""; $("#siteTaglineDv").value = settings.tagline_dv || "";
    $("#siteCommunityUrl").value = settings.community_url || ""; $("#siteTipUrl").value = settings.tip_url || "";
    $("#siteContactEmail").value = settings.contact_email || ""; $("#siteDefaultTheme").value = settings.default_theme || "system";
    $("#siteShowAi").checked = settings.show_ai_chat !== false;
  } catch (error) { toast(error.message, true); }
}
async function saveSiteSettings(event) {
  event.preventDefault(); $("#siteSettingsError").textContent = "";
  try { await api("/api/admin/site-settings", {method:"POST", body:JSON.stringify({tagline_en:$("#siteTaglineEn").value.trim(),tagline_dv:$("#siteTaglineDv").value.trim(),community_url:$("#siteCommunityUrl").value.trim(),tip_url:$("#siteTipUrl").value.trim(),contact_email:$("#siteContactEmail").value.trim(),default_theme:$("#siteDefaultTheme").value,show_ai_chat:$("#siteShowAi").checked})}); toast("Website settings saved"); }
  catch (error) { $("#siteSettingsError").textContent = error.message; }
}

async function loadAds() { try { const data = await api("/api/admin/ads"); renderAds(data.ads || []); } catch (error) { toast(error.message, true); } }
function renderAds(ads) {
  const container = $("#adList");
  if (!ads.length) { container.innerHTML = `<div class="empty-panel">No advertisements yet.</div>`; return; }
  container.innerHTML = `<div class="table-row header"><span>Advertisement</span><span>Status</span><span>Placement</span><span>Schedule</span><span></span></div>` + ads.map(ad => `<div class="table-row"><div class="article-cell"><strong>${esc(ad.name)}</strong><span>${esc(ad.caption || ad.destination_url || "")}</span></div><span class="status-pill ${ad.active ? "posted" : "draft"}">${ad.active ? "Active" : "Inactive"}</span><span>${esc(ad.placement)}</span><span>${esc(ad.starts_at ? shortDate(ad.starts_at) : "Always")}${ad.ends_at ? ` → ${esc(shortDate(ad.ends_at))}` : ""}</span><div class="row-actions"><button data-edit-ad="${ad.id}">Edit</button></div></div>`).join("");
  $$('[data-edit-ad]', container).forEach(button => button.addEventListener("click", () => openAdDialog(ads.find(ad => String(ad.id) === button.dataset.editAd))));
}
function openAdDialog(ad = {}) {
  $("#adForm").reset(); $("#adError").textContent = "";
  $("#adId").value = ad.id || ""; $("#adName").value = ad.name || ""; $("#adImage").value = ad.image_url || "";
  $("#adMobileImage").value = ad.mobile_image_url || ""; $("#adLink").value = ad.destination_url || ""; $("#adCaption").value = ad.caption || "";
  $("#adPlacement").value = ad.placement || "feed"; $("#adFit").value = ad.fit_mode || "contain"; $("#adActive").checked = ad.active !== false;
  $("#adStartsAt").value = toLocalInput(ad.starts_at); $("#adEndsAt").value = toLocalInput(ad.ends_at);
  $("#adDialogTitle").textContent = ad.id ? "Edit advertisement" : "Add advertisement"; $("#adDialog").showModal();
}
async function saveAd(event) {
  event.preventDefault(); event.stopPropagation(); $("#adError").textContent = "";
  const iso = id => $(id).value ? new Date($(id).value).toISOString() : null;
  try { await api("/api/admin/ads", {method:"POST", body:JSON.stringify({id:$("#adId").value || null,name:$("#adName").value.trim(),image_url:$("#adImage").value.trim(),mobile_image_url:$("#adMobileImage").value.trim(),destination_url:$("#adLink").value.trim(),caption:$("#adCaption").value.trim(),placement:$("#adPlacement").value,fit_mode:$("#adFit").value,active:$("#adActive").checked,starts_at:iso("#adStartsAt"),ends_at:iso("#adEndsAt")})}); $("#adDialog").close(); toast("Advertisement saved"); loadAds(); }
  catch (error) { $("#adError").textContent = error.message; }
}

async function loadUsers() { try { const data = await api("/api/admin/users"); renderUsers(data.users || []); } catch (error) { toast(error.message, true); } }
function renderUsers(users) {
  const container = $("#userList");
  container.innerHTML = `<div class="table-row header"><span>Name</span><span>Email</span><span>Role</span><span>Status</span><span></span></div>` + users.map(account => `<div class="table-row"><div class="article-cell"><strong>${esc(account.name)}</strong><span>Last login: ${esc(shortDateTime(account.last_login))}</span></div><span>${esc(account.email)}</span><span>${esc(String(account.role).replaceAll("_"," "))}</span><span class="status-pill ${account.active ? "posted" : "draft"}">${account.active ? "Active" : "Disabled"}</span><div class="row-actions"><button data-edit-user="${account.id}">Edit</button></div></div>`).join("");
  $$('[data-edit-user]', container).forEach(button => button.addEventListener("click", () => openUserDialog(users.find(account => String(account.id) === button.dataset.editUser))));
}
function openUserDialog(account = {}) {
  $("#userForm").reset(); $("#userError").textContent = ""; $("#userId").value = account.id || ""; $("#userName").value = account.name || ""; $("#userEmail").value = account.email || ""; $("#userRole").value = account.role || "journalist"; $("#userActive").checked = account.active !== false; $("#userPassword").required = !account.id; $("#userDialogTitle").textContent = account.id ? "Edit user" : "Add user"; $("#userDialog").showModal();
}
async function saveUser(event) {
  event.preventDefault(); event.stopPropagation(); $("#userError").textContent = "";
  try { await api("/api/admin/users", {method:"POST", body:JSON.stringify({id:$("#userId").value || null,name:$("#userName").value.trim(),email:$("#userEmail").value.trim(),role:$("#userRole").value,password:$("#userPassword").value,active:$("#userActive").checked})}); $("#userDialog").close(); toast("User saved"); loadUsers(); }
  catch (error) { $("#userError").textContent = error.message; }
}

async function loadAudit() {
  try {
    const data = await api("/api/admin/audit"), events = data.events || [], container = $("#auditList");
    if (!events.length) { container.innerHTML = `<div class="empty-panel">No activity recorded yet.</div>`; return; }
    container.innerHTML = `<div class="table-row header"><span>Action</span><span>User</span><span>Item</span><span>Time</span><span></span></div>` + events.map(event => `<div class="table-row"><div class="article-cell"><strong>${esc(String(event.action || "").replaceAll("_"," "))}</strong><span>${esc(event.entity_type || "system")}</span></div><span>${esc(event.user_email || "System")}</span><span>${esc(event.entity_id || "—")}</span><span>${esc(shortDateTime(event.created_at))}</span><span></span></div>`).join("");
  } catch (error) { toast(error.message, true); }
}

function toggleTheme() { const next = document.documentElement.dataset.theme === "light" ? "dark" : "light"; document.documentElement.dataset.theme = next; localStorage.setItem("samuga-theme", next); }
function shortDate(value) { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString("en-GB", {day:"2-digit",month:"short",year:"numeric"}); }
function shortDateTime(value) { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("en-GB", {day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}); }
function toLocalInput(value) { if (!value) return ""; const date = new Date(value); if (Number.isNaN(date.getTime())) return ""; const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000); return local.toISOString().slice(0,16); }
function formatBytes(bytes) { const n = Number(bytes || 0); if (n < 1024) return `${n} B`; if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`; return `${(n / 1024 ** 2).toFixed(1)} MB`; }
function toast(message, error = false) { const element = $("#toast"); element.textContent = message || "Done"; element.style.background = error ? "var(--danger)" : "var(--text)"; element.style.color = error ? "#fff" : "var(--bg)"; element.classList.add("show"); clearTimeout(element._timer); element._timer = setTimeout(() => element.classList.remove("show"), 3900); }
function debounce(fn, wait) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), wait); }; }
