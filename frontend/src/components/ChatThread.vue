<script setup>
import { ref } from "vue";

defineProps({
  messages: {
    type: Array,
    default: () => [],
  },
  emptyText: {
    type: String,
    default: "暂无消息。",
  },
});

const expandedRetrieval = ref({});

function senderLabel(sender) {
  return {
    user: "客户",
    ai: "AI 客服",
    human: "人工客服",
    system: "系统",
  }[sender] || sender;
}

function senderClass(sender) {
  return sender;
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function retrievalHits(message) {
  return message?.metadata?.retrieval?.hits || [];
}

function hasRetrieval(message) {
  return message?.sender_type === "ai" && retrievalHits(message).length > 0;
}

function isRetrievalOpen(message) {
  return Boolean(expandedRetrieval.value[message.id]);
}

function toggleRetrieval(message) {
  expandedRetrieval.value = {
    ...expandedRetrieval.value,
    [message.id]: !expandedRetrieval.value[message.id],
  };
}

function scoreLabel(value) {
  if (value === undefined || value === null) return "";
  return Number(value).toFixed(4);
}
</script>

<template>
  <div class="chat-thread">
    <div v-if="messages.length === 0" class="empty-state">{{ emptyText }}</div>
    <article v-for="message in messages" :key="message.id" class="chat-message" :class="senderClass(message.sender_type)">
      <div class="bubble">
        <strong>{{ senderLabel(message.sender_type) }}</strong>
        <p v-if="message.pending_role === 'reply'" class="pending-reply">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span>{{ message.content }}</span>
        </p>
        <p v-else>{{ message.content }}</p>
        <button
          v-if="hasRetrieval(message)"
          type="button"
          class="retrieval-toggle"
          @click="toggleRetrieval(message)"
        >
          {{ isRetrievalOpen(message) ? "收起检索内容" : `查看检索内容 ${retrievalHits(message).length} 条` }}
        </button>
        <div v-if="hasRetrieval(message) && isRetrievalOpen(message)" class="retrieval-panel">
          <div v-for="hit in retrievalHits(message)" :key="hit.chunk_id" class="retrieval-hit">
            <div class="retrieval-hit-head">
              <b>{{ hit.chunk_id }}</b>
              <small>score {{ scoreLabel(hit.score) }}</small>
            </div>
            <p>{{ hit.retrieval_text }}</p>
            <small v-if="hit.matched_sparse_terms?.length">
              命中词：{{ hit.matched_sparse_terms.join("、") }}
            </small>
          </div>
        </div>
        <span>{{ formatTime(message.created_at) }}</span>
      </div>
    </article>
  </div>
</template>
