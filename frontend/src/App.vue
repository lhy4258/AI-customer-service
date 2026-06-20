<script setup>
import { computed, ref } from "vue";
import CustomerChatView from "./views/CustomerChatView.vue";
import HumanSupportDeskView from "./views/HumanSupportDeskView.vue";
import { API_BASE_KEY } from "./api/customerService";
import { resolveAppRole } from "./appRole";

const views = {
  customer: CustomerChatView,
  support: HumanSupportDeskView,
};

const routeLabels = {
  customer: {
    title: "客户聊天端",
    subtitle: "AI 回复、转人工等待、人工客服回复都显示在同一条会话里。",
  },
  support: {
    title: "人工客服工作台",
    subtitle: "接收转人工工单、接入会话、查看上下文、回复客户并结束服务。",
  },
};

const appRole = resolveAppRole(import.meta.env.MODE);
const apiBase = ref(localStorage.getItem(API_BASE_KEY) || "http://127.0.0.1:8000");

const currentComponent = computed(() => views[appRole]);
const copy = computed(() => routeLabels[appRole]);
const isSupport = computed(() => appRole === "support");

function persistApiBase() {
  localStorage.setItem(API_BASE_KEY, apiBase.value);
}
</script>

<template>
  <header class="topbar">
    <div>
      <span v-if="isSupport" class="internal-badge">内部客服端</span>
      <h1>{{ copy.title }}</h1>
      <p>{{ copy.subtitle }}</p>
    </div>
    <label class="api-base">
      <span>API Base</span>
      <input v-model="apiBase" @change="persistApiBase" />
    </label>
  </header>

  <component :is="currentComponent" :api-base="apiBase" />
</template>
