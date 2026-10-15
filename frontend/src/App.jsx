import { useEffect, useMemo, useRef, useState } from "react";
import {
  getAgentConversations,
  getConversationHistory,
  getConversationMetrics,
  getUserConversations,
  postAgentConversationReply,
  postConversationMessage,
  resolveAgentConversation,
  startConversation,
  uploadKnowledgeDocument,
} from "./api";

const emptyMetrics = {
  total_conversations: 0,
  ai_handling: 0,
  pending_agent: 0,
  agent_handling: 0,
  resolved: 0,
};

const BRAND_LOGO_SRC = "/optisolve-logo.png";

function getConversationDraft(conversationData, conversationId) {
  const selected = conversationData.find((item) => item.conversation_id === conversationId);
  return selected?.pending_agent_draft || "";
}

/* ── STATUS CHIP ─────────────────────────────────────────────── */
const STATUS_STYLES = {
  ai_handling:    { color: "#1f5aa6", borderColor: "#b9d3f3", background: "#e9f2fd" },
  pending_agent:  { color: "#8a5a10", borderColor: "#efd39a", background: "#fdf3df" },
  agent_handling: { color: "#16683a", borderColor: "#b5e0c4", background: "#e5f5eb" },
  resolved:       { color: "#4a2f86", borderColor: "#d3c5ee", background: "#efe9f9" },
  none:           { color: "#4a2f86", borderColor: "#d3c5ee", background: "#efe9f9" },
};

function StatusChip({ status }) {
  const s = STATUS_STYLES[status] || STATUS_STYLES.none;
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: "13px",
        fontFamily: "'DM Mono', monospace",
        fontWeight: 500,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        borderRadius: "4px",
        padding: "3px 8px",
        border: `1px solid ${s.borderColor}`,
        background: s.background,
        color: s.color,
      }}
    >
      {status}
    </span>
  );
}

function BrandLogo({ compact = false }) {
  const [imageFailed, setImageFailed] = useState(false);

  return (
    <div className={`brand-logo ${compact ? "compact" : ""}`}>
      {!imageFailed ? (
        <img
          className="brand-logo-image"
          src={BRAND_LOGO_SRC}
          alt="Optisolve logo"
          onError={() => setImageFailed(true)}
        />
      ) : (
        <h1 className="brand-title">OPTISOLVE</h1>
      )}
    </div>
  );
}

