"use strict";

(() => {
  const API = "https://samuga-news-bot-production.up.railway.app";
  const BUILD = "16.2.0-full-audit";
  const SOCIAL_KEYS = ["facebook", "instagram", "x", "telegram", "tiktok", "youtube", "whatsapp"];
  const CATEGORY_LABELS = {
    en: {
      all: "Latest News", BREAKING: "Breaking News", LOCAL: "Local", POLITICAL: "Politics",
      BUSINESS: "Business", WORLD: "World", SPORTS: "Sports", LIFESTYLE: "Lifestyle"
    },
    dv: {
      all: "އެންމެ ފަހުގެ ޚަބަރު", BREAKING: "ބްރޭކިންގ ނިއުސް", LOCAL: "ލޯކަލް",
      POLITICAL: "ސިޔާސީ", BUSINESS: "ވިޔަފާރި", WORLD: "ދުނިޔެ", SPORTS: "ކުޅިވަރު", LIFESTYLE: "ލައިފްސްޓައިލް"
    }
  };
  const SOCIAL_LABELS = {
    facebook: "Facebook", instagram: "Instagram", x: "X", telegram: "Telegram",
    tiktok: "TikTok", youtube: "YouTube", whatsapp: "WhatsApp"
  };
  const ICONS = {
    facebook: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13.7 22v-9h3l.5-3.5h-3.5V7.2c0-1 .3-1.7 1.8-1.7h1.9V2.4c-.3 0-1.5-.1-2.8-.1-2.8 0-4.7 1.7-4.7 4.8v2.4H6.8V13h3.1v9h3.8Z"/></svg>',
    instagram: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7.2 2h9.6A5.2 5.2 0 0 1 22 7.2v9.6a5.2 5.2 0 0 1-5.2 5.2H7.2A5.2 5.2 0 0 1 2 16.8V7.2A5.2 5.2 0 0 1 7.2 2Zm-.2 2A3 3 0 0 0 4 7v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V7a3 3 0 0 0-3-3H7Zm10.3 1.5a1.2 1.2 0 1 1 0 2.4 1.2 1.2 0 0 1 0-2.4ZM12 7a5 5 0 1 1 0 10 5 5 0 0 1 0-10Zm0 2a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/></svg>',
    x: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.6 2H22l-7.4 8.5L23.3 22h-6.8l-5.3-7-6.1 7H1.7l7.9-9.1L1.3 2h7l4.8 6.4L18.6 2Zm-1.2 18h1.9L7.3 3.9h-2L17.4 20Z"/></svg>',
    telegram: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21.7 3.3 18.6 21c-.2 1.2-.9 1.5-1.9.9L12 18.4l-2.3 2.2c-.3.3-.5.5-1 .5l.3-4.8 8.8-8c.4-.3-.1-.5-.6-.2L6.3 15 1.6 13.5c-1-.3-1-1 .2-1.5L20.2 3c.8-.3 1.6.2 1.5.3Z"/></svg>',
    tiktok: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.3 2h3.3c.2 1.4 1 2.6 2.1 3.4A6.7 6.7 0 0 0 23 6.6v3.3a9.8 9.8 0 0 1-5.4-1.6v7a6.4 6.4 0 1 1-6.4-6.4h.9v3.3a3.2 3.2 0 1 0 2.2 3.1V2Z"/></svg>',
    youtube: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.6 12 3.6 12 3.6s-7.5 0-9.4.5A3 3 0 0 0 .5 6.2 31 31 0 0 0 0 12a31 31 0 0 0 .5 5.8 3 3 0 0 0 2.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 0 0 2.1-2.1A31 31 0 0 0 24 12a31 31 0 0 0-.5-5.8ZM9.6 15.6V8.4l6.2 3.6-6.2 3.6Z"/></svg>',
    whatsapp: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 3.5A11.8 11.8 0 0 0 12.1 0C5.6 0 .3 5.3.3 11.8c0 2.1.5 4.1 1.6 5.9L.2 24l6.4-1.7a11.8 11.8 0 0 0 5.6 1.4h.1c6.5 0 11.7-5.3 11.7-11.8 0-3.2-1.2-6.1-3.5-8.4ZM12.2 21.7c-1.8 0-3.5-.5-5-1.4l-.4-.2-3.8 1 1-3.7-.2-.4a9.7 9.7 0 1 1 8.4 4.7Zm5.3-7.3c-.3-.1-1.7-.8-2-.9-.3-.1-.5-.1-.7.1-.2.3-.8 1-1 1.2-.2.2-.4.2-.7.1-1.9-.9-3.1-1.7-4.4-3.9-.3-.5.3-.5.9-1.6.1-.2.1-.4 0-.6l-.9-2.1c-.2-.5-.5-.5-.7-.5h-.6c-.2 0-.6.1-.9.4-.3.3-1.2 1.2-1.2 2.9 0 1.7 1.2 3.3 1.4 3.5.2.2 2.4 3.7 5.9 5.2.8.4 1.5.6 2 .7.8.3 1.6.2 2.2.1.7-.1 1.7-.7 1.9-1.4.2-.7.2-1.3.2-1.4-.1-.1-.3-.2-.6-.3Z"/></svg>'
  };

  let drawer;
  let overlay;
  let lastFocused = null;
  let socials = {telegram: "https://t.me/samugacommunity"};
  const storage = {
    get(key) { try { return window.localStorage?.getItem(key) ?? null; } catch { return null; } },
    set(key, value) { try { window.localStorage?.setItem(key, String(value)); return true; } catch { return false; } }
  };
  async function apiFetch(path, options = {}) {
    const attempts = [path, `${API}${path}`];
    let lastError = null;
    for (const url of attempts) {
      try {
        const response = await fetch(url, {...options});
        if (response.ok) return response;
        lastError = new Error(`HTTP ${response.status}`);
      } catch (error) { lastError = error; }
    }
    throw lastError || new Error("API unavailable");
  }
  

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const safeUrl = value => {
    const raw = String(value || "").trim();
    if (!raw) return "";
    try {
      const url = new URL(raw, location.origin);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch { return ""; }
  };
  const preferredLang = () => storage.get("samuga-lang") === "dv" ? "dv" : "en";

  function socialLinkMarkup(key, cssClass = "") {
    const url = safeUrl(socials[key]);
    const disabled = !url;
    return `<a class="v3-social-link ${cssClass}" data-social-key="${key}" href="${disabled ? "#" : url}" ${disabled ? 'data-unconfigured="true" role="button"' : 'target="_blank" rel="noopener"'} aria-label="${SOCIAL_LABELS[key]}" title="${disabled ? `${SOCIAL_LABELS[key]} link is not configured yet` : SOCIAL_LABELS[key]}">${ICONS[key]}</a>`;
  }

  function drawerMarkup() {
    const lang = preferredLang();
    const labels = CATEGORY_LABELS[lang];
    const categories = ["all", "BREAKING", "LOCAL", "POLITICAL", "BUSINESS", "WORLD", "SPORTS", "LIFESTYLE"];
    return `
      <div class="v3-drawer-overlay" id="v3DrawerOverlay" aria-hidden="true"></div>
      <aside class="v3-drawer" id="v3Drawer" role="dialog" aria-modal="true" aria-label="Samuga Media menu" aria-hidden="true" tabindex="-1">
        <div class="v3-drawer-top">
          <a class="v3-drawer-logo" href="/" aria-label="Samuga Media home"><img src="/assets/Samuga_Media_Logo_White.png" alt="Samuga Media"></a>
          <button class="v3-drawer-close" id="v3DrawerClose" type="button" aria-label="Close menu">×</button>
        </div>
        <button class="v3-ai-drawer-btn" id="v3AskAi" type="button" aria-controls="chatPanel"><span aria-hidden="true">✦</span><span data-v3-ai-label>Ask Samuga AI</span></button>
        <section class="v3-drawer-section" aria-labelledby="v3FollowHeading">
          <h2 class="v3-drawer-heading" id="v3FollowHeading">Follow Samuga</h2>
          <div class="v3-social-row" data-v3-socials>${SOCIAL_KEYS.map(key => socialLinkMarkup(key)).join("")}</div><p class="v3-social-status" role="status" aria-live="polite"></p>
        </section>
        <nav class="v3-drawer-section" aria-labelledby="v3CategoriesHeading">
          <h2 class="v3-drawer-heading" id="v3CategoriesHeading">Categories</h2>
          <div class="v3-category-list">${categories.map(cat => `<button class="v3-category-btn" type="button" data-v3-category="${cat}">${labels[cat]}</button>`).join("")}</div>
        </nav>
        <section class="v3-drawer-section" aria-labelledby="v3NewsletterHeading">
          <h2 class="v3-drawer-heading" id="v3NewsletterHeading">Stay updated</h2>
          <p class="v3-newsletter-copy">Get every new Samuga story in your inbox. Free, with one-click unsubscribe.</p>
          <form class="v3-newsletter-form" data-newsletter-form novalidate>
            <label class="sr-only" for="v3NewsletterEmail">Email address</label>
            <input id="v3NewsletterEmail" name="email" type="email" autocomplete="email" inputmode="email" maxlength="254" placeholder="Enter your email" required>
            <input name="company" type="text" tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px;width:1px;height:1px;opacity:0">
            <label class="v3-newsletter-consent"><input name="terms" type="checkbox" required><span>I agree to the <a href="/terms.html">Terms</a> and <a href="/privacy-policy.html">Privacy Policy</a>.</span></label>
            <button class="v3-newsletter-submit" type="submit">Subscribe free</button>
            <p class="v3-newsletter-status" role="status" aria-live="polite"></p>
          </form>
        </section>
        <nav class="v3-drawer-section v3-drawer-links" aria-label="Samuga information">
          <a href="/about.html">About Samuga</a><a href="/advertising.html">Advertise with us</a>
          <a href="/contact.html">Contact</a><a href="/editorial-policy.html">Editorial policy</a>
          <a href="/privacy-policy.html">Privacy</a><a href="/terms.html">Terms</a>
        </nav>
        <p class="v3-drawer-signoff">Maldives, as it happens.</p>
      </aside>`;
  }

  function addDrawer() {
    if (q("#v3Drawer")) return;
    document.body.insertAdjacentHTML("beforeend", drawerMarkup());
    drawer = q("#v3Drawer");
    overlay = q("#v3DrawerOverlay");
    bindDrawer();
    bindCategories();
    bindNewsletterForms();
    q("#v3AskAi")?.addEventListener("click", event => {
      event.preventDefault();
      closeDrawer();
      window.setTimeout(() => window.SamugaChat?.open?.(), 170);
    });
  }

  function backgroundChildren() {
    return qa("body > *").filter(node => !node.matches("#v3Drawer,#v3DrawerOverlay,.chat-panel,.chat-fab"));
  }

  function openDrawer(trigger) {
    if (!drawer) return;
    lastFocused = trigger || document.activeElement;
    drawer.scrollTop = 0;
    document.body.classList.add("v3-drawer-open");
    drawer.setAttribute("aria-hidden", "false");
    overlay?.setAttribute("aria-hidden", "false");
    qa("[data-drawer-toggle],#menuBtn").forEach(button => button.setAttribute("aria-expanded", "true"));
    backgroundChildren().forEach(node => { try { node.inert = true; } catch {} });
    window.setTimeout(() => q("#v3DrawerClose")?.focus(), 20);
  }

  function closeDrawer() {
    if (!drawer || !document.body.classList.contains("v3-drawer-open")) return;
    document.body.classList.remove("v3-drawer-open");
    drawer.setAttribute("aria-hidden", "true");
    overlay?.setAttribute("aria-hidden", "true");
    qa("[data-drawer-toggle],#menuBtn").forEach(button => button.setAttribute("aria-expanded", "false"));
    backgroundChildren().forEach(node => { try { node.inert = false; } catch {} });
    const target = lastFocused;
    lastFocused = null;
    target?.focus?.();
  }

  function bindDrawer() {
    qa("[data-drawer-toggle],#menuBtn").forEach(button => {
      if (button.dataset.v3DrawerBound) return;
      button.dataset.v3DrawerBound = "true";
      button.addEventListener("click", event => {
        event.preventDefault();
        document.body.classList.contains("v3-drawer-open") ? closeDrawer() : openDrawer(button);
      });
    });
    q("#v3DrawerClose")?.addEventListener("click", closeDrawer);
    overlay?.addEventListener("click", closeDrawer);
    drawer?.addEventListener("click", event => {
      const link = event.target.closest("a[href]");
      if (!link) return;
      if (link.dataset.unconfigured === "true") {
        event.preventDefault();
        const status = q(".v3-social-status", drawer);
        if (status) {
          status.textContent = `${link.getAttribute("aria-label") || "Social"} link is being connected.`;
          window.setTimeout(() => { status.textContent = ""; }, 2200);
        }
        return;
      }
      closeDrawer();
    });
    document.addEventListener("keydown", event => {
      if (!document.body.classList.contains("v3-drawer-open")) return;
      if (event.key === "Escape") { event.preventDefault(); closeDrawer(); return; }
      if (event.key !== "Tab") return;
      const focusable = qa('a[href]:not([aria-disabled="true"]),button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])', drawer).filter(el => !el.hidden && el.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
  }

  function bindCategories() {
    qa("[data-v3-category]").forEach(button => button.addEventListener("click", () => {
      const category = button.dataset.v3Category || "all";
      const homepageButton = qa(".nav-btn[data-cat]").find(item => item.dataset.cat === category) || null;
      if (homepageButton) {
        homepageButton.click();
        setActiveCategory(category);
        closeDrawer();
        q("#latest")?.scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start"});
      } else {
        location.href = category === "all" ? "/#latest" : `/?cat=${encodeURIComponent(category)}#latest`;
      }
    }));
  }

  function setActiveCategory(category) {
    qa("[data-v3-category]").forEach(button => button.classList.toggle("active", button.dataset.v3Category === category));
  }

  function updateLanguage(lang = preferredLang()) {
    const labels = CATEGORY_LABELS[lang] || CATEGORY_LABELS.en;
    qa("[data-v3-category]").forEach(button => { button.textContent = labels[button.dataset.v3Category] || button.dataset.v3Category; });
    const aiLabel = q("[data-v3-ai-label]");
    if (aiLabel) aiLabel.textContent = lang === "dv" ? "ސަމުގާ AI އަށް އަހާ" : "Ask Samuga AI";
    const drawerEl = q("#v3Drawer");
    if (drawerEl) { drawerEl.dir = "ltr"; drawerEl.classList.toggle("is-dv", lang === "dv"); }
  }

  async function loadSocials() {
    const merged = {...socials};
    try {
      const response = await fetch("/site-social-links.json", {cache: "no-store"});
      if (response.ok) Object.assign(merged, await response.json());
    } catch {}
    try {
      window.__samugaSiteSettingsFetch = window.__samugaSiteSettingsFetch || (function(){
        let p = null;
        return function(){
          if (!p) p = (async () => {
            try { const r = await apiFetch("/api/site-settings", {cache: "no-store"}); if (!r.ok) return null; return await r.json(); }
            catch { return null; }
          })();
          return p;
        };
      })();
      const data = await window.__samugaSiteSettingsFetch();
      if (data) {
        const settings = data?.settings || {};
        const mapping = {
          facebook: settings.facebook_url,
          instagram: settings.instagram_url,
          x: settings.x_url || settings.twitter_url,
          telegram: settings.community_url || settings.telegram_url,
          tiktok: settings.tiktok_url,
          youtube: settings.youtube_url,
          whatsapp: settings.whatsapp_url || settings.whatsapp_channel_url
        };
        Object.entries(mapping).forEach(([key, value]) => { if (safeUrl(value)) merged[key] = value; });
      }
    } catch {}
    socials = merged;
    hydrateSocialLinks();
  }

  function hydrateFooterSocialContainers() {
    qa("[data-v3-footer-socials]").forEach(container => {
      if (!container.children.length) container.innerHTML = SOCIAL_KEYS.map(key => socialLinkMarkup(key, "v3-footer-social-link")).join("");
    });
  }

  function hydrateSocialLinks() {
    hydrateFooterSocialContainers();
    qa("[data-social-key]").forEach(link => {
      const key = link.dataset.socialKey;
      const url = safeUrl(socials[key]);
      if (url) {
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener";
        link.removeAttribute("aria-disabled");
        link.removeAttribute("data-unconfigured");
        link.removeAttribute("role");
        link.removeAttribute("tabindex");
        link.title = SOCIAL_LABELS[key];
      } else {
        link.href = "#";
        link.dataset.unconfigured = "true";
        link.setAttribute("role", "button");
        link.removeAttribute("aria-disabled");
        link.removeAttribute("tabindex");
        link.removeAttribute("target");
        link.removeAttribute("rel");
        link.title = `${SOCIAL_LABELS[key]} link is not configured yet`;
      }
    });
  }

  function bindNewsletterForms() {
    qa("[data-newsletter-form]").forEach(form => {
      if (form.dataset.newsletterBound) return;
      form.dataset.newsletterBound = "true";
      form.addEventListener("submit", async event => {
        event.preventDefault();
        const email = String(form.email?.value || "").trim();
        const terms = Boolean(form.terms?.checked);
        const company = String(form.company?.value || "").trim();
        const status = q(".v3-newsletter-status", form);
        const submit = q(".v3-newsletter-submit", form);
        status?.classList.remove("is-error");
        if (!email || !/^\S+@\S+\.\S+$/.test(email)) return showNewsletterStatus(status, "Enter a valid email address.", true);
        if (!terms) return showNewsletterStatus(status, "Please agree to the Terms and Privacy Policy.", true);
        submit.disabled = true;
        showNewsletterStatus(status, "Subscribing…", false);
        try {
          const response = await fetch("/api/newsletter/subscribe", {
            method: "POST",
            headers: {"Content-Type": "application/json", "Accept": "application/json"},
            body: JSON.stringify({email, terms, company, referrer: location.href, language: preferredLang()})
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok || !data.ok) throw new Error(data.message || "Subscription is temporarily unavailable.");
          form.reset();
          showNewsletterStatus(status, data.duplicate ? "You are already on the list." : "Check your inbox to confirm your subscription.", false);
        } catch (error) {
          showNewsletterStatus(status, error.message || "Subscription is temporarily unavailable.", true);
        } finally { submit.disabled = false; }
      });
    });
  }

  function showNewsletterStatus(node, message, isError) {
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("is-error", Boolean(isError));
  }

  function ensureChat() {
    if (document.body.dataset.floatingAi === "disabled") return;
    if (q("#chatFab") && q("#chatPanel")) { bindGenericChat(); return; }
    document.body.insertAdjacentHTML("beforeend", `
      <button class="chat-fab" id="chatFab" type="button" aria-label="Ask Samuga AI" aria-expanded="false" aria-controls="chatPanel">
        <span class="chat-fab-logo-wrap"><img class="chat-fab-logo" src="/assets/SamugaNewsBot_Profile.png" alt=""><span class="chat-status-dot" aria-hidden="true"></span></span>
        <span class="chat-fab-label">Ask Samuga AI</span>
      </button>
      <section class="chat-panel" id="chatPanel" dir="ltr" role="dialog" aria-label="Samuga AI" aria-modal="true" aria-hidden="true">
        <header><div class="chat-identity"><img class="chat-header-logo" src="/assets/SamugaNewsBot_Profile.png" alt="Samuga AI"><div><strong>Samuga AI</strong><span>Maldives news assistant</span></div></div><button id="chatClose" type="button" aria-label="Close">×</button></header>
        <div class="chat-messages" id="chatMessages" role="log"><div class="msg bot">Ask me about a story on Samuga Media.</div></div>
        <form id="chatForm" dir="ltr"><textarea id="chatInput" rows="1" placeholder="Ask about the news…" aria-label="Message"></textarea><button id="chatSend" type="submit">Send</button></form>
      </section>`);
    bindGenericChat();
  }

  function bindGenericChat() {
    const fab = q("#chatFab"), panel = q("#chatPanel"), close = q("#chatClose"), form = q("#chatForm"), input = q("#chatInput"), send = q("#chatSend"), messages = q("#chatMessages");
    if (!fab || !panel || !form || !input || !messages) return;
    if (fab.dataset.chatBound === "true") return;
    fab.dataset.chatBound = "true";
    panel.hidden = true;
    panel.classList.remove("open", "closing");
    panel.setAttribute("aria-hidden", "true");
    const mobile = () => matchMedia("(max-width:760px)").matches;
    const clearViewportStyles = () => ["left","right","top","bottom","width","height","max-height"].forEach(name => panel.style.removeProperty(name));
    const fitKeyboard = () => {
      if (!panel.classList.contains("open") || !mobile()) return;
      const vv = window.visualViewport;
      if (!vv) return;
      const keyboardOpen = vv.height < window.innerHeight * .79;
      if (!keyboardOpen) { clearViewportStyles(); return; }
      const gap = 8;
      panel.style.left = `${Math.round(vv.offsetLeft + gap)}px`;
      panel.style.right = "auto";
      panel.style.top = `${Math.round(vv.offsetTop + gap)}px`;
      panel.style.bottom = "auto";
      panel.style.width = `${Math.max(280, Math.round(vv.width - gap * 2))}px`;
      panel.style.height = `${Math.max(280, Math.round(vv.height - gap * 2))}px`;
      panel.style.maxHeight = `${Math.max(280, Math.round(vv.height - gap * 2))}px`;
      requestAnimationFrame(() => { messages.scrollTop = messages.scrollHeight; });
    };
    let closeTimer = 0;
    const open = () => {
      clearTimeout(closeTimer);
      panel.hidden = false;
      panel.classList.remove("closing");
      requestAnimationFrame(() => requestAnimationFrame(() => {
        panel.classList.add("open");
        panel.setAttribute("aria-hidden", "false");
        fab.setAttribute("aria-expanded", "true");
        document.body.classList.add("chat-open");
        fitKeyboard();
        if (!mobile()) input.focus({preventScroll:true});
      }));
    };
    const hide = () => {
      if (panel.hidden) return;
      panel.classList.remove("open");
      panel.classList.add("closing");
      panel.setAttribute("aria-hidden", "true");
      fab.setAttribute("aria-expanded", "false");
      document.body.classList.remove("chat-open");
      input.blur();
      clearViewportStyles();
      closeTimer = window.setTimeout(() => { panel.hidden = true; panel.classList.remove("closing"); }, 250);
    };
    const toggle = () => panel.classList.contains("open") ? hide() : open();
    window.SamugaChat = {open, close:hide, toggle};
    fab.addEventListener("click", toggle);
    close?.addEventListener("click", hide);
    document.addEventListener("keydown", event => { if (event.key === "Escape" && panel.classList.contains("open")) hide(); });
    window.visualViewport?.addEventListener("resize", fitKeyboard);
    window.visualViewport?.addEventListener("scroll", fitKeyboard);
    window.addEventListener("orientationchange", () => window.setTimeout(fitKeyboard, 160));
    input.addEventListener("focus", () => window.setTimeout(fitKeyboard, 120));
    input.addEventListener("blur", () => window.setTimeout(fitKeyboard, 120));
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const message = input.value.trim();
      if (!message || send.disabled) return;
      addChatMessage(messages, message, "user");
      input.value = "";
      send.disabled = true;
      const wait = addChatMessage(messages, "Samuga AI is checking…", "bot");
      try {
        const response = await apiFetch("/api/chat", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message, lang:preferredLang(), surface:"floating"})});
        const data = await response.json();
        wait.remove();
        addChatMessage(messages, data.reply || "I could not find an answer right now.", "bot");
      } catch {
        wait.remove();
        addChatMessage(messages, "Connection issue. Please try again.", "bot");
      } finally {
        send.disabled = false;
        fitKeyboard();
        if (!mobile()) input.focus({preventScroll:true});
      }
    });
  }

  function addChatMessage(container, text, type) {
    const node = document.createElement("div"); node.className = `msg ${type}`; node.textContent = text; container.appendChild(node); container.scrollTop = container.scrollHeight; return node;
  }

  function bindStandaloneLanguageButtons() {
    qa(".lang-btn").forEach(button => {
      if (button.dataset.v3LangBound) return;
      button.dataset.v3LangBound = "true";
      button.addEventListener("click", () => {
        const lang = button.dataset.lang === "dv" ? "dv" : "en";
        storage.set("samuga-lang", lang);
        qa(".lang-btn").forEach(item => {
          const active = item.dataset.lang === lang;
          item.classList.toggle("active", active);
          item.setAttribute("aria-pressed", String(active));
        });
        updateLanguage(lang);
      });
    });
  }

  function markBuild() {
    document.documentElement.dataset.samugaPublicShell = BUILD;
  }

  document.addEventListener("DOMContentLoaded", () => {
    try { markBuild(); addDrawer(); bindStandaloneLanguageButtons(); ensureChat(); updateLanguage(); }
    catch (error) { console.error("[SAMUGA V3] shell startup failed", error); }
    loadSocials().catch(() => {});
    hydrateFooterSocialContainers();
    const footerObserver = new MutationObserver(() => { hydrateFooterSocialContainers(); hydrateSocialLinks(); });
    footerObserver.observe(document.body, {childList: true, subtree: true});
    const initialCat = new URLSearchParams(location.search).get("cat") || "all";
    setActiveCategory(initialCat);
    document.addEventListener("samuga:languagechange", event => updateLanguage(event.detail?.lang || preferredLang()));
    document.addEventListener("samuga:categorychange", event => setActiveCategory(event.detail?.category || "all"));
  });

  window.SamugaV3 = {openDrawer, closeDrawer, updateLanguage, setActiveCategory};
})();
