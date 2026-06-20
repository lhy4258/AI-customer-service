export const API_BASE_KEY = "project1.apiBase";

const endpoint = "/api/v1/customer-service";

export function conversationWebSocketUrl(apiBase, conversationId) {
  const base = apiBase.replace(/\/$/, "");
  const url = new URL(base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `${url.pathname.replace(/\/$/, "")}${endpoint}/ws/conversations/${conversationId}`;
  url.search = "";
  url.hash = "";
  return url.toString();
}

export async function apiRequest(apiBase, path, options = {}) {
  const response = await fetch(`${apiBase.replace(/\/$/, "")}${endpoint}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data;
}

export function getSummary(apiBase) {
  return apiRequest(apiBase, "/summary");
}

export function sendChat(apiBase, payload) {
  return apiRequest(apiBase, "/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function requestHandoff(apiBase, conversationId, reason) {
  return apiRequest(apiBase, `/conversations/${conversationId}/handoff`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function getConversation(apiBase, conversationId) {
  return apiRequest(apiBase, `/conversations/${conversationId}`);
}

export function listHandoffTickets(apiBase) {
  return apiRequest(apiBase, "/admin/handoff-tickets");
}

export function claimTicket(apiBase, ticketId) {
  return apiRequest(apiBase, `/admin/handoff-tickets/${ticketId}/claim`, {
    method: "POST",
  });
}

export function sendHumanReply(apiBase, conversationId, content) {
  return apiRequest(apiBase, `/admin/conversations/${conversationId}/reply`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function closeConversation(apiBase, conversationId) {
  return apiRequest(apiBase, `/admin/conversations/${conversationId}/close`, {
    method: "POST",
    body: JSON.stringify({ reason: "resolved" }),
  });
}

export function uploadKnowledge(apiBase, payload, onProgress) {
  if (!onProgress) {
    return apiRequest(apiBase, "/admin/knowledge/upload", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `${apiBase.replace(/\/$/, "")}${endpoint}/admin/knowledge/upload`);
    request.setRequestHeader("Content-Type", "application/json");
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.min(90, Math.round((event.loaded / event.total) * 90)));
      }
    };
    request.onload = () => {
      let data = {};
      try {
        data = request.responseText ? JSON.parse(request.responseText) : {};
      } catch {
        data = { raw: request.responseText };
      }
      if (request.status >= 200 && request.status < 300) {
        onProgress(100);
        resolve(data);
        return;
      }
      reject(new Error(data.detail || `HTTP ${request.status}`));
    };
    request.onerror = () => reject(new Error("资料上传失败，请检查后端是否可用。"));
    request.send(JSON.stringify(payload));
  });
}

export function listKnowledgeDocuments(apiBase) {
  return apiRequest(apiBase, "/admin/knowledge/documents");
}

export function cancelKnowledgeDocument(apiBase, documentId) {
  return apiRequest(apiBase, `/admin/knowledge/documents/${documentId}/cancel`, {
    method: "POST",
  });
}

export function deleteKnowledgeDocument(apiBase, documentId) {
  return apiRequest(apiBase, `/admin/knowledge/documents/${documentId}`, {
    method: "DELETE",
  });
}
