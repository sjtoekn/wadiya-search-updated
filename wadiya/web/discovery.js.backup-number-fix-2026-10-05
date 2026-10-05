(function () {
  'use strict';

  var statusEl = document.getElementById('status');
  var discoveryEl = document.getElementById('discovery');
  var searchForm = document.getElementById('searchForm');
  var searchInput = document.getElementById('q');

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function setStatus(text, error) {
    statusEl.textContent = text || '';
    statusEl.className = 'status' + (error ? ' error' : '');
  }

  function safeHttpUrl(url) {
    return /^https?:\/\//i.test(url) ? url : null;
  }

  function formatDateTime(value) {
    if (!value) return '';
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;

    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short'
    }).format(date);
  }

  function render(data) {
    discoveryEl.textContent = '';

    var hero = el('section', 'discovery-hero');
    hero.appendChild(el('p', 'discovery-kicker', 'WEBSITE DISCOVERY'));
    hero.appendChild(el('h1', null, data.domain));
    hero.appendChild(el('p', 'discovery-summary',
      data.page_count.toLocaleString() + ' discovered page' +
      (data.page_count === 1 ? '' : 's')
    ));

    var meta = el('div', 'discovery-meta');
    meta.appendChild(el('span', null, 'First crawled: ' + formatDateTime(data.first_crawled)));
    meta.appendChild(el('span', null, 'Last crawled: ' + formatDateTime(data.last_crawled)));
    hero.appendChild(meta);

    var pages = el('section', 'discovery-pages');
    pages.appendChild(el('h2', null, 'Discovered pages'));

    var list = el('ol', 'discovery-list');

    data.pages.forEach(function (page) {
      var item = el('li', 'discovery-page');

      var href = safeHttpUrl(page.url);
      var title = el(href ? 'a' : 'span', 'discovery-page-title', page.title || page.url);

      if (href) {
        title.href = href;
        title.target = '_blank';
        title.rel = 'noopener noreferrer nofollow';
      }

      item.appendChild(title);
      item.appendChild(el('div', 'discovery-url', page.url));

      if (page.description) {
        item.appendChild(el('p', 'discovery-description', page.description));
      }

      var details = [];
      if (page.language) details.push(page.language);
      if (page.crawled_at) details.push('crawled ' + formatDateTime(page.crawled_at));

      if (details.length) {
        item.appendChild(el('div', 'discovery-details', details.join(' · ')));
      }

      list.appendChild(item);
    });

    pages.appendChild(list);
    discoveryEl.appendChild(hero);
    discoveryEl.appendChild(pages);
  }

  searchForm.addEventListener('submit', function (event) {
    event.preventDefault();

    var query = (searchInput.value || '').trim();
    if (!query) {
      searchInput.focus();
      return;
    }

    window.location.href = '/?q=' + encodeURIComponent(query);
  });

  var params = new URLSearchParams(location.search);
  var domain = (params.get('domain') || '').trim();

  if (!domain) {
    setStatus('No website was specified.', true);
    return;
  }

  document.title = domain + ' – Website Discovery – Wadiya.com';

  fetch('/api/discovery?domain=' + encodeURIComponent(domain), {
    headers: { Accept: 'application/json' }
  })
    .then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        return { ok: response.ok, body: body };
      });
    })
    .then(function (result) {
      if (!result.ok) {
        setStatus(
          result.body.error && result.body.error.message
            ? result.body.error.message
            : 'Could not discover this website.',
          true
        );
        return;
      }

      setStatus('');
      render(result.body);
    })
    .catch(function () {
      setStatus('Could not reach the discovery service.', true);
    });
})();
