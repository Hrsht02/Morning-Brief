"""Safe first-start defaults; all tunable behavior remains admin-editable."""
import logging
from sqlalchemy.orm import Session
from . import models
from .security import hash_password
from .config import settings
logger=logging.getLogger("morning_brief.seed")
DEFAULT_CATEGORIES=[("general","Mixed / For You",None,0),("national","National",None,1),("international","International",None,2),("business","Business",None,3),("technology","Technology",None,4),("sports","Sports",None,5),("entertainment","Entertainment",None,6),("science-health","Science & Health",None,7),("politics","Politics",None,8),("cricket","Cricket","sports",0),("football","Football","sports",1)]
DEFAULT_SOURCES=[("The Hindu - National","https://www.thehindu.com/news/national/feeder/default.rss","national","IN",2),("The Hindu - International","https://www.thehindu.com/news/international/feeder/default.rss","international","IN",2),("NDTV Top Stories","https://feeds.feedburner.com/ndtvnews-top-stories","general","IN",2),("Indian Express - India","https://indianexpress.com/section/india/feed/","national","IN",2),("BBC World","http://feeds.bbci.co.uk/news/world/rss.xml","international","GB",1),("BBC Top Stories","http://feeds.bbci.co.uk/news/rss.xml","general","GB",1),("Al Jazeera","https://www.aljazeera.com/xml/rss/all.xml","international","GLOBAL",1),("NPR News","https://feeds.npr.org/1001/rss.xml","international","US",2),("TechCrunch","https://techcrunch.com/feed/","technology","US",2),("ESPN Top Headlines","https://www.espn.com/espn/rss/news","sports","US",2)]
DEFAULT_SETTINGS=[
("stories_per_edition","8","Maximum stories in an edition"),("min_confidence_score","0.55","Minimum AI confidence before review"),("cluster_similarity_threshold","0.25","Article clustering threshold"),("summary_max_sentences","3","Maximum summary sentences"),("outside_bubble_min_stories","1","Minimum stories outside selected categories"),("require_human_approval_all","true","Require explicit human approval for every production story"),("skip_all_verification","false","Danger: bypass every verification layer"),("near_verbatim_similarity_threshold","0.55","Word overlap threshold for near-verbatim risk"),("long_phrase_overlap_threshold","0.20","Long phrase overlap threshold"),("long_phrase_words","6","Consecutive words used by long-phrase detection"),("originality_rewrite_trigger_threshold","0.35","Similarity score that triggers automatic Groq originality rewrite"),("max_entries_per_source","15","Maximum RSS entries processed per source per run"),("source_fetch_timeout_seconds","15","RSS request timeout in seconds"),("max_clusters_per_run","100","Safety cap on clusters processed in one production run"),("llm_pause_seconds","7","Pause between Groq generation calls"),("blocked_source_domains","ani.in,aninews.in,ptinews.com,ptinews.in","Domains never fetched"),("bilingual_generation","true","Generate English and Hindi variants"),("scheduling_mode","auto","auto or manual"),("admin_timezone","Asia/Kolkata","Timezone used for edition dates and final ingestion deadline"),("final_ingestion_hour","23","Informational final daily ingestion hour"),("email_send_window_start","06:00","Intended daily send window start"),("email_send_window_end","07:00","Intended daily send window end"),("testing_mode","false","Show testing-mode indicator"),("developer_test_email","","Safe destination for developer test email")]
DEFAULT_VERIFICATION_LAYERS=[("source_policy","Source Policy Check",True,True,0),("citation_completeness","Citation Completeness",True,True,1),("near_verbatim_similarity","Near-Verbatim Similarity Check",True,True,2),("long_phrase_similarity","Long-Phrase Copy Check",True,True,3),("confidence_threshold","AI Confidence Threshold",True,True,4),("independent_ai_verifier","Independent AI Verifier (Gemini)",True,True,5)]
DEFAULT_PLANS=[("free","Free",0)]

def run_seed(db:Session):
    if db.query(models.Category).count()==0:
        for slug,name,parent,order in DEFAULT_CATEGORIES: db.add(models.Category(slug=slug,name=name,parent_slug=parent,sort_order=order))
    if db.query(models.Source).count()==0:
        for name,url,cat,country,tier in DEFAULT_SOURCES: db.add(models.Source(name=name,rss_url=url,default_category=cat,country_code=country,trust_tier=tier))
    existing_keys={s.key for s in db.query(models.Setting).all()}
    for key,value,desc in DEFAULT_SETTINGS:
        if key not in existing_keys: db.add(models.Setting(key=key,value=value,description=desc))
    existing_layers={l.key for l in db.query(models.VerificationLayer).all()}
    for key,name,enabled,blocking,order in DEFAULT_VERIFICATION_LAYERS:
        if key not in existing_layers: db.add(models.VerificationLayer(key=key,name=name,is_enabled=enabled,is_blocking=blocking,sort_order=order))
    if db.query(models.Plan).count()==0:
        for slug,name,price in DEFAULT_PLANS: db.add(models.Plan(slug=slug,name=name,price_cents=price))
    db.commit()
    admin=db.query(models.User).filter(models.User.email==settings.ADMIN_EMAIL).first()
    if admin is None:
        free=db.query(models.Plan).filter(models.Plan.slug=="free").first()
        db.add(models.User(email=settings.ADMIN_EMAIL,hashed_password=hash_password(settings.ADMIN_PASSWORD),is_admin=True,role="admin",onboarded=True,country_code="IN",plan_id=free.id if free else None)); db.commit()

def get_setting(db:Session,key:str,default:str="")->str:
    row=db.query(models.Setting).filter(models.Setting.key==key).first(); return row.value if row else default

def set_setting(db:Session,key:str,value:str,description:str=""):
    row=db.query(models.Setting).filter(models.Setting.key==key).first()
    if row: row.value=value
    else: db.add(models.Setting(key=key,value=value,description=description))
