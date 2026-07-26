"use strict";

const API = "https://samuga-news-bot-production.up.railway.app";
const TOKEN_KEY = "samuga-newsroom-token";
const RECOVERY_KEY = "samuga-newsroom-recovery-v2";
const SAMUGA_BUILD = "8";
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]));
const attr = value => esc(value).replace(/`/g, "&#096;");

let token = localStorage.getItem(TOKEN_KEY) || "";
let user = null;
let currentArticles = [];
let currentMedia = [];
let currentAuthors = [];
let editorLang = "en";
let coverType = "image";
let mediaItems = [];
let mediaPickerTarget = "cover";
let dirty = false;
let recoveryTimer = null;
let mediaSearchTimer = null;
let publishingRefreshTimer = null;
let contentLabRefreshTimer = null;
const contentLabObjectUrls = new Map();

const TITLES = {home:"Overview",articles:"Articles",editor:"Article editor",media:"Media library",contentlab:"Content Lab",publishing:"Publishing centre",ads:"Advertisements",site:"Website settings",authors:"Author profiles",users:"Newsroom users",activity:"Activity log"};
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
  document.addEventListener("click", event => {
    const navButton = event.target.closest(".side-link[data-view]");
    if (navButton) { event.preventDefault(); openView(navButton.dataset.view); return; }
    const retryLab = event.target.closest("[data-retry-content-lab]");
    if (retryLab) { event.preventDefault(); loadContentLab(); }
  });
  window.addEventListener("hashchange", () => {
    if (!user) return;
    const requested = location.hash.replace(/^#/, "");
    if (TITLES[requested]) openView(requested, {updateHash:false});
  });
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
  $("#deleteArticleBtn")?.addEventListener("click", () => deleteArticle($("#articleId")?.value, $("#articleTitle")?.value));
  $("#articlePublishStatus")?.addEventListener("change", updateScheduleVisibility);
  $("#addMediaBtn")?.addEventListener("click", () => { mediaItems.push({type:"image",url:"",poster:"",caption:"",position:""}); renderMediaItems(); markDirty(); });
  $$('[data-editor-lang]').forEach(button => button.addEventListener("click", () => setEditorLanguage(button.dataset.editorLang)));
  $$('[data-cover-type]').forEach(button => button.addEventListener("click", () => setCoverType(button.dataset.coverType)));
  $$('[data-open-media-picker]').forEach(button => button.addEventListener("click", () => openMediaPicker(button.dataset.openMediaPicker)));
  $("#coverUrl")?.addEventListener("input", () => { renderCoverPreview(); markDirty(); });
  $("#videoPosterUrl")?.addEventListener("input", markDirty);
  $("#coverUpload")?.addEventListener("change", event => handleCoverUpload(event.target.files?.[0]));
  $("#videoPosterUpload")?.addEventListener("change", event => handlePosterUpload(event.target.files?.[0]));
  $("#removeCoverBtn")?.addEventListener("click", clearCoverFromArticle);
  $("#brandCoverBtn")?.addEventListener("click", brandCurrentCover);

  $("#articleForm")?.addEventListener("input", onEditorInput);
  $("#articleForm")?.addEventListener("change", onEditorInput);
  $("#restoreRecoveryBtn")?.addEventListener("click", restoreRecovery);
  $("#discardRecoveryBtn")?.addEventListener("click", discardRecovery);

  $("#libraryUpload")?.addEventListener("change", event => uploadLibraryFiles(event.target.files));
  $("#mediaSearch")?.addEventListener("input", () => { clearTimeout(mediaSearchTimer); mediaSearchTimer = setTimeout(loadMediaLibrary, 300); });
  $("#mediaTypeFilter")?.addEventListener("change", loadMediaLibrary);
  const dropZone = $("#mediaDropZone");
  ["dragenter","dragover"].forEach(name => dropZone?.addEventListener(name, event => { event.preventDefault(); dropZone.classList.add("dragging"); }));
  ["dragleave","drop"].forEach(name => dropZone?.addEventListener(name, event => { event.preventDefault(); dropZone.classList.remove("dragging"); }));
  dropZone?.addEventListener("drop", event => uploadLibraryFiles(event.dataTransfer?.files));
  dropZone?.addEventListener("click", () => $("#libraryUpload")?.click());
  dropZone?.addEventListener("keydown", event => { if (["Enter"," "].includes(event.key)) { event.preventDefault(); $("#libraryUpload")?.click(); } });

  $("#refreshContentLabBtn")?.addEventListener("click", loadContentLab);
  $("#checkConnectionsBtn")?.addEventListener("click", checkPublishingConnections);
  $("#refreshPublishingBtn")?.addEventListener("click", loadPublishing);
  $("#retryFailedJobsBtn")?.addEventListener("click", () => retryPublishJob());

  $("#newAdBtn")?.addEventListener("click", () => openAdDialog());
  $("#adForm")?.addEventListener("submit", saveAd);
  $("#adUpload")?.addEventListener("change", async event => {
    const file = event.target.files?.[0]; if (!file) return;
    try { const data = await uploadFile(file); if (data.type !== "image") throw new Error("Advertisement banners must be images."); $("#adImage").value = data.url; toast("Banner uploaded"); }
    catch (error) { toast(error.message, true); }
    finally { event.target.value = ""; }
  });

  $("#siteSettingsForm")?.addEventListener("submit", saveSiteSettings);
  $("#refreshAuthorsBtn")?.addEventListener("click", loadAuthorProfiles);
  $("#authorForm")?.addEventListener("submit", saveAuthorProfile);
  $("#authorProfilePhoto")?.addEventListener("input", renderAuthorAvatarPreview);
  $("#authorProfileName")?.addEventListener("input", renderAuthorAvatarPreview);
  $("#authorPhotoUpload")?.addEventListener("change", handleAuthorPhotoUpload);
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
  $$(".publish-only").forEach(el => el.hidden = !PUBLISH_ROLES.has(user?.role));
  configureRoleControls();
  loadAuthors();
  if (PUBLISH_ROLES.has(user?.role)) loadContentLab();
  const requested = location.hash.replace(/^#/, "");
  openView(TITLES[requested] ? requested : "home");
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

function openView(name, options = {}) {
  if (!TITLES[name]) name = "home";
  if (["ads","site","users","activity"].includes(name) && !ADMIN_ROLES.has(user?.role)) name = "home";
  if (["contentlab","publishing"].includes(name) && !PUBLISH_ROLES.has(user?.role)) name = "home";
  clearInterval(publishingRefreshTimer); publishingRefreshTimer = null;
  clearInterval(contentLabRefreshTimer); contentLabRefreshTimer = null;
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".side-link").forEach(button => button.classList.toggle("active", button.dataset.view === name));
  $("#viewTitle").textContent = TITLES[name];
  $("#sidebar")?.classList.remove("open");
  if (options.updateHash !== false && location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  if (name === "home") loadDashboard();
  if (name === "articles") loadArticles();
  if (name === "media") loadMediaLibrary();
  if (name === "contentlab") { setContentLabLoading(); loadContentLab(); contentLabRefreshTimer = setInterval(loadContentLab, 5000); }
  if (name === "publishing") { loadPublishing(); publishingRefreshTimer = setInterval(loadPublishing, 15000); }
  if (name === "ads") loadAds();
  if (name === "site") loadSiteSettings();
  if (name === "authors") loadAuthorProfiles();
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
      <div class="row-actions"><button data-edit-article="${attr(article.id)}">Edit</button>${isPublicStatus(status) ? `<button data-view-public="${attr(article.id)}">View</button>` : ""}${user?.role === "super_admin" ? `<button class="danger-link" data-delete-article="${attr(article.id)}" data-delete-title="${attr(article.title || "Untitled")}">Delete</button>` : ""}</div>
    </div>`;
  }).join("");
  $$('[data-edit-article]', container).forEach(button => button.addEventListener("click", () => openArticle(button.dataset.editArticle)));
  $$('[data-view-public]', container).forEach(button => button.addEventListener("click", () => window.open(`/article?id=${encodeURIComponent(button.dataset.viewPublic)}`, "_blank", "noopener")));
  $$('[data-delete-article]', container).forEach(button => button.addEventListener("click", () => deleteArticle(button.dataset.deleteArticle, button.dataset.deleteTitle)));
}

