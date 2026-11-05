import test from 'node:test';
import assert from 'node:assert/strict';
import { byKinds, dateTypeLabel, featured, formatDate, kindLabel, precision, roleLabel, rowDate, sortKey, sortRecords, sourceDisplay, topicCounts, workDate } from '../../src/lib/catalog.ts';

const rec = (id, data) => ({ id, origin: 'candidates', data: { title: id, kind: 'talk', topics: ['java'], year: null, stephen_role: null, review_status: 'candidate', event: null, ...data } });

test('precision follows the length of the value', () => {
  assert.equal(precision('2025'), 'year');
  assert.equal(precision('2025-07'), 'month');
  assert.equal(precision('2025-07-21'), 'day');
});

test('formatDate never invents a missing month or day', () => {
  assert.equal(formatDate('2025'), '2025');
  assert.equal(formatDate('2025-07'), 'July 2025');
  assert.equal(formatDate('2025-07-21'), '21 July 2025');
  assert.equal(formatDate('2009-01-05'), '5 January 2009');
});

test('workDate prefers an event date, then a publication date, then an upload', () => {
  const d = { dates: [{ value: '2025-07-22', type: 'upload' }, { value: '2025-07-20', type: 'event' }] };
  assert.equal(workDate(d).value, '2025-07-20');
  assert.equal(workDate({ dates: [{ value: '2025-07-22', type: 'upload' }] }).type, 'upload');
});

test('repository dates and planned dates never stand in for the work date', () => {
  const d = { year: null, dates: [{ value: '2015-03-22', type: 'repository_created' }, { value: '2015-03-22', type: 'repository_last_push' }] };
  assert.equal(workDate(d), null);
  assert.equal(rowDate(d), 'Date unknown');
  assert.equal(sortKey(d), '0000-00-00');
});

test('rowDate labels what kind of date it shows', () => {
  assert.equal(rowDate({ year: 2025, dates: [{ value: '2025-07-21', type: 'upload' }] }), 'Uploaded 21 July 2025');
  assert.equal(rowDate({ year: 2010, date: { value: '2010-09-02', type: 'publisher_label_recorded_at' } }), '2 September 2010 (publisher label)');
  assert.equal(rowDate({ year: null, dates: [{ value: '2027-01', type: 'planned_publication' }] }), 'Planned January 2027');
  assert.equal(rowDate({ year: 2015 }), '2015');
  assert.equal(rowDate({ year: null }), 'Date unknown');
});

test('sortRecords orders newest first, breaks ties by title, and puts unknown dates last', () => {
  const list = sortRecords([
    rec('c', { year: 2014, date: { value: '2014-05', type: 'publication' } }),
    rec('a', { year: 2025, date: { value: '2025-07-21', type: 'publication' } }),
    rec('unknown', {}),
    rec('b', { year: 2025, date: { value: '2025-07-21', type: 'publication' } }),
    rec('d', { year: 2025 }),
  ]);
  assert.deepEqual(list.map((r) => r.id), ['a', 'b', 'd', 'c', 'unknown']);
});

test('a month-only date sorts before a day in the same month', () => {
  assert.ok(sortKey({ date: { value: '2014-05', type: 'publication' }, year: 2014 }) < sortKey({ date: { value: '2014-05-02', type: 'publication' }, year: 2014 }));
});

test('labels', () => {
  assert.equal(kindLabel('talk'), 'Talk');
  assert.equal(kindLabel('unheard-of'), 'unheard-of');
  assert.equal(roleLabel('co-author'), 'Co author');
  assert.equal(roleLabel(null), null);
  assert.equal(dateTypeLabel('repository_created'), 'Repository created');
  assert.equal(dateTypeLabel('something_new'), 'something new');
});

test('sourceDisplay drops the scheme, www and a trailing slash', () => {
  assert.equal(sourceDisplay('https://www.infoq.com/news/2009/01/widgetfx/'), 'infoq.com/news/2009/01/widgetfx');
  assert.equal(sourceDisplay('https://aifirstprogramming.com/'), 'aifirstprogramming.com');
});

test('byKinds, topicCounts and featured', () => {
  const list = [rec('t', { kind: 'talk', topics: ['java', 'ai'], featured_rank: 2 }), rec('b', { kind: 'book', topics: ['java'], featured_rank: 1 }), rec('x', { kind: 'video' })];
  assert.deepEqual(byKinds(list, ['talk', 'video']).map((r) => r.id), ['t', 'x']);
  assert.deepEqual([...topicCounts(list)], [['java', 3], ['ai', 1]]);
  assert.deepEqual(featured(list).map((r) => r.id), ['b', 't']);
  assert.equal(featured(list, 1).length, 1);
});
