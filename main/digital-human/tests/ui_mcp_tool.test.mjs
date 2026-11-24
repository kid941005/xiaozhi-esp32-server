import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, '..', 'js', 'ui', 'controller.js'), 'utf8');

test('addMCPTool 给容器设置 id，removeMCPTool 才能按 id 找到节点', () => {
  assert.match(source, /toolDiv\.id = toolId/);
});

test('删除按钮用事件监听而非内联 onclick（避免依赖未挂到 window 的 uiController）', () => {
  assert.match(source, /removeBtn\.addEventListener\('click'/);
  assert.doesNotMatch(source, /onclick="uiController\.removeMCPTool/);
});