function socialStateClass(value) {
  const status = String(value?.status || "").toLowerCase();
  if (value?.ok === true || ["succeeded","posted","published","sent"].includes(status)) return "ok";
  if (["queued","pending","retry","retrying","processing"].includes(status)) return "queued";
  if (["cancelled","canceled"].includes(status)) return "muted";
  return "failed";
}
function socialBadges(status) {
  if (!status || typeof status !== "object" || !Object.keys(status).length) return "";
  const badges = Object.entries(status).map(([platform, value]) => `<span class="social-badge ${socialStateClass(value)}">${esc(platform)}</span>`).join("");
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
  $("#deleteArticleBtn").hidden = true;
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
  $("#deleteArticleBtn").hidden = !(article.id && user?.role === "super_admin");
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
    if (data.share_jobs?.length) {
      toast(`${data.share_jobs.length} social publishing job${data.share_jobs.length === 1 ? "" : "s"} queued`);
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
    const jobs = data.jobs || [];
    toast(jobs.length ? `${jobs.length} publishing job${jobs.length === 1 ? "" : "s"} queued` : "Publishing request queued");
  } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; button.textContent = "Share selected now"; }
}

function renderSocialSummary(status) {
  const target = $("#socialStatusSummary"); if (!target) return;
  const entries = Object.entries(status || {});
  target.innerHTML = entries.length ? entries.map(([name,value]) => `<span class="social-badge ${socialStateClass(value)}" title="${attr(value?.message || value?.status || "")}">${esc(name)}</span>`).join("") : `<span class="optional-text">Not shared</span>`;
}

function renderCoverPreview() {
  const box = $("#coverPreview"); if (!box) return;
  const url = $("#coverUrl")?.value.trim();
  const hasCover = !!url;
  if (!hasCover) {
    box.innerHTML = "<span>No cover selected</span>";
  } else {
    box.innerHTML = coverType === "video"
      ? `<video src="${attr(url)}" poster="${attr($("#videoPosterUrl")?.value || "")}" controls playsinline preload="metadata"></video>`
      : `<img src="${attr(url)}" alt="Cover preview">`;
  }
  const remove = $("#removeCoverBtn"), brand = $("#brandCoverBtn"), label = $("#coverUploadLabel"), hint = $("#coverActionHint");
  if (remove) remove.hidden = !hasCover;
  if (brand) brand.hidden = !hasCover || coverType !== "image";
  if (label) label.textContent = hasCover ? "Replace file" : "Upload file";
  if (hint) hint.textContent = hasCover
    ? (coverType === "image" ? "Remove, replace, or apply the same Samuga branding used by Telegram." : "Remove or replace this video cover.")
    : "Upload or choose an image, then add Samuga branding when needed.";
}

