(function () {
  'use strict';

  var $ = function (id) {
    return document.getElementById(id);
  };

  var state = {
    page: 1,
    loading: false,
    timer: null
  };

  function el(tag, text) {
    var node = document.createElement(tag);
    if (text != null) node.textContent = String(text);
    return node;
  }

  function fmt(value) {
    return value == null || value === '' ? '—' : String(value);
  }

  function date(value) {
    if (!value) return '—';

    var d = new Date(value);

    return Number.isNaN(d.getTime())
      ? value
      : new Intl.DateTimeFormat(undefined, {
          dateStyle: 'medium',
          timeStyle: 'short'
        }).format(d);
  }

  function safeUrl(value) {
    return /^https?:\/\//i.test(value || '') ? value : null;
  }

  function setStatus(message, error) {
    $('statusMsg').textContent = message || '';
    $('statusMsg').className = 'status' + (error ? ' error' : '');
  }

  function renderSummary(stats) {
    var summary = $('summary');
    summary.textContent = '';

    var status = stats.by_status || {};

    [
      ['Total discovered', stats.total || 0],
      ['Pending', status.pending || 0],
      ['Active', status.active || 0],
      ['Failed', status.failed || 0]
    ].forEach(function (item) {
      var card = el('div');
      card.className = 'card';

      var number = el('div', Number(item[1]).toLocaleString());
      number.className = 'n';

      var label = el('div', item[0]);
      label.className = 'l';

      card.appendChild(number);
      card.appendChild(label);
      summary.appendChild(card);
    });

    var source = $('source');
    var current = source.value;

    source.textContent = '';

    var all = el('option', 'All sources');
    all.value = '';
    source.appendChild(all);

    Object.keys(stats.by_source || {})
      .sort()
      .forEach(function (name) {
        var option = el(
          'option',
          name + ' (' + stats.by_source[name] + ')'
        );
        option.value = name;
        source.appendChild(option);
      });

    source.value = current;

    if (source.value !== current) {
      source.value = '';
    }
  }

  function renderRows(sites) {
    var tbody = $('rows');
    tbody.textContent = '';

    if (!sites.length) {
      var empty = el('tr');
      var cell = el('td', 'No discovery records found.');
      cell.colSpan = 9;
      empty.appendChild(cell);
      tbody.appendChild(empty);
      return;
    }

    sites.forEach(function (site) {
      var row = el('tr');

      var urlCell = el('td');
      var href = safeUrl(site.url);

      if (href) {
        var link = el('a', site.url);
        link.href = href;
        link.target = '_blank';
        link.rel = 'noopener noreferrer nofollow';
        urlCell.appendChild(link);
      } else {
        urlCell.textContent = fmt(site.url);
      }

      row.appendChild(urlCell);

      var domainCell = el('td', fmt(site.domain));
      domainCell.className = 'discovery-domain-name';
      row.appendChild(domainCell);

      var admission = site.admission || 'auto';
      var admissionCell = el('td');
      var badge = el('span', admission);
      badge.className = 'discovery-admission discovery-admission-' + admission;
      admissionCell.appendChild(badge);
      row.appendChild(admissionCell);

      var actionsCell = el('td');

      if (admission !== 'auto') {
        var select = el('select');
        select.className = 'discovery-domain-action-select';
        select.setAttribute('aria-label', 'Actions for ' + (site.domain || 'domain'));

        [
          ['auto', 'Approve'],
          ['quarantine', 'Quarantine'],
          ['blocked', 'Block']
        ].forEach(function (item) {
          var option = el('option', item[1]);
          option.value = item[0];
          select.appendChild(option);
        });

        select.value = admission;

        select.addEventListener('change', function () {
          var next = select.value;

          if (!window.confirm(
            'Are you sure you want to set "' +
            (site.domain || 'domain') +
            '" to ' +
            next +
            '?'
          )) {
            select.value = admission;
            return;
          }

          updateDomainAdmission(site.domain || '', next);
        });

        actionsCell.appendChild(select);
      }

      row.appendChild(actionsCell);

      [
        site.source,
        site.status,
        date(site.first_seen_at),
        date(site.last_crawled_at),
        site.failure_count,
        date(site.next_attempt_at),
        site.last_error
      ].forEach(function (value) {
        row.appendChild(el('td', fmt(value)));
      });

      tbody.appendChild(row);
    });
  }

  function updateDomainAdmission(domain, admission) {
    if (!domain || !admission) return;

    var label =
      admission === 'auto'
        ? 'approve'
        : admission === 'quarantine'
          ? 'quarantine'
          : 'block';

    if (!window.confirm(
      'Are you sure you want to ' + label + ' the domain "' + domain + '"?'
    )) {
      return;
    }

    setStatus('Updating ' + domain + '…');

    fetch('/api/admin/discovery/domain', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json'
      },
      body: JSON.stringify({
        domain: domain,
        admission: admission
      })
    })
      .then(function (response) {
        return response.json().catch(function () {
          return {};
        }).then(function (body) {
          return { response: response, body: body };
        });
      })
      .then(function (result) {
        if (result.response.status === 401) {
          window.location.href = '/admin';
          return;
        }

        if (!result.response.ok) {
          throw new Error(
            result.body.error && result.body.error.message
              ? result.body.error.message
              : 'Could not update domain admission.'
          );
        }

        setStatus(
          domain +
          ' → ' +
          admission +
          ' (' +
          Number(result.body.updated_sites || 0).toLocaleString() +
          ' URLs updated)'
        );

        load();
      })
      .catch(function (error) {
        setStatus(
          error.message || 'Could not update domain admission.',
          true
        );
      });
  }

  function renderPagination(pagination) {
    var page = Number(pagination.page) || 1;
    var totalPages = Number(pagination.total_pages) || 0;
    var total = Number(pagination.total) || 0;
    var start = Number(pagination.start) || 0;
    var end = Number(pagination.end) || 0;

    if (total > 0) {
      $('range').textContent =
        'Showing ' +
        start.toLocaleString() +
        '–' +
        end.toLocaleString() +
        ' of ' +
        total.toLocaleString();
    } else {
      $('range').textContent = 'Showing 0 of 0';
    }

    $('pageInfo').textContent =
      totalPages > 0
        ? 'Page ' + page.toLocaleString() + ' of ' + totalPages.toLocaleString()
        : 'Page 1 of 1';

    $('prevPage').disabled = page <= 1;
    $('nextPage').disabled = totalPages === 0 || page >= totalPages;
  }

  function load() {
    if (state.loading) return;

    state.loading = true;

    var params = new URLSearchParams();
    var query = $('q').value.trim();
    var status = $('status').value;
    var source = $('source').value;
    var limit = $('pageSize').value;

    if (query) params.set('q', query);
    if (status) params.set('status', status);
    if (source) params.set('source', source);

    params.set('page', String(state.page));
    params.set('limit', limit);

    setStatus('Loading…');

    fetch('/api/admin/discovery?' + params.toString(), {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' }
    })
      .then(function (response) {
        return response.json().catch(function () {
          return {};
        }).then(function (body) {
          return { response: response, body: body };
        });
      })
      .then(function (result) {
        if (result.response.status === 401) {
          window.location.href = '/admin';
          return;
        }

        if (!result.response.ok) {
          throw new Error(
            result.body.error && result.body.error.message
              ? result.body.error.message
              : 'Could not load discovery data.'
          );
        }

        var pagination = result.body.pagination || {};

        /*
         * If records disappear between refreshes and the current page is
         * now beyond the final page, move back to the final valid page.
         */
        if (
          pagination.total_pages > 0 &&
          state.page > pagination.total_pages
        ) {
          state.page = pagination.total_pages;
          state.loading = false;
          load();
          return;
        }

        renderSummary(result.body.stats || {});
        renderRows(result.body.sites || []);
        renderPagination(pagination);

        setStatus('');

        $('updated').textContent =
          'Updated ' +
          new Date().toLocaleTimeString() +
          ' · auto-refresh every 15 seconds';
      })
      .catch(function (error) {
        setStatus(
          error.message || 'Could not load discovery data.',
          true
        );
      })
      .finally(function () {
        state.loading = false;
      });
  }

  function resetPageAndLoad() {
    state.page = 1;
    load();
  }

  $('filters').addEventListener('submit', function (event) {
    event.preventDefault();
    resetPageAndLoad();
  });

  $('clear').addEventListener('click', function () {
    $('q').value = '';
    $('status').value = '';
    $('source').value = '';
    $('pageSize').value = '50';
    resetPageAndLoad();
  });

  $('pageSize').addEventListener('change', function () {
    resetPageAndLoad();
  });

  $('prevPage').addEventListener('click', function () {
    if (state.page > 1) {
      state.page -= 1;
      load();
    }
  });

  $('nextPage').addEventListener('click', function () {
    state.page += 1;
    load();
  });

  $('logout').addEventListener('click', function () {
    fetch('/api/admin/logout', {
      method: 'POST',
      credentials: 'same-origin'
    }).then(function () {
      window.location.href = '/admin';
    });
  });

  load();

  state.timer = setInterval(function () {
    load();
  }, 15000);
})();

(function () {
  function reportLayout() {
    var main = document.querySelector('main.admin-discovery-page');
    var table = document.querySelector('main.admin-discovery-page table');

    if (!main) return;

    var mainRect = main.getBoundingClientRect();
    var tableRect = table ? table.getBoundingClientRect() : null;
    var cs = getComputedStyle(main);

    console.log('=== WADIYA DISCOVERY WIDTH DIAGNOSTIC ===');
    console.log({
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio,
      mainWidth: mainRect.width,
      mainLeft: mainRect.left,
      mainRight: mainRect.right,
      computedWidth: cs.width,
      computedMaxWidth: cs.maxWidth,
      computedPaddingLeft: cs.paddingLeft,
      computedPaddingRight: cs.paddingRight,
      tableWidth: tableRect ? tableRect.width : null,
      tableScrollWidth: table ? table.scrollWidth : null,
      bodyWidth: document.body.getBoundingClientRect().width,
      documentWidth: document.documentElement.getBoundingClientRect().width
    });
  }

  window.addEventListener('load', reportLayout);
  setTimeout(reportLayout, 500);
})();
