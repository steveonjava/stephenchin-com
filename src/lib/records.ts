import { getCollection } from 'astro:content';
import topics from '../data/topics.json';
import { IS_PREVIEW } from '../site';
import { sortRecords, type Rec } from './catalog';

// Production shows published records from the reviewed collection only. The preview also shows every
// reviewed record that is not published yet, and the unreviewed candidates, so the owner can inspect them.
export async function visibleRecords(): Promise<Rec[]> {
  const works = await getCollection('works');
  const out: Rec[] = works
    .filter((e) => (IS_PREVIEW ? e.data.review_status !== 'rejected' : e.data.review_status === 'published'))
    .map((e) => ({ id: e.id, origin: 'works', data: e.data }));
  if (IS_PREVIEW) {
    const candidates = await getCollection('candidates');
    for (const e of candidates) if (e.data.review_status !== 'rejected') out.push({ id: e.id, origin: 'candidates', data: e.data });
  }
  return sortRecords(out);
}

export const topicLabels: Record<string, string> = Object.fromEntries(topics.map((t) => [t.id, t.label]));

type TopicEntry = { id: string; label: string; aliases?: string[] };
const topicEntries = topics as TopicEntry[];

export function topicAliases(ids: string[]): string[] {
  return ids.flatMap((id) => topicEntries.find((x) => x.id === id)?.aliases ?? []);
}
