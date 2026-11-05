import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { precision, workDate } from '../lib/catalog';
import { visibleRecords } from '../lib/records';
import { SITE_NAME } from '../site';

export async function GET(context: APIContext) {
  const recs = (await visibleRecords()).slice(0, 30);
  return rss({
    title: SITE_NAME,
    description: 'Talks, writing, books and projects by Stephen Chin.',
    site: context.site!,
    items: recs.map((rec) => {
      const w = workDate(rec.data);
      // RSS needs a full date. A month or a year is never stretched into a day, so those items carry none.
      const pubDate = w && precision(w.value) === 'day' ? new Date(`${w.value}T00:00:00Z`) : undefined;
      return { title: rec.data.title, link: `/work/${rec.id}/`, description: rec.data.summary ?? rec.data.title, pubDate };
    }),
  });
}
