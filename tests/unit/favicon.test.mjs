import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { inflateSync } from 'node:zlib';

test('favicon is a 64px RGB PNG without inherited metadata', () => {
  const png = readFileSync('public/favicon.png');
  assert.deepEqual(png.subarray(0, 8), Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  const types = [];
  const imageData = [];
  let offset = 8;
  while (offset < png.length) {
    assert.ok(offset + 12 <= png.length, 'complete chunk header and CRC');
    const length = png.readUInt32BE(offset);
    const end = offset + 12 + length;
    assert.ok(end <= png.length, 'complete chunk');
    const type = png.toString('ascii', offset + 4, offset + 8);
    const data = png.subarray(offset + 8, offset + 8 + length);
    types.push(type);
    if (type === 'IHDR') {
      assert.equal(length, 13);
      assert.deepEqual([data.readUInt32BE(0), data.readUInt32BE(4)], [64, 64]);
      assert.deepEqual([...data.subarray(8)], [8, 2, 0, 0, 0]);
    }
    if (type === 'IDAT') imageData.push(data);
    offset = end;
  }
  assert.equal(types[0], 'IHDR');
  assert.equal(types.at(-1), 'IEND');
  assert.ok(imageData.length > 0);
  assert.ok(types.slice(1, -1).every((type) => type === 'IDAT'), 'no ancillary metadata chunks');
  assert.equal(inflateSync(Buffer.concat(imageData)).length, 64 * (1 + 64 * 3));
});
