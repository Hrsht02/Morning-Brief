export default function StoryDetailModal({ story, onClose }) {
  if (!story) return null;

  return (
    <div className="story-detail-overlay" onClick={onClose}>
      <div className="story-detail-card" onClick={(e) => e.stopPropagation()}>
        <button className="close-btn" onClick={onClose} aria-label="Close">✕</button>
        <span className="category-chip">{(story.category_slug || "general").replace(/-/g, " ")}</span>
        <h2 className="story-headline" style={{ fontSize: 26, marginTop: 12 }}>{story.headline}</h2>
        <p className="story-summary" style={{ fontSize: 16, lineHeight: 1.65 }}>{story.summary}</p>

        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-faint)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 8 }}>
            Sources for this story
          </div>
          <div className="citation-row">
            {story.citations.map((c, i) => (
              <a key={i} href={c.url} target="_blank" rel="noopener noreferrer" className="citation-badge">
                🔗 {c.source_name}{c.title ? ` — ${c.title}` : ""}
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
