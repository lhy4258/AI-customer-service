<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import ChatThread from "../components/ChatThread.vue";
import {
  cancelKnowledgeDocument,
  claimTicket,
  closeConversation,
  conversationWebSocketUrl,
  deleteKnowledgeDocument,
  getConversation,
  listHandoffTickets,
  listKnowledgeDocuments,
  sendHumanReply,
  uploadKnowledge,
} from "../api/customerService";

const props = defineProps({
  apiBase: {
    type: String,
    required: true,
  },
});

const tickets = ref([]);
const ticketId = ref("");
const conversationId = ref("");
const conversationStatus = ref("");
const reply = ref("您好，我已经接入，会继续协助处理。");
const messages = ref([]);
const notice = ref("请选择一个待接入工单");
const loading = ref(false);
const knowledgeDocuments = ref([]);
const selectedKnowledgeFile = ref(null);
const knowledgeFileInput = ref(null);
const knowledgeNotice = ref("支持上传 txt、md、csv 文本资料。");
const uploadingKnowledge = ref(false);
const knowledgeUploadProgress = ref(0);
const deletingKnowledgeDocumentId = ref("");
const socketStatus = ref("未连接");
let conversationSocket = null;
let socketConversationId = "";
let knowledgePollTimer = null;

const canReply = computed(() => conversationStatus.value === "human_active");
const canClose = computed(() => conversationStatus.value === "human_active");
const replyHint = computed(() => {
  if (!conversationId.value) return "请先从左侧选择工单。";
  if (conversationStatus.value === "handoff_requested") return "请先点击“接入”，接入后才能发送人工回复。";
  if (["human_closed", "auto_closed"].includes(conversationStatus.value)) return "该会话已结束，不能继续回复。";
  return "";
});

async function refreshTickets() {
  try {
    tickets.value = await listHandoffTickets(props.apiBase);
  } catch (error) {
    notice.value = error.message;
  }
}

async function selectTicket(ticket) {
  ticketId.value = ticket.id;
  conversationId.value = ticket.conversation_id;
  await refreshConversation();
}

async function refreshConversation() {
  if (!conversationId.value) {
    notice.value = "请先选择或接入一个工单。";
    return;
  }
  const data = await getConversation(props.apiBase, conversationId.value);
  messages.value = data.messages || [];
  conversationStatus.value = data.status;
  notice.value = `${data.id} · ${readableStatus(data.status)} · 实时${socketStatus.value}`;
  connectConversationSocket();
}

async function claimSelectedTicket() {
  if (!ticketId.value) {
    notice.value = "请先选择待接入工单。";
    return;
  }
  loading.value = true;
  try {
    const ticket = await claimTicket(props.apiBase, ticketId.value);
    conversationId.value = ticket.conversation_id;
    await refreshTickets();
    await refreshConversation();
    notice.value = `${ticket.conversation_id} · 已接入，可以回复`;
  } catch (error) {
    notice.value = error.message;
  } finally {
    loading.value = false;
  }
}

async function submitReply() {
  if (!conversationId.value) {
    notice.value = "请先选择并接入一个工单。";
    return;
  }
  if (!canReply.value) {
    notice.value = replyHint.value || `当前会话状态为“${readableStatus(conversationStatus.value)}”，不能发送人工回复。`;
    return;
  }
  if (!reply.value.trim()) {
    notice.value = "请输入人工客服回复内容。";
    return;
  }
  loading.value = true;
  try {
    await sendHumanReply(props.apiBase, conversationId.value, reply.value.trim());
    reply.value = "";
    await refreshConversation();
  } catch (error) {
    notice.value = error.message;
  } finally {
    loading.value = false;
  }
}

async function closeCurrentConversation() {
  if (!conversationId.value) {
    notice.value = "请先选择并接入一个工单。";
    return;
  }
  if (!canClose.value) {
    notice.value = replyHint.value || `当前会话状态为“${readableStatus(conversationStatus.value)}”，不能结束服务。`;
    return;
  }
  loading.value = true;
  try {
    await closeConversation(props.apiBase, conversationId.value);
    archiveCurrentConversation("会话已结束并归档，不再显示在当前接待面板。");
    await refreshTickets();
  } catch (error) {
    notice.value = error.message;
  } finally {
    loading.value = false;
  }
}

