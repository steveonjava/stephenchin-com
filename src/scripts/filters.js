// Progressive enhancement for the record lists. Without this script the full list stays visible.
const form = document.getElementById('filters');
const list = document.getElementById('records');

if (form && list) {
  const rows = Array.from(list.querySelectorAll('.record'));
  const status = document.getElementById('list-status');
  const empty = document.getElementById('list-empty');
  const kinds = new Map();
  const topics = new Map();
  const roles = new Map();
  const years = new Set();

  for (const row of rows) {
    kinds.set(row.dataset.kind, row.dataset.kindLabel);
    if (row.dataset.role !== 'none') roles.set(row.dataset.role, row.dataset.roleLabel);
    years.add(row.dataset.year);
    const ids = row.dataset.topics.split(' ');
    const labels = Array.from(row.querySelectorAll('.chips a')).map((a) => a.textContent);
    ids.forEach((id, i) => topics.set(id, labels[i] || id));
  }

  function fill(name, entries) {
    const select = form.elements[name];
    for (const [value, label] of entries) select.add(new Option(label, value));
  }
  const byLabel = (a, b) => a[1].localeCompare(b[1], 'en');
  fill('kind', [...kinds].sort(byLabel));
  fill('topic', [...topics].sort(byLabel));
  fill('role', [...roles].sort(byLabel));
  fill('year', [...years].sort((a, b) => (a === 'unknown') - (b === 'unknown') || (a < b ? 1 : -1)).map((y) => [y, y === 'unknown' ? 'Date unknown' : y]));

  const params = new URLSearchParams(location.search);
  for (const name of ['kind', 'topic', 'year', 'role']) {
    const want = params.get(name);
    if (want && Array.from(form.elements[name].options).some((o) => o.value === want)) form.elements[name].value = want;
  }

  function apply() {
    const v = { kind: form.elements.kind.value, topic: form.elements.topic.value, year: form.elements.year.value, role: form.elements.role.value };
    let shown = 0;
    for (const row of rows) {
      const ok =
        (!v.kind || row.dataset.kind === v.kind) &&
        (!v.topic || row.dataset.topics.split(' ').includes(v.topic)) &&
        (!v.year || row.dataset.year === v.year) &&
        (!v.role || row.dataset.role === v.role);
      row.hidden = !ok;
      if (ok) shown += 1;
    }
    status.textContent = `Showing ${shown} of ${rows.length} records.`;
    empty.hidden = shown !== 0;
    const next = new URLSearchParams();
    for (const [k, val] of Object.entries(v)) if (val) next.set(k, val);
    history.replaceState(null, '', next.size ? `?${next}` : location.pathname);
  }

  form.addEventListener('change', apply);
  form.addEventListener('submit', (e) => e.preventDefault());
  form.hidden = false;
  apply();
}
