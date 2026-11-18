import { CircleHelp, MessageCircle, Plug, ShieldCheck } from "lucide-react";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { post, useAction, useResource } from "./api";
import { Badge, Button, Card, ErrorBox } from "./ui";
import "./support-workspace.css";
type Status = {
  enabled: boolean;
  available: boolean;
  model: string;
  reason: string;
  max_history: number;
  timeout_seconds: number;
};
type Message = { role: "user" | "assistant"; content: string };
/** max_history 与服务端一致，表示完整对话轮次数；一个轮次含 user/assistant 两条。 */
const boundedHistory = (messages: Message[], rounds: number) =>
  rounds > 0 ? messages.slice(-Math.floor(rounds) * 2) : [];
export function Assistant() {
  const status = useResource<Status>("/assistant/status");
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [currentReply, setCurrentReply] = useState<string>();
  const conversation = useRef(0);
  const action = useAction();
  const cancelWait = () => {
    conversation.current += 1;
    action.cancel();
  };
  const clearConversation = () => {
    cancelWait();
    setMessages([]);
    setCurrentReply(undefined);
    setText("");
  };
  const sendMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const input = text.trim();
    if (!input) return;
    const epoch = conversation.current;
    const historyLimit = status.data?.max_history ?? 0;
    const snapshot = boundedHistory(messages, historyLimit);
    void action.run(async (signal) => {
      const result = await post<{ reply: string; model: string }>(
        "/assistant/chat",
        { text: input, messages: snapshot },
        signal,
      );
      if (signal.aborted || conversation.current !== epoch) return;
      setMessages((previous) =>
        boundedHistory(
          [
            ...previous,
            { role: "user", content: input },
            { role: "assistant", content: result.reply },
          ],
          historyLimit,
        ),
      );
      setCurrentReply(historyLimit === 0 ? result.reply : undefined);
      setText((current) => (current.trim() === input ? "" : current));
    });
  };
  const connection = status.data?.available
    ? "已连接"
    : status.data
      ? status.data.enabled
        ? "未连接"
        : "未启用"
      : status.loading
        ? "正在检查"
        : "状态不可用";
  const displayedReply = status.data?.max_history === 0 ? currentReply : undefined;

  return (
    <>
      <ErrorBox error={status.error ?? action.error} retry={status.refresh} />
      <div className="assistant-workspace">
        <Card className="support-panel assistant-conversation">
          <div className="support-panel-heading">
            <span className="support-icon">
              <MessageCircle size={20} aria-hidden="true" />
            </span>
            <h2>本次会话</h2>
          </div>
          {status.data?.available ? (
            <>
              <div className="chat-messages" role="log" aria-label="对话记录">
                {messages.length ? (
                  messages.map((message, index) => (
                    <div key={index} className={`chat-message ${message.role}`}>
                      <small>{message.role === "user" ? "您" : "文字助手"}</small>
                      <p>{message.content}</p>
                    </div>
                  ))
                ) : !displayedReply ? (
                  <div className="assistant-empty">
                    <MessageCircle size={27} aria-hidden="true" />
                    <h3>开始对话</h3>
                    <p>可询问工作流程、字段含义或一般研究问题。</p>
                  </div>
                ) : null}
                {displayedReply && (
                  <div className="current-reply">
                    <small>本次回复 · 会话历史已关闭</small>
                    <p className="pre-wrap">{displayedReply}</p>
                  </div>
                )}
              </div>
              <form className="assistant-composer" onSubmit={sendMessage}>
                <label>
                  您的问题
                  <textarea
                    rows={3}
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                    maxLength={4000}
                    placeholder="仅输入希望主动发送的文字"
                  />
                </label>
                <div className="form-actions">
                  <Button
                    disabled={action.pending || !text.trim()}
                    type="submit"
                    icon="arrow"
                  >
                    {action.pending ? "正在等待本机助手…" : "发送文字"}
                  </Button>
                  {action.pending && (
                    <Button variant="secondary" type="button" onClick={cancelWait}>
                      取消等待
                    </Button>
                  )}
                  <Button
                    variant="quiet"
                    type="button"
                    disabled={
                      !action.pending && !messages.length && !currentReply && !text
                    }
                    onClick={clearConversation}
                  >
                    清空本次会话
                  </Button>
                </div>
              </form>
            </>
          ) : (
            <div className="assistant-empty assistant-unavailable">
              <Plug size={30} aria-hidden="true" />
              <h3>
                {status.loading ? "正在检查助手状态" : "连接本机助手后开始对话"}
              </h3>
              {status.data && <p>导入、任务与报告可继续使用。</p>}
            </div>
          )}
        </Card>
        <div className="assistant-side">
          <Card className="support-panel">
            <div className="support-panel-heading">
              <span className="support-icon">
                <Plug size={20} aria-hidden="true" />
              </span>
              <h2>本机连接</h2>
              <Badge tone={status.data?.available ? "green" : "neutral"}>
                {connection}
              </Badge>
            </div>
            {status.data?.available ? (
              <dl className="support-facts">
                <div>
                  <dt>当前模型</dt>
                  <dd className="mono">{status.data.model}</dd>
                </div>
              </dl>
            ) : status.data && (
              <div className="support-text-list">
                <p>{status.data.reason}</p>
                <p>
                  在 <code>config/xinlan.json</code> 中配置{" "}
                  <code>assistant_enabled</code>、<code>assistant_base_url</code> 和{" "}
                  <code>assistant_model</code>，然后重启工作台。模型服务须兼容 OpenAI 接口。
                </p>
                <div>
                  <Button variant="secondary" icon="refresh" onClick={status.refresh}>
                    检查连接
                  </Button>
                </div>
              </div>
            )}
          </Card>
          <Card className="support-panel">
            <div className="support-panel-heading">
              <span className="support-icon">
                <ShieldCheck size={20} aria-hidden="true" />
              </span>
              <h2>会话与隐私</h2>
            </div>
            <p className="support-description">
              助手仅接收您主动发送的文字。脑电数据和评估记录不会自动发送。
            </p>
            <p className="assistant-note">
              <CircleHelp size={16} aria-hidden="true" />
              助手回答需独立核验。
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}
