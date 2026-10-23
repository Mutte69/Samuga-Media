export const PUBLIC_PATH = /^\/news\/[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{32}$/;
export function articlePath(article = {}) {
  if (PUBLIC_PATH.test(String(article.public_path || ""))) return article.public_path;
  return `/article?id=${encodeURIComponent(String(article.id || ""))}`;
}
