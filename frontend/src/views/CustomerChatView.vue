<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import ChatThread from "../components/ChatThread.vue";
import MetricGrid from "../components/MetricGrid.vue";
import { conversationWebSocketUrl, getConversation, requestHandoff, sendChat } from "../api/customerService";
import {
  addOptimisticExchange,
  clearPendingForRealMessage,
  replacePendingReplyWithError,
} from "../utils/chatOptimisticMessages";

const props = defineProps({
  apiBase: {
    type: String,
    required: true,
  },
});

const CONVERSATION_ID_KEY = "project1.customerConversationId";

const customerId = ref("customer-001");
const conversationId = ref(localStorage.getItem(CONVERSATION_ID_KEY) || "");
const input = ref("你好，我想咨询一下");
const messages = ref([]);
const lastAnswer = ref({ status: "", message_id: "", handoff_suggested: false });
const notice = ref("");
const loading = ref(false);
const socketStatus = ref("未连接");
let conversationSocket = null;
let socketConversationId = "";

const statusText = computed(() => readableStatus(lastAnswer.value.status));
const metrics = computed(() => [
  { label: "会话状态", value: statusText.value },
  { label: "本轮回复", value: lastAnswer.value.message_id ? "已生成" : "待发送" },
  { label: "建议转人工", value: lastAnswer.value.handoff_suggested ? "是" : "否" },
  { label: "实时连接", value: socketStatus.value },
]);

function readableStatus(status) {
  return {
    ai_active: "AI 正在接待",
    handoff_requested: "已请求人工",
    human_active: "人工已接入",
    human_closed: "人工服务已结束",
    auto_closed: "AI 空闲关闭",
  }[status] || "尚未开始";
}

async function refreshConversation() {
  if (!conversationId.value) {
    notice.value = "还没有会话 ID。";
    return;
  }
  const data = await getConversation(props.apiBase, conversationId.value);
  messages.value = data.messages || [];
  lastAnswer.value = { ...lastAnswer.value, status: data.status };
  notice.value = `${data.id} · ${readableStatus(data.status)}`;
  localStorage.setItem(CONVERSATION_ID_KEY, data.id);
  connectConversationSocket();
}

async function submitMessage() {
  const content = input.value.trim();
  if (!content) return;
  loading.value = true;
  messages.value = addOptimisticExchange(messages.value, {
    content,
    conversationId: conversationId.value,
    customerId: customerId.value,
  });
  input.value = "";
  try {
    const response = await sendChat(props.apiBase, {
      customer_id: customerId.value,
      conversation_id: conversationId.value || null,
      content,
    });
    conversationId.value = response.conversation_id;
    localStorage.setItem(CONVERSATION_ID_KEY, response.conversation_id);
    connectConversationSocket();
    lastAnswer.value = response;
    await refreshConversation();
  } catch (error) {
    messages.value = replacePendingReplyWithError(messages.value);
    notice.value = error.message;
  } finally {
    loading.value = false;
  }
}

async function handoff() {
  loading.value = true;
  try {
    if (!conversationId.value) {
      input.value = "我要转人工，人工处理";
      await submitMessage();
      return;
    }
    const response = await requestHandoff(props.apiBase, conversationId.value, "customer_clicked_handoff");
    localStorage.setItem(CONVERSATION_ID_KEY, response.conversation_id);
    lastAnswer.value = response;
    await refreshConversation();
  } catch (error) {
    notice.value = error.message;
  } finally {
    loading.value = false;
  }
}

function resetConversation() {
  conversationId.value = "";
  localStorage.removeItem(CONVERSATION_ID_KEY);
  closeConversationSocket();
  input.value = "你好，我想咨询一下";
  messages.value = [];
  lastAnswer.value = { status: "", message_id: "", handoff_suggested: false };
  notice.value = "";
}

function upsertMessage(message) {
  if (!message?.id) return;
  messages.value = clearPendingForRealMessage(messages.value, message);
  const index = messages.value.findIndex((item) => item.id === message.id);
  if (index >= 0) {
    messages.value.splice(index, 1, message);
    return;
  }
  messages.value = [...messages.value, message];
}

function closeConversationSocket() {
  if (!conversationSocket) return;
  conversationSocket.onclose = null;
  conversationSocket.close();
  conversationSocket = null;
  socketConversationId = "";
  socketStatus.value = "未连接";
}

function connectConversationSocket() {
  if (!conversationId.value) return;
  if (conversationSocket && socketConversationId === conversationId.value) return;
  if (conversationSocket) {
    conversationSocket.close();
  }
  socketStatus.value = "连接中";
  const socket = new WebSocket(conversationWebSocketUrl(props.apiBase, conversationId.value));
  conversationSocket = socket;
  socketConversationId = conversationId.value;
  socket.onopen = () => {
    socketStatus.value = "已连接";
  };
  socket.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.event === "message") {
      upsertMessage(payload.message);
    }
  };
  socket.onerror = () => {
    socketStatus.value = "连接异常";
  };
  socket.onclose = () => {
    if (conversationSocket === socket) {
      conversationSocket = null;
      socketConversationId = "";
      socketStatus.value = "已断开";
    }
  };
}

onMounted(async () => {
  if (!conversationId.value) return;
  try {
    await refreshConversation();
  } catch (error) {
    localStorage.removeItem(CONVERSATION_ID_KEY);
    conversationId.value = "";
    notice.value = `已清除失效会话：${error.message}`;
  }
});

onBeforeUnmount(() => {
  closeConversationSocket();
});

watch(
  () => props.apiBase,
  () => {
    if (conversationId.value) {
      connectConversationSocket();
    }
  },
);
</script>

<template>
  <main class="workspace chat-layout">
    <section class="chat-shell">
      <div class="chat-head">
        <div>
          <h2>会话</h2>
          <p>{{ notice || "尚未开始" }}</p>
        </div>
        <div class="chat-head-actions">
          <button type="button" @click="resetConversation">新会话</button>
          <button class="secondary" type="button" @click="refreshConversation">刷新消息</button>
        </div>
      </div>

      <div class="form-row compact">
        <label>
          客户 ID
          <input v-model="customerId" />
        </label>
        <label>
          会话 ID
          <input v-model="conversationId" placeholder="发送后自动生成" />
        </label>
      </div>

      <ChatThread :messages="messages" empty-text="输入问题后开始会话。示例：你好，我想咨询一下" />

      <form class="composer" @submit.prevent="submitMessage">
        <textarea v-model="input" rows="3" placeholder="输入客服问题或补充说明" />
        <div class="actions">
          <button type="submit" :disabled="loading">发送</button>
          <button class="secondary" type="button" :disabled="loading" @click="handoff">转人工</button>
        </div>
      </form>
    </section>

    <aside class="side-panel">
      <h2>会话状态</h2>
      <MetricGrid :items="metrics" />
    </aside>
  </main>
</template>
