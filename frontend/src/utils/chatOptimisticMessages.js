const PENDING_PREFIX = "pending-";

export function isPendingMessage(message) {
  return Boolean(message?.pending || String(message?.id || "").startsWith(PENDING_PREFIX));
}

export function addOptimisticExchange(
  messages,
  {
    content,
    conversationId,
    customerId,
    responderType = "ai",
    now = () => new Date().toISOString(),
    token = `${Date.now()}-${Math.random().toString(16).slice(2)}`,
  },
) {
  const createdAt = now();
  return [
    ...messages,
    {
      id: `${PENDING_PREFIX}user-${token}`,
      conversation_id: conversationId || "",
      sender_type: "user",
      sender_id: customerId,
      content,
      metadata: {},
      created_at: createdAt,
      pending: true,
      pending_role: "user",
    },
    {
      id: `${PENDING_PREFIX}reply-${token}`,
      conversation_id: conversationId || "",
      sender_type: responderType,
      sender_id: responderType === "human" ? "human-support" : "ai-customer-service",
      content: "正在检索资料并生成回复",
      metadata: {},
      created_at: createdAt,
      pending: true,
      pending_role: "reply",
    },
  ];
}

export function clearPendingMessages(messages) {
  return messages.filter((message) => !isPendingMessage(message));
}

export function clearPendingForRealMessage(messages, realMessage) {
  return messages.filter((message) => {
    if (!isPendingMessage(message)) return true;
    if (message.pending_role === "user" && realMessage.sender_type === "user") return false;
    if (message.pending_role === "reply" && realMessage.sender_type !== "user") return false;
    return true;
  });
}

export function replacePendingReplyWithError(messages) {
  return messages.map((message) => {
    if (message.pending_role !== "reply") return message;
    return {
      ...message,
      sender_type: "system",
      content: "发送失败，请稍后重试。",
      pending: false,
      failed: true,
    };
  });
}
