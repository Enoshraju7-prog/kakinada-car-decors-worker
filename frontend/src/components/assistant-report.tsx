import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Model output is untrusted: keep raw HTML and embedded images disabled.
export default function AssistantReport({ text }: { text: string }) {
  return (
    <div className="report-summary">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        disallowedElements={["img"]}
        components={{
          table: ({ children }) => (
            <div
              className="report-table"
              tabIndex={0}
              aria-label="Assistant report table"
            >
              <table>{children}</table>
            </div>
          ),
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}
