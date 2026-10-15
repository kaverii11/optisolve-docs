const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Request failed");
  }

  return response.json();
}

export function startConversation(username) {
  return request("/conversation/start", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
}

export function getUserConversations(username) {
  return request(`/conversation/user/${encodeURIComponent(username)}`);
}

export function postConversationMessage(conversationId, content) {
  return request(`/conversation/${conversationId}/message`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function getConversationHistory(conversationId) {
  return request(`/conversation/${conversationId}/history`);
}

export function getAgentConversations() {
  return request("/agent/conversations");
}

export function postAgentConversationReply(conversationId, content) {
  return request(`/agent/conversation/${conversationId}/reply`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function resolveAgentConversation(conversationId) {
  return request(`/agent/conversation/${conversationId}/resolve`, {
    method: "POST",
  });
}

export function getConversationMetrics() {
  return request("/conversation-metrics");
}

export async function uploadKnowledgeDocument(file) {
  const formData = new FormData();
  formData.append("file", file);

  // No JSON Content-Type here: the browser sets the multipart boundary itself.
  const response = await fetch(`${API_BASE_URL}/knowledge-base/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    let detail = errorText;
    try {
      detail = JSON.parse(errorText).detail || errorText;
    } catch {
      // plain-text error body
    }
    throw new Error(detail || "Upload failed");
  }

  return response.json();
}

export { API_BASE_URL };
