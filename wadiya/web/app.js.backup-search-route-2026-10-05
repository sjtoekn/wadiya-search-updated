(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var form = $('searchForm'), input = $('q'), statusEl = $('status'), resultsEl = $('results'),
      pagerEl = $('pager'), flow = $('flow'), controller = null;

  // ---- pure helpers (kept free of DOM so they are easy to reason about) ----
  function queryTerms(q) {
    var m = (q || '').toLowerCase().match(/[\p{L}\p{N}]+/gu) || [], seen = {}, out = [];
    m.forEach(function (t) { if (!seen[t]) { seen[t] = 1; out.push(t); } });
    return out;
  }
  function stem(t) { return t.length <= 4 ? t : t.slice(0, Math.max(4, t.length - 2)); }
  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function splitForHighlight(text, terms) {            // -> [{text, hit}]
    if (!terms.length) return [{ text: text, hit: false }];
    var re = new RegExp('(^|[^\\p{L}\\p{N}])(' + terms.map(function (t) { return escapeRe(stem(t)); }).join('|') + ')([\\p{L}\\p{N}]*)', 'giu');
    var parts = [], last = 0, m;
    while ((m = re.exec(text)) !== null) {
      var start = m.index + m[1].length, end = start + m[2].length + m[3].length;
      if (start > last) parts.push({ text: text.slice(last, start), hit: false });
      parts.push({ text: text.slice(start, end), hit: true });
      last = end;
      if (m[0].length === 0) re.lastIndex++;
    }
    if (last < text.length) parts.push({ text: text.slice(last), hit: false });
    return parts;
  }
  function safeHttpUrl(u) { return /^https?:\/\//i.test(u) ? u : null; }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function setStatus(msg, isError) { statusEl.textContent = msg || ''; statusEl.className = 'status' + (isError ? ' error' : ''); }
  function setBusy(b) { flow.hidden = !b; }
  function urlFor(q, page) { return '/?q=' + encodeURIComponent(q) + (page > 1 ? '&page=' + page : ''); }

  // ---- rendering (textContent only: crawled content is never interpreted as HTML) ----
  function renderResult(r, terms) {
    var li = el('li', 'result'), site = el('div', 'site');
    site.appendChild(el('b', null, r.domain)); site.appendChild(document.createTextNode(' · ' + r.url));
    var h = el('h2'), href = safeHttpUrl(r.url), a = el(href ? 'a' : 'span');
    a.textContent = r.title || r.url;
    if (href) {
      a.href = href;
      a.target = '_blank';
      a.rel = 'noopener noreferrer nofollow';
    }
    h.appendChild(a);
    var p = el('p');
    splitForHighlight(r.snippet || '', terms).forEach(function (part) { p.appendChild(part.hit ? el('mark', null, part.text) : document.createTextNode(part.text)); });
    var discover = el('a', 'discover-link', 'Discover website');
    discover.href = '/discovery?domain=' + encodeURIComponent(r.domain);
    discover.setAttribute('aria-label', 'Discover ' + (r.domain || 'this website'));

    li.appendChild(h);
    li.appendChild(site);
    li.appendChild(p);
    li.appendChild(discover);
    return li;
  }
  function renderPager(d) {
    pagerEl.textContent = '';
    if (d.total_pages <= 1) return;
    var prev = d.page > 1 ? el('a', null, '← Previous') : el('span', 'off', '← Previous');
    var next = d.page < d.total_pages ? el('a', null, 'Next →') : el('span', 'off', 'Next →');
    if (d.page > 1) { prev.href = urlFor(d.query, d.page - 1); prev.dataset.page = d.page - 1; }
    if (d.page < d.total_pages) { next.href = urlFor(d.query, d.page + 1); next.dataset.page = d.page + 1; }
    pagerEl.appendChild(prev); pagerEl.appendChild(el('span', null, 'Page ' + d.page + ' of ' + d.total_pages)); pagerEl.appendChild(next);
  }

  function search(q, page, push) {
    q = (q || '').trim(); page = page || 1;
    if (!q) return;
    document.body.classList.remove('home'); input.value = q; document.title = q + ' – Wadiya.com';
    if (push) history.pushState({ q: q, page: page }, '', urlFor(q, page));
    if (controller) controller.abort();
    controller = new AbortController();
    resultsEl.textContent = ''; pagerEl.textContent = ''; setStatus('Searching…', false); setBusy(true);

    fetch('/api/search?q=' + encodeURIComponent(q) + '&page=' + page, { signal: controller.signal, headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        setBusy(false);
        if (!res.ok) { setStatus((res.body.error && res.body.error.message) || 'Something went wrong.', true); return; }
        var d = res.body, terms = queryTerms(d.query);
        if (!d.results.length) {
          setStatus('', false);
          var box = el('li', 'empty'); box.appendChild(el('h2', null, d.result_count ? 'No more results' : 'No results for “' + d.query + '”'));
          box.appendChild(el('p', null, d.result_count ? 'Go back to the previous page.' : 'Try different or fewer words. Wadiya only searches the pages it has crawled so far.'));
          resultsEl.appendChild(box); renderPager(d); return;
        }
        var count = 'About ' + d.result_count.toLocaleString() + (d.result_count_exact ? '' : '+') + ' result' + (d.result_count === 1 ? '' : 's') +
          ' (' + (d.latency_ms / 1000).toFixed(3) + ' seconds)' + (d.match === 'any' ? ' · matching any of your words' : '');
        setStatus(count, false);
        d.results.forEach(function (r) { resultsEl.appendChild(renderResult(r, terms)); });
        renderPager(d);
        if (!push) return; window.scrollTo(0, 0);
      })
      .catch(function (e) {
        if (e && e.name === 'AbortError') return;
        setBusy(false); setStatus('Could not reach the search service. ', true);
        var b = el('button', null, 'Retry'); b.type = 'button'; b.onclick = function () { search(q, page, false); }; statusEl.appendChild(b);
      });
  }

  form.addEventListener('submit', function (e) { e.preventDefault(); search(input.value, 1, true); });   // button + Enter
  pagerEl.addEventListener('click', function (e) {
    var a = e.target.closest('a[data-page]'); if (!a) return;
    e.preventDefault(); search(input.value, parseInt(a.dataset.page, 10), true);
  });
  $('markLink').addEventListener('click', function (e) {
    e.preventDefault(); if (controller) controller.abort(); setBusy(false); history.pushState({}, '', '/');
    document.body.classList.add('home'); input.value = ''; setStatus(''); resultsEl.textContent = ''; pagerEl.textContent = ''; document.title = 'Wadiya.com'; input.focus();
  });
  window.addEventListener('popstate', function () { boot(false); });

  function boot(push) {
    var p = new URLSearchParams(location.search), q = p.get('q'), page = parseInt(p.get('page') || '1', 10);
    if (q && q.trim()) search(q, page > 0 ? page : 1, false);
    else { document.body.classList.add('home'); input.value = ''; setStatus(''); resultsEl.textContent = ''; pagerEl.textContent = ''; }
  }
  boot();
})();
