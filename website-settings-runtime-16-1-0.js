"use strict";
(() => {
  const API = "https://samuga-news-bot-production.up.railway.app";
  const SESSION_KEY = "samuga-ai-chat-history-v1";
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const safeStorage = {
    get(key){ try { return sessionStorage.getItem(key); } catch { return null; } },
    set(key,value){ try { sessionStorage.setItem(key,value); } catch {} }
  };
  const asBool = (value, fallback = false) => value === undefined || value === null || value === "" ? fallback : (value === true || value === 1 || String(value).toLowerCase() === "true");
  const safeUrl = value => {
    const raw = String(value || "").trim();
    if (!raw) return "";
    try { const url = new URL(raw, location.origin); return ["http:","https:","mailto:","tel:"].includes(url.protocol) ? url.href : ""; }
    catch { return ""; }
  };
  const parseMaybe = value => {
    if (!value) return {};
    if (typeof value === "object") return value;
    try { return JSON.parse(value); } catch { return {}; }
  };
  function flattenSettings(raw = {}) {
    const nested = parseMaybe(raw.website_settings_v2 || raw.website_settings || {});
    const sections = ["general","branding","header","footer","homepage","ai","seo","contact","legal"];
    const flat = {...raw, ...nested};
    sections.forEach(section => { if (nested[section] && typeof nested[section] === "object") Object.assign(flat, nested[section]); });
    flat.social_links = Array.isArray(nested.social_links) ? nested.social_links : (Array.isArray(raw.social_links) ? raw.social_links : []);
    return flat;
  }
  async function apiFetch(path, options = {}) {
    let lastError;
    for (const url of [path, `${API}${path}`]) {
      try {
        const response = await fetch(url, {...options, cache:"no-store"});
        if (response.ok) return response;
        lastError = new Error(`HTTP ${response.status}`);
      } catch (error) { lastError = error; }
    }
    throw lastError || new Error("Settings unavailable");
  }
  function setMeta(selector, value, attr = "content") {
    if (!value) return;
    const node = $(selector); if (node) node.setAttribute(attr, value);
  }
  function applyBranding(s) {
    const root = document.documentElement;
    if (/^#[0-9a-f]{6}$/i.test(s.primary_color || "")) root.style.setProperty("--brand", s.primary_color);
    if (/^#[0-9a-f]{6}$/i.test(s.accent_color || "")) root.style.setProperty("--samuga-sky", s.accent_color);
    if (/^#[0-9a-f]{6}$/i.test(s.header_background || "")) root.style.setProperty("--settings-header-bg", s.header_background);
    if (/^#[0-9a-f]{6}$/i.test(s.footer_background || "")) root.style.setProperty("--settings-footer-bg", s.footer_background);
    const logo = safeUrl(s.logo_url || s.main_logo_url);
    const darkLogo = safeUrl(s.dark_logo_url) || logo;
    const mobileLogo = safeUrl(s.mobile_logo_url) || logo;
    if (logo || darkLogo || mobileLogo) {
      $$(".site-header .brand img,.article-header .brand img,.v3-drawer-logo img,.v3-footer-brand img").forEach(img => {
        const isFooter = img.closest(".v3-footer-brand");
        const chosen = innerWidth <= 760 ? mobileLogo : (isFooter ? darkLogo : logo);
        if (chosen) img.src = chosen;
      });
    }
    const favicon = safeUrl(s.favicon_url); if (favicon) { const node = $('link[rel="icon"]'); if (node) node.href = favicon; }
  }
  function applyHeader(s) {
    const sticky = asBool(s.header_sticky, true);
    $$(".site-header,.article-header").forEach(h => h.classList.toggle("settings-sticky-header", sticky));
    document.body.classList.toggle("settings-header-static", !sticky);
    $$(".site-header .brand,.article-header .brand").forEach(el => el.hidden = !asBool(s.header_show_logo, true));
    $$(".site-header .segmented,.article-header .segmented").forEach(el => el.hidden = !asBool(s.header_show_language, true));
    $$(".site-header .theme-toggle,.article-header .theme-toggle").forEach(el => el.hidden = !asBool(s.header_show_theme, true));
    $$("[data-drawer-toggle],#menuBtn").forEach(el => el.hidden = !asBool(s.header_show_menu, true));
    const search = $(".search-box"); if (search) search.hidden = !asBool(s.header_show_search, true);
    const existing = $("#settingsAnnouncement"); existing?.remove();
    if (asBool(s.announcement_enabled, false) && String(s.announcement_text || "").trim()) {
      const bar = document.createElement(safeUrl(s.announcement_url) ? "a" : "div");
      bar.id = "settingsAnnouncement"; bar.className = "settings-announcement"; bar.textContent = s.announcement_text;
      if (bar.tagName === "A") { bar.href = safeUrl(s.announcement_url); bar.target = "_blank"; bar.rel = "noopener"; }
      const header = $(".site-header,.article-header"); header?.insertAdjacentElement("afterend", bar);
    }
  }
  function socialList(s) {
    if (Array.isArray(s.social_links) && s.social_links.length) return s.social_links;
    const labels = {facebook:"Facebook",instagram:"Instagram",x:"X",telegram:"Telegram",tiktok:"TikTok",youtube:"YouTube",whatsapp:"WhatsApp",linkedin:"LinkedIn",viber:"Viber",threads:"Threads",snapchat:"Snapchat"};
    return Object.entries(labels).map(([platform,label]) => ({platform,label,url:s[`${platform}_url`] || (platform === "telegram" ? s.community_url : ""), enabled:Boolean(s[`${platform}_url`] || (platform === "telegram" && s.community_url)), new_tab:true}));
  }
  function applySocials(s) {
    const items = socialList(s).filter(item => asBool(item.enabled, true) && safeUrl(item.url));
    const byPlatform = Object.fromEntries(items.map(item => [String(item.platform || "").toLowerCase(), item]));
    $$('[data-social-key]').forEach(link => {
      const item = byPlatform[link.dataset.socialKey];
      if (!item) { link.hidden = true; return; }
      link.hidden = false; link.href = safeUrl(item.url); link.title = item.label || item.platform;
      if (asBool(item.new_tab, true)) { link.target = "_blank"; link.rel = "noopener"; } else { link.removeAttribute("target"); link.removeAttribute("rel"); }
      link.removeAttribute("data-unconfigured"); link.removeAttribute("role");
    });
    const known = new Set($$('[data-social-key]').map(link => link.dataset.socialKey));
    const custom = items.filter(item => !known.has(String(item.platform || "").toLowerCase()));
    $$('[data-v3-socials],[data-v3-footer-socials]').forEach(container => {
      container.querySelectorAll('[data-settings-custom-social]').forEach(node => node.remove());
      custom.forEach(item => {
        const a = document.createElement("a"); a.dataset.settingsCustomSocial = "true"; a.className = "v3-social-link settings-custom-social";
        a.href = safeUrl(item.url); a.textContent = String(item.label || item.platform || "Link").slice(0,2).toUpperCase(); a.title = item.label || item.platform;
        if (asBool(item.new_tab, true)) { a.target = "_blank"; a.rel = "noopener"; }
        container.appendChild(a);
      });
    });
  }
  function applyFooter(s) {
    const description = s.footer_description || s.tagline_en || s.website_tagline;
    $$(".v3-footer-brand p").forEach(node => { if (description) node.textContent = description; });
    $$(".v3-footer-brand h2").forEach(node => { if (s.website_tagline || s.tagline_en) node.textContent = s.website_tagline || s.tagline_en; });
    const logo = safeUrl(s.footer_logo_url || s.dark_logo_url || s.logo_url); if (logo) $$(".v3-footer-brand img").forEach(img => img.src = logo);
    $$("[data-v3-footer-socials]").forEach(el => el.hidden = !asBool(s.footer_show_socials, true));
    const copyright = s.copyright_text;
    if (copyright) $$(".footer-bottom span:first-child").forEach(node => node.textContent = copyright.replace(/\{year\}/g, String(new Date().getFullYear())));
    const links = {
      "/about.html": s.about_url, "/contact.html": s.contact_url, "/advertising.html": s.advertising_url,
      "/privacy-policy.html": s.privacy_url, "/terms.html": s.terms_url,
      "/editorial-policy.html": s.editorial_policy_url, "/corrections-policy.html": s.corrections_policy_url
    };
    $$(".v3-footer-links a,.v3-drawer-links a").forEach(a => { const replacement = links[new URL(a.href,location.origin).pathname]; if (safeUrl(replacement)) a.href = safeUrl(replacement); });
  }
  function applyAI(s) {
    const enabled = asBool(s.ai_enabled, asBool(s.show_ai_chat, true));
    const showFloating = enabled && asBool(s.ai_floating_enabled, true);
    const showSidebar = enabled && asBool(s.ai_sidebar_enabled, true);
    const fab = $("#chatFab"), panel = $("#chatPanel"), drawerLink = $("#v3AskAi");
    if (fab) { fab.hidden = !showFloating && !document.body.classList.contains("ai-page"); fab.dataset.position = s.ai_button_position || "bottom-right"; }
    if (panel && !enabled) panel.hidden = true;
    if (drawerLink) drawerLink.hidden = !showSidebar;
    $$(".chat-fab-label,[data-v3-ai-label]").forEach(node => node.textContent = s.ai_button_text || "Ask Samuga AI");
    const first = $("#chatMessages .msg.bot"); if (first && s.ai_welcome_message && $$("#chatMessages .msg").length === 1) first.textContent = s.ai_welcome_message;
    const input = $("#chatInput"); if (input && s.ai_placeholder) input.placeholder = s.ai_placeholder;
    document.body.classList.toggle("settings-ai-mobile-hidden", !asBool(s.ai_mobile_enabled, true));
  }
  function applyHomepage(s) {
    const toggle = (selector,key,fallback=true) => $$(selector).forEach(node => node.hidden = !asBool(s[key],fallback));
    toggle(".lead-section","homepage_show_hero",true);
    toggle(".top-rail","homepage_show_trending",true);
    toggle("#newsStrip","homepage_show_breaking",true);
    toggle(".feed-section","homepage_show_latest",true);
    const limit = Math.max(1, Math.min(100, Number(s.homepage_cards_limit || 30)));
    const enforce = () => $$("#storyGrid > .story-card").forEach((card,index) => card.hidden = index >= limit);
    enforce(); const grid = $("#storyGrid"); if (grid && !grid.dataset.settingsObserved) { grid.dataset.settingsObserved="true"; new MutationObserver(enforce).observe(grid,{childList:true}); }
  }
  function applyContact(s) {
    const contactEmail = s.public_contact_email || s.contact_email;
    $$('[data-contact-email]').forEach(node => { if (contactEmail) { node.href=`mailto:${contactEmail}`; node.textContent=contactEmail; node.closest('[data-contact-email-block]')?.removeAttribute('hidden'); } });
    const mapping = {"[data-business-name]":s.business_name || s.registered_company_name,"[data-business-phone]":s.public_phone,"[data-business-address]":s.office_address || s.address,"[data-office-hours]":s.office_hours};
    Object.entries(mapping).forEach(([selector,value]) => { if (value) $$(selector).forEach(node => node.textContent=value); });
  }
  function applySEO(s) {
    const isHome = location.pathname === "/" || location.pathname.endsWith("/index.html");
    if (isHome && s.default_seo_title) document.title = s.default_seo_title;
    if (isHome) {
      setMeta('meta[name="description"]', s.default_meta_description || s.website_description);
      setMeta('meta[property="og:title"]', s.default_og_title || s.default_seo_title);
      setMeta('meta[property="og:description"]', s.default_og_description || s.default_meta_description);
      setMeta('meta[property="og:image"]', safeUrl(s.default_og_image));
      setMeta('meta[name="twitter:card"]', s.twitter_card_type || "summary_large_image");
      const canonical = safeUrl(s.canonical_url); if (canonical) { const node=$('link[rel="canonical"]'); if(node) node.href=canonical; }
    }
    if (s.google_verification) { let node=$('meta[name="google-site-verification"]'); if(!node){node=document.createElement('meta');node.name='google-site-verification';document.head.appendChild(node)} node.content=s.google_verification; }
  }
  function moveFloatingChat() {
    const fab=$("#chatFab"), panel=$("#chatPanel");
    if (fab && fab.parentElement !== document.body) document.body.appendChild(fab);
    if (panel && panel.parentElement !== document.body) document.body.appendChild(panel);
  }
  function restoreChatHistory() {
    const box=$("#chatMessages"); if (!box || box.dataset.historyReady) return;
    box.dataset.historyReady="true";
    let history=[]; try { history=JSON.parse(safeStorage.get(SESSION_KEY)||"[]"); } catch {}
    if (Array.isArray(history) && history.length) {
      box.innerHTML=""; history.slice(-40).forEach(item => { const div=document.createElement("div"); div.className=`msg ${item.type === "user" ? "user" : "bot"}`; div.textContent=String(item.text||""); box.appendChild(div); }); box.scrollTop=box.scrollHeight;
    }
    const persist=()=>{ const rows=$$(".msg",box).filter(n=>!/checking…$/i.test(n.textContent||"")).slice(-40).map(n=>({type:n.classList.contains("user")?"user":"bot",text:n.textContent||""})); safeStorage.set(SESSION_KEY,JSON.stringify(rows)); };
    new MutationObserver(persist).observe(box,{childList:true,subtree:true,characterData:true});
  }
  function setupAIPage() {
    if (!document.body.classList.contains("ai-page")) return;
    const openPage = () => {
      moveFloatingChat(); restoreChatHistory();
      const fab=$("#chatFab"), panel=$("#chatPanel");
      if (!fab || !panel) return setTimeout(openPage,50);
      if (!panel.classList.contains("open")) fab.click();
      const close=$("#chatClose"); if(close){ close.title="Back to website"; close.setAttribute("aria-label","Back to website"); close.addEventListener("click",()=>{ if(history.length>1) history.back(); else location.href="/"; }); }
      $("#chatInput")?.focus();
    };
    setTimeout(openPage,80);
  }
  function applySettings(s) {
    window.SamugaWebsiteSettings = s;
    document.documentElement.dataset.samugaSettings = "16.1.0";
    applyBranding(s); applyHeader(s); applyFooter(s); applyAI(s); applyHomepage(s); applyContact(s); applySEO(s);
    applySocials(s); setTimeout(()=>applySocials(s),700); setTimeout(()=>applySocials(s),1700);
    if (!localStorage.getItem("samuga-theme") && ["light","dark"].includes(s.default_theme)) document.documentElement.dataset.theme=s.default_theme;
    moveFloatingChat(); restoreChatHistory(); setupAIPage();
    document.dispatchEvent(new CustomEvent("samuga:settingsloaded",{detail:{settings:s}}));
  }
  async function start() {
    moveFloatingChat(); restoreChatHistory(); setupAIPage();
    try { const response=await apiFetch("/api/site-settings"); const data=await response.json(); applySettings(flattenSettings(data?.settings||{})); }
    catch { document.documentElement.dataset.samugaSettings="fallback"; }
  }
  document.addEventListener("DOMContentLoaded", start);
})();
