import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { stripChunkCitations } from "../../utils/stripChunkCitations";

type MarkdownMessageProps = {
  children: string;
  className?: string;
  /** Avoid block elements (e.g. text inside buttons or list items). */
  inline?: boolean;
};

export function MarkdownMessage({ children, className, inline }: MarkdownMessageProps) {
  const cleaned = stripChunkCitations(children);
  const body = (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        p: ({ children: c }) =>
          inline ? <span>{c}</span> : <p style={{ margin: "0 0 0.4em" }}>{c}</p>,
        ul: ({ children: c }) =>
          inline ? <span>{c}</span> : (
            <ul style={{ margin: "0 0 0.4em", paddingLeft: "1.4em" }}>{c}</ul>
          ),
        ol: ({ children: c }) =>
          inline ? <span>{c}</span> : (
            <ol style={{ margin: "0 0 0.4em", paddingLeft: "1.4em" }}>{c}</ol>
          ),
        li: ({ children: c }) =>
          inline ? <span>{c} </span> : <li style={{ margin: "0.15em 0" }}>{c}</li>,
        code: ({ children: c, className: lang }) => {
          const isBlock = lang?.startsWith("language-");
          return isBlock ? (
            <pre
              style={{
                overflowX: "auto",
                padding: "0.6em",
                borderRadius: 6,
                background: "var(--color-panel-low)",
              }}
            >
              <code>{c}</code>
            </pre>
          ) : (
            <code
              style={{
                fontFamily: "var(--font-mono, monospace)",
                fontSize: "0.88em",
                background: "var(--color-panel-low)",
                padding: "0.1em 0.3em",
                borderRadius: 4,
              }}
            >
              {c}
            </code>
          );
        },
      }}
    >
      {cleaned}
    </ReactMarkdown>
  );

  if (className) {
    return <div className={className}>{body}</div>;
  }
  return body;
}
