import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../api";
import CategoryTabs from "../components/CategoryTabs";
import StoryCard from "../components/StoryCard";
import StoryDetailModal from "../components/StoryDetailModal";
import Loader from "../components/Loader";

export default function DailyEdition() {
  const [searchParams] = useSearchParams();
  const [categories, setCategories] = useState([]);
  const [activeCategory, setActiveCategory] = useState("general");
  const [edition, setEdition] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openStory, setOpenStory] = useState(null);

  const dateParam = searchParams.get("date");

  useEffect(() => {
    api.get("/categories").then((res) => {
      setCategories([{ slug: "general", name: "Mixed / For You" }, ...res.data.filter((c) => c.slug !== "general")]);
    }).catch(() => {});
  }, []);

  const loadEdition = useCallback(() => {
    setLoading(true);
    setError("");
    const params = {};
    if (dateParam) params.date = dateParam;
    if (activeCategory !== "general") params.category = activeCategory;

    api.get("/editions", { params })
      .then((res) => setEdition(res.data))
      .catch((err) => setError(err.friendlyMessage || "Couldn't load today's edition"))
      .finally(() => setLoading(false));
  }, [activeCategory, dateParam]);

  useEffect(() => { loadEdition(); }, [loadEdition]);

  return (
    <div className="container">
      <CategoryTabs categories={categories} active={activeCategory} onSelect={setActiveCategory} />

      <div className="edition-header">
        <div className="edition-date">{edition?.edition_date || "Today"}</div>
        <div className="edition-title">Your Morning Brief</div>
        {edition && (
          <div className="edition-meta">
            {edition.story_count} {edition.story_count === 1 ? "story" : "stories"} · ~{edition.estimated_read_minutes} min read
          </div>
        )}
      </div>

      {loading && <Loader text="Fetching today's stories..." />}

      {!loading && error && (
        <div className="empty-state">
          <div className="empty-state-title">Couldn't load this edition</div>
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && edition && edition.stories.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-title">No stories here yet</div>
          <p>Check back after the next ingestion run, or try a different category.</p>
        </div>
      )}

      {!loading && !error && edition && edition.stories.length > 0 && (
        <>
          <div className="story-list">
            {edition.stories.map((s) => (
              <StoryCard key={s.id} story={s} onOpen={setOpenStory} />
            ))}
          </div>
          <div className="caught-up">You're all caught up for today. ✓</div>
        </>
      )}

      <StoryDetailModal story={openStory} onClose={() => setOpenStory(null)} />
    </div>
  );
}
