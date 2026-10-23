/* Small browser counterpart of functions/_lib/article-links.js. No framework required. */
(() => {
  const legacy=/^\/news\/[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{32}$/;
  const shortPath=key=>"/n/"+btoa(String.fromCharCode(...key.match(/../g).map(x=>parseInt(x,16)))).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
  const keyFromPath=value=>{
    const path=String(value||"");
    if(legacy.test(path))return path.slice(-32);
    if(!/^\/n\/[A-Za-z0-9_-]{22}$/.test(path))return "";
    try{const key=[...atob(path.slice(3).replace(/-/g,"+").replace(/_/g,"/")+"==")].map(x=>x.charCodeAt(0).toString(16).padStart(2,"0")).join("");return shortPath(key)===path?key:""}catch{return ""}
  };
  globalThis.SamugaArticleLinks = Object.freeze({
    pathFor(article = {}) {
      const key=keyFromPath(article.public_path);
      if(key)return shortPath(key);
      return `/article?id=${encodeURIComponent(String(article.id || ""))}`;
    }
  });
})();
