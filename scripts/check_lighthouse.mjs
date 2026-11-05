// Reads Lighthouse JSON reports and fails when a score is under the budget. Reads files only.
import { readdirSync, readFileSync } from 'node:fs';

const dir = process.argv[2] ?? 'lighthouse';
const budget = Number(process.env.LH_BUDGET ?? 0.9);
const categories = ['performance', 'accessibility', 'best-practices'];
let failed = 0;

const files = readdirSync(dir).filter((f) => f.endsWith('.json'));
if (files.length === 0) {
  console.log(`FAIL no Lighthouse reports in ${dir}`);
  process.exit(1);
}
for (const file of files.sort()) {
  const report = JSON.parse(readFileSync(`${dir}/${file}`, 'utf8'));
  const cells = categories.map((c) => {
    const score = report.categories?.[c]?.score;
    const ok = typeof score === 'number' && score >= budget;
    if (!ok) failed += 1;
    return `${c} ${typeof score === 'number' ? Math.round(score * 100) : 'missing'}${ok ? '' : ' FAIL'}`;
  });
  console.log(`${report.requestedUrl ?? file}: ${cells.join(' | ')}`);
}
console.log(`${failed} score(s) under ${Math.round(budget * 100)}`);
process.exit(failed ? 1 : 0);
