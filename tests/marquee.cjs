// Run with Node.js and Playwright. All images, labels and browser data are isolated fixtures.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const ROOT=path.resolve(__dirname,'..');
const RUN=fs.mkdtempSync(path.join(process.env.IMAGE_REVIEW_TEST_OUTPUT||os.tmpdir(),'marquee-'));
const DATA=path.join(RUN,'images'),OUT=path.join(RUN,'results.csv');
const PORT=Number(process.env.IMAGE_REVIEW_TEST_PORT||8891),URL=`http://127.0.0.1:${PORT}/`;
const TOTAL=2005,checks=[],sleep=ms=>new Promise(r=>setTimeout(r,ms));
function pass(name){checks.push(name);console.log('PASS',name)}
async function selected(page){return page.locator('.card.batch').count()}
async function rect(page,index){return page.locator(`.card[data-index="${index}"]`).evaluate(el=>{const r=el.getBoundingClientRect();return {x:r.left,y:r.top,right:r.right,bottom:r.bottom}})}
async function vp(page){return page.locator('#viewport').evaluate(el=>{const r=el.getBoundingClientRect();return {x:r.left,y:r.top,right:r.right,bottom:r.bottom,top:el.scrollTop,left:el.scrollLeft}})}
async function drag(page,a,b,{hold=0,release=true}={}){
  await page.mouse.move(a.x,a.y);await page.mouse.down();
  await page.mouse.move(b.x,b.y,{steps:12});if(hold)await sleep(hold);
  if(release){await page.mouse.up();await sleep(70)}
}
async function box(page,first=0,last=7,options){
  const a=await rect(page,first),b=await rect(page,last);
  await drag(page,{x:a.x+8,y:a.y+8},{x:b.right-8,y:b.bottom-8},options);
}
async function top(page){await page.locator('#viewport').evaluate(el=>{el.scrollTop=0;el.scrollLeft=0});await sleep(80)}
async function labels(page){return page.evaluate(()=>JSON.parse(JSON.stringify(__ft.state.personal.labels)))}
async function compareFinal(page){return page.evaluate(()=>JSON.parse(JSON.stringify(__ft.state.compare.final)))}
async function ready(page){await page.waitForFunction(n=>window.__ft?.state.items.length===n&&document.querySelectorAll('.card').length>0,TOTAL)}
function csv(manifest,name,id,values){
  const rows=[['序号','相对路径','标签','淘汰原因','筛选人','筛选人标识','批次校验','内容校验','导出时间','格式版本']];
  for(let i=0;i<manifest.items.length;i++){
    const it=manifest.items[i];rows.push([i+1,it.file,values[i]||'',values[i]==='No'?'fixture reason':'',name,id,manifest.batch,it.sig,'2026-11-25T00:00:00Z','3']);
  }
  return '\ufeff'+rows.map(r=>r.map(x=>'"'+String(x??'').replaceAll('"','""')+'"').join(',')).join('\r\n');
}
(async()=>{
 let browser,server;
 const errors=[];
 try{
  fs.mkdirSync(DATA);
  const fixture=fs.readFileSync(path.join(ROOT,'examples','images','sample_001.png'));
  for(let i=0;i<TOTAL;i++){
    const dir=path.join(DATA,i%2?'中文子目录':'fixtures');fs.mkdirSync(dir,{recursive:true});
    fs.writeFileSync(path.join(dir,`fixture_${String(i).padStart(4,'0')}.png`),fixture);
  }
  server=spawn(process.env.IMAGE_REVIEW_PYTHON||'python',['-u','-B','-X','utf8',path.join(ROOT,'筛选工具.py'),DATA,'--port',String(PORT),'--no-browser','--out',OUT],{cwd:ROOT,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let log='';server.stdout.on('data',s=>log+=s);server.stderr.on('data',s=>log+=s);server.on('error',e=>log+=e.message);
  let online=false;for(let i=0;i<600;i++){try{const r=await fetch(URL+'manifest.json');if(r.ok){online=true;break}}catch{}await sleep(100)}
  assert.ok(online,log);const manifest=await(await fetch(URL+'manifest.json')).json();assert.equal(manifest.items.length,TOTAL);
  assert.equal(path.resolve(manifest.source_path),fs.realpathSync(DATA),'test port belongs to another image directory');
  browser=await chromium.launch({headless:true,...(process.env.IMAGE_REVIEW_BROWSER?{executablePath:process.env.IMAGE_REVIEW_BROWSER}:{})});
  const context=await browser.newContext({viewport:{width:1600,height:1100}}),page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));await page.goto(URL);await ready(page);
  await page.evaluate(()=>{
    const p=__ft.state.personal;p.labels={};p.bookmarks=[];
    for(let i=0;i<1700;i++)p.labels[__ft.state.items[i].file]={label:i%3?'pass':'reject',reason:`old reason ${i}`};
    __ft.state.profile={name:'Fixture reviewer',id:'F-FIXTURE-P'};__ft.select(3);__ft.persist();
  });
  const baseline=await labels(page);await sleep(500);await page.reload();await ready(page);
  assert.deepEqual(await labels(page),baseline);assert.equal(await page.evaluate(()=>__ft.state.personal.idx),3);
  pass('1700 existing v3 labels, reasons and current position survive reload');
  await top(page);await box(page,0,7,{release:false});assert.equal(await selected(page),8);
  assert.equal(await page.locator('#marquee').isVisible(),true);
  await page.screenshot({path:path.join(RUN,'marquee.png')});await page.mouse.up();
  assert.equal(await selected(page),8);assert.deepEqual(await labels(page),baseline);
  pass('real mouse marquee selects eight cards without changing any labels');
  await page.locator('#markYes').click();
  const files=manifest.items.slice(0,8).map(it=>it.file),after=await labels(page);
  for(const file of files)assert.equal(after[file].label,'pass');
  for(const [file,value]of Object.entries(baseline))if(!files.includes(file))assert.deepEqual(after[file],value);
  assert.equal(await page.evaluate(()=>__ft.state.personal.idx),8);assert.equal(await selected(page),0);
  pass('Yes button marks only the selection, keeps other 1692 records intact and advances');
  await page.keyboard.press('Control+z');assert.deepEqual(await labels(page),baseline);
  pass('one undo restores the entire batch including original rejection reasons');
  await top(page);await box(page);await page.keyboard.press('2');
  for(const file of files)assert.equal((await labels(page))[file].label,'reject');
  await page.keyboard.press('Control+z');assert.deepEqual(await labels(page),baseline);
  pass('No hotkey applies to every selected card and is undone as one action');
  await top(page);await box(page);await page.locator('#clearButton').click();
  for(const file of files)assert.equal((await labels(page))[file],undefined);
  await page.keyboard.press('Control+z');assert.deepEqual(await labels(page),baseline);
  pass('batch clear removes only selected labels and undo restores all of them');
  await top(page);await box(page);await page.keyboard.press('Escape');assert.equal(await selected(page),0);
  await box(page,0,7,{release:false});await page.keyboard.press('Escape');
  await page.mouse.move(500,400);assert.equal(await selected(page),0);assert.equal(await page.locator('#marquee').isHidden(),true);await page.mouse.up();
  pass('Escape cancels a completed selection and an active drag without ghost rectangles');
  await top(page);await box(page);await page.locator('.card[data-index="2"] .photo').click();assert.equal(await selected(page),0);
  await box(page);await page.locator('#nextPage').click();assert.equal(await selected(page),0);
  await page.locator('#prevPage').click();
  await top(page);await box(page);await page.locator('#modeCompare').click();assert.equal(await selected(page),0);
  await page.locator('#modePersonal').click();
  pass('single click, pagination and mode switching clear multi-selection');
  await page.selectOption('#filter','unlabeled');assert.equal(await page.evaluate(()=>__ft.visible.length),305);
  const unmarked=await page.evaluate(()=>__ft.visible.slice(0,8));await box(page,unmarked[0],unmarked[7]);
  await page.keyboard.press('1');assert.equal(await page.evaluate(()=>__ft.visible.length),297);
  await page.keyboard.press('Control+z');assert.equal(await page.evaluate(()=>__ft.visible.length),305);assert.deepEqual(await labels(page),baseline);
  pass('batch marking in the unlabeled filter updates membership and undo restores it');
  await page.selectOption('#filter','all');await top(page);
  let v=await vp(page),a=await rect(page,0);
  await drag(page,{x:a.x+8,y:a.y+8},{x:v.right-25,y:v.bottom-3},{hold:600});
  assert.ok((await vp(page)).top>0);assert.ok(await selected(page)>8);
  assert.ok(await page.locator('.card.batch').evaluateAll(cs=>cs.every(c=>Number(c.dataset.index)<1000)));
  pass('downward edge scrolling expands selection within the current page only');
  await page.keyboard.press('Escape');
  const oldTop=(await vp(page)).top;
  const firstOnscreen=await page.locator('.card').evaluateAll(cs=>{const v=document.querySelector('#viewport').getBoundingClientRect();const c=cs.find(c=>{const r=c.getBoundingClientRect();return r.top>v.top+10&&r.bottom<v.bottom-10});const r=c.getBoundingClientRect();return {x:r.left+8,y:r.top+8}});
  v=await vp(page);await drag(page,firstOnscreen,{x:v.right-25,y:v.y+3},{hold:350});
  assert.ok((await vp(page)).top<oldTop);await page.keyboard.press('Escape');
  pass('upward edge scrolling also works');
  await page.locator('#viewport').evaluate(el=>el.scrollTop=el.scrollHeight);await sleep(80);
  const bottom=(await vp(page)).top;v=await vp(page);
  const end=await rect(page,999);
  await drag(page,{x:end.x+10,y:Math.max(v.y+10,end.y+10)},{x:v.right-25,y:v.bottom-3},{hold:300});
  assert.equal((await vp(page)).top,bottom);await page.keyboard.press('Escape');
  pass('automatic scrolling stops at the page bottom');
  await top(page);for(let i=0;i<4;i++)await page.locator('#zoomIn').click();
  v=await vp(page);a=await rect(page,0);
  await drag(page,{x:a.x+8,y:a.y+8},{x:v.right-3,y:Math.min(v.bottom-100,a.y+100)},{hold:400});
  assert.ok((await vp(page)).left>0);await page.keyboard.press('0');assert.equal(await selected(page),0);
  pass('zoomed grids support horizontal edge scrolling and reset cancels selection');
  await top(page);await box(page,0,7,{release:false});await page.evaluate(()=>window.dispatchEvent(new Event('blur')));
  assert.equal(await page.locator('#marquee').isHidden(),true);await page.mouse.up();await page.keyboard.press('Escape');
  pass('losing window focus ends the drag');
  await top(page);await page.locator('.card[data-index="0"] .star').click();assert.equal(await page.evaluate(()=>__ft.state.personal.bookmarks.length),1);
  await page.locator('.card[data-index="0"] .photo').dblclick();assert.equal(await page.locator('#preview').isVisible(),true);await page.keyboard.press('Escape');
  pass('bookmark clicks and double-click preview still work');
  await page.evaluate(()=>__ft.select(996));await page.locator('#viewport').evaluate(el=>el.scrollTop=el.scrollHeight);await sleep(80);
  await box(page,996,999);await page.keyboard.press('1');
  assert.equal(await page.evaluate(()=>__ft.state.personal.page),1);assert.equal(await page.evaluate(()=>__ft.state.personal.idx),1000);
  assert.equal(await page.locator('.card[data-index="1000"]').count(),1);await page.keyboard.press('Control+z');assert.deepEqual(await labels(page),baseline);
  pass('batch auto-advance across the 1000-card page boundary renders the next page');
  await page.locator('#modeCompare').click();
  fs.writeFileSync(path.join(RUN,'a.csv'),csv(manifest,'Reviewer A','F-FIXTURE-A',['Yes','No','Yes','No','Yes','','','Yes']));
  fs.writeFileSync(path.join(RUN,'b.csv'),csv(manifest,'Reviewer B','F-FIXTURE-B',['Yes','No','No','Yes','','No','','Yes']));
  await page.locator('#pairInput').setInputFiles([path.join(RUN,'a.csv'),path.join(RUN,'b.csv')]);await page.locator('#startPair').click();
  const originalPair=await page.evaluate(()=>JSON.stringify(__ft.state.compare.pair));
  await top(page);await box(page);await page.keyboard.press('2');
  let finals=await compareFinal(page);for(const i of [0,2,3,7])assert.equal(finals[manifest.items[i].file].label,'reject');
  for(const i of [1,4,5,6])assert.equal(finals[manifest.items[i].file],undefined);
  assert.match(await page.locator('#toast').innerText(),/3 张待补筛已跳过/);
  assert.equal(await page.evaluate(()=>JSON.stringify(__ft.state.compare.pair)),originalPair);
  pass('compare batch writes only eligible final decisions, skips three incomplete items and preserves both reviewers');
  await page.keyboard.press('Control+z');assert.deepEqual(await compareFinal(page),{});
  pass('compare batch undo restores all explicit final decisions as one operation');
  await page.evaluate(()=>{const file=__ft.state.items[0].file;__ft.state.compare.final[file]={label:'reject',source:'third',updatedAt:'2026-11-24T00:00:00Z',recheck:true};__ft.renderPage({reset:true});__ft.persist()});
  const oldFinal=await compareFinal(page);await top(page);await box(page);await page.locator('#markYes').click();
  finals=await compareFinal(page);assert.equal(finals[manifest.items[0].file],undefined);assert.equal(finals[manifest.items[1].file].label,'pass');
  await page.keyboard.press('Control+z');assert.deepEqual(await compareFinal(page),oldFinal);
  pass('agreeing with both reviewers removes an override; undo restores recheck metadata');
  await top(page);await box(page);await page.locator('#clearButton').click();assert.deepEqual(await compareFinal(page),{});
  await page.keyboard.press('Control+z');assert.deepEqual(await compareFinal(page),oldFinal);
  pass('compare batch clear and undo preserve original judgments and previous adjudication metadata');
  await page.locator('#compareFilterTabs [data-filter="need_fill"]').click();
  const pendingIds=await page.evaluate(()=>__ft.visible.slice(0,8));await top(page);await box(page,pendingIds[0],pendingIds[7]);
  await page.keyboard.press('1');assert.deepEqual(await compareFinal(page),oldFinal);assert.equal(await selected(page),8);await page.keyboard.press('Escape');
  pass('an entirely incomplete selection cannot acquire a final judgment');
  await page.locator('#compareFilterTabs [data-filter="conflict"]').click();await top(page);await box(page,2,3);await page.keyboard.press('1');
  assert.equal(await page.locator('#compareFilterTabs [data-filter="conflict"] .count').innerText(),'2 张');
  assert.equal(await page.evaluate(()=>JSON.stringify(__ft.state.compare.pair)),originalPair);
  const beforeReload=await compareFinal(page);await sleep(600);await page.reload();await ready(page);assert.deepEqual(await compareFinal(page),beforeReload);
  pass('conflict filters retain original counts, reviewer data and saved batch decisions across reload');
  await page.locator('#toolsCompare [data-act="export"]').click();
  const downloaded=page.waitForEvent('download');await page.locator('#summaryExport').click();
  const download=await downloaded,summaryPath=path.join(RUN,'summary.csv');await download.saveAs(summaryPath);
  const analyzed=await page.evaluate(text=>__ft.analyzeCSV(text,'summary.csv'),fs.readFileSync(summaryPath,'utf8'));
  assert.equal(analyzed.format,'summary');assert.equal(analyzed.persons[0].id,'F-FIXTURE-A');assert.equal(analyzed.persons[1].id,'F-FIXTURE-B');
  pass('summary export keeps both reviewer identities and remains readable by the importer');
  await page.locator('#compareFilterTabs [data-filter="all"]').click();await top(page);await box(page);
  await page.screenshot({path:path.join(RUN,'compare-selection.png')});await page.keyboard.press('Escape');
  await page.setViewportSize({width:900,height:800});assert.equal(await page.locator('#grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),4);
  assert.ok(await page.locator('footer').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
  pass('four-column layout and footer stay usable in a narrow window');
  const local=await browser.newContext({viewport:{width:1600,height:1100}}),localPage=await local.newPage();
  localPage.on('pageerror',e=>errors.push(e.message));await localPage.goto('file:///'+path.join(ROOT,'筛选工具.html').replaceAll('\\','/'));
  await localPage.locator('#folderInput').setInputFiles(DATA);await ready(localPage);await box(localPage);await localPage.keyboard.press('1');
  assert.equal(Object.values(await labels(localPage)).filter(v=>v.label==='pass').length,8);await localPage.keyboard.press('Control+z');assert.deepEqual(await labels(localPage),{});
  pass('direct file HTML mode also supports marquee, batch marking and undo');
  await sleep(500);assert.ok(fs.existsSync(OUT));assert.ok(fs.existsSync(OUT.replace(/\.csv$/,'.session.json')));
  assert.deepEqual(errors,[]);pass('server saves local results and sessions; no uncaught browser errors');
 }finally{
  fs.writeFileSync(path.join(RUN,'checks.json'),JSON.stringify({passed:checks.length,checks,errors},null,2));
  console.log('ARTIFACTS',RUN);await browser?.close();server?.kill();
 }
})().catch(e=>{console.error(e);process.exitCode=1});
