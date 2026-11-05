import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const slug = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);
// Day, month or year precision. A missing part is never filled in.
const dateValue = z.string().regex(/^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$/);
const dateEntry = z.strictObject({ value: dateValue, type: z.string().min(1), source: z.string().optional() });
const relation = z.strictObject({
  type: z.enum(['isRecordingOf', 'presentedAt', 'companionCode', 'partOf', 'relatedTo', 'alternateVersion']),
  target: z.union([z.string(), z.array(z.string())]),
  note: z.string().optional(),
});
const audit = z.union([
  z.strictObject({ kind: z.literal('flag'), text: z.string(), checked: z.string() }),
  z.strictObject({ kind: z.literal('fix'), field: z.string(), from: z.unknown(), to: z.unknown(), evidence: z.string(), checked: z.string() }),
]);

const record = z.strictObject({
  title: z.string().min(1),
  kind: z.enum(['article', 'book', 'code', 'community', 'interview', 'project', 'talk', 'video']),
  topics: z.array(slug).min(1),
  source_ids: z.array(z.string().regex(/^S\d+$/)).min(1),
  url: z.string().startsWith('https://'),
  year: z.number().int().min(1990).max(2100).nullable(),
  stephen_role: z.string().nullable(),
  review_status: z.enum(['candidate', 'verified', 'approved', 'published', 'rejected']),
  verification_status: z.string(),
  rights_status: z.string(),
  event: z.string().nullable(),
  note: z.string().optional(),
  date: dateEntry.optional(),
  dates: z.array(dateEntry).optional(),
  platform_video_id: z.string().optional(),
  page_title_observed: z.string().optional(),
  license_observed: z.string().optional(),
  relations: z.array(relation).optional(),
  audit: z.array(audit).optional(),
  // Approved editorial text and the manual featured rank belong to reviewed records only.
  summary: z.string().optional(),
  featured_rank: z.number().int().positive().optional(),
});

// Reviewed records. Rendered in every build.
const works = defineCollection({ loader: glob({ base: './src/content/works', pattern: '**/*.json' }), schema: record });
// Unreviewed seeds. Rendered only in the preview build, never in production.
const candidates = defineCollection({ loader: glob({ base: './src/content/candidates', pattern: '**/*.json' }), schema: record });

export const collections = { works, candidates };
