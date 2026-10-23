// Offline browser adapter for the real Pages handlers. Synthetic stories only.
// No AI, database writes or publication. Bind localhost, not a public interface.
import http from "node:http";
import {readFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import path from "node:path";
import {createHash} from "node:crypto";
import {onRequest as articleRoute} from "./functions/article.js";

const root=fileURLToPath(new URL(".",import.meta.url)), port=4187;
const origin=`http://127.0.0.1:${port}`;
const stories=["WORLD","POLITICAL","LOCAL","SPORTS"].map((category,i)=>{
  const id=`argus:offline-design-fixture-${i}`, key=createHash("md5").update(id).digest("hex");
  return {id,title:`Samuga ${category.toLowerCase()} link preview`,summary:"Synthetic local engineering fixture. This is not a published news story.",
    body:"This synthetic story verifies the new public URL and article rendering.\n\nThe source-provider identity remains separate from the public link.",
    public_path:`/news/samuga-${category.toLowerCase()}-link-preview-${key}`,category,lang:"en",
    cover_image:"/assets/maldives-scenic/island-harbour.jpg",published_at:"2026-10-23T14:00:00Z",related:[]};
});
globalThis.fetch=async address=>{
  const url=new URL(String(address));
  if(url.pathname==="/api/site-settings") return Response.json({settings:{}});
  if(url.pathname==="/api/article"){
    const article=stories.find(item=>item.id===url.searchParams.get("id") || item.public_path.endsWith(url.searchParams.get("public_key")||"!"));
    return Response.json(article||{error:"not found"},{status:article?200:404});
  }
  throw new Error("Unexpected preview upstream: "+url.pathname);
};
const types={".html":"text/html",".js":"text/javascript",".css":"text/css",".png":"image/png",".jpg":"image/jpeg",".webp":"image/webp",".svg":"image/svg+xml",".ttf":"font/ttf"};
http.createServer(async(req,res)=>{
  const url=new URL(req.url,origin);
  try{
    console.log(req.method,url.pathname);
    if(url.pathname.startsWith("/news/") || ["/article","/story"].includes(url.pathname)){
      const response=await articleRoute({request:new Request(url),env:{},params:url.pathname.startsWith("/news/")?{slug:url.pathname.slice(6)}:{}});
      const headers=Object.fromEntries(response.headers);
      if(headers.location)headers.location=headers.location.replace("https://samugamedia.com",origin);
      res.writeHead(response.status,headers);res.end(Buffer.from(await response.arrayBuffer()));return;
    }
    if(url.pathname.startsWith("/api/")){
      const data=url.pathname==="/api/stories"?stories:url.pathname==="/api/site-settings"?{settings:{}}:{};
      res.writeHead(200,{"content-type":"application/json"});res.end(JSON.stringify(data));return;
    }
    const file=path.resolve(root,"."+(url.pathname==="/"?"/index.html":decodeURIComponent(url.pathname)));
    const type=types[path.extname(file)];
    if(!file.startsWith(root)||!type){res.writeHead(404);res.end();return;}
    const data=await readFile(file);res.writeHead(200,{"content-type":type});res.end(data);
  }catch(error){console.error(error.message);res.writeHead(404);res.end("Local fixture unavailable");}
}).listen(port,"127.0.0.1",()=>{
  console.log(`Offline link preview: ${origin}`);
  console.log(`Legacy redirect test: ${origin}/article?id=${encodeURIComponent(stories[0].id)}`);
});