function clearCoverFromArticle() {
  const url = $("#coverUrl")?.value.trim();
  if (!url) return;
  if (!confirm("Remove this cover from the article? The uploaded file will stay safely in the Media Library.")) return;
  $("#coverUrl").value = "";
  $("#videoPosterUrl").value = "";
  $("#coverCaption").value = "";
  renderCoverPreview();
  markDirty();
  toast("Cover removed from this article. You can upload or choose another one.");
}

async function brandCurrentCover() {
  const button = $("#brandCoverBtn");
  const sourceUrl = $("#coverUrl")?.value.trim();
  if (!sourceUrl || coverType !== "image") {
    toast("Choose an image cover first.", true);
    return;
  }
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Adding branding…";
  try {
    const data = await api("/api/admin/media/brand-cover", {
      method: "POST",
      body: JSON.stringify({
        url: sourceUrl,
        title: $("#articleTitle")?.value.trim() || "Samuga Media",
        category: $("#articleCategory")?.value || "LOCAL"
      })
    });
    const media = data.media || data;
    if (!media.url) throw new Error("The branded cover URL was not returned.");
    setCoverType("image");
    $("#coverUrl").value = media.url;
    $("#videoPosterUrl").value = "";
    renderCoverPreview();
    markDirty();
    toast("Samuga branding added. The original photo remains in the Media Library.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

async function handleCoverUpload(file) {
  if (!file) return;
  try { let data = await uploadFile(file, true); data = await waitForMediaReady(data, "Preparing video for the website"); coverType = data.type; setCoverType(data.type); $("#coverUrl").value = data.url; if (data.poster) $("#videoPosterUrl").value = data.poster; renderCoverPreview(); markDirty(); toast(data.type === "video" ? "Video ready" : "Cover uploaded"); }
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
    try { let data = await uploadFile(file, true); data = await waitForMediaReady(data, "Preparing video for the website"); mediaItems[index].url = data.url; mediaItems[index].type = data.type; mediaItems[index].poster = data.poster || ""; renderMediaItems(); markDirty(); toast(data.type === "video" ? "Video ready" : "Media uploaded"); }
    catch (error) { toast(error.message, true); }
  }));
}

async function loadAuthors(includeInactive = false) {
  try {
    const suffix = includeInactive && ADMIN_ROLES.has(user?.role) ? "?all=1" : "";
    const data = await api(`/api/admin/authors${suffix}`);
    currentAuthors = data.authors || [];
    const activeAuthors = currentAuthors.filter(author => author.active !== false);
    const articleSelect = $("#articleAuthor");
    if (articleSelect) {
      articleSelect.innerHTML = activeAuthors.map(author => `<option value="${attr(author.author_id)}">${esc(author.name)} — ${esc(author.role || "Reporter")}</option>`).join("");
      if (user?.author_id && activeAuthors.some(author => author.author_id === user.author_id)) articleSelect.value = user.author_id;
    }
    populateUserAuthorSelect();
    return currentAuthors;
  } catch (error) { toast(error.message, true); return []; }
}

