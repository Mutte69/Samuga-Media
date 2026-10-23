/* Small browser counterpart of functions/_lib/article-links.js. No framework required. */
(() => {
  const valid = /^\/news\/[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{32}$/;
  globalThis.SamugaArticleLinks = Object.freeze({
    pathFor(article = {}) {
      if (valid.test(String(article.public_path || ""))) return article.public_path;
      return `/article?id=${encodeURIComponent(String(article.id || ""))}`;
    }
  });
})();
