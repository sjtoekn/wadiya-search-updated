// Runs the REAL wadiya/web/app.js against a minimal fake DOM and a canned API response.
// NOT a browser: it verifies rendering logic and XSS-safety (no HTML parsing ever happens here).
const fs = require('fs'), vm = require('vm');
const api = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
class El {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.className = ''; this.dataset = {}; this.listeners = {}; this._text = ''; this.hidden = false;
    const self = this; this.classList = { add: c => { if (!self.className.split(' ').includes(c)) self.className += ' ' + c; }, remove: c => { self.className = self.className.split(' ').filter(x => x !== c).join(' '); } }; }
  set textContent(v) { this.children = []; this._text = String(v); } get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  appendChild(c) { this.children.push(c); return c; }
  addEventListener(t, f) { this.listeners[t] = f; } closest() { return null; } focus() {}
}
const text = s => ({ tagName: '#text', children: [], get textContent() { return s; } });
const ids = {}; ['searchForm', 'q', 'status', 'results', 'pager', 'flow', 'markLink'].forEach(i => ids[i] = new El(i === 'q' ? 'input' : 'div'));
const body = new El('body'); body.className = 'home';
const doc = { getElementById: i => ids[i], createElement: t => new El(t), createTextNode: text, body, title: '' };
const calls = [];
const ctx = { document: doc, window: { addEventListener() {}, scrollTo() {} }, history: { pushState() {} }, location: { search: '?q=' + encodeURIComponent(api.query) },
  fetch: (u) => { calls.push(u); return Promise.resolve({ ok: true, json: () => Promise.resolve(api) }); },
  AbortController, URLSearchParams, encodeURIComponent, setTimeout, console };
vm.createContext(ctx); vm.runInContext(fs.readFileSync(__dirname + '/../wadiya/web/app.js', 'utf8'), ctx);
setTimeout(() => {
  const walk = (n, f) => { f(n); (n.children || []).forEach(c => walk(c, f)); };
  const tags = new Set(); walk(ids.results, n => tags.add(n.tagName));
  console.log('fetch called with  :', calls[0]);
  console.log('status line        :', ids.status.textContent);
  console.log('element types made :', [...tags].sort().join(', '));
  console.log('results rendered   :', ids.results.children.length);
  ids.results.children.forEach((li, i) => {
    const h2 = li.children[1], a = h2.children[0];
    console.log(`  #${i + 1} title=${JSON.stringify(a.textContent)}  link=${a.tagName === 'A' ? a.href : '(no link)'}  rel=${a.rel || ''}`);
    console.log('      snippet:', JSON.stringify(li.children[2].textContent), ' <mark> count:', li.children[2].children.filter(c => c.tagName === 'MARK').length);
  });
  const bad = []; walk(ids.results, n => { if (['SCRIPT', 'IMG', 'IFRAME', 'STYLE'].includes(n.tagName)) bad.push(n.tagName); });
  console.log('SCRIPT/IMG/IFRAME elements created from page content:', bad.length);
  console.log('body is results-mode (home class removed):', !body.className.includes('home'));
  process.exit(bad.length ? 1 : 0);
}, 50);