function populateUserAuthorSelect(selected = "") {
  const select = $("#userAuthor");
  if (!select) return;
  const options = currentAuthors.filter(author => author.active !== false || author.author_id === selected).map(author => {
    const source = author.source === "telegram" ? "Telegram" : author.source === "ai" ? "AI" : "Dashboard";
    const linked = author.linked_users ? " · linked" : "";
    return `<option value="${attr(author.author_id)}">${esc(author.name)} — ${esc(author.role || "Reporter")} (${source}${linked})</option>`;
  }).join("");
  select.innerHTML = `<option value="">Auto-match by exact name</option>${options}`;
  if (selected) select.value = selected;
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

function mediaStatusLabel(item) {
  const status = String(item.status || "ready").toLowerCase();
  if (status === "pending") return "Waiting";
  if (status === "processing") return "Processing";
  if (status === "failed") return "Failed";
  return "Ready";
}
function mediaMeta(item) {
  const parts = [formatBytes(item.size_bytes)];
  if (item.type === "video" && item.duration) parts.push(formatDuration(item.duration));
  if (item.width && item.height) parts.push(`${item.width}×${item.height}`);
  if (item.source === "telegram") parts.push("Telegram");
  parts.push(shortDate(item.created_at));
  return parts.filter(Boolean).join(" · ");
}
function mediaVisual(item) {
  const status = String(item.status || "ready").toLowerCase();
  if (item.type === "video") {
    const visual = item.poster ? `<img src="${attr(item.poster)}" alt="${attr(item.name || "Video")}" loading="lazy">` : `<div class="video-placeholder">▶</div>`;
    return `${visual}<span class="video-badge">▶ Video</span>${status !== "ready" ? `<span class="processing-overlay"><i></i>${esc(mediaStatusLabel(item))}</span>` : ""}`;
  }
  return `<img src="${attr(item.url)}" alt="${attr(item.name || "")}" loading="lazy">`;
}
function renderMediaLibrary(container, items, picker = false) {
  if (!container) return;
  if (!items.length) { container.innerHTML = `<div class="empty-panel">No uploaded media found.</div>`; return; }
  container.innerHTML = items.map(item => {
    const status = String(item.status || "ready").toLowerCase();
    const ready = status === "ready";
    const useButton = picker ? `<button data-pick-media="${item.id}" ${ready ? "" : "disabled"}>${ready ? "Use media" : mediaStatusLabel(item)}</button>` : `<button data-use-cover="${item.id}" ${ready ? "" : "disabled"}>Use as cover</button><button data-add-inline="${item.id}" ${ready ? "" : "disabled"}>Add inline</button>`;
    const retry = status === "failed" ? `<button data-reprocess-media="${item.id}">Reprocess</button>` : "";
    const error = item.error ? `<span class="media-error" title="${attr(item.error)}">${esc(item.error)}</span>` : "";
    return `<article class="media-card ${status}"><div class="media-thumb">${mediaVisual(item)}</div><div class="media-info"><div><strong>${esc(item.name || "Uploaded media")}</strong><span class="media-status ${status}">${esc(mediaStatusLabel(item))}</span></div><span>${esc(mediaMeta(item))}</span>${error}</div><div class="media-actions">${useButton}${retry}${!picker && ADMIN_ROLES.has(user?.role) ? `<button data-delete-media="${item.id}">Delete</button>` : ""}</div></article>`;
  }).join("");
  $$('[data-pick-media]', container).forEach(button => button.addEventListener("click", () => chooseMedia(items.find(item => String(item.id) === button.dataset.pickMedia))));
  $$('[data-use-cover]', container).forEach(button => button.addEventListener("click", () => { const item = items.find(x => String(x.id) === button.dataset.useCover); useMediaAsCover(item); openView("editor"); }));
  $$('[data-add-inline]', container).forEach(button => button.addEventListener("click", () => { const item = items.find(x => String(x.id) === button.dataset.addInline); addMediaInline(item); openView("editor"); }));
  $$('[data-reprocess-media]', container).forEach(button => button.addEventListener("click", () => reprocessMedia(button.dataset.reprocessMedia)));
  $$('[data-delete-media]', container).forEach(button => button.addEventListener("click", () => deleteMedia(button.dataset.deleteMedia)));
}

async function uploadLibraryFiles(fileList) {
  const files = [...(fileList || [])]; if (!files.length) return;
  for (const file of files) {
    try { const data = await uploadFile(file, true); toast(data.type === "video" ? `${file.name} uploaded — preparing in background` : `${file.name} uploaded`); }
    catch (error) { toast(`${file.name}: ${error.message}`, true); }
  }
  $("#libraryUpload").value = ""; loadMediaLibrary();
  setTimeout(loadMediaLibrary, 3000);
}

async function waitForMediaReady(upload, message = "Processing media") {
  if (!upload || upload.type !== "video" || !upload.id || String(upload.status || "ready") === "ready") return upload;
  toast(`${message}…`);
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    await delay(2000);
    const data = await api(`/api/admin/media?id=${encodeURIComponent(upload.id)}`);
    const item = data.media?.[0];
    if (!item) throw new Error("Uploaded video could not be found.");
    if (item.status === "ready") return item;
    if (item.status === "failed") throw new Error(item.error || "Video processing failed.");
  }
  throw new Error("The video is still processing. It is safely saved in the Media library.");
}
async function reprocessMedia(id) {
  try { await api("/api/admin/media/reprocess", {method:"POST", body:JSON.stringify({id})}); toast("Video processing restarted"); loadMediaLibrary(); setTimeout(loadMediaLibrary, 3000); }
  catch (error) { toast(error.message, true); }
}
async function openMediaPicker(target) {
  mediaPickerTarget = target === "inline" ? "inline" : "cover";
  $("#mediaPickerGrid").innerHTML = `<div class="empty-panel">Loading media…</div>`;
  $("#mediaPickerDialog").showModal();
  try { const data = await api("/api/admin/media"); renderMediaLibrary($("#mediaPickerGrid"), data.media || [], true); }
  catch (error) { $("#mediaPickerGrid").innerHTML = `<div class="empty-panel">${esc(error.message)}</div>`; }
}
function chooseMedia(item) { if (!item || item.status === "failed" || ["pending","processing"].includes(item.status)) return; if (mediaPickerTarget === "cover") useMediaAsCover(item); else addMediaInline(item); $("#mediaPickerDialog").close(); }
function useMediaAsCover(item) { if (!item) return; setCoverType(item.type); $("#coverUrl").value = item.url; if (item.type === "video") $("#videoPosterUrl").value = item.poster || ""; renderCoverPreview(); markDirty(); toast("Cover selected"); }
function addMediaInline(item) { if (!item) return; mediaItems.push({type:item.type,url:item.url,poster:item.poster || "",caption:"",position:""}); renderMediaItems(); markDirty(); toast("Media added to article"); }
async function deleteMedia(id) {
  if (!confirm("Remove this item from the media library? Live article files are kept safely.")) return;
  try { const data = await api("/api/admin/media/delete", {method:"POST", body:JSON.stringify({id})}); toast(data.kept_for_article ? "Removed from library; file kept because an article uses it." : "Media deleted"); loadMediaLibrary(); }
  catch (error) { toast(error.message, true); }
}


