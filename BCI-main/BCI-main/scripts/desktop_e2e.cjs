/* Actual WebView2 native host, isolated synthetic input, no browser substitution. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const net = require('node:net');
const { spawn } = require('node:child_process');
const { chromium } = require('../frontend/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const executable = path.join(root, 'desktop/dist/心澜.exe');
async function freePort() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve)); return port;
}
async function until(action, timeout=45000) {
  const end=Date.now()+timeout; let failure;
  while(Date.now()<end) { try { const result=await action(); if(result) return result; } catch(e) { failure=e; }
    await new Promise(resolve=>setTimeout(resolve,250)); }
  throw failure || new Error('Timed out');
}
function native(pid, action, file) {
  return new Promise((resolve,reject)=> {
    const helper=spawn(path.join(root,'.runtime/Scripts/python.exe'),['-B','-X','utf8','tests/desktop_native.py',String(pid),action,...(file?[file]:[])],{cwd:root,windowsHide:true});
    let output=''; helper.stderr.on('data',data=>output+=data); helper.stdout.on('data',data=>output+=data);
    helper.once('error',reject);
    helper.once('exit',code=>code===0?resolve(output.trim()):reject(new Error(output)));
  });
}
async function main() {
  assert.ok(await fs.stat(executable).catch(()=>null), 'Native desktop EXE must exist');
  const folder=await fs.mkdtemp(path.join(root,'.desktop-build/e2e-'));
  const apiPort=await freePort(), debugPort=await freePort();
  const child=spawn(executable,[],{cwd:root,windowsHide:false,env:{...process.env,
    XINLAN_STORAGE_DIR:path.join(folder,'data'), XINLAN_PORT:String(apiPort),
    // 仅隔离测试：受限工具进程不支持 WebView2 的嵌套 Windows 沙箱/GPU。
    // 交付宿主不设置这些选项，正常启动保留 WebView2 默认安全策略。
    WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${debugPort} --remote-debugging-address=127.0.0.1 --no-sandbox --disable-gpu`}});
  let browser, page;
  try {
    await until(async()=> (await fetch(`http://127.0.0.1:${debugPort}/json/version`)).ok);
    browser=await chromium.connectOverCDP(`http://127.0.0.1:${debugPort}`);
    // CDP 连接默认接管下载，恢复原生宿主行为以验证真实系统对话框。
    const cdp=await browser.newBrowserCDPSession();
    await cdp.send('Browser.setDownloadBehavior',{behavior:'default'});
    page=await until(async()=>browser.contexts()[0]?.pages()[0]);
    console.log('Native WebView connected:', page.url());
    await page.getByRole('button',{name:'体验演示',exact:true}).waitFor();
    await page.screenshot({path:path.join(folder,'desktop-workbench.png')});
    await page.getByRole('button',{name:'体验演示',exact:true}).click();
    await page.getByRole('button',{name:'导入固定合成样本'}).click();
    await page.getByRole('button',{name:'继续预览'}).click();
    await page.getByRole('button',{name:'继续确认'}).click();
    await page.getByRole('checkbox',{name:'我已核对数据来源、轴定义与标签空间'}).check();
    await page.getByRole('button',{name:'提交演示任务'}).click();
    await page.getByRole('button',{name:'查看评估结果'}).click();
    await page.getByLabel('复核人编码').fill('DESKTOP-TEST');
    await page.getByLabel('复核意见').fill('固定合成数据，仅用于桌面应用流程验证。');
    await page.getByRole('button',{name:'保存复核记录'}).click();
    await page.getByText('DESKTOP-TEST',{exact:true}).waitFor();
    await page.screenshot({path:path.join(folder,'desktop-assessment.png'),fullPage:true});
    for(const format of ['JSON','PDF']) {
      const [downloads]=await Promise.all([native(child.pid,'save-default'),page.getByRole('button',{name:`导出 ${format} 报告`}).click()]);
      const reports=await (await fetch(`http://127.0.0.1:${apiPort}/api/v1/reports`)).json();
      const report=reports.find(item=>item.format===format.toLowerCase());
      const saved=path.join(downloads,`xinlan-demo-reviewed-${report.id}.${report.format}`);
      await until(async()=> (await fs.stat(saved).catch(()=>null))?.size>100);
      const bytes=await fs.readFile(saved);
      await fs.writeFile(path.join(folder,'desktop-report.'+report.format),bytes);
      if(format==='JSON') { const report=JSON.parse(bytes.toString()); assert.equal(report.data_mode,'demo'); assert.equal(report.reviews.at(-1).reviewer,'DESKTOP-TEST'); }
      else assert.equal(bytes.subarray(0,5).toString(),'%PDF-');
      console.log('Native save passed:',format);
    }
    const [downloads]=await Promise.all([native(child.pid,'cancel-download'),page.getByRole('button',{name:'导出 JSON 报告'}).click()]);
    await until(async()=>(await fs.readFile(path.join(folder,'data/desktop-profile/desktop-events.log'),'utf8')).includes('save dialog result=Cancel'));
    const cancelledReports=await (await fetch(`http://127.0.0.1:${apiPort}/api/v1/reports`)).json();
    const cancelledReport=cancelledReports.find(item=>item.format==='json');
    assert.equal(await fs.stat(path.join(downloads,`xinlan-demo-reviewed-${cancelledReport.id}.json`)).catch(()=>null),null);
    await page.locator('.report-row').filter({hasText:'PDF'}).first().getByRole('button',{name:'预览',exact:true}).click();
    // WebView2 可能先发布 window.open 的占位目标，再发布宿主提供的原生预览视图。
    const popup=await until(async()=>page.context().pages().find(candidate=>candidate!==page && candidate.url().includes('preview=true')),15000)
      .catch(error=>{throw new Error('PDF targets: '+JSON.stringify(page.context().pages().map(p=>p.url()))+': '+error.message)});
    await popup.screenshot({path:path.join(folder,'desktop-pdf-preview.png')});
    await native(child.pid,'close-preview');
    const duplicate=spawn(executable,[],{cwd:root,windowsHide:false,env:{...process.env,XINLAN_STORAGE_DIR:path.join(folder,'data'),XINLAN_PORT:String(apiPort)}});
    await new Promise((resolve,reject)=> { duplicate.once('exit',code=>code===0?resolve():reject(new Error('Duplicate launch failed'))); duplicate.once('error',reject); });
    await fs.writeFile(path.join(folder,'checks.json'),JSON.stringify({folder,native_pid:child.pid,checks:['native-window','demo','review','native-json-save','native-pdf-save','cancel-save','pdf-preview','single-instance']},null,2));
  } catch(error) { if(page) await page.screenshot({path:path.join(folder,'failure.png')}).catch(()=>{}); console.error('Native workflow:',error); throw error; } finally {
    // WM_CLOSE targets only the native window from this test process.
    const close=spawn(path.join(root,'.runtime/Scripts/python.exe'),['-B','tests/desktop_native.py',String(child.pid),'close'],{cwd:root,windowsHide:true});
    await new Promise(resolve=>close.once('exit',resolve));
    await until(()=>child.exitCode!==null,35000);
    if(browser) await browser.close();
    assert.equal(child.exitCode,0,'Native app exits cleanly');
    await assert.rejects(()=>fetch(`http://127.0.0.1:${apiPort}/api/v1/health`),'Owned service must stop');
  }
  console.log(JSON.stringify({status:'passed',folder,cleanup:'native app and owned service exited'}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
