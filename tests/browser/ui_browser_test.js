// Real Chromium (Playwright) test of the shipped UI. Run from the project root:
//   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers NODE_PATH=<global node_modules> node tests/browser/ui_browser_test.js
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const SHOTS = process.env.SHOTS || '/tmp/shots'; fs.mkdirSync(SHOTS, { recursive: true });
const results = []; const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  -> ' + detail}`); };

(async () => {
  const serverModule = process.env.UI_SERVER === 'real' ? 'tests.browser.real_server' : 'tests.browser.dev_server';   // real = the actual FastAPI app
  console.log('server under test:', serverModule);
  const srv = spawn('python3', ['-m', serverModule], { stdio: ['ignore', 'pipe', 'inherit'] });
  const base = await new Promise((res, rej) => { srv.stdout.on('data', d => { const m = /PORT=(\d+)/.exec(d.toString()); if (m) res(`http://127.0.0.1:${m[1]}`); }); setTimeout(() => rej(new Error('server did not start')), 15000); });
  for (let i = 0; ; i++) {           // wait until the server actually answers (uvicorn needs a moment after printing PORT)
    try { if ((await fetch(base + '/api/health')).ok) break; } catch (e) {}
    if (i > 100) throw new Error('server never became healthy'); await new Promise(r => setTimeout(r, 200));
  }
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const errors = []; let expectCspBlock = false;
  const newPage = async (viewport) => {
    const ctx = await browser.newContext({ viewport: viewport || { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    await page.addInitScript(() => { window.__csp = []; document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI)); });
    page.on('pageerror', e => errors.push('pageerror: ' + e.message));
    page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text()) && !(expectCspBlock && /(Refused to execute inline script|Executing inline script violates the following Content Security Policy directive)/.test(m.text()))) errors.push('console: ' + m.text()); });
    return page;
  };
  const results$ = p => p.locator('#results .result');
  const status = p => p.locator('#status').innerText();

  try {
    // ---------- home + search + highlighting ----------
    let page = await newPage();
    const resp = await page.goto(base + '/');
    const h = resp.headers();
    check('response carries CSP / nosniff / frame-deny headers', h['content-security-policy'] && h['x-content-type-options'] === 'nosniff' && h['x-frame-options'] === 'DENY', JSON.stringify(h));
    check('home state shown (centered, class "home")', await page.evaluate(() => document.body.classList.contains('home')));
    await page.waitForTimeout(50);
    check('search input is focused on load', await page.evaluate(() => document.activeElement && document.activeElement.id === 'q'));
    await page.screenshot({ path: `${SHOTS}/home-desktop.png` });
    await page.keyboard.type('riverbed wadi'); await page.keyboard.press('Enter');   // Enter-to-search
    await results$(page).first().waitFor();
    check('Enter submits search and renders results', (await results$(page).count()) >= 1);
    check('home state removed after search', await page.evaluate(() => !document.body.classList.contains('home')));
    check('result count + response time shown', /About \d+ results? \(\d\.\d{3} seconds\)/.test(await status(page)), await status(page));
    check('result shows title, domain+URL, snippet', await page.evaluate(() => { const r = document.querySelector('.result'); return r.querySelector('h2 a') && /example\.org/.test(r.querySelector('.site').textContent) && r.querySelector('p').textContent.length > 10; }));
    const marks = await page.locator('#results mark').allInnerTexts();
    check('query terms highlighted in snippets', marks.length > 0 && marks.every(m => /riverbed|wadi/i.test(m)), JSON.stringify(marks));
    check('URL and title reflect the query', page.url().includes('q=riverbed') && /riverbed wadi/.test(await page.title()), page.url());
    await page.click('#searchForm button');   // button click path
    await page.waitForTimeout(150);
    check('Search button also works', (await results$(page).count()) >= 1);

    // ---------- search → website discovery → discovered pages ----------
    await page.goto(base + '/?q=wadi'); await results$(page).first().waitFor();
    await page.locator('.discover-link').first().click();
    await page.waitForURL(/\/discovery\?domain=example\.org/);
    await page.waitForSelector('.discovery-hero');
    check('result → Discover website opens Website Discovery', /\/discovery\?domain=example\.org/.test(page.url()) && /WEBSITE DISCOVERY/.test(await page.locator('.discovery-kicker').innerText()));
    check('Website Discovery shows correct domain and page count', (await page.locator('.discovery-hero h1').innerText()) === 'example.org' && /2 discovered pages?/.test(await page.locator('.discovery-summary').innerText()));
    check('Website Discovery renders discovered pages from API data', (await page.locator('.discovery-list .discovery-page').count()) === 2 && /Wadi guide/.test(await page.locator('.discovery-list').innerText()) && /Oasis facts/.test(await page.locator('.discovery-list').innerText()));
    check('discovered pages show URL, language and crawl time', /https:\/\/example\.org\/wadi/.test(await page.locator('.discovery-list').innerText()) && /en/.test(await page.locator('.discovery-list').innerText()) && /crawled/.test(await page.locator('.discovery-list').innerText()));
    await page.screenshot({ path: `${SHOTS}/discovery-desktop.png`, fullPage: true });

    // ---------- pagination ----------
    await page.goto(base + '/?q=paginate'); await results$(page).first().waitFor();
    check('page 1: 10 results, "Page 1 of 3"', (await results$(page).count()) === 10 && /Page 1 of 3/.test(await page.locator('#pager').innerText()));
    check('count says 25 results', /About 25 results/.test(await status(page)), await status(page));
    const first1 = await results$(page).first().locator('h2').innerText();
    await page.click('#pager a:has-text("Next")'); await page.waitForFunction(() => /Page 2 of 3/.test(document.getElementById('pager').textContent));
    check('Next → page 2 (10 results, URL has page=2)', (await results$(page).count()) === 10 && page.url().includes('page=2'));
    check('page 2 differs from page 1', (await results$(page).first().locator('h2').innerText()) !== first1);
    await page.click('#pager a:has-text("Next")'); await page.waitForFunction(() => /Page 3 of 3/.test(document.getElementById('pager').textContent));
    check('last page has 5 results and Next disabled', (await results$(page).count()) === 5 && (await page.locator('#pager span.off:has-text("Next")').count()) === 1);
    await page.goBack(); await page.waitForFunction(() => /Page 2 of 3/.test(document.getElementById('pager').textContent));
    check('browser Back restores page 2', page.url().includes('page=2') && (await results$(page).count()) === 10);
    await page.click('#pager a:has-text("Previous")'); await page.waitForFunction(() => /Page 1 of 3/.test(document.getElementById('pager').textContent));
    check('Previous → page 1', (await results$(page).count()) === 10);
    await page.goto(base + '/?q=paginate&page=4'); await page.waitForSelector('.empty');
    check('page beyond the end shows a graceful empty state', /No more results/.test(await page.locator('.empty h2').innerText()));

    // ---------- empty / error states ----------
    await page.goto(base + '/?q=zzzzqqqq'); await page.waitForSelector('.empty');
    check('empty state: "No results for …" + hint', /No results for/.test(await page.locator('.empty h2').innerText()) && /different or fewer/.test(await page.locator('.empty p').innerText()));
    await page.screenshot({ path: `${SHOTS}/empty-desktop.png` });
    await page.route('**/api/search*', r => r.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: { code: 500, message: 'internal error' } }) }));
    await page.goto(base + '/?q=wadi'); await page.waitForSelector('#status.error');
    check('server error (500) shows an error state, no results', /internal error/.test(await status(page)) && (await results$(page).count()) === 0, await status(page));
    await page.unroute('**/api/search*');
    await page.route('**/api/search*', r => r.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ error: { code: 400, message: 'query too long (max 200 characters)' } }) }));
    await page.goto(base + '/?q=wadi'); await page.waitForSelector('#status.error');
    check('validation error (400) message is shown', /query too long/.test(await status(page)));
    await page.unroute('**/api/search*');
    await page.route('**/api/search*', r => r.abort());
    await page.goto(base + '/?q=wadi'); await page.waitForSelector('#status.error');
    check('network failure shows error + Retry button', /Could not reach/.test(await status(page)) && (await page.locator('#status button:has-text("Retry")').count()) === 1);
    await page.screenshot({ path: `${SHOTS}/error-desktop.png` });
    await page.unroute('**/api/search*');
    await page.click('#status button:has-text("Retry")'); await results$(page).first().waitFor();
    check('Retry recovers and renders results', (await results$(page).count()) >= 1);
    await page.click('#markLink'); 
    check('clicking the wordmark returns to the home state', await page.evaluate(() => document.body.classList.contains('home') && document.getElementById('results').children.length === 0));

    // ---------- hostile indexed content ----------
    page = await newPage();
    await page.goto(base + '/?q=hostile'); await results$(page).first().waitFor(); await page.waitForTimeout(400);
    check('hostile content: no script executed (window.__pwned unset)', (await page.evaluate(() => window.__pwned)) === undefined);
    check('hostile content: no <img>/<script> elements created inside results', (await page.locator('#results img, #results script, #results iframe').count()) === 0);
    check('hostile markup is displayed as inert text', /<img src=x/.test(await page.locator('#results').innerText()) && /<script>/.test(await page.locator('#results').innerText()));
    check('javascript: URL is never rendered as a link', (await page.locator('a[href^="javascript:" i]').count()) === 0 && (await results$(page).count()) === 2);
    check('external result links are http(s) with noopener/nofollow', await page.evaluate(() => [...document.querySelectorAll('#results .result h2 a')].every(a => /^https?:/.test(a.href) && /noopener/.test(a.rel) && /nofollow/.test(a.rel))));
    await page.screenshot({ path: `${SHOTS}/hostile-desktop.png` });

    // ---------- CSP actually enforced by the browser ----------
    expectCspBlock = false; page = await newPage(); await page.goto(base + '/?q=wadi'); await results$(page).first().waitFor();
    check('normal operation triggers zero CSP violations', (await page.evaluate(() => window.__csp.length)) === 0, await page.evaluate(() => JSON.stringify(window.__csp)));
    expectCspBlock = true;   // the probe below is SUPPOSED to be refused by the browser
    const inl = await page.evaluate(() => { const s = document.createElement('script'); s.textContent = 'window.__inline = 1'; document.head.appendChild(s); return window.__inline; });
    await page.waitForTimeout(100); expectCspBlock = false;
    check('CSP blocks an injected inline script', inl === undefined && (await page.evaluate(() => window.__csp.length)) >= 1);

    // ---------- responsive layout ----------
    for (const [name, vp] of [['mobile', { width: 375, height: 667 }], ['tablet', { width: 768, height: 1024 }], ['desktop', { width: 1280, height: 800 }]]) {
      page = await newPage(vp);
      await page.goto(base + '/'); await page.screenshot({ path: `${SHOTS}/home-${name}.png` });
      const homeOk = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth && document.getElementById('q').getBoundingClientRect().width > 200);
      await page.goto(base + '/?q=paginate'); await results$(page).first().waitFor(); await page.screenshot({ path: `${SHOTS}/results-${name}.png`, fullPage: true });
      const resOk = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
      const boxOk = await page.evaluate(() => { const r = document.getElementById('q').getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth; });
      check(`${name} ${vp.width}px: no horizontal overflow, search box usable`, homeOk && resOk && boxOk, JSON.stringify({ homeOk, resOk, boxOk }));
    }

    // ---------- admin page (stand-in server uses the real AdminAuth) ----------
    page = await newPage(); await page.goto(base + '/admin');
    await page.waitForSelector('#loginView:not([hidden])');
    check('admin: unauthenticated visit shows only the login form', await page.evaluate(() => document.getElementById('dash').hidden));
    await page.fill('#pw', 'wrong'); await page.click('#loginForm button'); await page.waitForFunction(() => document.getElementById('loginMsg').textContent.length > 0);
    check('admin: wrong password shows error, stays logged out', /invalid credentials/.test(await page.locator('#loginMsg').innerText()) && await page.evaluate(() => document.getElementById('dash').hidden));
    await page.fill('#pw', 'browser-test-password'); await page.click('#loginForm button'); await page.waitForSelector('#dash:not([hidden])');
    check('admin: correct password shows dashboard (8 stat cards, tables)', (await page.locator('#cards .card').count()) === 8 && (await page.locator('#dash table').count()) >= 4);
    check('admin: password field cleared after submit', (await page.inputValue('#pw')) === '');
    check('admin: session cookie is HttpOnly (not readable from JS)', !(await page.evaluate(() => document.cookie)).includes('wadiya_admin'));
    await page.screenshot({ path: `${SHOTS}/admin-desktop.png`, fullPage: true });
    await page.reload(); await page.waitForSelector('#dash:not([hidden])');
    check('admin: session survives reload (dashboard visible, cards rendered)', !(await page.evaluate(() => document.getElementById('dash').hidden)) && (await page.locator('#cards .card').count()) === 8);
    await page.click('#logout'); await page.waitForSelector('#loginView:not([hidden])');
    await page.reload(); await page.waitForSelector('#loginView:not([hidden])');
    check('admin: logout really ends the session', await page.evaluate(() => document.getElementById('dash').hidden));

    check('no uncaught JS errors / console errors in any page', errors.length === 0, errors.join(' | '));
  } catch (e) { check('test run completed without exceptions', false, e.stack); }
  finally { await browser.close(); srv.kill(); }
  const failed = results.filter(r => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} browser checks passed; screenshots in ${SHOTS}`);
  process.exit(failed.length ? 1 : 0);
})();
