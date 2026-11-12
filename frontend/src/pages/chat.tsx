/**
 * N1 · 对话页（v2，参考 RAG 项目前端交互）：Markdown 渲染、消息操作栏
 * （复制/重新生成/👍👎）、欢迎态引导、textarea 多行输入、自动滚动、
 * 引用来源列表。SSE 流式 + 无状态多轮（history 回传）。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Button,
  Input,
  Space,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  CopyOutlined,
  RedoOutlined,
  SendOutlined,
  ThunderboltFilled,
} from "@ant-design/icons";
import { API_BASE, documentsApi } from "../api";
import { getToken } from "../auth";
import "./chat.css";

interface Citation {
  index: number;
  doc_id: string;
  version: number;
  page: number | null;
  score: number;
}

interface ChatTurn {
  id: number;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  usage?: { total_tokens: number };
  feedback?: "good" | "bad" | null;
}

const WELCOME_EXAMPLES = [
  "知识库里有哪些合作办学项目？",
  "总结一下上传文档的主要内容",
  "信息管理硕士项目由谁负责实施？",
];

async function streamChat(
  body: { query: string; history: Array<{ role: string; content: string }> },
  onToken: (delta: string) => void,
): Promise<{ answer: string; citations: Citation[]; usage?: { total_tokens: number } }> {
  const resp = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken() ?? ""}` },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    let detail = `HTTP ${resp.status}`;
    try {
      const j = (await resp.json()) as { message?: string };
      if (j.message) detail = j.message;
    } catch {
      /* keep status line */
    }
    throw new Error(detail);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let answer = "";
  let citations: Citation[] = [];
  let usage: { total_tokens: number } | undefined;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const lines = block.split("\n");
      const eventLine = lines.find((l) => l.startsWith("event: "));
      const dataLine = lines.find((l) => l.startsWith("data: "));
      if (!eventLine || !dataLine) continue;
      const event = eventLine.slice(7);
      const data = JSON.parse(dataLine.slice(6)) as Record<string, unknown>;
      if (event === "token") {
        answer += String(data.delta ?? "");
        onToken(String(data.delta ?? ""));
      } else if (event === "done") {
        answer = String(data.answer ?? answer);
        citations = (data.citations as Citation[]) ?? [];
        usage = data.usage as { total_tokens: number } | undefined;
      } else if (event === "error") {
        throw new Error(String(data.message ?? "LLM 调用失败"));
      }
    }
  }
  return { answer, citations, usage };
}