/* ── APP ─────────────────────────────────────────────────────── */
function App() {
  const [role, setRole] = useState("");
  const [username, setUsername] = useState("");

  if (!role) {
    return (
      <div className="container centered">
        <div className="card login-card">
          <BrandLogo />

          <label>Username</label>
          <input
            type="text"
            value={username}
            placeholder="Enter your name"
            onChange={(event) => setUsername(event.target.value)}
            onKeyDown={(e) => e.key === "Enter" && username.trim() && setRole("user")}
          />

          <div className="row" style={{ marginTop: "20px" }}>
            <button disabled={!username.trim()} onClick={() => setRole("user")}>
              User Portal
            </button>
            <button
              className="secondary"
              disabled={!username.trim()}
              onClick={() => setRole("agent")}
            >
              AGENT INBOX
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (role === "user") {
    return (
      <UserPortal
        username={username}
        onLogout={() => { setRole(""); setUsername(""); }}
      />
    );
  }

  return (
    <AgentPortal
      username={username}
      onLogout={() => { setRole(""); setUsername(""); }}
    />
  );
}

/* ── USER PORTAL ─────────────────────────────────────────────── */
function UserPortal({ username, onLogout }) {
  const [conversations, setConversations] = useState([]);
  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [dismissedConversationIds, setDismissedConversationIds] = useState(() => new Set());
  const [messages, setMessages] = useState([]);
  const [messageInput, setMessageInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const userMessageListRef = useRef(null);

  const visibleConversations = useMemo(
    () => conversations.filter((item) => !dismissedConversationIds.has(item.conversation_id)),
    [conversations, dismissedConversationIds]
  );

  const selectedConversation = useMemo(
    () => visibleConversations.find((item) => item.conversation_id === selectedConversationId),
    [visibleConversations, selectedConversationId]
  );

  async function loadConversations(autoSelect = true) {
    const data = await getUserConversations(username);
    setConversations(data);
    const visibleData = data.filter((item) => !dismissedConversationIds.has(item.conversation_id));
    const selectedVisible = visibleData.find((item) => item.conversation_id === selectedConversationId);

    if (!visibleData.length) {
      setSelectedConversationId("");
      setMessages([]);
      return;
    }

    if (autoSelect && !selectedVisible) {
      setSelectedConversationId(visibleData[0].conversation_id);
      const history = await getConversationHistory(visibleData[0].conversation_id);
      setMessages(history);
      return;
    }

    if (!autoSelect && selectedConversationId) {
      const current = visibleData.find((item) => item.conversation_id === selectedConversationId);
      if (current) {
        const history = await getConversationHistory(selectedConversationId);
        setMessages(history);
      } else {
        setSelectedConversationId(visibleData[0].conversation_id);
        const history = await getConversationHistory(visibleData[0].conversation_id);
        setMessages(history);
      }
    }
  }

  async function loadHistory(conversationId) {
    const history = await getConversationHistory(conversationId);
    setMessages(history);
  }

  async function handleStartConversation() {
    setError("");
    try {
      setLoading(true);
      const created = await startConversation(username);
      await loadConversations(false);
      setSelectedConversationId(created.conversation_id);
      await loadHistory(created.conversation_id);
    } catch (startError) {
      setError(`Failed to start conversation: ${startError.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleSendMessage(event) {
    event.preventDefault();
    if (!messageInput.trim()) return;

    setError("");
    try {
      setLoading(true);
      let targetConversationId = selectedConversationId;
      if (!targetConversationId) {
        const created = await startConversation(username);
        targetConversationId = created.conversation_id;
        setSelectedConversationId(targetConversationId);
      }

      await postConversationMessage(targetConversationId, messageInput.trim());
      setMessageInput("");
      await loadHistory(targetConversationId);
      await loadConversations(false);
    } catch (sendError) {
      setError(`Failed to send message: ${sendError.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function selectConversation(conversationId) {
    setSelectedConversationId(conversationId);
    setError("");
    try {
      setLoading(true);
      await loadHistory(conversationId);
    } catch (historyError) {
      setError(`Failed to load history: ${historyError.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleResolvedAcknowledgement() {
    if (!selectedConversationId) return;

    const resolvedId = selectedConversationId;
    const remainingConversations = visibleConversations.filter((item) => item.conversation_id !== resolvedId);

    setDismissedConversationIds((previous) => {
      const next = new Set(previous);
      next.add(resolvedId);
      return next;
    });
    setConversations((previous) => previous.filter((item) => item.conversation_id !== resolvedId));

    if (!remainingConversations.length) {
      setSelectedConversationId("");
      setMessages([]);
      return;
    }

    const nextConversationId = remainingConversations[0].conversation_id;
    setSelectedConversationId(nextConversationId);
    try {
      setLoading(true);
      const history = await getConversationHistory(nextConversationId);
      setMessages(history);
    } catch (historyError) {
      setError(`Failed to load history: ${historyError.message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let mounted = true;
    async function bootstrap() {
      setError("");
      try {
        setLoading(true);
        const data = await getUserConversations(username);
        if (!mounted) return;
        setConversations(data);
        const visibleData = data.filter((item) => !dismissedConversationIds.has(item.conversation_id));
        if (visibleData.length) {
          const first = visibleData[0];
          setSelectedConversationId(first.conversation_id);
          const history = await getConversationHistory(first.conversation_id);
          if (!mounted) return;
          setMessages(history);
        }
      } catch (bootstrapError) {
        if (mounted) setError(`Failed to load conversations: ${bootstrapError.message}`);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    bootstrap();
    return () => { mounted = false; };
  }, [username, dismissedConversationIds]);

  useEffect(() => {
    if (!selectedConversationId) return undefined;
    const intervalId = setInterval(async () => {
      try {
        const [conversationData, history] = await Promise.all([
          getUserConversations(username),
          getConversationHistory(selectedConversationId),
        ]);
        setConversations(conversationData);
        if (!dismissedConversationIds.has(selectedConversationId)) {
          setMessages(history);
        }
      } catch { /* silent background polling */ }
    }, 4000);
    return () => clearInterval(intervalId);
  }, [selectedConversationId, username, dismissedConversationIds]);

  useEffect(() => {
    if (userMessageListRef.current) {
      userMessageListRef.current.scrollTop = userMessageListRef.current.scrollHeight;
    }
  }, [messages]);

  const status = selectedConversation?.status || "ai_handling";
  const lastMessage = messages.length ? messages[messages.length - 1] : null;
  const waitingForAgentReply =
    status === "pending_agent" || (status === "agent_handling" && lastMessage?.role !== "agent");
  const isInputDisabled = waitingForAgentReply;

  return (
    <div className="container">
      <header className="header l-header">
        <div className="header-brand">
          <BrandLogo compact />
        </div>
        <div className="row header-actions">
          <button onClick={() => loadConversations(false)} disabled={loading} className="secondary">
            Refresh
          </button>
          <button onClick={handleStartConversation} disabled={loading}>
            + New
          </button>
          <button className="secondary" onClick={onLogout}>
            Logout
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className="card sidebar">
          <h3>Conversations</h3>
          {!visibleConversations.length ? (
            <p className="muted small" style={{ padding: "8px 0" }}>No conversations yet.</p>
          ) : (
            <div className="conversation-list">
              {visibleConversations.map((conversation) => (
                <button
                  key={conversation.conversation_id}
                  className={`conversation-item ${selectedConversationId === conversation.conversation_id ? "active" : ""}`}
                  onClick={() => selectConversation(conversation.conversation_id)}
                >
                  <div className="conversation-top">
                    <span style={{ fontSize: "16px", color: "var(--silver-hi)", fontFamily: "'DM Mono', monospace" }}>
                      #{conversation.conversation_id.slice(0, 8)}
                    </span>
                    <StatusChip status={conversation.status} />
                  </div>
                  <p className="muted small" style={{ marginTop: "4px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {conversation.last_message_preview}
                  </p>
                </button>
              ))}
            </div>
          )}
        </aside>

        <section className="card chat-panel">
          <div className="chat-header">
            <h3>Thread</h3>
            <StatusChip status={status} />
          </div>

          <div className="message-list" ref={userMessageListRef}>
            {!messages.length ? (
              <p className="muted small">No messages yet.</p>
            ) : (
              messages.map((message) => (
                <div key={message.message_id} className={`message ${message.role}`}>
                  <p className="small muted">{message.role.toUpperCase()}</p>
                  <p>{message.content}</p>
                </div>
              ))
            )}
          </div>

          <form onSubmit={handleSendMessage} className="message-form">
            <textarea
              rows={3}
              value={messageInput}
              onChange={(event) => setMessageInput(event.target.value)}
              placeholder={isInputDisabled ? "Waiting for agent…" : "Type your message…"}
              disabled={isInputDisabled}
            />
            <button
              type="submit"
              disabled={loading || isInputDisabled || !messageInput.trim()}
            >
              {loading ? "Sending…" : "Send"}
            </button>
          </form>

          {status === "resolved" && (
            <div className="resolved-box">
              <p className="muted small">This chat has been resolved by an agent.</p>
              <button type="button" className="secondary" onClick={handleResolvedAcknowledgement}>OK</button>
            </div>
          )}
        </section>
      </div>

      {error && <p className="error">{error}</p>}
    </div>
  );
}

/* ── AGENT PORTAL ────────────────────────────────────────────── */
function AgentPortal({ username, onLogout }) {
  const [conversations, setConversations] = useState([]);
  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [messages, setMessages] = useState([]);
  const [replyInput, setReplyInput] = useState("");
  const [metrics, setMetrics] = useState(emptyMetrics);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const agentMessageListRef = useRef(null);

  const selectedConversation = useMemo(
    () => conversations.find((item) => item.conversation_id === selectedConversationId),
    [conversations, selectedConversationId]
  );

  const pending = conversations.filter((item) => item.status === "pending_agent");
  const active  = conversations.filter((item) => item.status === "agent_handling");

  async function refreshData(selectFirst = false) {
    const [conversationData, metricData] = await Promise.all([
      getAgentConversations(),
      getConversationMetrics(),
    ]);
    const actionableConversations = conversationData.filter(
      (item) => item.status === "pending_agent" || item.status === "agent_handling"
    );
    setConversations(actionableConversations);
    setMetrics(metricData);

    if (selectFirst && actionableConversations.length) {
      const target = actionableConversations[0].conversation_id;
      setSelectedConversationId(target);
      const history = await getConversationHistory(target);
      setMessages(history);
      setReplyInput(getConversationDraft(actionableConversations, target));
    } else if (selectedConversationId) {
      const stillExists = actionableConversations.find((item) => item.conversation_id === selectedConversationId);
      if (stillExists) {
        const history = await getConversationHistory(selectedConversationId);
        setMessages(history);
        setReplyInput(getConversationDraft(actionableConversations, selectedConversationId));
      } else if (actionableConversations.length) {
        const next = actionableConversations[0].conversation_id;
        setSelectedConversationId(next);
        const history = await getConversationHistory(next);
        setMessages(history);
        setReplyInput(getConversationDraft(actionableConversations, next));
      } else {
        setSelectedConversationId("");
        setMessages([]);
        setReplyInput("");
      }
    }
  }

  async function selectConversation(conversationId) {
    setSelectedConversationId(conversationId);
    setError("");
    try {
      setLoading(true);
      const history = await getConversationHistory(conversationId);
      setMessages(history);
      setReplyInput(getConversationDraft(conversations, conversationId));
    } catch (historyError) {
      setError(`Failed to load history: ${historyError.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleReply(event) {
    event.preventDefault();
    if (!selectedConversationId || !replyInput.trim()) return;

    setError("");
    try {
      setLoading(true);
      await postAgentConversationReply(selectedConversationId, replyInput.trim());
      setReplyInput("");
      await refreshData(false);
    } catch (replyError) {
      setError(`Failed to send agent reply: ${replyError.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleResolve() {
    if (!selectedConversationId) return;
    const resolvedId = selectedConversationId;
    setError("");
    try {
      setLoading(true);
      await resolveAgentConversation(resolvedId);
      setConversations((previous) => previous.filter((item) => item.conversation_id !== resolvedId));
      await refreshData(false);
    } catch (resolveError) {
      setError(`Failed to resolve conversation: ${resolveError.message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let mounted = true;
    async function bootstrap() {
      setError("");
      try {
        setLoading(true);
        const [conversationData, metricData] = await Promise.all([
          getAgentConversations(),
          getConversationMetrics(),
        ]);
        if (!mounted) return;
        const actionableConversations = conversationData.filter(
          (item) => item.status === "pending_agent" || item.status === "agent_handling"
        );
        setConversations(actionableConversations);
        setMetrics(metricData);
        if (actionableConversations.length) {
          const first = actionableConversations[0].conversation_id;
          setSelectedConversationId(first);
          const history = await getConversationHistory(first);
          if (!mounted) return;
          setMessages(history);
          setReplyInput(getConversationDraft(actionableConversations, first));
        }
      } catch (bootstrapError) {
        if (mounted) setError(`Failed to load agent data: ${bootstrapError.message}`);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    bootstrap();
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (agentMessageListRef.current) {
      agentMessageListRef.current.scrollTop = agentMessageListRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div className="container">
      <header className="header l-header">
        <div className="header-brand">
          <BrandLogo compact />
        </div>
        <div className="header-actions agent-actions">
          <h2 className="header-actions-title">AGENT INBOX</h2>
          <div className="row">
            <button onClick={() => refreshData(true)} disabled={loading} className="secondary">
              Refresh
            </button>
            <button className="secondary" onClick={onLogout}>
              Logout
            </button>
          </div>
        </div>
      </header>

      <section className="grid metrics-grid">
        <MetricCard title="Total" value={metrics.total_conversations} />
        <MetricCard title="AI Handling" value={metrics.ai_handling} color="#1f5aa6" />
        <MetricCard title="Pending" value={metrics.pending_agent} color="#b7791f" />
        <MetricCard title="Agent Active" value={metrics.agent_handling} color="#1e8a4c" />
        <MetricCard title="Resolved" value={metrics.resolved} color="#6d28d9" />
      </section>

      <div className="layout">
        <aside className="card sidebar">
          <h3>Pending Agent</h3>
          <ConversationSection
            conversations={pending}
            selectedConversationId={selectedConversationId}
            onSelect={selectConversation}
          />
          <h3>Agent Handling</h3>
          <ConversationSection
            conversations={active}
            selectedConversationId={selectedConversationId}
            onSelect={selectConversation}
          />
          <h3>Knowledge Base</h3>
          <KnowledgeBaseUpload />
        </aside>

        <section className="card chat-panel">
          <div className="chat-header">
            <h3>Thread</h3>
            <StatusChip status={selectedConversation?.status || "none"} />
          </div>

          <div className="message-list" ref={agentMessageListRef}>
            {selectedConversation?.pending_agent_draft && (
              <div className="message-draft">
                <p className="small muted">TIER2 AI DRAFT</p>
                <p>{selectedConversation.pending_agent_draft}</p>
              </div>
            )}
            {!messages.length ? (
              <p className="muted small">Select a conversation from the inbox.</p>
            ) : (
              messages.map((message) => (
                <div key={message.message_id} className={`message ${message.role}`}>
                  <p className="small muted">{message.role.toUpperCase()}</p>
                  <p>{message.content}</p>
                  {message.agent_draft_reply && (
                    <div className="message-draft">
                      <p className="small muted">TIER2 AI DRAFT</p>
                      <p>{message.agent_draft_reply}</p>
                    </div>
                  )}
                  <p className="small muted" style={{ marginTop: "6px" }}>
                    {message.tier ? `tier: ${message.tier}` : ""}
                    {message.confidence !== null && message.confidence !== undefined
                      ? `  ·  confidence: ${message.confidence}`
                      : ""}
                  </p>
                </div>
              ))
            )}
          </div>

          <form onSubmit={handleReply} className="message-form">
            <textarea
              rows={3}
              value={replyInput}
              onChange={(event) => setReplyInput(event.target.value)}
              placeholder="Type agent reply…"
              disabled={!selectedConversationId}
            />
            <div className="row">
              <button
                type="submit"
                disabled={!selectedConversationId || !replyInput.trim() || loading}
              >
                {loading ? "Sending…" : "Send Reply"}
              </button>
              <button
                type="button"
                className="secondary"
                onClick={handleResolve}
                disabled={!selectedConversationId || loading}
              >
                Mark Resolved
              </button>
            </div>
          </form>
        </section>
      </div>

      {error && <p className="error">{error}</p>}
    </div>
  );
}

/* ── CONVERSATION SECTION ────────────────────────────────────── */
function ConversationSection({ conversations, selectedConversationId, onSelect }) {
  if (!conversations.length) {
    return <p className="muted small" style={{ padding: "4px 0 8px" }}>No conversations</p>;
  }

  return (
    <div className="conversation-list compact">
      {conversations.map((conversation) => (
        <button
          key={conversation.conversation_id}
          className={`conversation-item ${selectedConversationId === conversation.conversation_id ? "active" : ""}`}
          onClick={() => onSelect(conversation.conversation_id)}
        >
          <div className="conversation-top">
            <span style={{ fontSize: "17px", color: "var(--silver-hi)", fontFamily: "'DM Mono', monospace" }}>
              {conversation.username}
            </span>
            <StatusChip status={conversation.status} />
          </div>
          <p className="muted small" style={{ marginTop: "4px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {conversation.last_message_preview}
          </p>
        </button>
      ))}
    </div>
  );
}

/* ── KNOWLEDGE BASE UPLOAD ───────────────────────────────────── */
function KnowledgeBaseUpload() {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState("");
  const [uploadError, setUploadError] = useState("");
  const fileInputRef = useRef(null);

  async function handleUpload(event) {
    event.preventDefault();
    if (!file) return;
    setUploading(true);
    setResult("");
    setUploadError("");
    try {
      const data = await uploadKnowledgeDocument(file);
      setResult(`Added ${data.chunks_added} chunk${data.chunks_added === 1 ? "" : "s"} from ${data.filename}`);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <form onSubmit={handleUpload} style={{ display: "grid", gap: "8px" }}>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.txt"
        onChange={(event) => setFile(event.target.files?.[0] || null)}
      />
      <button type="submit" disabled={!file || uploading}>
        {uploading ? "Uploading…" : "Upload document"}
      </button>
      {result && <p className="muted small">{result}</p>}
      {uploadError && <p className="error small">{uploadError}</p>}
    </form>
  );
}

/* ── METRIC CARD ─────────────────────────────────────────────── */
function MetricCard({ title, value, color }) {
  return (
    <div className="card metric-card">
      <p className="muted small">{title}</p>
      <h3 style={color ? { color } : {}}>{value}</h3>
    </div>
  );
}

export default App;
