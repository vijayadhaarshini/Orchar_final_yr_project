import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { atomDark } from "react-syntax-highlighter/dist/esm/styles/prism";

export default function CodeViewer({ code, title = "Generated Code", emptyText = "No code generated yet." }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-50">{title}</h2>
      </div>
      {code ? (
        <div className="max-h-96 overflow-auto rounded-md border border-slate-800 bg-slate-950/70">
          <SyntaxHighlighter language="python" style={atomDark} customStyle={{ margin: 0, padding: "1rem" }}>
            {code}
          </SyntaxHighlighter>
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-slate-700 bg-slate-900/60 p-4 text-xs text-slate-400">
          {emptyText}
        </div>
      )}
    </div>
  );
}

