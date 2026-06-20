import assert from "node:assert/strict";

import {
  addOptimisticExchange,
  clearPendingForRealMessage,
  clearPendingMessages,
  isPendingMessage,
  replacePendingReplyWithError,
} from "../src/utils/chatOptimisticMessages.js";

const messages = addOptimisticExchange([], {
  content: "买茶具是否包邮",
  conversationId: "conv-1",
  customerId: "customer-1",
  responderType: "ai",
  now: () => "2026-06-20T08:00:00.000Z",
  token: "test",
});

assert.equal(messages.length, 2);
assert.equal(messages[0].sender_type, "user");
assert.equal(messages[0].content, "买茶具是否包邮");
assert.equal(messages[1].sender_type, "ai");
assert.equal(messages[1].pending_role, "reply");
assert.equal(isPendingMessage(messages[1]), true);

const realMessage = { id: "msg-1", sender_type: "ai", content: "默认不包邮" };
assert.deepEqual(clearPendingMessages([...messages, realMessage]), [realMessage]);

const failed = replacePendingReplyWithError(messages);
assert.equal(failed[1].sender_type, "system");
assert.equal(failed[1].pending, false);
assert.equal(failed[1].failed, true);

const afterRealUser = clearPendingForRealMessage(messages, { id: "msg-user", sender_type: "user" });
assert.equal(afterRealUser.length, 1);
assert.equal(afterRealUser[0].pending_role, "reply");

const afterRealAi = clearPendingForRealMessage(messages, { id: "msg-ai", sender_type: "ai" });
assert.equal(afterRealAi.length, 1);
assert.equal(afterRealAi[0].pending_role, "user");