function setContentLabLoading() {
  const list = $("#contentLabList"), historyBox = $("#contentLabHistory"), state = $("#contentLabConnection");
  if (list) list.innerHTML = `<div class="empty-panel lab-loading">Connecting to the live Telegram Content Lab…</div>`;
  if (historyBox && !historyBox.children.length) historyBox.innerHTML = `<div class="empty-panel">Loading synchronized actions…</div>`;
  if (state) state.textContent = "Connecting to the shared Telegram approval queue…";
}
function showContentLabError(error) {
  const message = error?.message || "Content Lab could not be loaded.";
  const list = $("#contentLabList"), historyBox = $("#contentLabHistory"), state = $("#contentLabConnection");
  if (state) state.textContent = `Connection problem: ${message}`;
  if (list) list.innerHTML = `<div class="empty-panel lab-error"><strong>Content Lab is not connected</strong><span>${esc(message)}</span><button type="button" class="secondary" data-retry-content-lab>Retry connection</button></div>`;
  if (historyBox) historyBox.innerHTML = `<div class="empty-panel">Actions will appear after the shared queue connects.</div>`;
  ["#labStatPending","#labStatEnglish","#labStatDhivehi","#labStatBreaking"].forEach(selector => { const el=$(selector); if(el) el.textContent="—"; });
}
async function loadContentLab() {
  if (!PUBLISH_ROLES.has(user?.role)) return;
  const state = $("#contentLabConnection");
  try {
    const data = await api(`/api/admin/content-lab?build=${SAMUGA_BUILD}`);
    const items = data.items || [], counts = data.counts || {};
    if (state) state.textContent = data.sync_mode === "shared_approval_queue"
      ? `Connected — dashboard and Telegram are using the same live approval queue${data.telegram_linked === false ? " (Telegram settings need attention)" : ""}.`
      : "Connected to Content Lab.";
    $("#labStatPending").textContent = counts.pending ?? items.length;
    $("#labStatEnglish").textContent = counts.english ?? items.filter(item => item.lang === "en").length;
    $("#labStatDhivehi").textContent = counts.dhivehi ?? items.filter(item => item.lang === "dv").length;
    $("#labStatBreaking").textContent = counts.breaking ?? items.filter(item => item.breaking).length;
    const badge = $("#contentLabBadge");
    if (badge) { badge.textContent = items.length > 99 ? "99+" : String(items.length); badge.hidden = !items.length; }
    renderContentLab(items);
    renderContentLabHistory(data.history || []);
    await loadContentLabImages(items);
  } catch (error) { showContentLabError(error); toast(error.message, true); }
}
function renderContentLab(items) {
  const container = $("#contentLabList"); if (!container) return;
  for (const url of contentLabObjectUrls.values()) URL.revokeObjectURL(url);
  contentLabObjectUrls.clear();
  if (!items.length) { container.innerHTML = `<div class="empty-panel">Content Lab is clear. New Telegram review cards will appear here automatically.</div>`; return; }
  container.innerHTML = items.map(item => {
    const copy = item.lang === "dv" ? (item.dv_text || item.summary || "") : (item.caption || item.summary || "");
    const direction = item.lang === "dv" ? "rtl" : "ltr";
    return `<article class="lab-card ${item.breaking ? "breaking" : ""}" data-lab-key="${attr(item.key)}" dir="${direction}">
      <div class="lab-card-media">${item.has_card ? `<span class="no-card">Loading card…</span>` : `<span class="no-card">Text preview</span>`}</div>
      <div class="lab-card-body">
        <div class="lab-card-kicker"><div><span class="lab-key">${esc(String(item.key || "").toUpperCase())}</span><span class="lab-category">${esc(item.category || "LOCAL")}</span><span class="lab-language">${item.lang === "dv" ? "Dhivehi" : "English"}</span></div><span class="lab-age">${esc(relativeAdminTime(item.created_at))}</span></div>
        <h3 class="lab-title">${esc(item.title || "Untitled")}</h3>
        ${copy ? `<div class="lab-copy">${esc(copy)}</div>` : ""}
        <div class="lab-actions">
          <button data-lab-action="post_tg" type="button">📣 Post to Telegram</button><button data-lab-action="post_soc" type="button">📱 Post to Social</button>
          <button class="lab-all" data-lab-action="post_all" type="button">🌐 Post to All</button><button data-lab-edit type="button">✏️ Edit</button><button class="lab-reject" data-lab-action="reject" type="button">❌ Reject</button>
        </div>
        <div class="lab-edit-box"><textarea class="lab-edit-text" dir="${direction}" placeholder="Correct the caption or Dhivehi text before posting">${esc(copy)}</textarea><div class="lab-edit-destinations"><button data-lab-edit-action="post_tg" type="button">Save + Telegram</button><button data-lab-edit-action="post_soc" type="button">Save + Social</button><button data-lab-edit-action="post_all" type="button">Save + All</button></div></div>
      </div></article>`;
  }).join("");
  $$('[data-lab-action]', container).forEach(button => button.addEventListener("click", () => runContentLabAction(button.closest("[data-lab-key]"), button.dataset.labAction)));
  $$('[data-lab-edit]', container).forEach(button => button.addEventListener("click", () => button.closest(".lab-card-body").querySelector(".lab-edit-box")?.classList.toggle("open")));
  $$('[data-lab-edit-action]', container).forEach(button => button.addEventListener("click", () => {
    const card = button.closest("[data-lab-key]"); const corrected = card.querySelector(".lab-edit-text")?.value.trim() || "";
    runContentLabAction(card, button.dataset.labEditAction, corrected);
  }));
}
async function loadContentLabImages(items) {
  await Promise.all(items.filter(item => item.has_card).map(async item => {
    try {
      const response = await fetch(`${API}/api/admin/content-lab/card?key=${encodeURIComponent(item.key)}`, {headers:{Authorization:`Bearer ${token}`},cache:"no-store"});
      if (!response.ok) return;
      const blob = await response.blob(), url = URL.createObjectURL(blob); contentLabObjectUrls.set(item.key, url);
      const media = document.querySelector(`[data-lab-key="${CSS.escape(item.key)}"] .lab-card-media`);
      if (media) media.innerHTML = `<img src="${url}" alt="Content Lab card for ${attr(item.title || item.key)}">`;
    } catch {}
  }));
}
async function runContentLabAction(card, action, corrected = "") {
  if (!card) return;
  const key = card.dataset.labKey;
  const label = {post_tg:"Post this card to Telegram? The website will also be published.",post_soc:"Post this card to social platforms? The website will also be published.",post_all:"Post this card everywhere?",reject:"Reject and remove this card?"}[action] || "Continue?";
  if (!confirm(label)) return;
  card.classList.add("lab-working");
  try {
    const data = await api("/api/admin/content-lab/action", {method:"POST",body:JSON.stringify({key,action,corrected:corrected || null})});
    toast(data.message || `${String(key).toUpperCase()} action accepted`); await loadContentLab();
  } catch (error) { card.classList.remove("lab-working"); toast(error.message, true); }
}
function renderContentLabHistory(rows) {
  const container = $("#contentLabHistory"); if (!container) return;
  if (!rows.length) { container.innerHTML = `<div class="empty-panel">No Content Lab actions recorded yet.</div>`; return; }
  container.innerHTML = `<div class="table-row header"><span>Card</span><span>Action</span><span>Status</span><span>Time</span><span></span></div>` + rows.map(row => `<div class="table-row"><div class="article-cell"><strong>${esc(String(row.key || "").toUpperCase())} — ${esc(row.title || "Untitled")}</strong><span>${esc(row.actor || "Samuga team")} · ${esc(row.origin || "Telegram")}</span></div><span>${esc((row.action || "—").replaceAll("_"," "))}</span><span class="lab-status ${esc(row.status || "")}">${esc(row.status || "—")}</span><span>${esc(shortDateTime(row.actioned_at || row.updated_at || row.created_at))}</span><span></span></div>`).join("");
}
function relativeAdminTime(value) {
  if (!value) return "now"; const date = new Date(value); if (Number.isNaN(date.getTime())) return "now";
  const sec = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (sec < 60) return "now"; if (sec < 3600) return `${Math.floor(sec/60)}m ago`; if (sec < 86400) return `${Math.floor(sec/3600)}h ago`; return `${Math.floor(sec/86400)}d ago`;
}

