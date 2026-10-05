(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); }, timer = null;
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function fmt(v) { return v == null ? '—' : (typeof v === 'number' ? v.toLocaleString() : String(v)); }
  function table(target, headers, rows) {
    target.textContent = '';
    var t = el('table'), hr = el('tr');
    headers.forEach(function (h) { hr.appendChild(el('th', null, h)); }); t.appendChild(hr);
    if (!rows.length) { var r = el('tr'), c = el('td', null, 'Nothing yet.'); c.colSpan = headers.length; r.appendChild(c); t.appendChild(r); }
    rows.forEach(function (row) { var r = el('tr'); row.forEach(function (v) { r.appendChild(el('td', null, fmt(v))); }); t.appendChild(r); });
    target.appendChild(t);
  }
  function show(authed) { $('loginView').hidden = authed; $('dash').hidden = !authed; if (!authed && timer) { clearInterval(timer); timer = null; } }

  function render(d) {
    var c = d.crawler, s = d.search, cards = $('cards'); cards.textContent = '';
    [['Documents', d.documents], ['Domains', d.domains], ['Queue', c.queue_size], ['Crawled OK', c.successful_crawls],
     ['Failed', c.failed_crawls], ['Robots-blocked', c.robots_blocked], ['Searches', s.search_count],
     ['Avg latency (ms)', s.avg_latency_ms]].forEach(function (x) {
      var k = el('div', 'card'); k.appendChild(el('div', 'n', fmt(x[1]))); k.appendChild(el('div', 'l', x[0])); cards.appendChild(k);
    });
    var l = c.last_crawl;
    table($('crawler'), ['Status', 'Last run state', 'Started', 'Finished', 'Attempted', 'Fetched', 'Robots', 'Failed', 'Stored', 'Dupes', 'Avg fetch ms', 'Duration s'],
      [[c.status, l && l.state, l && l.started_at, l && l.finished_at, l && l.attempted, l && l.fetched, l && l.robots_blocked, l && l.failed, l && l.stored, l && l.duplicates, l && l.avg_fetch_ms, l && l.duration_s]]);
    table($('errors'), ['When', 'URL', 'Outcome', 'HTTP', 'Error'], d.recent_errors.map(function (e) { return [e.at, e.url, e.outcome, e.http_status, e.error]; }));
    table($('queries'), ['When', 'Query', 'Results', 'ms'], s.recent_queries.map(function (q) { return [q.at, q.query, q.result_count, q.latency_ms]; }));
    table($('index'), ['Engine', 'Tokenizer', 'Documents', 'Size (bytes)', 'SQLite'], [[d.index.engine, d.index.tokenizer, d.index.documents, d.index.size_bytes, d.index.sqlite_version]]);
    $('updated').textContent = 'Updated ' + new Date().toLocaleTimeString() + ' (auto-refresh every 10 s)';
  }
  function load() {
    return fetch('/api/admin/stats', { credentials: 'same-origin' }).then(function (r) {
      if (r.status === 401) { show(false); return; }
      return r.json().then(function (d) { show(true); render(d); if (!timer) timer = setInterval(load, 10000); });
    }).catch(function () { $('updated').textContent = 'Could not load stats.'; });
  }
  $('loginForm').addEventListener('submit', function (e) {
    e.preventDefault(); $('loginMsg').textContent = '';
    fetch('/api/admin/login', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: $('pw').value }) })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
      .then(function (res) { $('pw').value = ''; if (res.ok) load(); else $('loginMsg').textContent = (res.b.error && res.b.error.message) || 'Sign-in failed.'; });
  });
  $('logout').addEventListener('click', function () { fetch('/api/admin/logout', { method: 'POST', credentials: 'same-origin' }).then(function () { show(false); }); });
  load();
})();
