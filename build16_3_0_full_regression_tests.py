from pathlib import Path
import re, subprocess, sys, zipfile
ROOT=Path(__file__).resolve().parent
checks=[]
def ok(name,cond):
    checks.append((name,bool(cond)))
    if not cond: print('FAIL:',name)

def text(name): return (ROOT/name).read_text(encoding='utf-8')
active=['site-build16-2-1.css','site-v3-16-2-1.css','site-build16-2-1.js','samuga-v3-shell-16-2-1.js','website-settings-runtime-16-2-1.js','website-settings-runtime-16-2-1.css']
for f in active: ok(f'{f} exists',(ROOT/f).is_file())
index=text('index.html'); shell=text('samuga-v3-shell-16-2-1.js'); site=text('site-build16-2-1.js'); base=text('site-build16-2-1.css'); v3=text('site-v3-16-2-1.css'); runtime=text('website-settings-runtime-16-2-1.css'); settings=text('website-settings-runtime-16-2-1.js')
ok('index build marker','data-samuga-build="16.2.1"' in index)
ok('index uses new site JS','site-build16-2-1.js?v=16.2.1' in index)
ok('index uses new shell','samuga-v3-shell-16-2-1.js?v=16.2.1' in index)
ok('index uses new settings runtime','website-settings-runtime-16-2-1.js?v=16.2.1' in index)
ok('standalone AI page removed',not (ROOT/'ask-samuga-ai.html').exists())
ok('no active standalone AI href','href="/ask-samuga-ai' not in shell and 'href="/ask-samuga-ai' not in index)
ok('sidebar AI is a button','<button class="v3-ai-drawer-btn" id="v3AskAi"' in shell)
ok('sidebar opens shared controller','window.SamugaChat?.open?.()' in shell)
ok('shared controller exported','window.SamugaChat = {open, close:hide, toggle}' in shell)
ok('site duplicate chat binder disabled','Shared chat is bound once' in site)
ok('mobile keyboard-aware chat','window.visualViewport' in shell and 'fitKeyboard' in shell)
ok('chat panel animates','body>.chat-panel.open' in runtime and 'transition:opacity .2s ease' in runtime)
ok('mobile chat is compact sheet','height:min(560px,72dvh)' in runtime and 'bottom:calc(72px + env(safe-area-inset-bottom))' in runtime)
ok('body animation no retained transform','samuga-page-enter .28s cubic-bezier(.2,.75,.2,1) both' not in base and '@keyframes samuga-page-enter{from{opacity:0}to{opacity:1}}' in base)
ok('root horizontal clipping does not create sticky scroller','html,body{max-width:100%;overflow-x:clip}' in v3)
ok('article body clipping does not create sticky scroller','body.article-page-body{direction:ltr!important;text-align:left;overflow-x:clip}' in base)
ok('sticky header blue fallback','--settings-header-bg:#29b8fe' in runtime and 'background:var(--settings-header-bg,#29b8fe)!important' in runtime)
ok('featured media fills frame','#featuredMedia{' in base and 'position:absolute' in base and '#featuredMedia>img' in base)
ok('featured media fixed aspect ratio','aspect-ratio:16 / 10' in base)
ok('mobile hero is block layout','@media(max-width:760px)' in base and '.lead-story{display:block;width:100%;min-width:0}' in base)
ok('mobile title capped','font-size:clamp(27px,7.3vw,33px)' in base)
ok('headline no arbitrary word breaking','overflow-wrap:normal' in base and 'word-break:normal' in base)
ok('runtime does not use ai-page','.ai-page' not in runtime and 'isDedicatedAIPage' not in settings)
ok('AI defaults visible on legacy settings','s.ai_enabled === undefined' in settings)
ok('hero settings remain respected','dataset.settingsHidden' in settings and 'dataset.settingsHidden' in site)
ok('cache headers include active site CSS','/site-build16-2-1.css' in text('_headers'))
ok('cache headers include active shell JS','/samuga-v3-shell-16-2-1.js' in text('_headers'))
ok('redirects describe overlay','there is no standalone AI page' in text('_redirects'))
ok('version file updated',text('VERSION.txt').strip()=='16.3.2')
# all build-numbered local references from public HTML exist
for html in ROOT.glob('*.html'):
    if html.name=='admin.html': continue
    content=html.read_text(encoding='utf-8')
    refs=re.findall(r'(?:src|href)=["\']([^"\']+)["\']',content)
    for ref in refs:
        clean=ref.split('?',1)[0].split('#',1)[0]
        if not clean or clean.startswith(('http:','https:','mailto:','tel:','data:')): continue
        if clean in {'/','.'}: continue
        target=ROOT/clean.lstrip('/')
        if clean.startswith('/article'): continue
        ok(f'{html.name} ref {clean} exists',target.exists())
# JS syntax
for f in ['site-build16-2-1.js','samuga-v3-shell-16-2-1.js','website-settings-runtime-16-2-1.js']:
    result=subprocess.run(['node','--check',str(ROOT/f)],capture_output=True,text=True)
    ok(f'{f} syntax',result.returncode==0)
passed=sum(v for _,v in checks); total=len(checks)
print(f'Build 16.3 regression: {passed}/{total} checks passed')
if passed!=total: sys.exit(1)
