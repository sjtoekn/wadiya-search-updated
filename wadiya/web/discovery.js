(function () {
  'use strict';

  var statusEl = document.getElementById('status');
  var discoveryEl = document.getElementById('discovery');
  var searchForm = document.getElementById('searchForm');
  var searchInput = document.getElementById('q');

  var websiteSubmitForm = document.getElementById('websiteSubmitForm');
  var websiteUrlInput = document.getElementById('websiteUrl');
  var websiteSubmitButton = document.getElementById('websiteSubmitButton');
  var websiteSubmitMessage = document.getElementById('websiteSubmitMessage');

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function setStatus(message, isError) {
    statusEl.textContent = message;
    statusEl.classList.toggle('error', !!isError);
  }

  function setSubmitMessage(message, state) {
    websiteSubmitMessage.textContent = message;
    websiteSubmitMessage.className = 'website-submit-message';
    if (state) {
      websiteSubmitMessage.classList.add(state);
    }
  }

  function setSubmitBusy(busy) {
    websiteSubmitButton.disabled = busy;
    websiteUrlInput.disabled = busy;
    websiteSubmitButton.textContent = busy ? 'Submitting…' : 'Submit website';
  }

  function safeHttpUrl(value) {
    try {
      var url = new URL(value);
      if (url.protocol !== 'http:' && url.protocol !== 'https:') {
        return null;
      }
      return url.href;
    } catch (error) {
      return null;
    }
  }

  function formatDateTime(value) {
    if (!value) return '—';

    var date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString();
  }

  function render(data) {
    discoveryEl.textContent = '';

    var hero = el('section', 'discovery-hero');

    hero.appendChild(
      el('p', 'discovery-kicker', 'WEBSITE DISCOVERY')
    );

    hero.appendChild(
      el('h1', null, data.domain || 'Website')
    );

    var summary = el(
      'p',
      'discovery-summary',
      String(data.page_count || 0) + ' discovered pages'
    );

    hero.appendChild(summary);

    var meta = el('div', 'discovery-meta');

    var first = el(
      'span',
      null,
      'First crawled: ' + formatDateTime(data.first_crawled)
    );

    var last = el(
      'span',
      null,
      'Last crawled: ' + formatDateTime(data.last_crawled)
    );

    meta.appendChild(first);
    meta.appendChild(last);
    hero.appendChild(meta);

    discoveryEl.appendChild(hero);

    var pagesSection = el('section', 'discovery-pages');
    pagesSection.appendChild(el('h2', null, 'Discovered pages'));

    var list = el('div', 'discovery-list');

    var pages = Array.isArray(data.pages) ? data.pages : [];

    if (!pages.length) {
      list.appendChild(
        el(
          'p',
          'discovery-description',
          'No pages have been indexed for this website yet.'
        )
      );
    } else {
      pages.forEach(function (page, index) {
        var item = el('article', 'discovery-page');

        item.appendChild(
          el('div', 'discovery-number', String(index + 1))
        );

        var safeUrl = safeHttpUrl(page.url);

        if (safeUrl) {
          var link = document.createElement('a');
          link.className = 'discovery-page-title';
          link.href = safeUrl;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.textContent = page.title || page.url || 'Untitled page';
          item.appendChild(link);
        } else {
          item.appendChild(
            el(
              'div',
              'discovery-page-title',
              page.title || page.url || 'Untitled page'
            )
          );
        }

        if (page.url) {
          item.appendChild(
            el('div', 'discovery-url', page.url)
          );
        }

        if (page.description) {
          item.appendChild(
            el('p', 'discovery-description', page.description)
          );
        }

        if (page.language) {
          item.appendChild(
            el('div', 'discovery-details', 'Language: ' + page.language)
          );
        }

        if (page.crawled_at) {
          item.appendChild(
            el(
              'div',
              'discovery-details',
              'Crawled: ' + formatDateTime(page.crawled_at)
            )
          );
        }

        list.appendChild(item);
      });
    }

    pagesSection.appendChild(list);
    discoveryEl.appendChild(pagesSection);
  }

  if (searchForm && searchInput) {
    searchForm.addEventListener('submit', function (event) {
      event.preventDefault();

      var query = searchInput.value.trim();
      if (!query) return;

      window.location.href = '/?q=' + encodeURIComponent(query);
    });
  }

  if (websiteSubmitForm) {
    websiteSubmitForm.addEventListener('submit', async function (event) {
      event.preventDefault();

      var url = (websiteUrlInput.value || '').trim();

      if (!url) {
        setSubmitMessage('Enter your website URL.', 'error');
        websiteUrlInput.focus();
        return;
      }

      if (url.length > 2048) {
        setSubmitMessage('That URL is too long.', 'error');
        websiteUrlInput.focus();
        return;
      }

      if (!/^https?:\/\//i.test(url)) {
        setSubmitMessage(
          'Use a full URL starting with http:// or https://.',
          'error'
        );
        websiteUrlInput.focus();
        return;
      }

      setSubmitBusy(true);
      setSubmitMessage('Submitting your website…', 'busy');

      try {
        var response = await fetch('/api/submit', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ url: url })
        });

        var body = {};

        try {
          body = await response.json();
        } catch (error) {
          body = {};
        }

        if (!response.ok || !body.ok) {
          var message =
            body &&
            body.error &&
            body.error.message
              ? body.error.message
              : 'Could not submit this website right now.';

          setSubmitMessage(message, 'error');
          return;
        }

        if (body.submitted) {
          setSubmitMessage(
            'Website submitted successfully. Wadiya will discover and crawl it automatically.',
            'success'
          );
        } else {
          setSubmitMessage(
            'This website is already in the discovery queue.',
            'success'
          );
        }
      } catch (error) {
        setSubmitMessage(
          'Could not reach the website submission service.',
          'error'
        );
      } finally {
        setSubmitBusy(false);
      }
    });
  }

  var params = new URLSearchParams(window.location.search);
  var domain = params.get('domain');

  if (!domain) {
    setStatus('No website was specified.', true);
    return;
  }

  fetch('/api/discovery?domain=' + encodeURIComponent(domain))
    .then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) {
          var message =
            body &&
            body.error &&
            body.error.message
              ? body.error.message
              : 'Unable to load website discovery data.';
          throw new Error(message);
        }

        return body;
      });
    })
    .then(function (data) {
      setStatus('');
      render(data);
    })
    .catch(function (error) {
      setStatus(
        error && error.message
          ? error.message
          : 'Unable to load website discovery data.',
        true
      );
    });
})();
