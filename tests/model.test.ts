import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { datasetSchema, emptyWorkspace, contextStats, nextAdminResponse, reviewKey } from '../lib/model.ts';

const raw = JSON.parse(readFileSync(new URL('../lib/demo.json', import.meta.url), 'utf8'));
test('example import is valid and complete at selected moments', () => {
  const pack = datasetSchema.parse(raw);
  assert.equal(pack.dialogues.length, 5);
  assert.equal(pack.source.is_demo, true);
  const d = pack.dialogues[0];
  assert.equal(d.messages.length, 8);
  assert.deepEqual(contextStats(d, d.analyses[0]), { preceding: 7, used: 7, historyComplete: true });
  assert.equal(nextAdminResponse(d, 'm7')[0].id, 'm8');
});
test('future administrator response cannot be used as model context', () => {
  const changed = structuredClone(raw); changed.dialogues[0].analyses[0].used_message_ids.push('m8');
  assert.equal(datasetSchema.safeParse(changed).success, false);
});
test('unknown message in a model context is rejected', () => {
  const changed = structuredClone(raw); changed.dialogues[0].analyses[0].used_message_ids.push('not-present');
  assert.equal(datasetSchema.safeParse(changed).success, false);
});
test('duplicate dialogue and message IDs are rejected', () => {
  const a = structuredClone(raw); a.dialogues.push(a.dialogues[0]); assert.equal(datasetSchema.safeParse(a).success, false);
  const b = structuredClone(raw); b.dialogues[0].messages[1].id = b.dialogues[0].messages[0].id; assert.equal(datasetSchema.safeParse(b).success, false);
});
test('analysis cannot anchor on administrator message', () => {
  const changed = structuredClone(raw); changed.dialogues[0].analyses[0].client_message_id = 'm8';
  assert.equal(datasetSchema.safeParse(changed).success, false);
});
test('out-of-order messages rejected rather than silently reordered', () => {
  const changed = structuredClone(raw); changed.dialogues[0].messages.reverse();
  assert.equal(datasetSchema.safeParse(changed).success, false);
});
test('external and credential-bearing CRM links rejected', () => {
  for (const url of ['javascript:alert(1)', 'https://example.com/a', 'https://key:secret@kodologiyapiksel.s20.online/a']) {
    const changed = structuredClone(raw); changed.dialogues[0].crm_url = url;
    assert.equal(datasetSchema.safeParse(changed).success, false);
  }
});
test('legitimate private CRM link accepted', () => {
  const changed = structuredClone(raw); changed.dialogues[0].crm_url = 'https://kodologiyapiksel.s20.online/company/1/chat-admin/index';
  assert.equal(datasetSchema.safeParse(changed).success, true);
});
test('absent coverage and trace remain explicitly unknown', () => {
  const changed = structuredClone(raw); delete changed.dialogues[0].history_complete; delete changed.dialogues[0].analyses[0].used_message_ids;
  const pack = datasetSchema.parse(changed);
  assert.equal(pack.dialogues[0].history_complete, false);
  assert.equal(contextStats(pack.dialogues[0], pack.dialogues[0].analyses[0]).used, null);
});
test('rating identifiers cannot collide through concatenation', () => {
  assert.notEqual(reviewKey('a:b', 'c', 'd'), reviewKey('a', 'b:c', 'd'));
  assert.notEqual(reviewKey('demo', 'same', 'same'), reviewKey('real', 'same', 'same'));
});
test('no administrator response fabricated when next client arrives', () => {
  const d = datasetSchema.parse(raw).dialogues[0];
  assert.equal(nextAdminResponse(d, 'm5').length, 1);
  assert.equal(nextAdminResponse(d, 'missing').length, 0);
  const synthetic = { ...d, messages: [d.messages[0], { ...d.messages[0], id: 'second' }] };
  assert.equal(nextAdminResponse(synthetic, 'm1').length, 0);
});
test('new owner workspace never contains imported customer data or approvals', () => {
  const state = emptyWorkspace(); assert.equal(state.dataset, null); assert.equal(state.principles.length, 0);
  assert.equal(state.settings.tone, 'unset');
});