async function loadPublishing() {
  if (!PUBLISH_ROLES.has(user?.role)) return;
  try {
    const data = await api("/api/admin/publishing");
    renderPublishingConnections(data.connections || {}, data.connections_checked_at);
    const jobs = data.jobs || [];
    $("#publishStatWaiting").textContent = jobs.filter(job => ["pending","retry"].includes(job.status)).length;
    $("#publishStatProcessing").textContent = jobs.filter(job => job.status === "processing").length;
    $("#publishStatFailed").textContent = data.counts?.failed ?? jobs.filter(job => job.status === "failed").length;
    $("#publishStatSent").textContent = data.counts?.sent_24h ?? 0;
    renderPublishQueue(jobs); renderPublishingActivity(data.logs || []);
  } catch (error) { toast(error.message, true); }
}
function renderPublishingConnections(connections, checkedAt = null) {
  ["telegram","facebook","x"].forEach(platform => {
    const card = $(`[data-platform-card="${platform}"]`); if (!card) return;
    const value = connections[platform] || {};
    const state = value.ok === true ? "connected" : value.ok === false ? "failed" : value.configured ? "configured" : "missing";
    card.className = `connection-card ${state}`;
    const message = value.message || (value.configured ? "Configured" : "Not configured");
    $("span", card.querySelector("div")).textContent = message;
    card.title = checkedAt ? `Checked ${shortDateTime(checkedAt)}` : message;
  });
}
function renderPublishQueue(jobs) {
  const container = $("#publishQueue"); if (!container) return;
  const active = jobs.filter(job => ["pending","retry","processing","failed"].includes(job.status));
  if (!active.length) { container.innerHTML = `<div class="empty-panel">The publishing queue is clear.</div>`; return; }
  container.innerHTML = `<div class="table-row header"><span>Article</span><span>Platform</span><span>Status</span><span>Attempt</span><span></span></div>` + active.map(job => `<div class="table-row"><div class="article-cell"><strong>${esc(job.title || job.article_id)}</strong><span>${esc(job.error || (job.next_attempt_at ? `Next try ${shortDateTime(job.next_attempt_at)}` : shortDateTime(job.created_at)))}</span></div><span class="platform-name">${esc(job.platform)}</span><span class="status-pill ${esc(job.status)}">${esc(job.status)}</span><span>${esc(`${job.attempts}/${job.max_attempts}`)}</span><div class="row-actions">${["failed","retry"].includes(job.status) ? `<button data-retry-job="${job.id}">Retry</button>` : ""}${["pending","retry"].includes(job.status) ? `<button data-cancel-job="${job.id}">Cancel</button>` : ""}</div></div>`).join("");
  $$('[data-retry-job]', container).forEach(button => button.addEventListener("click", () => retryPublishJob(button.dataset.retryJob)));
  $$('[data-cancel-job]', container).forEach(button => button.addEventListener("click", () => cancelPublishJob(button.dataset.cancelJob)));
}
function renderPublishingActivity(logs) {
  const container = $("#publishingActivity"); if (!container) return;
  if (!logs.length) { container.innerHTML = `<div class="empty-panel">No social publishing activity yet.</div>`; return; }
  container.innerHTML = `<div class="table-row header"><span>Article</span><span>Platform</span><span>Status</span><span>Time</span><span></span></div>` + logs.slice(0,30).map(log => `<div class="table-row"><div class="article-cell"><strong>${esc(log.title || log.article_id || "Article")}</strong><span>${esc(log.message || "")}</span></div><span class="platform-name">${esc(log.platform)}</span><span class="status-pill ${esc(log.status)}">${esc(log.status)}</span><span>${esc(shortDateTime(log.created_at))}</span><span></span></div>`).join("");
}
async function checkPublishingConnections() {
  const button = $("#checkConnectionsBtn"); button.disabled = true; button.textContent = "Checking…";
  try { const data = await api("/api/admin/connections/check", {method:"POST", body:"{}"}); renderPublishingConnections(data.connections || {}, data.checked_at); toast("Connections checked"); }
  catch (error) { toast(error.message, true); }
  finally { button.disabled = false; button.textContent = "Check connections"; }
}
async function retryPublishJob(id = null) {
  try { const data = await api("/api/admin/publish-jobs/retry", {method:"POST", body:JSON.stringify(id ? {id} : {})}); toast(`${data.retried || 0} job${data.retried === 1 ? "" : "s"} queued for retry`); loadPublishing(); }
  catch (error) { toast(error.message, true); }
}
async function cancelPublishJob(id) {
  if (!confirm("Cancel this pending publishing job?")) return;
  try { await api("/api/admin/publish-jobs/cancel", {method:"POST", body:JSON.stringify({id})}); toast("Publishing job cancelled"); loadPublishing(); }
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

async function loadAuthorProfiles() {
  try {
    await loadAuthors(false);
    renderAuthorProfiles(currentAuthors);
  } catch (error) { toast(error.message, true); }
}

function authorInitial(name) {
  return String(name || "S").trim().charAt(0).toUpperCase() || "S";
}

function renderAuthorProfiles(authors) {
  const container = $("#authorGrid");
  if (!container) return;
  if (!authors.length) { container.innerHTML = `<div class="empty-panel panel">No author profiles found.</div>`; return; }
  const canManageAll = ADMIN_ROLES.has(user?.role);
  container.innerHTML = authors.map(author => {
    const canEdit = canManageAll || author.is_mine;
    const avatar = author.photo_url ? `<img src="${attr(author.photo_url)}" alt="">` : esc(authorInitial(author.name));
    const sourceLabel = author.source === "telegram" ? "Telegram author" : author.source === "ai" ? "AI newsroom" : "Dashboard author";
    return `<article class="author-card ${author.active === false ? "inactive" : ""}">
      <div class="author-avatar">${avatar}</div>
      <div class="author-card-copy"><div class="author-card-title"><strong>${esc(author.name || "Unnamed author")}</strong><span class="author-source ${esc(author.source || "dashboard")}">${esc(sourceLabel)}</span></div><span>${esc(author.role || "Reporter")}</span><p>${esc(author.bio || "No public bio added yet.")}</p><div class="author-stats"><span>${Number(author.article_count || 0)} articles</span><span>${Number(author.linked_users || 0)} linked login${Number(author.linked_users || 0) === 1 ? "" : "s"}</span>${author.telegram_user_id ? `<span>Telegram connected</span>` : ""}</div></div>
      <div class="author-card-actions">${canEdit ? `<button class="secondary compact" data-edit-author="${attr(author.author_id)}">Edit profile</button>` : ""}</div>
    </article>`;
  }).join("");
  $$('[data-edit-author]', container).forEach(button => button.addEventListener("click", () => openAuthorDialog(authors.find(author => author.author_id === button.dataset.editAuthor))));
}

function renderAuthorAvatarPreview() {
  const preview = $("#authorAvatarPreview");
  if (!preview) return;
  const photo = $("#authorProfilePhoto")?.value.trim();
  const name = $("#authorProfileName")?.value;
  preview.innerHTML = photo ? `<img src="${attr(photo)}" alt="">` : esc(authorInitial(name));
}

function openAuthorDialog(author = {}) {
  if (!author?.author_id) return;
  const canManageAll = ADMIN_ROLES.has(user?.role);
  $("#authorForm").reset();
  $("#authorError").textContent = "";
  $("#authorProfileId").value = author.author_id || "";
  $("#authorProfileName").value = author.name || "";
  $("#authorProfileRole").value = author.role || "Reporter";
  $("#authorProfilePhoto").value = author.photo_url || "";
  $("#authorProfileBio").value = author.bio || "";
  $("#authorTelegramId").value = author.telegram_user_id || "";
  $("#authorProfileActive").checked = author.active !== false;
  $("#authorProfileRole").disabled = !canManageAll;
  $$(".author-admin-field", $("#authorDialog")).forEach(field => field.hidden = !canManageAll);
  $("#authorProfileSource").textContent = author.source === "telegram" ? "Connected Telegram author" : author.source === "ai" ? "Samuga AI profile" : "Dashboard author profile";
  $("#authorDialogTitle").textContent = `Edit ${author.name || "author"}`;
  renderAuthorAvatarPreview();
  $("#authorDialog").showModal();
}

async function handleAuthorPhotoUpload(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const data = await uploadFile(file);
    if (data.type !== "image") throw new Error("Author profile photos must be images.");
    $("#authorProfilePhoto").value = data.url;
    renderAuthorAvatarPreview();
    toast("Profile photo uploaded");
  } catch (error) { toast(error.message, true); }
  finally { event.target.value = ""; }
}

