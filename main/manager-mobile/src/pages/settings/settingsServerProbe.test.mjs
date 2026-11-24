import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, 'index.vue'), 'utf8');

test('服务端地址探测使用真实匿名端点 /user/pub-config，而非不存在的 /api/ping', () => {
  assert.match(source, /\$\{baseUrlInput\.value\}\/user\/pub-config/);
  assert.doesNotMatch(source, /\/api\/ping/);
});
