#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = Path('/mnt/data/samuga_media_source/Samuga-Media-main')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def text(name: str) -> str:
    return (ROOT / name).read_text(encoding='utf-8')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def node_check(path: Path) -> None:
    subprocess.run(['node', '--check', str(path)], check=True, capture_output=True, text=True)


# 1. Active public files reference the hotfix assets with cache-busting.
index = text('index.html')
require('site-build16-0-1.js?v=16.0.1' in index, 'homepage does not load the 16.0.1 script')
require('site-v3-16-0-1.css?v=16.0.1' in index, 'homepage does not load the 16.0.1 CSS')
require('samuga-v3-shell-16-0-1.js?v=16.0.1' in index, 'homepage does not load the 16.0.1 shell')

# 2. Storage guard is declared before first use. This was the real mobile skeleton blocker.
home_js = text('site-build16-0-1.js')
require(home_js.index('const safeStorage=') < home_js.index('activeLang=safeStorage.get'), 'safeStorage is used before initialization')
require('Promise.allSettled([loadStories(),loadBanner(),loadSiteSettings()])' in home_js, 'independent startup tasks are not isolated')
require('const attempts=[path,`${API}${path}`]' in home_js, 'same-origin API with Railway fallback is missing')
require('if((i+1)%3===0&&ads.length)' in home_js, 'advertisement-after-three rule changed')
require('document.documentElement.dir="ltr"' in home_js, 'global shell direction can still flip to RTL')
require('panelHeight=keyboardOpen' in home_js and 'Math.round(viewportHeight*0.68)' in home_js, 'compact mobile AI sizing is missing')

# 3. Drawer stays physically left-to-right while its Dhivehi content aligns right.
shell_js = text('samuga-v3-shell-16-0-1.js')
css = text('site-v3-16-0-1.css')
require('drawer.scrollTop = 0;' in shell_js, 'drawer does not reset to the top on open')
require('drawerEl.dir = "ltr"' in shell_js, 'Dhivehi can reverse the drawer geometry')
require('drawerEl.classList.toggle("is-dv"' in shell_js, 'Dhivehi drawer content mode missing')
require('data-unconfigured="true" role="button"' in shell_js, 'unconfigured social icons are still dead controls')
require('.v3-drawer.is-dv .v3-category-btn' in css, 'Dhivehi drawer alignment rules missing')
require('height:100dvh' in css and 'overflow-y:auto' in css, 'mobile drawer cannot reliably show its complete contents')
require('position:sticky' in css and '.v3-drawer-top' in css, 'drawer top controls are not kept visible')

# 4. Same-origin proxy functions exist for mobile/in-app browsers, with direct fallback in clients.
for rel in ['functions/api/stories.js', 'functions/api/site-settings.js', 'functions/api/ads.js',
            'functions/api/banner.js', 'functions/api/article.js', 'functions/api/chat.js']:
    require((ROOT / rel).is_file(), f'missing API proxy: {rel}')

# 5. Ask Samuga AI and existing preview structure remain present.
require('id="chatFab"' in index and 'id="chatPanel"' in index, 'Ask Samuga AI was removed')
for token in ['story-card', 'card-kicker', 'card-title', 'card-summary', 'author-chip']:
    require(token in home_js, f'existing article preview token missing: {token}')

# 6. Every active JavaScript file parses.
active_js = [
    'site-build16-0-1.js', 'samuga-v3-shell-16-0-1.js', 'site-common-build16-0-1.js',
    'article-build16-0-1.js', 'functions/article.js', 'functions/story.js', 'functions/feed.xml.js',
    'functions/api/stories.js', 'functions/api/site-settings.js', 'functions/api/ads.js',
    'functions/api/banner.js', 'functions/api/article.js', 'functions/api/chat.js',
    'functions/api/newsletter/subscribe.js',
]
for rel in active_js:
    node_check(ROOT / rel)

# 7. Evaluate the two primary scripts with localStorage actively throwing.
#    The test intentionally does not dispatch DOMContentLoaded; it proves scripts can load safely.
vm_test = r'''
const fs=require('fs'),vm=require('vm');
const listeners={};
const document={
  addEventListener:(n,cb)=>{listeners[n]=cb},
  querySelector:()=>null,
  querySelectorAll:()=>[],
  documentElement:{dataset:{theme:'dark'},lang:'en',dir:'ltr'},
  body:{classList:{toggle(){},add(){},remove(){},contains(){return false}},insertAdjacentHTML(){}},
};
const throwingStorage={getItem(){throw new Error('blocked')},setItem(){throw new Error('blocked')}};
const window={localStorage:throwingStorage,addEventListener(){},matchMedia:()=>({matches:false,addEventListener(){}})};
const context={console,document,window,location:{origin:'https://samugamedia.com',search:'',href:'https://samugamedia.com/'},
  URL,URLSearchParams,CustomEvent:function(){},fetch:async()=>({ok:false,status:404}),setInterval(){},setTimeout(){},clearTimeout(){},
  requestAnimationFrame(){},MutationObserver:function(){this.observe=()=>{}},matchMedia:window.matchMedia};
context.globalThis=context;vm.createContext(context);
for(const name of ['site-build16-0-1.js','samuga-v3-shell-16-0-1.js']){
  vm.runInContext(fs.readFileSync(name,'utf8'),context,{filename:name});
}
console.log('storage-blocked-load-ok');
'''
result = subprocess.run(['node', '-e', vm_test], cwd=ROOT, check=True, capture_output=True, text=True)
require('storage-blocked-load-ok' in result.stdout, 'scripts fail when storage is blocked')

# 8. Admin/dashboard files must remain byte-for-byte identical to the uploaded baseline.
if SOURCE.is_dir():
    admin_files = [p.relative_to(SOURCE) for p in SOURCE.glob('admin*') if p.is_file()]
    for rel in admin_files:
        current = ROOT / rel
        require(current.is_file(), f'admin file missing: {rel}')
        require(sha(SOURCE / rel) == sha(current), f'admin file changed unexpectedly: {rel}')

# 9. No packaged environment secrets.
for path in ROOT.rglob('*'):
    if path.is_file():
        require(path.name not in {'.env', '.env.local', '.env.production'}, f'secret file packaged: {path}')

print(json.dumps({
    'ok': True,
    'build': '16.0.1',
    'checks': 9,
    'active_js_syntax': len(active_js),
    'admin_unchanged': SOURCE.is_dir(),
}, indent=2))
