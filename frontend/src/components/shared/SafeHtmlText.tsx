interface SafeHtmlTextProps {
  text: string;
  className?: string;
}

export function SafeHtmlText({ text, className = "" }: SafeHtmlTextProps) {
  if (!text) return null;

  // Check if text has any HTML tags (e.g., <p>, <ul>, <li>, <br>)
  const hasHtml = /<[a-z][\s\S]*>/i.test(text);

  if (hasHtml) {
    return (
      <div 
        className={`safe-html-content ${className}`} 
        dangerouslySetInnerHTML={{ __html: text }} 
      />
    );
  }

  return (
    <p className={`whitespace-pre-line ${className}`}>
      {text}
    </p>
  );
}