async function saveAuthorProfile(event) {
  event.preventDefault(); event.stopPropagation();
  $("#authorError").textContent = "";
  const canManageAll = ADMIN_ROLES.has(user?.role);
  const payload = {
    author_id: $("#authorProfileId").value,
    name: $("#authorProfileName").value.trim(),
    photo_url: $("#authorProfilePhoto").value.trim(),
    bio: $("#authorProfileBio").value.trim(),
  };
  if (canManageAll) {
    payload.role = $("#authorProfileRole").value.trim();
    payload.telegram_user_id = $("#authorTelegramId").value.trim() || null;
    payload.active = $("#authorProfileActive").checked;
  }
  try {
    await api("/api/admin/authors", {method:"POST", body:JSON.stringify(payload)});
    $("#authorDialog").close();
    const me = await api("/api/admin/me");
    user = me.user;
    $("#profileName").textContent = user?.name || "Newsroom user";
    toast("Author profile saved");
    await loadAuthorProfiles();
  } catch (error) { $("#authorError").textContent = error.message; }
}

async function loadUsers() {
  try {
    await loadAuthors(true);
    const data = await api("/api/admin/users");
    renderUsers(data.users || []);
  } catch (error) { toast(error.message, true); }
}
function renderUsers(users) {
  const container = $("#userList");
  if (!users.length) { container.innerHTML = `<div class="empty-panel">No newsroom users found.</div>`; return; }
  const authorById = new Map(currentAuthors.map(author => [author.author_id, author]));
  container.innerHTML = `<div class="table-row header"><span>Name</span><span>Email</span><span>Role</span><span>Author</span><span></span></div>` + users.map(account => {
    const linked = authorById.get(account.author_id);
    return `<div class="table-row"><div class="article-cell"><strong>${esc(account.name)}</strong><span>Last login: ${esc(shortDateTime(account.last_login))}</span></div><span>${esc(account.email)}</span><span>${esc(String(account.role).replaceAll("_"," "))}</span><span>${esc(linked?.name || "Not linked")}</span><div class="row-actions"><button data-edit-user="${account.id}">Edit</button></div></div>`;
  }).join("");
  $$('[data-edit-user]', container).forEach(button => button.addEventListener("click", () => openUserDialog(users.find(account => String(account.id) === button.dataset.editUser))));
}
function openUserDialog(account = {}) {
  $("#userForm").reset();
  $("#userError").textContent = "";
  populateUserAuthorSelect(account.author_id || "");
  $("#userId").value = account.id || "";
  $("#userName").value = account.name || "";
  $("#userEmail").value = account.email || "";
  $("#userRole").value = account.role || "journalist";
  $("#userAuthor").value = account.author_id || "";
  $("#userTelegramId").value = account.telegram_user_id || "";
  $("#userActive").checked = account.active !== false;
  $("#userPassword").required = !account.id;
  $("#userDialogTitle").textContent = account.id ? "Edit user" : "Add user";
  $("#userDialog").showModal();
}
async function saveUser(event) {
  event.preventDefault(); event.stopPropagation(); $("#userError").textContent = "";
  try {
    await api("/api/admin/users", {method:"POST", body:JSON.stringify({
      id:$("#userId").value || null,
      name:$("#userName").value.trim(),
      email:$("#userEmail").value.trim(),
      role:$("#userRole").value,
      author_id:$("#userAuthor").value || null,
      telegram_user_id:$("#userTelegramId").value.trim() || null,
      password:$("#userPassword").value,
      active:$("#userActive").checked,
    })});
    $("#userDialog").close(); toast("User saved and author identity linked"); loadUsers();
  } catch (error) { $("#userError").textContent = error.message; }
}

async function deleteArticle(id, title = "this article") {
  if (user?.role !== "super_admin" || !id) return;
  const safeTitle = String(title || "this article").slice(0, 120);
  if (!confirm(`Permanently delete “${safeTitle}”? This cannot be undone.`)) return;
  try {
    await api("/api/admin/article/delete", {method:"POST", body:JSON.stringify({id})});
    toast("Article deleted");
    if ($("#articleId")?.value === String(id)) resetEditor();
    openView("articles");
  } catch (error) { toast(error.message, true); }
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
function formatDuration(seconds) { const total = Math.max(0, Math.round(Number(seconds) || 0)); const minutes = Math.floor(total / 60); const rest = total % 60; return minutes ? `${minutes}:${String(rest).padStart(2,"0")}` : `${rest}s`; }
function delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

function debounce(fn, wait) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), wait); }; }