async function refreshKnowledgeDocuments() {
  try {
    knowledgeDocuments.value = await listKnowledgeDocuments(props.apiBase);
    scheduleKnowledgeRefresh();
  } catch (error) {
    knowledgeNotice.value = error.message;
  }
}

function selectKnowledgeFile(event) {
  selectedKnowledgeFile.value = event.target.files?.[0] || null;
  knowledgeUploadProgress.value = 0;
  knowledgeNotice.value = selectedKnowledgeFile.value ? selectedKnowledgeFile.value.name : "支持上传 txt、md、csv 文本资料。";
}

async function uploadSelectedKnowledge() {
  if (!selectedKnowledgeFile.value) {
    knowledgeNotice.value = "请先选择资料文件。";
    return;
  }
  uploadingKnowledge.value = true;
  knowledgeUploadProgress.value = 5;
  try {
    const content = await selectedKnowledgeFile.value.text();
    const result = await uploadKnowledge(props.apiBase, {
      file_name: selectedKnowledgeFile.value.name,
      content,
      source: "support-upload",
    }, (progress) => {
      knowledgeUploadProgress.value = progress;
    });
    knowledgeNotice.value = result.status === "processing"
      ? `${result.file_name} 已接收，正在后台切片入库。`
      : `${result.file_name} 已入库，切片 ${result.chunk_count} 条。`;
    selectedKnowledgeFile.value = null;
    if (knowledgeFileInput.value) {
      knowledgeFileInput.value.value = "";
    }
    upsertKnowledgeDocument(result);
    await refreshKnowledgeDocuments();
    knowledgeUploadProgress.value = 0;
  } catch (error) {
    knowledgeNotice.value = error.message;
    knowledgeUploadProgress.value = 0;
  } finally {
    uploadingKnowledge.value = false;
  }
}

function scheduleKnowledgeRefresh() {
  if (knowledgePollTimer) {
    clearTimeout(knowledgePollTimer);
    knowledgePollTimer = null;
  }
  if (!knowledgeDocuments.value.some((document) => document.status === "processing")) return;
  knowledgePollTimer = window.setTimeout(refreshKnowledgeDocuments, 1500);
}

function readableKnowledgeStatus(document) {
  if (document.status === "failed") return "上传失败";
  if (document.status === "canceled") return "已取消切片入库";
  if (document.status === "processing") return "正在切片入库";
  if (document.status === "ready") return `已入库 · ${document.chunk_count} 条切片`;
  return document.status;
}

function upsertKnowledgeDocument(document) {
  const index = knowledgeDocuments.value.findIndex((item) => item.id === document.id);
  if (index >= 0) {
    knowledgeDocuments.value.splice(index, 1, document);
    return;
  }
  knowledgeDocuments.value = [document, ...knowledgeDocuments.value];
}

async function cancelSelectedKnowledgeDocument(document) {
  deletingKnowledgeDocumentId.value = document.id;
  try {
    const canceled = await cancelKnowledgeDocument(props.apiBase, document.id);
    upsertKnowledgeDocument(canceled);
    knowledgeNotice.value = `${document.file_name} 已取消切片入库。`;
  } catch (error) {
    knowledgeNotice.value = error.message;
  } finally {
    deletingKnowledgeDocumentId.value = "";
  }
}

async function deleteSelectedKnowledgeDocument(document) {
  if (!window.confirm(`确定删除“${document.file_name}”吗？`)) return;
  deletingKnowledgeDocumentId.value = document.id;
  try {
    await deleteKnowledgeDocument(props.apiBase, document.id);
    knowledgeDocuments.value = knowledgeDocuments.value.filter((item) => item.id !== document.id);
    knowledgeNotice.value = `${document.file_name} 已删除。`;
  } catch (error) {
    knowledgeNotice.value = error.message;
  } finally {
    deletingKnowledgeDocumentId.value = "";
  }
}

function readableStatus(status) {
  return {
    ai_active: "AI 正在接待",
    handoff_requested: "等待人工接入",
    human_active: "人工接待中",
    human_closed: "人工服务已结束",
    auto_closed: "AI 空闲关闭",
  }[status] || status;
}

function archiveCurrentConversation(message) {
  ticketId.value = "";
  conversationId.value = "";
  conversationStatus.value = "";
  messages.value = [];
  closeConversationSocket();
  notice.value = message;
}

