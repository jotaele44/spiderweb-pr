import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const base="http://127.0.0.1:4173";
const out=process.env.RENDER_OUT||"rendered";
fs.mkdirSync(out,{recursive:true});
const cases=[
  {name:"desktop-1440x900",width:1440,height:900},
  {name:"iphone-393x852",width:393,height:852},
  {name:"iphone-430x932",width:430,height:932},
];
const browser=await chromium.launch({headless:true});
const results=[];
try{
 for(const c of cases){
  const context=await browser.newContext({viewport:{width:c.width,height:c.height},deviceScaleFactor:1});
  const page=await context.newPage();
  const consoleErrors=[];
  page.on("console",msg=>{if(msg.type()==="error")consoleErrors.push(msg.text())});
  page.on("pageerror",err=>consoleErrors.push(String(err)));
  await page.route("**/_api/**",route=>route.fulfill({status:401,contentType:"application/json",body:JSON.stringify({error:"UNAUTHENTICATED_RENDER_QA"})}));
  const response=await page.goto(base+"/spatial-analysis",{waitUntil:"networkidle",timeout:30000});
  await page.getByText("Spatial analysis workbench").waitFor({state:"visible",timeout:15000});
  await page.getByText("Dataset intake & preflight").waitFor({state:"visible",timeout:15000});
  await page.getByLabel("File upload").waitFor({state:"visible"});
  await page.getByLabel("Analysis preset").waitFor({state:"visible"});
  const metrics=await page.evaluate(()=>({
    innerWidth:window.innerWidth,
    documentScrollWidth:document.documentElement.scrollWidth,
    bodyScrollWidth:document.body.scrollWidth,
    hasHorizontalOverflow:document.documentElement.scrollWidth>window.innerWidth+1||document.body.scrollWidth>window.innerWidth+1,
    heading:document.querySelector("h1")?.textContent??null,
    backLink:(Array.from(document.querySelectorAll("a")).find(a=>a.textContent?.includes("Back to map renderer"))?.textContent??null),
  }));
  const screenshot=path.join(out,c.name+".png");
  await page.screenshot({path:screenshot,fullPage:true});
  results.push({viewport:c,status:response?.status()??null,metrics,consoleErrors,screenshot});
  if(metrics.hasHorizontalOverflow)throw new Error(c.name+": horizontal overflow "+metrics.documentScrollWidth+"/"+metrics.innerWidth);
  const unexpected=consoleErrors.filter(x=>!/UNAUTHENTICATED_RENDER_QA|401|Failed to load resource/.test(x));
  if(unexpected.length)throw new Error(c.name+": unexpected console errors: "+unexpected.join(" | "));
  await context.close();
 }
} finally { await browser.close(); }
fs.writeFileSync(path.join(out,"rendered-qa.json"),JSON.stringify({schema:"spiderweb-rendered-qa/v1",results},null,2)+"\n");
console.log(JSON.stringify(results,null,2));
