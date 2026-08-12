import { Message } from "@patternfly/chatbot";

export interface AiMessage {
  role: "ai" | "system";
  content: string;
  timestamp?: string;
}

export interface AiReasoningPanelProps {
  messages: AiMessage[];
}

export function AiReasoningPanel({ messages }: AiReasoningPanelProps) {
  if (messages.length === 0) return null;

  return (
    <div>
      {messages.map((msg, i) => (
        <Message
          key={i}
          role="bot"
          content={msg.content}
          name={msg.role === "ai" ? "AI Agent" : "System"}
          timestamp={msg.timestamp}
        />
      ))}
    </div>
  );
}
