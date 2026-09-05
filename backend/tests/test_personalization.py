from types import SimpleNamespace
from app.services.personalization import select_personalized_stories


def story(category, country="IN", confidence=0.9):
    return SimpleNamespace(category_slug=category, country_code=country, confidence_score=confidence, is_pinned=False)


def test_empty_preferences_return_all_matching_country_news():
    stories=[story("fintech"),story("sports"),story("technology")]
    selected,_=select_personalized_stories(stories,"IN",set(),None)
    assert {s.category_slug for s in selected}=={"fintech","sports","technology"}


def test_selected_category_is_strict():
    stories=[story("fintech"),story("sports"),story("technology")]
    selected,_=select_personalized_stories(stories,"IN",{"fintech"},None)
    assert [s.category_slug for s in selected]==["fintech"]


def test_email_limit_is_applied_after_personalization():
    stories=[story("fintech"),story("fintech"),story("sports")]
    selected,_=select_personalized_stories(stories,"IN",{"fintech"},1)
    assert len(selected)==1
    assert selected[0].category_slug=="fintech"