function upsertMessage(message) {
  if (!message?.id) return;
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
    notice.value = `${conversationId.value} · 实时已连接`;
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
  await refreshTickets();
  await refreshKnowledgeDocuments();
});

onBeforeUnmount(() => {
  if (knowledgePollTimer) {
    clearTimeout(knowledgePollTimer);
  }
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
  <main class="workspace support-layout">
    <aside class="queue-panel">
      <div class="section-title">
        <div>
          <h2>待接入队列</h2>
          <p>客户在聊天端点击“转人工”后，会出现在这里。</p>
        </div>
        <button type="button" @click="refreshTickets">刷新</button>
      </div>

      <div class="ticket-list">
        <div v-if="tickets.length === 0" class="empty-state">暂无待接入工单。</div>
        <button
          v-for="ticket in tickets"
          :key="ticket.id"
          class="ticket-card"
          type="button"
          @click="selectTicket(ticket)"
        >
          <strong>{{ ticket.id }}</strong>
          <span>会话 {{ ticket.conversation_id }}</span>
          <small>{{ ticket.requested_reason }}</small>
        </button>
      </div>

      <div class="knowledge-panel">
        <div class="section-title compact-title">
          <div>
            <h2>资料上传</h2>
            <p>{{ knowledgeNotice }}</p>
          </div>
          <button class="secondary" type="button" @click="refreshKnowledgeDocuments">刷新</button>
        </div>
        <input
          ref="knowledgeFileInput"
          type="file"
          accept=".txt,.md,.csv,text/plain,text/markdown,text/csv"
          :disabled="uploadingKnowledge"
          @change="selectKnowledgeFile"
        />
        <div v-if="uploadingKnowledge || knowledgeUploadProgress > 0" class="upload-progress">
          <progress max="100" :value="knowledgeUploadProgress"></progress>
          <span>{{ uploadingKnowledge ? `上传处理中 ${knowledgeUploadProgress}%` : "上传完成" }}</span>
        </div>
        <div class="actions knowledge-actions">
          <button type="button" :disabled="uploadingKnowledge" @click="uploadSelectedKnowledge">上传入库</button>
        </div>
        <div class="knowledge-list">
          <div v-if="knowledgeDocuments.length === 0" class="empty-state">暂无资料。</div>
          <article v-for="document in knowledgeDocuments" :key="document.id" class="knowledge-card">
            <div class="knowledge-card-head">
              <strong>{{ document.file_name }}</strong>
              <button
                v-if="document.status === 'processing'"
                class="secondary danger-button"
                type="button"
                :disabled="deletingKnowledgeDocumentId === document.id"
                @click="cancelSelectedKnowledgeDocument(document)"
              >
                取消
              </button>
              <button
                v-else
                class="secondary danger-button"
                type="button"
                :disabled="deletingKnowledgeDocumentId === document.id"
                @click="deleteSelectedKnowledgeDocument(document)"
              >
                删除
              </button>
            </div>
            <span>{{ readableKnowledgeStatus(document) }}</span>
          </article>
        </div>
      </div>
    </aside>

    <section class="chat-shell">
      <div class="chat-head">
        <div>
          <h2>人工接待会话</h2>
          <p>{{ notice }}</p>
        </div>
        <div class="chat-head-actions">
          <button type="button" :disabled="loading" @click="claimSelectedTicket">接入</button>
          <button class="secondary" type="button" @click="refreshConversation">刷新消息</button>
        </div>
      </div>

      <div class="form-row compact">
        <label>
          Ticket ID
          <input v-model="ticketId" placeholder="从左侧队列选择" />
        </label>
        <label>
          会话 ID
          <input v-model="conversationId" placeholder="接入后自动填入" />
        </label>
      </div>

      <ChatThread :messages="messages" empty-text="接入工单后，这里会显示客户与 AI 的完整上下文。" />

      <form class="composer" @submit.prevent="submitReply">
        <textarea v-model="reply" rows="3" placeholder="输入人工客服回复" />
        <p v-if="replyHint" class="form-hint">{{ replyHint }}</p>
        <div class="actions">
          <button type="submit" :disabled="loading || !canReply">发送人工回复</button>
          <button class="secondary" type="button" :disabled="loading || !canClose" @click="closeCurrentConversation">结束服务</button>
        </div>
      </form>
    </section>
  </main>
</template>
