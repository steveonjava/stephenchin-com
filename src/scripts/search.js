// Search over the Pagefind index that is built next to the pages. Without JavaScript the page points to /work/.
const form = document.getElementById('search-form');

if (form) {
  const status = document.getElementById('search-status');
  const list = document.getElementById('results');
  const more = document.getElementById('more');
  const PAGE = 20;
  const NAMES = ['kind', 'topic', 'year'];
  let pagefind = null;
  let token = 0;
  let pending = [];

  const q = form.elements.q;

  function fill(name, counts) {
    const select = form.elements[name];
    const keys = Object.keys(counts || {});
    keys.sort(name === 'year' ? (a, b) => (a === 'Unknown') - (b === 'Unknown') || (a < b ? 1 : -1) : (a, b) => a.localeCompare(b, 'en'));
    for (const key of keys) select.add(new Option(`${key} (${counts[key]})`, key));
  }

  // Keep only text and <mark> from the excerpt, so nothing else in it can become markup.
  function excerptNode(html) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const p = document.createElement('p');
    p.className = 'excerpt';
    for (const node of doc.body.childNodes) {
      if (node.nodeName === 'MARK') {
        const mark = document.createElement('mark');
        mark.textContent = node.textContent;
        p.append(mark);
      } else {
        p.append(document.createTextNode(node.textContent));
      }
    }
    return p;
  }

  async function renderMore(mine) {
    const slice = pending.splice(0, PAGE);
    const data = await Promise.all(slice.map((r) => r.data()));
    if (mine !== token) return;
    for (const item of data) {
      const li = document.createElement('li');
      li.className = 'record result';
      const h = document.createElement('h2');
      const a = document.createElement('a');
      a.href = item.url;
      a.textContent = (item.meta && item.meta.title) || item.url;
      h.append(a);
      li.append(h, excerptNode(item.excerpt || ''));
      list.append(li);
    }
    more.hidden = pending.length === 0;
  }

  async function run() {
    const mine = ++token;
    const term = q.value.trim();
    const filters = {};
    for (const name of NAMES) if (form.elements[name].value) filters[name] = form.elements[name].value;
    const params = new URLSearchParams();
    if (term) params.set('q', term);
    for (const [k, v] of Object.entries(filters)) params.set(k, v);
    history.replaceState(null, '', params.size ? `?${params}` : location.pathname);

    list.replaceChildren();
    more.hidden = true;
    if (!term && Object.keys(filters).length === 0) {
      status.textContent = 'Type a word, or choose a format, topic or year.';
      return;
    }
    const res = await pagefind.search(term || null, { filters });
    if (mine !== token) return;
    const n = res.results.length;
    status.textContent =
      n === 0
        ? `No results${term ? ` for \u201c${term}\u201d` : ''}. Try another word or remove a filter.`
        : `${n} ${n === 1 ? 'result' : 'results'}${term ? ` for \u201c${term}\u201d` : ''}.`;
    pending = res.results;
    await renderMore(mine);
  }

  let timer = 0;
  q.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(run, 200);
  });
  form.addEventListener('change', run);
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    clearTimeout(timer);
    run();
  });
  more.addEventListener('click', () => renderMore(token));

  (async () => {
    try {
      const path = '/pagefind/pagefind.js';
      pagefind = await import(/* @vite-ignore */ path);
      await pagefind.options({ excerptLength: 26 });
      const filters = await pagefind.filters();
      for (const name of NAMES) fill(name, filters[name]);
    } catch {
      status.textContent = 'Search could not load. Browse the full list instead.';
      return;
    }
    const params = new URLSearchParams(location.search);
    q.value = params.get('q') || '';
    for (const name of NAMES) {
      const want = params.get(name);
      if (want && Array.from(form.elements[name].options).some((o) => o.value === want)) form.elements[name].value = want;
    }
    form.hidden = false;
    await run();
  })();
}
