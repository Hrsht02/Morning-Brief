export default function StoryCard({ story, onOpen }) {
  const categoryLabel = (story.category_slug || "general").replace(/-/g, " ");

  return (
    <div className={`story-card ${story.is_pinned ? "pinned" : ""}`} onClick={() => onOpen(story)}>
      <div className="story-top-row">
        <span className="category-chip">{categoryLabel}</span>
        {story.is_pinned && <span className="pinned-badge">Top Story</span>}
        {story.needs_review && <span className="review-badge">Under review</span>}
      </div>
      <h3 className="story-headline">{story.headline}</h3>
      <p className="story-summary">{story.summary}</p>
      {story.citations && story.citations.length > 0 && (
        <div className="citation-row" onClick={(e) => e.stopPropagation()}>
          {story.citations.slice(0, 3).map((c, i) => (
            <a key={i} href={c.url} target="_blank" rel="noopener noreferrer" className="citation-badge">
              🔗 {c.source_name}
            </a>
          ))}
          {story.citations.length > 3 && (
            <span className="citation-badge">+{story.citations.length - 3} more</span>
          )}
        </div>
      )}
    </div>
  );
}
