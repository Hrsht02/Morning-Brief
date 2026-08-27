export default function CategoryTabs({ categories, active, onSelect }) {
  return (
    <div className="category-tabs">
      {categories.map((c) => (
        <button
          key={c.slug}
          className={`category-tab ${active === c.slug ? "active" : ""}`}
          onClick={() => onSelect(c.slug)}
        >
          {c.name}
        </button>
      ))}
    </div>
  );
}
