// Pure helpers for catalog records. No Astro imports, so Node can test them directly.

export interface DateEntry { value: string; type: string; source?: string }
export type Relation = { type: string; target: string | string[]; note?: string };
export type AuditItem =
  | { kind: 'flag'; text: string; checked: string }
  | { kind: 'fix'; field: string; evidence: string; checked: string; from?: unknown; to?: unknown };
export interface RecordData {
  title: string;
  kind: string;
  topics: string[];
  source_ids: string[];
  url: string;
  year: number | null;
  stephen_role: string | null;
  review_status: string;
  verification_status: string;
  rights_status: string;
  event: string | null;
  note?: string;
  date?: DateEntry;
  dates?: DateEntry[];
  platform_video_id?: string;
  page_title_observed?: string;
  license_observed?: string;
  relations?: Relation[];
  audit?: AuditItem[];
  summary?: string;
  featured_rank?: number;
}
export interface Rec { id: string; origin: 'works' | 'candidates'; data: RecordData }

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

export function precision(value: string): 'year' | 'month' | 'day' {
  return value.length === 4 ? 'year' : value.length === 7 ? 'month' : 'day';
}

// Never fills in a missing month or day.
export function formatDate(value: string): string {
  const [y, m, d] = value.split('-');
  if (!m) return y;
  const month = MONTHS[Number(m) - 1];
  return d ? `${Number(d)} ${month} ${y}` : `${month} ${y}`;
}

const DATE_LABELS: Record<string, string> = {
  event: 'Event date',
  publication: 'Published',
  publisher_publication: 'Published',
  guest_index_publication: 'Listed by the publisher',
  indexed_publication: 'Listed by the publisher',
  publisher_label_recorded_at: 'Publisher date label',
  upload: 'Video uploaded',
  planned_publication: 'Planned',
  repository_created: 'Repository created',
  repository_last_push: 'Repository last pushed',
};

export function dateTypeLabel(type: string): string {
  return DATE_LABELS[type] ?? type.replace(/_/g, ' ');
}

// Date types that describe the work itself, best first. Repository dates and planned dates never stand in for it.
const WORK_DATE_ORDER = ['event', 'publication', 'publisher_publication', 'guest_index_publication', 'indexed_publication', 'publisher_label_recorded_at', 'upload'];

export function allDates(d: RecordData): DateEntry[] {
  return [...(d.date ? [d.date] : []), ...(d.dates ?? [])];
}

export function workDate(d: RecordData): DateEntry | null {
  const all = allDates(d);
  for (const t of WORK_DATE_ORDER) {
    const hit = all.find((x) => x.type === t);
    if (hit) return hit;
  }
  return null;
}

// The date text for a list row. It always says what kind of date it is when that is not obvious.
export function rowDate(d: RecordData): string {
  const w = workDate(d);
  if (w) {
    const text = formatDate(w.value);
    return w.type === 'upload' ? `Uploaded ${text}` : w.type === 'publisher_label_recorded_at' ? `${text} (publisher label)` : text;
  }
  const planned = allDates(d).find((x) => x.type === 'planned_publication');
  if (planned) return `Planned ${formatDate(planned.value)}`;
  if (d.year) return String(d.year);
  return 'Date unknown';
}

// Sortable text, newest first when compared descending. A missing part sorts as the start of the unit.
export function sortKey(d: RecordData): string {
  const w = workDate(d);
  if (w) {
    const [y, m = '00', day = '00'] = w.value.split('-');
    return `${y}-${m}-${day}`;
  }
  const planned = allDates(d).find((x) => x.type === 'planned_publication');
  if (planned) {
    const [y, m = '00', day = '00'] = planned.value.split('-');
    return `${y}-${m}-${day}`;
  }
  return d.year ? `${d.year}-00-00` : '0000-00-00';
}

export function sortRecords(recs: Rec[]): Rec[] {
  return [...recs].sort((a, b) => {
    const ka = sortKey(a.data);
    const kb = sortKey(b.data);
    if (ka !== kb) return ka < kb ? 1 : -1;
    return a.data.title.localeCompare(b.data.title, 'en');
  });
}

const KINDS: Record<string, string> = {
  article: 'Article', book: 'Book', code: 'Code', community: 'Community', interview: 'Interview',
  project: 'Project', talk: 'Talk', video: 'Video',
};
export function kindLabel(kind: string): string {
  return KINDS[kind] ?? kind;
}

export function roleLabel(role: string | null): string | null {
  if (!role) return null;
  const text = role.replace(/-/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function sourceHost(url: string): string {
  return new URL(url).hostname.replace(/^www\./, '');
}

// Host and path without the scheme, for showing where the original lives.
export function sourceDisplay(url: string): string {
  const u = new URL(url);
  return `${u.hostname.replace(/^www\./, '')}${u.pathname === '/' ? '' : u.pathname.replace(/\/$/, '')}`;
}

export function byKinds(recs: Rec[], kinds: string[]): Rec[] {
  return recs.filter((r) => kinds.includes(r.data.kind));
}

export function topicCounts(recs: Rec[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const r of recs) for (const t of r.data.topics) counts.set(t, (counts.get(t) ?? 0) + 1);
  return counts;
}

export function featured(recs: Rec[], max = 3): Rec[] {
  return recs
    .filter((r) => typeof r.data.featured_rank === 'number')
    .sort((a, b) => (a.data.featured_rank as number) - (b.data.featured_rank as number))
    .slice(0, max);
}
