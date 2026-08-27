"""
Lightweight, dependency-free clustering: groups articles covering the same
story (from different outlets) using word-overlap similarity on titles.
Deliberately avoids heavy ML libraries (sklearn/numpy) to keep the app fast
and easy to deploy on a free, low-CPU hosting tier.
"""
import re
from .rss_fetcher import RawArticle

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "with", "is", "are", "was", "were", "as", "by", "from", "after", "before",
    "over", "into", "amid", "says", "say", "said", "will", "it", "its", "his",
    "her", "their", "this", "that", "new", "how", "why", "what",
}


# Common cross-outlet phrasing variants: different outlets describe the same
# entity/action differently ("Fed" vs "Federal Reserve", "raises" vs "hikes").
# Normalizing these BEFORE tokenizing lets word-overlap matching actually work
# across outlets, without needing a heavy embeddings model.
SYNONYM_MAP = {
    "fed": "federal reserve", "hikes": "raises", "hiked": "raised",
    "slams": "criticizes", "blasts": "criticizes", "vows": "promises",
    "eyes": "considers", "mulls": "considers", "nixes": "cancels",
    "inks": "signs", "probe": "investigation", "cops": "police",
    "govt": "government", "polls": "election",
}


def _normalize(text: str) -> str:
    text = text.lower()
    for slang, formal in SYNONYM_MAP.items():
        text = re.sub(rf"\b{slang}\b", formal, text)
    return text


def _tokenize(text: str) -> set:
    text = _normalize(text)
    words = re.findall(r"[a-zA-Z0-9']+", text)
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def _jaccard_similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


# Longer words carry more topical signal ("inflation", "election") than short
# generic ones ("says", "new"). Two articles that share several such
# "distinctive" words are very likely the same story even if the overall
# Jaccard ratio is diluted by differing phrasing elsewhere in the title.
DISTINCTIVE_MIN_LEN = 6
DISTINCTIVE_MATCH_COUNT = 2


def _distinctive_overlap(a: set, b: set) -> int:
    long_a = {w for w in a if len(w) >= DISTINCTIVE_MIN_LEN}
    long_b = {w for w in b if len(w) >= DISTINCTIVE_MIN_LEN}
    return len(long_a & long_b)


def _is_same_story(a: set, b: set, jaccard_threshold: float) -> bool:
    if _jaccard_similarity(a, b) >= jaccard_threshold:
        return True
    # Fallback rule: enough shared distinctive/topical words = same story,
    # even if generic phrasing differs a lot between outlets.
    return _distinctive_overlap(a, b) >= DISTINCTIVE_MATCH_COUNT


class Cluster:
    def __init__(self, first: RawArticle, token_set: set):
        self.articles: list[RawArticle] = [first]
        self.token_union: set = set(token_set)

    def add(self, article: RawArticle, token_set: set):
        self.articles.append(article)
        self.token_union |= token_set


def cluster_articles(articles: list[RawArticle], similarity_threshold: float = 0.35) -> list[Cluster]:
    """
    Greedy single-pass clustering: O(n * clusters), fine for the few hundred
    articles/day this app deals with. For each new article, join the most
    similar existing cluster if above threshold, else start a new one.
    """
    clusters: list[Cluster] = []

    for article in articles:
        # Use title + a slice of the summary - more shared vocabulary to match on
        # than the title alone, which is often too short to overlap reliably.
        combined_text = f"{article.title} {article.summary[:200]}"
        tokens = _tokenize(combined_text)
        if not tokens:
            continue  # skip articles with no usable text

        best_cluster = None
        best_score = -1.0
        for cluster in clusters:
            if _is_same_story(tokens, cluster.token_union, similarity_threshold):
                score = _jaccard_similarity(tokens, cluster.token_union)
                if score > best_score:
                    best_score = score
                    best_cluster = cluster

        if best_cluster is not None:
            best_cluster.add(article, tokens)
        else:
            clusters.append(Cluster(article, tokens))

    return clusters