export default function ChatPage() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  /** doc_id -> 标题（引用来源行展示用，跨回答缓存）。 */
  const [docTitles, setDocTitles] = useState<Record<string, string>>({});
  const listRef = useRef<HTMLDivElement | null>(null);
  const nextId = useRef(1);

  /** 引用里出现的 doc_id 批量拉标题（标题让来源行信息充实不空旷）。 */
  useEffect(() => {
    const missing = Array.from(
      new Set(
        turns
          .flatMap((t) => t.citations ?? [])
          .map((c) => c.doc_id)
          .filter((id) => id && docTitles[id] === undefined),
      ),
    );
    if (missing.length === 0) return;
    let mounted = true;
    void Promise.all(
      missing.map(async (id) => {
        try {
          const d = await documentsApi.detail(id);
          return [id, d.title ?? d.file_name] as const;
        } catch {
          return [id, ""] as const;
        }
      }),
    ).then((pairs) => {
      if (mounted) setDocTitles((prev) => ({ ...prev, ...Object.fromEntries(pairs) }));
    });
    return () => {
      mounted = false;
    };
  }, [turns, docTitles]);

  /** 新消息/流式输出时自动滚到底部。 */
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, streamText]);

  const ask = useCallback(
    async (query: string, opts?: { replaceFrom?: number }) => {
      if (!query.trim() || streaming) return;
      const history = turns
        .slice(0, opts?.replaceFrom)
        .map((t) => ({ role: t.role, content: t.content }));
      if (opts?.replaceFrom !== undefined) {
        // regenerate: drop everything from the replaced turn onward
        setTurns((t) => t.slice(0, opts.replaceFrom));
      } else {
        setTurns((t) => [...t, { id: nextId.current++, role: "user", content: query }]);
      }
      setStreaming(true);
      setStreamText("");
      try {
        const result = await streamChat({ query, history }, (delta) =>
          setStreamText((s) => s + delta),
        );
        setTurns((t) => [
          ...t,
          {
            id: nextId.current++,
            role: "assistant",
            content: result.answer,
            citations: result.citations,
            usage: result.usage,
            feedback: null,
          },
        ]);
      } catch (err) {
        setTurns((t) => [
          ...t,
          {
            id: nextId.current++,
            role: "assistant",
            content: `⚠️ ${err instanceof Error ? err.message : "对话失败"}`,
            feedback: null,
          },
        ]);
      } finally {
        setStreamText("");
        setStreaming(false);
      }
    },
    [turns, streaming],
  );

  const send = useCallback(() => {
    const q = input.trim();
    if (!q || streaming) return;
    setInput("");
    void ask(q);
  }, [input, streaming, ask]);

  const regenerate = useCallback(
    (turnId: number) => {
      const idx = turns.findIndex((t) => t.id === turnId);
      if (idx === -1) return;
      const prevUser = [...turns.slice(0, idx)].reverse().find((t) => t.role === "user");
      if (!prevUser) {
        message.warning("找不到对应的提问");
        return;
      }
      void ask(prevUser.content, { replaceFrom: idx });
    },
    [turns, ask],
  );

  const copyTurn = useCallback(async (t: ChatTurn) => {
    try {
      await navigator.clipboard.writeText(t.content);
      message.success("已复制到剪贴板");
    } catch {
      message.error("复制失败");
    }
  }, []);

  const feedback = useCallback((turnId: number, mark: "good" | "bad") => {
    setTurns((t) =>
      t.map((x) =>
        x.id === turnId ? { ...x, feedback: x.feedback === mark ? null : mark } : x,
      ),
    );
  }, []);

  const renderAssistantBody = (t: ChatTurn) => (
    <div className="chat-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{t.content}</ReactMarkdown>
      {t.citations && t.citations.length > 0 && (
        <div className="chat-sources">
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            引用来源（{t.citations.length}）：
          </Typography.Text>
          <div className="chat-citations">
            {t.citations.map((c) => {
              const title = docTitles[c.doc_id] || `文档 ${c.doc_id.slice(0, 8)}…`;
              return (
                <Tooltip
                  key={c.index}
                  title={`文档 ID ${c.doc_id} · v${c.version}${
                    c.page ? ` · 第 ${c.page} 页` : ""
                  } · 相似度 ${c.score.toFixed(3)}`}
                >
                  <div className="chat-citation-row">
                    <span className="chat-citation-idx">[{c.index}]</span>
                    <span className="chat-citation-title">{title}</span>
                    <span className="chat-citation-meta">
                      v{c.version}
                      {c.page ? ` · 第 ${c.page} 页` : ""} · {c.score.toFixed(3)}
                    </span>
                  </div>
                </Tooltip>
              );
            })}
          </div>
        </div>
      )}
      <div className="chat-actions">
        <Tooltip title="复制回答">
          <Button size="small" type="text" icon={<CopyOutlined />} onClick={() => void copyTurn(t)} />
        </Tooltip>
        <Tooltip title="重新生成">
          <Button
            size="small"
            type="text"
            icon={<RedoOutlined />}
            disabled={streaming}
            onClick={() => regenerate(t.id)}
          />
        </Tooltip>
        <Tooltip title="有帮助">
          <Button
            size="small"
            type="text"
            danger={t.feedback === "bad"}
            style={t.feedback === "good" ? { color: "#52c41a" } : undefined}
            onClick={() => feedback(t.id, "good")}
          >
            👍
          </Button>
        </Tooltip>
        <Tooltip title="没帮助">
          <Button
            size="small"
            type="text"
            style={t.feedback === "bad" ? { color: "#ff4d4f" } : undefined}
            onClick={() => feedback(t.id, "bad")}
          >
            👎
          </Button>
        </Tooltip>
        {t.usage?.total_tokens ? (
          <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: "auto" }}>
            {t.usage.total_tokens} tokens
          </Typography.Text>
        ) : null}
      </div>
    </div>
  );

  return (
    <div className="chat-page">
      <div className="chat-list" ref={listRef}>
        <div className="chat-list-inner">
          {turns.length === 0 && !streaming && (
            <div className="chat-welcome">
              <ThunderboltFilled style={{ fontSize: 40, color: "#1677ff" }} />
              <Typography.Title level={3} style={{ marginTop: 12 }}>
                知识库问答
              </Typography.Title>
              <Typography.Paragraph type="secondary" style={{ maxWidth: 460 }}>
                仅依据知识库检索到的内容回答（带 [n] 引用溯源）；知识库覆盖不足时会明确拒答而不是编造。
              </Typography.Paragraph>
              <Space direction="vertical" size={8} style={{ marginTop: 8 }}>
                {WELCOME_EXAMPLES.map((ex) => (
                  <Button key={ex} onClick={() => setInput(ex)} style={{ textAlign: "left" }}>
                    {ex}
                  </Button>
                ))}
              </Space>
            </div>
          )}

          {turns.map((t) => (
            <div key={t.id} className={`chat-row ${t.role}`}>
              <div className={`chat-bubble ${t.role}`}>
                {t.role === "user" ? (
                  <div className="chat-user-text">{t.content}</div>
                ) : (
                  renderAssistantBody(t)
                )}
              </div>
            </div>
          ))}

          {streaming && (
            <div className="chat-row assistant">
              <div className="chat-bubble assistant">
                <div className="chat-markdown">
                  {streamText ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamText}</ReactMarkdown>
                  ) : (
                    <Typography.Text type="secondary">检索知识库并生成中…</Typography.Text>
                  )}
                  <span className="chat-caret" />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="chat-inputbar">
        <div className="chat-inputbar-inner">
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="向知识库提问…（Enter 发送，Shift+Enter 换行）"
            autoSize={{ minRows: 1, maxRows: 6 }}
            disabled={streaming}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={streaming}
            disabled={!input.trim()}
            onClick={send}
            style={{ height: "auto", minHeight: 40, paddingLeft: 20, paddingRight: 20 }}
          >
            发送
          </Button>
        </div>
      </div>
    </div>
  );
}
