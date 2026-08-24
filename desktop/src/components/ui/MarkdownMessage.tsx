import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

export function MarkdownMessage({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        p: ({ children: c }) => <p style={{ margin: "0 0 0.4em" }}>{c}</p>,
        ul: ({ children: c }) => <ul style={{ margin: "0 0 0.4em", paddingLeft: "1.4em" }}>{c}</ul>,
        ol: ({ children: c }) => <ol style={{ margin: "0 0 0.4em", paddingLeft: "1.4em" }}>{c}</ol>,
        li: ({ children: c }) => <li style={{ margin: "0.15em 0" }}>{c}</li>,
        code: ({ children: c, className }) => {
          const isBlock = className?.startsWith("language-");
          return isBlock ? (
            <pre style={{ overflowX: "auto", padding: "0.6em", borderRadius: 6, background: "var(--color-panel-low)" }}>
              <code>{c}</code>
            </pre>
          ) : (
            <code style={{ fontFamily: "var(--font-mono, monospace)", fontSize: "0.88em", background: "var(--color-panel-low)", padding: "0.1em 0.3em", borderRadius: 4 }}>{c}</code>
          );
        },
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
