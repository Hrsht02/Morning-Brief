"""Cheap recall-first candidate selection before expensive clustering/LLM work.

RSS fetching remains broad, but expensive processing is applied only to a
ranked candidate pool. The selector deliberately preserves source diversity
and urgent-looking stories so a hard top-N cutoff does not silently discard an
important event from a single source.
"""
import datetime
import re
from collections import defaultdict
from .rss_fetcher import RawArticle

URGENT_TERMS={"breaking","urgent","alert","attack","crash","earthquake","cyclone","flood","fire","explosion","war","strike","killed","death","dies","resigns","resignation","arrested","arrest","verdict","court","ruling","election","poll","budget","rate","ban","bans","deal","agreement","launch","launched","acquires","acquisition","ipo","scandal","outage"}

def _text_tokens(article):
    return set(re.findall(r"[a-z0-9]+",f"{article.title} {article.summary[:500]}".lower()))

def _recency_score(published_at,now):
    if not published_at:return 8.0
    age_hours=max(0.0,(now-published_at).total_seconds()/3600.0)
    if age_hours<=2:return 35.0
    if age_hours<=6:return 30.0
    if age_hours<=12:return 24.0
    if age_hours<=24:return 18.0
    if age_hours<=48:return 8.0
    return 2.0

def score_article(article,now=None):
    now=now or datetime.datetime.now(datetime.timezone.utc)
    published=article.published_at
    if published and published.tzinfo is None:published=published.replace(tzinfo=datetime.timezone.utc)
    score=_recency_score(published,now)
    score+={1:10.0,2:15.0,3:17.0}.get(int(getattr(article,"trust_tier",2) or 2),12.0)
    score+=min(22.0,5.0*len(_text_tokens(article)&URGENT_TERMS))
    score+=min(8.0,len(article.summary)/180.0)
    if getattr(article,"source_legal_risk_level","standard")=="high":score-=3.0
    return score

def select_candidates(articles,per_source=6,pool_size=60,now=None):
    """High-recall candidate pool: source diversity first, score second."""
    if not articles:return []
    per_source=max(1,int(per_source));pool_size=max(per_source,int(pool_size));now=now or datetime.datetime.now(datetime.timezone.utc)
    grouped=defaultdict(list)
    for article in articles:grouped[article.source_name].append(article)
    scored={id(a):score_article(a,now) for a in articles};chosen=[];chosen_ids=set()
    for items in grouped.values():
        ranked=sorted(items,key=lambda a:(scored[id(a)],a.published_at or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)),reverse=True)
        for article in ranked[:per_source]:chosen.append(article);chosen_ids.add(id(article))
    if len(chosen)<pool_size:
        remainder=sorted((a for a in articles if id(a) not in chosen_ids),key=lambda a:scored[id(a)],reverse=True)
        chosen.extend(remainder[:pool_size-len(chosen)])
    chosen.sort(key=lambda a:(scored[id(a)],a.published_at or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)),reverse=True)
    return chosen[:pool_size]
