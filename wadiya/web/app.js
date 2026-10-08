(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var form = $('searchForm'), input = $('q'), statusEl = $('status'), resultsEl = $('results'),
      pagerEl = $('pager'), flow = $('flow'), searchModes = $('searchModes'), controller = null;

  function setSearchModes(visible) {
    if (!searchModes) return;
    searchModes.hidden = !visible;
  }

  function setActiveSearchMode(mode) {
    if (!searchModes) return;

    searchModes.querySelectorAll('.search-mode').forEach(function (link) {
      var active = link.getAttribute('data-search-mode') === mode;
      link.classList.toggle('is-active', active);
      link.setAttribute('aria-current', active ? 'page' : 'false');
    });
  }

  if (searchModes) {
    searchModes.addEventListener('click', function (e) {
      var link = e.target.closest('.search-mode');
      if (!link) return;

      e.preventDefault();

      var mode = link.getAttribute('data-search-mode') || 'web';
      var q = (input && input.value || '').trim();

      setActiveSearchMode(mode);

      if (mode === 'web') {
        if (q) {
          history.replaceState(
            { q: q, page: 1, mode: 'web' },
            '',
            urlFor(q, 1, 'web')
          );
          search(q, 1, false);
        }
        return;
      }

      if (mode === 'market') {
        history.pushState(
          { q: q, page: 1, mode: 'market' },
          '',
          '/search?q=' + encodeURIComponent(q) + '&type=market'
        );

        renderMarketHome();
        return;
      }

      var target = '/search?q=' + encodeURIComponent(q) + '&type=' + encodeURIComponent(mode);
      history.pushState(
        { q: q, page: 1, mode: mode },
        '',
        target
      );

      if (q) {
        search(q, 1, false, mode);
      } else {
        setStatus('', false);
        resultsEl.textContent = '';
        pagerEl.textContent = '';
      }
    });
  }

  // ---- pure helpers (kept free of DOM so they are easy to reason about) ----
  function queryTerms(q) {
    var m = (q || '').toLowerCase().match(/[\p{L}\p{M}\p{N}\u200D]+/gu) || [], seen = {}, out = [];
    m.forEach(function (t) { if (!seen[t]) { seen[t] = 1; out.push(t); } });
    return out;
  }
  function stem(t) { return t.length <= 4 ? t : t.slice(0, Math.max(4, t.length - 2)); }
  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function splitForHighlight(text, terms) {            // -> [{text, hit}]
    if (!terms.length) return [{ text: text, hit: false }];
    var re = new RegExp('(^|[^\\p{L}\\p{M}\\p{N}\\u200D])(' + terms.map(function (t) { return escapeRe(stem(t)); }).join('|') + ')([\\p{L}\\p{M}\\p{N}\\u200D]*)', 'giu');
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
  function crumbs(u) {                                   // https://a.org/x/y.html -> ' › x › y'
    try {
      var parts = new URL(u).pathname.split('/').filter(Boolean).map(function (p) { return decodeURIComponent(p).replace(/\.html?$/i, ''); });
      return parts.length ? ' › ' + parts.slice(0, 3).join(' › ') : '';
    } catch (e) { return ' · ' + u; }
  }
  function urlFor(q, page, mode) {
    var url = '/search?q=' + encodeURIComponent(q);
    if (mode && mode !== 'web') url += '&type=' + encodeURIComponent(mode);
    if (page > 1) url += '&page=' + page;
    return url;
  }

  // ---- rendering (textContent only: crawled content is never interpreted as HTML) ----
  function renderImageResult(r) {
    var card = el('article', 'image-card');
    var imageHref = safeHttpUrl(r.image_url);
    var sourceHref = safeHttpUrl(r.source_page_url);

    if (imageHref) {
      var imageLink = el('a', 'image-card-media');
      imageLink.href = imageHref;
      imageLink.target = '_blank';
      imageLink.rel = 'noopener noreferrer nofollow';

      var img = document.createElement('img');
      img.src = imageHref;
      img.alt = r.alt_text || r.title || 'Image result';
      img.loading = 'lazy';
      img.decoding = 'async';

      img.addEventListener('error', function () {
        imageLink.classList.add('image-load-error');
        img.removeAttribute('src');
        img.alt = '';
        imageLink.appendChild(el('span', 'image-fallback', 'Image unavailable'));
      }, { once: true });

      imageLink.appendChild(img);
      card.appendChild(imageLink);
    }

    var body = el('div', 'image-card-body');
    var title = r.title || r.source_page_url || 'Image result';

    if (sourceHref) {
      var source = el('a', 'image-card-title', title);
      source.href = sourceHref;
      source.target = '_blank';
      source.rel = 'noopener noreferrer nofollow';
      body.appendChild(source);
    } else {
      body.appendChild(el('div', 'image-card-title', title));
    }

    if (r.source_domain) {
      body.appendChild(el('div', 'image-card-domain', r.source_domain));
    } else if (sourceHref) {
      try {
        body.appendChild(el('div', 'image-card-domain', new URL(sourceHref).hostname));
      } catch (e) {}
    }

    card.appendChild(body);
    return card;
  }


  function renderVideoResult(r) {
    var card = el('article', 'video-card');
    var videoUrl = safeHttpUrl(r.video_url);
    var sourceHref = safeHttpUrl(r.source_page_url);

    if (!videoUrl) return card;

    var media = el('div', 'video-card-media');

    if (r.kind === 'embed') {
      var allowedEmbed =
        /^https:\/\/(?:www\.)?youtube\.com\/embed\//i.test(videoUrl) ||
        /^https:\/\/(?:www\.)?youtube-nocookie\.com\/embed\//i.test(videoUrl) ||
        /^https:\/\/player\.vimeo\.com\/video\//i.test(videoUrl);

      if (allowedEmbed) {
        var iframe = document.createElement('iframe');
        iframe.src = videoUrl;
        iframe.title = r.title || 'Video result';
        iframe.loading = 'lazy';
        iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
        iframe.setAttribute('allowfullscreen', '');
        iframe.referrerPolicy = 'strict-origin-when-cross-origin';
        media.appendChild(iframe);
      } else {
        media.appendChild(el('div', 'video-fallback', 'Video provider unavailable'));
      }
    } else {
      var video = document.createElement('video');
      video.controls = true;
      video.preload = 'metadata';
      video.playsInline = true;

      var posterUrl = '';
      if (r.thumbnail_url) {
        posterUrl = safeHttpUrl(r.thumbnail_url) || '';
        if (posterUrl) {
          video.poster = posterUrl;
        }
      }

      var source = document.createElement('source');
      source.src = videoUrl;

      if (/\.webm(?:$|\?)/i.test(videoUrl)) {
        source.type = 'video/webm';
      } else if (/\.mp4(?:$|\?)/i.test(videoUrl)) {
        source.type = 'video/mp4';
      }

      video.appendChild(source);
      media.appendChild(video);

      var fallback = el('div', 'video-fallback');

      if (posterUrl) {
        var fallbackImage = document.createElement('img');
        fallbackImage.src = posterUrl;
        fallbackImage.alt = '';
        fallbackImage.loading = 'lazy';
        fallbackImage.setAttribute('aria-hidden', 'true');
        fallback.appendChild(fallbackImage);
      }

      var fallbackContent = el('div', 'video-fallback-content');
      fallbackContent.appendChild(
        el('div', 'video-fallback-message', 'This video can\'t be played here.')
      );

      var fallbackLink = el('a', 'video-direct-link', 'Open original video');
      fallbackLink.href = videoUrl;
      fallbackLink.target = '_blank';
      fallbackLink.rel = 'noopener noreferrer nofollow';
      fallbackContent.appendChild(fallbackLink);

      fallback.appendChild(fallbackContent);
      fallback.hidden = true;
      media.appendChild(fallback);

      var playbackReady = false;
      var fallbackShown = false;

      function showVideoFallback() {
        if (playbackReady || fallbackShown) return;
        fallbackShown = true;
        video.hidden = true;
        fallback.hidden = false;
      }

      function markPlaybackReady() {
        playbackReady = true;
      }

      video.addEventListener('loadeddata', markPlaybackReady);
      video.addEventListener('canplay', markPlaybackReady);
      video.addEventListener('playing', markPlaybackReady);

      video.addEventListener('error', showVideoFallback);
      video.addEventListener('stalled', function () {
        if (video.error) {
          showVideoFallback();
        }
      });

      window.setTimeout(function () {
        if (!playbackReady && (
          video.error ||
          video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA
        )) {
          showVideoFallback();
        }
      }, 5000);

      video.load();
    }

    card.appendChild(media);

    var body = el('div', 'video-card-body');
    var title = r.title || r.source_page_url || 'Video result';

    if (sourceHref) {
      var source = el('a', 'video-card-title', title);
      source.href = sourceHref;
      source.target = '_blank';
      source.rel = 'noopener noreferrer nofollow';
      body.appendChild(source);
    } else {
      body.appendChild(el('div', 'video-card-title', title));
    }

    if (r.source_domain) {
      body.appendChild(el('div', 'video-card-domain', r.source_domain));
    } else if (sourceHref) {
      try {
        body.appendChild(
          el('div', 'video-card-domain', new URL(sourceHref).hostname)
        );
      } catch (e) {}
    }

    card.appendChild(body);
    return card;
  }

  function renderFinanceChart(points) {
    if (!points || !points.length) {
      return el(
        'div',
        'finance-chart-placeholder',
        'Historical price data unavailable'
      );
    }

    var width = 900;
    var height = 260;
    var padLeft = 8;
    var padRight = 8;
    var padTop = 18;
    var padBottom = 28;

    var values = points.map(function (point) {
      return Number(point.close);
    }).filter(function (value) {
      return Number.isFinite(value);
    });

    if (!values.length) {
      return el(
        'div',
        'finance-chart-placeholder',
        'Historical price data unavailable'
      );
    }

    var min = Math.min.apply(Math, values);
    var max = Math.max.apply(Math, values);

    if (min === max) {
      min -= 1;
      max += 1;
    }

    var innerWidth = width - padLeft - padRight;
    var innerHeight = height - padTop - padBottom;

    function x(index) {
      if (points.length === 1) return width / 2;
      return padLeft + (index / (points.length - 1)) * innerWidth;
    }

    function y(value) {
      return padTop + ((max - value) / (max - min)) * innerHeight;
    }

    var svg = document.createElementNS(
      'http://www.w3.org/2000/svg',
      'svg'
    );

    svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Historical price chart');
    svg.classList.add('finance-chart-svg');

    var pathData = '';

    points.forEach(function (point, index) {
      var value = Number(point.close);
      if (!Number.isFinite(value)) return;

      var command = pathData ? 'L' : 'M';
      pathData += command + ' ' + x(index).toFixed(2) + ' ' + y(value).toFixed(2) + ' ';
    });

    var path = document.createElementNS(
      'http://www.w3.org/2000/svg',
      'path'
    );

    path.setAttribute('d', pathData.trim());
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'currentColor');
    path.setAttribute('stroke-width', '2.5');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    path.classList.add('finance-chart-line');

    svg.appendChild(path);

    var latest = values[values.length - 1];

    var latestDot = document.createElementNS(
      'http://www.w3.org/2000/svg',
      'circle'
    );

    latestDot.setAttribute(
      'cx',
      x(points.length - 1).toFixed(2)
    );
    latestDot.setAttribute(
      'cy',
      y(latest).toFixed(2)
    );
    latestDot.setAttribute('r', '4');
    latestDot.setAttribute('fill', 'currentColor');
    latestDot.classList.add('finance-chart-dot');

    svg.appendChild(latestDot);

    var minLabel = document.createElementNS(
      'http://www.w3.org/2000/svg',
      'text'
    );

    minLabel.setAttribute('x', String(padLeft));
    minLabel.setAttribute('y', String(height - 6));
    minLabel.textContent = points[0].date;
    minLabel.classList.add('finance-chart-axis-label');
    svg.appendChild(minLabel);

    var maxLabel = document.createElementNS(
      'http://www.w3.org/2000/svg',
      'text'
    );

    maxLabel.setAttribute('x', String(width - padRight));
    maxLabel.setAttribute('y', String(height - 6));
    maxLabel.setAttribute('text-anchor', 'end');
    maxLabel.textContent = points[points.length - 1].date;
    maxLabel.classList.add('finance-chart-axis-label');
    svg.appendChild(maxLabel);

    var priceLabel = document.createElementNS(
      'http://www.w3.org/2000/svg',
      'text'
    );

    priceLabel.setAttribute('x', String(width - padRight));
    priceLabel.setAttribute('y', String(Math.max(14, y(latest) - 10)));
    priceLabel.setAttribute('text-anchor', 'end');
    priceLabel.textContent = latest.toFixed(2);
    priceLabel.classList.add('finance-chart-price-label');
    svg.appendChild(priceLabel);

    return svg;
  }

  function loadFinanceHistory(card, symbol, range) {
    var chart = card.querySelector('.finance-chart-shell');
    if (!chart || !symbol) return;

    var chartBody = chart.querySelector('.finance-chart-body');
    if (!chartBody) return;

    chartBody.textContent = 'Loading price history…';

    fetch(
      '/api/finance/history?symbol=' +
      encodeURIComponent(symbol) +
      '&range=' +
      encodeURIComponent(range),
      {
        headers: { Accept: 'application/json' }
      }
    )
      .then(function (response) {
        return response.json().catch(function () {
          return {};
        }).then(function (body) {
          return {
            ok: response.ok,
            body: body
          };
        });
      })
      .then(function (result) {
        if (!result.ok || !Array.isArray(result.body.points)) {
          chartBody.textContent = 'Historical price data unavailable';
          return;
        }

        chartBody.textContent = '';

        if (!result.body.points.length) {
          chartBody.textContent = 'Historical price data unavailable';
          return;
        }

        chartBody.appendChild(
          renderFinanceChart(result.body.points)
        );
      })
      .catch(function () {
        chartBody.textContent = 'Historical price data unavailable';
      });
  }

  function renderFinanceSummary(results) {
    if (!results || !results.length) return null;

    var r = results[0];
    var card = el('section', 'finance-summary');
    card.setAttribute('aria-label', 'Finance summary');

    var header = el('div', 'finance-summary-header');

    var identity = el('div', 'finance-summary-identity');

    var symbol = el('div', 'finance-summary-symbol');
    symbol.textContent = r.symbol || '';
    identity.appendChild(symbol);

    var name = el('div', 'finance-summary-name');
    name.textContent = r.name || r.symbol || 'Finance';
    identity.appendChild(name);

    if (r.region || r.currency) {
      var location = [
        r.region,
        r.currency ? 'Currency: ' + r.currency : ''
      ].filter(Boolean).join(' · ');

      identity.appendChild(
        el('div', 'finance-summary-location', location)
      );
    }

    header.appendChild(identity);

    var quote = el('div', 'finance-summary-quote');

    if (r.price !== null && r.price !== undefined) {
      quote.appendChild(
        el('div', 'finance-summary-price', String(r.price))
      );

      var changeParts = [];

      if (r.change !== null && r.change !== undefined) {
        changeParts.push(String(r.change));
      }

      if (r.change_percent) {
        changeParts.push(String(r.change_percent));
      }

      if (changeParts.length) {
        quote.appendChild(
          el('div', 'finance-summary-change', changeParts.join(' · '))
        );
      }
    } else {
      quote.appendChild(
        el(
          'div',
          'finance-summary-unavailable',
          'Live quote unavailable'
        )
      );
    }

    header.appendChild(quote);
    card.appendChild(header);

    var chart = el('div', 'finance-chart-shell');
    chart.setAttribute('aria-label', 'Price chart');

    var chartLabel = el(
      'div',
      'finance-chart-label',
      'Price history'
    );
    chart.appendChild(chartLabel);

    var chartBody = el(
      'div',
      'finance-chart-body',
      'Loading price history…'
    );
    chart.appendChild(chartBody);

    card.appendChild(chart);

    var ranges = el('div', 'finance-chart-ranges');

    [
      '1D',
      '1W',
      '1M',
      '3M',
      '6M',
      '1Y',
      '5Y',
      'MAX'
    ].forEach(function (range) {
      var button = el(
        'button',
        'finance-chart-range' +
          (range === '1M' ? ' is-active' : ''),
        range
      );

      button.type = 'button';
      button.setAttribute(
        'aria-label',
        'Price history range ' + range
      );

      button.addEventListener('click', function () {
        ranges.querySelectorAll('.finance-chart-range').forEach(
          function (item) {
            item.classList.remove('is-active');
          }
        );

        button.classList.add('is-active');
        loadFinanceHistory(card, r.symbol, range);
      });

      ranges.appendChild(button);
    });

    card.appendChild(ranges);

    loadFinanceHistory(card, r.symbol, '1M');

    return card;
  }


  function renderFinanceResult(r) {
    var card = el('article', 'result finance-result');
    var site = el('div', 'site');
    site.appendChild(el('i', 'fav'));
    site.appendChild(el('b', null, r.symbol || ''));
    if (r.type) site.appendChild(document.createTextNode(' · ' + r.type));
    card.appendChild(site);

    var h = el('h2', null, r.name || r.symbol || 'Finance result');
    card.appendChild(h);

    var meta = el('div', 'finance-meta');

    if (r.region) {
      meta.appendChild(el('div', 'finance-region', r.region));
    }

    if (r.currency) {
      meta.appendChild(el('div', 'finance-currency', 'Currency: ' + r.currency));
    }

    if (r.market_open || r.market_close || r.timezone) {
      var market = [];
      if (r.market_open && r.market_close) {
        market.push(r.market_open + '–' + r.market_close);
      } else if (r.market_open) {
        market.push('Open ' + r.market_open);
      } else if (r.market_close) {
        market.push('Close ' + r.market_close);
      }
      if (r.timezone) market.push(r.timezone);
      meta.appendChild(el('div', 'finance-market', market.join(' · ')));
    }

    if (r.price !== null && r.price !== undefined) {
      var quote = [];
      quote.push(String(r.price));
      if (r.change !== null && r.change !== undefined) {
        quote.push(String(r.change));
      }
      if (r.change_percent) {
        quote.push(String(r.change_percent));
      }
      meta.appendChild(el('div', 'finance-quote', quote.join(' · ')));
    }

    if (r.match_score !== null && r.match_score !== undefined) {
      meta.appendChild(
        el('div', 'finance-score', 'Match score: ' + String(r.match_score))
      );
    }

    card.appendChild(meta);
    return card;
  }

  function renderCryptoResult(r) {
    var card = el('article', 'result crypto-result');

    var header = el('div', 'crypto-result-header');

    var symbol = el(
      'div',
      'crypto-symbol',
      r.symbol || ''
    );
    header.appendChild(symbol);

    var rankText = r.rank != null
      ? 'Rank #' + String(r.rank)
      : '';

    if (rankText) {
      header.appendChild(
        el('div', 'crypto-rank', rankText)
      );
    }

    card.appendChild(header);

    var name = el(
      'h2',
      'crypto-name',
      r.name || r.symbol || 'Crypto result'
    );
    card.appendChild(name);

    if (r.asset_type) {
      card.appendChild(
        el('div', 'crypto-type', r.asset_type)
      );
    }

    var quote = [];

    if (r.price != null) {
      quote.push(
        String(r.price) +
        (r.currency ? ' ' + r.currency : '')
      );
    }

    if (r.change != null) {
      quote.push(String(r.change));
    }

    if (r.change_percent) {
      quote.push(String(r.change_percent));
    }

    if (quote.length) {
      card.appendChild(
        el('div', 'crypto-quote', quote.join(' · '))
      );
    } else {
      card.appendChild(
        el('div', 'crypto-quote-unavailable', 'Price data unavailable')
      );
    }

    return card;
  }


  function renderMapResult(r, terms) {
    var li = el("article", "result map-result"), site = el("div", "site");
    site.appendChild(el("i", "fav"));
    site.appendChild(el("b", null, r.domain));
    site.appendChild(document.createTextNode(crumbs(r.url)));

    var h = el("h2"), href = safeHttpUrl(r.url), a = el(href ? "a" : "span");
    a.textContent = r.title || r.url;
    if (href) {
      a.href = href;
      a.target = "_blank";
      a.rel = "noopener noreferrer nofollow";
    }
    h.appendChild(a);

    var p = el("p");
    splitForHighlight(r.snippet || "", terms).forEach(function (part) {
      p.appendChild(part.hit ? el("mark", null, part.text) : document.createTextNode(part.text));
    });

    var meta = el("div", "map-meta");
    var place = [r.address, r.city, r.region, r.country].filter(Boolean).join(", ");
    if (place) meta.appendChild(el("div", "map-location", place));
    meta.appendChild(el("div", "map-coordinates", r.latitude + ", " + r.longitude));

    var discover = el("a", "discover-link", "Discover website");
    discover.href = "/discovery?domain=" + encodeURIComponent(r.domain);
    discover.setAttribute("aria-label", "Discover " + (r.domain || "this website"));

    li.appendChild(h);
    li.appendChild(site);
    li.appendChild(p);
    li.appendChild(meta);
    li.appendChild(discover);
    return li;
  }

  function renderResult(r, terms) {
    var li = el('article', 'result'), site = el('div', 'site');
    site.appendChild(el('i', 'fav'));
    site.appendChild(el('b', null, r.domain)); site.appendChild(document.createTextNode(crumbs(r.url)));
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
  function renderPager(d, mode) {
    pagerEl.textContent = '';
    if (d.total_pages <= 1) return;
    var prev = d.page > 1 ? el('a', null, '← Previous') : el('span', 'off', '← Previous');
    var next = d.page < d.total_pages ? el('a', null, 'Next →') : el('span', 'off', 'Next →');
    if (d.page > 1) {
      prev.href = urlFor(d.query, d.page - 1, mode);
      prev.dataset.page = d.page - 1;
    }
    if (d.page < d.total_pages) {
      next.href = urlFor(d.query, d.page + 1, mode);
      next.dataset.page = d.page + 1;
    }
    pagerEl.appendChild(prev);
    pagerEl.appendChild(el('span', null, 'Page ' + d.page + ' of ' + d.total_pages));
    pagerEl.appendChild(next);
  }

  function renderMarketHome() {
    resultsEl.classList.remove('image-results', 'video-results');
    resultsEl.textContent = '';
    pagerEl.textContent = '';
    setStatus('', false);

    var wrapper = el('section', 'market-home');

    var intro = el('div', 'market-home-intro');
    intro.appendChild(el('h1', null, 'Market'));
    intro.appendChild(
      el(
        'p',
        null,
        'Explore stock markets and cryptocurrency markets in one place.'
      )
    );
    wrapper.appendChild(intro);

    var grid = el('div', 'market-home-grid');

    var stock = el('article', 'market-card');
    stock.appendChild(el('div', 'market-card-kicker', 'Stocks'));
    stock.appendChild(el('h2', null, 'Stock Market'));
    stock.appendChild(
      el(
        'p',
        null,
        'Search companies, stocks, prices, market information, and quotes.'
      )
    );

    var stockButton = el('button', 'market-card-button', 'Explore Stock Market');
    stockButton.type = 'button';
    stockButton.addEventListener('click', function () {
      var q = (input && input.value || '').trim();

      setActiveSearchMode('finance');

      history.pushState(
        { q: q, page: 1, mode: 'finance' },
        '',
        '/search?q=' + encodeURIComponent(q) + '&type=finance'
      );

      if (q) {
        search(q, 1, false, 'finance');
      } else {
        setStatus('Enter a stock or company name in the search box.', false);
        resultsEl.textContent = '';
        pagerEl.textContent = '';
      }
    });

    stock.appendChild(stockButton);
    grid.appendChild(stock);

    var crypto = el('article', 'market-card');
    crypto.appendChild(el('div', 'market-card-kicker', 'Digital assets'));
    crypto.appendChild(el('h2', null, 'Crypto Market'));
    crypto.appendChild(
      el(
        'p',
        null,
        'Search cryptocurrencies and view the latest cached market quotes.'
      )
    );

    var cryptoButton = el('button', 'market-card-button', 'Explore Crypto Market');
    cryptoButton.type = 'button';
    cryptoButton.addEventListener('click', function () {
      var q = (input && input.value || '').trim();

      setActiveSearchMode('crypto');

      history.pushState(
        { q: q, page: 1, mode: 'crypto' },
        '',
        '/search?q=' + encodeURIComponent(q) + '&type=crypto'
      );

      if (q) {
        search(q, 1, false, 'crypto');
      } else {
        setStatus('Enter a cryptocurrency name or symbol in the search box.', false);
        resultsEl.textContent = '';
        pagerEl.textContent = '';
      }
    });

    crypto.appendChild(cryptoButton);
    grid.appendChild(crypto);

    wrapper.appendChild(grid);
    resultsEl.appendChild(wrapper);
  }

  function search(q, page, push, mode) {
    q = (q || '').trim(); page = page || 1; mode = mode || 'web';
    if (!q) return;
    document.body.classList.remove('home'); input.value = q; document.title = q + ' – Wadiya.com';
    setActiveSearchMode(mode);
    if (push) history.pushState({ q: q, page: page, mode: mode }, '', urlFor(q, page, mode));
    if (controller) controller.abort();
    controller = new AbortController();
    resultsEl.textContent = '';
    resultsEl.classList.toggle('image-results', mode === 'images');
    resultsEl.classList.toggle('video-results', mode === 'videos');
    pagerEl.textContent = '';
    setStatus('Searching…', false);
    setBusy(true);
    setSearchModes(true);

    fetch('/api/search?q=' + encodeURIComponent(q) + '&page=' + page + '&type=' + encodeURIComponent(mode), { signal: controller.signal, headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        setBusy(false);
        if (!res.ok) { setStatus((res.body.error && res.body.error.message) || 'Something went wrong.', true); return; }
        var d = res.body, terms = queryTerms(d.query);
        if (!d.results.length) {
          setStatus('', false);
          var box = el('div', 'empty');
          box.appendChild(el('h2', null, d.result_count ? 'No more results' : 'No results for “' + d.query + '”'));
          box.appendChild(el('p', null, d.result_count ? 'Go back to the previous page.' : 'Try different or fewer words. Wadiya only searches the pages it has crawled so far.'));
          resultsEl.appendChild(box);
          renderPager(d, mode);
          return;
        }

        var count = 'About ' + d.result_count.toLocaleString() + (d.result_count_exact ? '' : '+') + ' result' + (d.result_count === 1 ? '' : 's') +
          ' (' + (d.latency_ms / 1000).toFixed(3) + ' seconds)';
        setStatus(count, false);

        if (mode === 'images') {
          resultsEl.classList.add('image-results');
          resultsEl.classList.remove('video-results');
          d.results.forEach(function (r) { resultsEl.appendChild(renderImageResult(r)); });
        } else if (mode === 'videos') {
          resultsEl.classList.add('video-results');
          resultsEl.classList.remove('image-results');
          d.results.forEach(function (r) { resultsEl.appendChild(renderVideoResult(r)); });
        } else if (mode === 'maps') {
          resultsEl.classList.remove('image-results', 'video-results');
          d.results.forEach(function (r) { resultsEl.appendChild(renderMapResult(r, terms)); });
        } else if (mode === 'finance') {
          resultsEl.classList.remove('image-results', 'video-results');

          var financeSummary = renderFinanceSummary(d.results);
          if (financeSummary) {
            resultsEl.appendChild(financeSummary);
          }

          d.results.forEach(function (r) {
            resultsEl.appendChild(renderFinanceResult(r));
          });
        } else if (mode === 'crypto') {
          resultsEl.classList.remove('image-results', 'video-results');

          d.results.forEach(function (r) {
            resultsEl.appendChild(renderCryptoResult(r));
          });
        } else {
          resultsEl.classList.remove('image-results', 'video-results');
          d.results.forEach(function (r) { resultsEl.appendChild(renderResult(r, terms)); });
        }

        renderPager(d, mode);
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
    e.preventDefault();
    var currentUrl = new URL(window.location.href);
    var currentMode = currentUrl.searchParams.get('type') || 'web';
    search(input.value, parseInt(a.dataset.page, 10), true, currentMode);
  });
  $('markLink').addEventListener('click', function (e) {
    e.preventDefault(); if (controller) controller.abort(); setBusy(false); history.pushState({}, '', '/');
    document.body.classList.add('home'); input.value = ''; setStatus(''); resultsEl.textContent = ''; resultsEl.classList.remove('image-results'); pagerEl.textContent = ''; setSearchModes(false); document.title = 'Wadiya.com'; input.focus();
  });
  window.addEventListener('popstate', function () { boot(false); });

  function boot(push) {
    var p = new URLSearchParams(location.search),
        q = p.get('q'),
        page = parseInt(p.get('page') || '1', 10),
        mode = p.get('type') || 'web';

    if (q && q.trim()) {
      if (mode === 'web') {
        search(q, page > 0 ? page : 1, false, 'web');
      } else {
        document.body.classList.remove('home');
        input.value = q.trim();
        document.title = q.trim() + ' – Wadiya.com';
        setSearchModes(true);
        setActiveSearchMode(mode);
        if (mode === 'market') {
          renderMarketHome();
        } else if (mode === 'images' || mode === 'videos' || mode === 'documents' || mode === 'news' || mode === 'finance' || mode === 'crypto') {
          search(q.trim(), page > 0 ? page : 1, false, mode);
        } else {
          setStatus(mode.charAt(0).toUpperCase() + mode.slice(1) + ' search is coming next.', false);
          resultsEl.textContent = '';
          pagerEl.textContent = '';
        }
      }
    } else {
      document.body.classList.add('home');
      input.value = '';
      setStatus('');
      resultsEl.textContent = '';
      pagerEl.textContent = '';
      setSearchModes(false);
      setActiveSearchMode('web');
    }
  }
  boot();
})();
