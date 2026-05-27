function inlineMarkdown(text: string): (string | JSX.Element)[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

export function MarkdownMessage({ content }: { content: string }) {
  const blocks = content
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  return (
    <div className="markdown-message">
      {blocks.map((block, index) => {
        const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
        const isList = lines.every((line) => /^([-*]|\d+\.)\s+/.test(line));
        if (isList) {
          const ordered = lines.every((line) => /^\d+\.\s+/.test(line));
          const items = lines.map((line) => line.replace(/^([-*]|\d+\.)\s+/, ""));
          const ListTag = ordered ? "ol" : "ul";
          return (
            <ListTag key={index}>
              {items.map((item, itemIndex) => (
                <li key={itemIndex}>{inlineMarkdown(item)}</li>
              ))}
            </ListTag>
          );
        }
        return <p key={index}>{inlineMarkdown(lines.join("\n"))}</p>;
      })}
    </div>
  );
}
