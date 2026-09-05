"""Full production ingestion: fetch -> cluster -> Groq draft -> originality -> verification -> publication gate."""
import datetime,json,logging,time
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from .. import models
from ..config import settings
from ..database import SessionLocal
from ..seed import get_setting,set_setting
from ..services.job_status import start_job, complete_job, fail_job, get_job
from ..services.editorial_compliance import mandatory_human_review
from .rss_fetcher import fetch_all_active_sources
from .clustering import cluster_articles
from .verification_layers import run_verification_pipeline
from .verification import compute_max_similarity
from ..llm.groq_client import summarize_cluster
from ..llm.originality import rewrite_for_originality
logger=logging.getLogger("morning_brief.pipeline")
STALE_INGESTION_SECONDS=45*60
ORIGINALITY_TARGET=0.20
MAX_ORIGINALITY_REWRITES=3


def _edition_date(db):
    try:tz=ZoneInfo(get_setting(db,"admin_timezone","Asia/Kolkata"))
    except Exception:tz=ZoneInfo("Asia/Kolkata")
    return datetime.datetime.now(tz).date().isoformat()


def run_ingestion(db:Session,test_mode=False,max_clusters=None,freshness_after=None):
    today=_edition_date(db); similarity_threshold=float(get_setting(db,"cluster_similarity_threshold","0.35")); max_sentences=int(get_setting(db,"summary_max_sentences","3")); configured_auto_threshold=float(get_setting(db,"auto_approval_similarity_threshold","0.20")); auto_approval_threshold=min(configured_auto_threshold,ORIGINALITY_TARGET); skip_verification=get_setting(db,"skip_all_verification","false").lower()=="true"; bilingual=get_setting(db,"bilingual_generation","true").lower()=="true"; blocked={d.strip().lower() for d in get_setting(db,"blocked_source_domains","").split(",") if d.strip()}; thresholds={"near_verbatim_similarity_threshold":float(get_setting(db,"near_verbatim_similarity_threshold","0.55")),"long_phrase_overlap_threshold":float(get_setting(db,"long_phrase_overlap_threshold","0.20")),"long_phrase_words":int(get_setting(db,"long_phrase_words","6")),"min_confidence_score":float(get_setting(db,"min_confidence_score","0.55"))}; categories=[c.slug for c in db.query(models.Category).filter(models.Category.is_active.is_(True)).all()] or ["general"]; layers=db.query(models.VerificationLayer).filter(models.VerificationLayer.is_enabled.is_(True)).order_by(models.VerificationLayer.sort_order).all()
    stage="rss_fetch"
    try:articles,fetch_diagnostics=fetch_all_active_sources(db,blocked_domains=blocked,published_after=freshness_after)
    except Exception as exc:logger.exception("Fetch stage failed: %s",exc);return {"status":"error","stage":stage,"detail":str(exc),"stories_created":0}
    if not articles:return {"status":"ok","stage":"rss_fetch","detail":"No new articles fetched after the configured freshness cutoff (or check source feeds)","stories_created":0,"fetch_diagnostics":fetch_diagnostics,"freshness_after":freshness_after.isoformat() if freshness_after else None}
    stage="clustering"
    try:clusters=cluster_articles(articles,similarity_threshold=similarity_threshold)
    except Exception as exc:logger.exception("Clustering stage failed: %s",exc);return {"status":"error","stage":stage,"detail":str(exc),"stories_created":0,"fetch_diagnostics":fetch_diagnostics}
    clusters=clusters[:((max_clusters or 3) if test_mode else (max_clusters or int(get_setting(db,"max_clusters_per_run","100"))))]
    if not test_mode:db.query(models.Story).filter(models.Story.edition_date==today,models.Story.is_pinned.is_(False),models.Story.publication_status!="approved",models.Story.is_test_content.is_(False)).delete(synchronize_session=False);db.commit()
    created=0;pause=float(get_setting(db,"llm_pause_seconds","7"));cluster_errors=[]
    for i,cluster in enumerate(clusters):
        snippets=[{"title":a.title,"summary":a.summary,"source":a.source_name} for a in cluster.articles];stage=f"generation_cluster_{i+1}"
        try:draft=summarize_cluster(snippets,categories,max_sentences=max_sentences,bilingual=bilingual)
        except Exception as exc:logger.exception("Generation failed for cluster %s",i+1);return {"status":"error","stage":stage,"detail":str(exc),"stories_created":created,"fetch_diagnostics":fetch_diagnostics,"cluster_errors":cluster_errors}
        originals=[f"{a.title} {a.summary}" for a in cluster.articles]
        rewrite_count=0
        if not skip_verification:
            try:
                # 20% is the hard originality target for publication. If the
                # first draft is above it, rewrite and re-measure. A later
                # pass gets a stronger instruction through the same editor.
                for attempt in range(MAX_ORIGINALITY_REWRITES):
                    current_similarity=compute_max_similarity(draft["summary"],originals)
                    if current_similarity < ORIGINALITY_TARGET:
                        break
                    revised=rewrite_for_originality(draft["summary"],originals,max_sentences)
                    if not revised or revised.strip()==draft["summary"].strip():
                        break
                    draft["summary"]=revised
                    rewrite_count+=1
                    if compute_max_similarity(draft["summary"],originals) < ORIGINALITY_TARGET:
                        break
            except Exception as exc:
                logger.warning("Originality rewrite check failed: %s",exc);cluster_errors.append({"cluster":i+1,"stage":"originality","error":str(exc)[:500]})
        stage=f"verification_cluster_{i+1}"
        try:
            if skip_verification:flags=[];max_similarity=0.0;long_phrase=0.0;report=None;verification_blocked=False
            else:
                context={"cluster_articles":cluster.articles,"draft":draft,"original_snippets":originals,"thresholds":thresholds,"blocked_domains":blocked};result=run_verification_pipeline(layers,context);flags=result["all_flags"];max_similarity=context.get("max_similarity",0.0);long_phrase=context.get("max_long_phrase_overlap",0.0);report=context.get("verifier_report")
                blocking_layer_keys={layer.key for layer in layers if layer.is_blocking}
                failed_blocking_layers=[key for key,row in result["layer_results"].items() if key in blocking_layer_keys and (not row.get("passed",False) or not row.get("available",False))]
                if failed_blocking_layers:flags.extend([f"blocking_layer:{key}" for key in failed_blocking_layers])
                verification_blocked=bool(failed_blocking_layers)
            compliance_required,compliance_flags=mandatory_human_review(draft.get("headline","")+" "+draft.get("hook","")+" "+draft.get("summary",""),len(cluster.articles),report,max_similarity,auto_approval_threshold)
            flags=list(dict.fromkeys(flags+compliance_flags))
            auto_approved=(not test_mode and max_similarity < auto_approval_threshold and not verification_blocked and not compliance_required)
            status="approved" if auto_approved else "pending";published=status=="approved"
        except Exception as exc:logger.exception("Verification stage failed for cluster %s",i+1);return {"status":"error","stage":stage,"detail":str(exc),"stories_created":created,"fetch_diagnostics":fetch_diagnostics,"cluster_errors":cluster_errors}
        countries={getattr(a,"country_code","GLOBAL") for a in cluster.articles};country=next(iter(countries)) if len(countries)==1 else "GLOBAL";story=models.Story(edition_date=today,headline=draft["headline"],hook=draft["hook"],summary=draft["summary"],headline_hi=draft.get("headline_hi"),hook_hi=draft.get("hook_hi"),summary_hi=draft.get("summary_hi"),category_slug=draft["category_slug"],country_code=country,confidence_score=draft["confidence"],needs_review=status=="pending",is_published=published,is_test_content=test_mode,publication_status=status,pipeline_stage="pending_human_review" if status=="pending" else "published",verification_flags=json.dumps(flags) if flags else None,max_source_similarity=max_similarity,max_long_phrase_overlap=long_phrase,originality_rewrite_applied=rewrite_count>0,generator_model=f"groq:{settings.GROQ_MODEL}",verifier_model=f"gemini:{settings.GEMINI_MODEL}" if report else None,verifier_report=json.dumps(report) if report else None,contradiction_flag=bool(report and report.get("contradiction_found")),citation_complete=bool(cluster.articles));db.add(story);db.flush();seen=set()
        for a in cluster.articles:
            if a.link in seen:continue
            seen.add(a.link);db.add(models.Citation(story_id=story.id,source_name=a.source_name,title=a.title,url=a.link))
        created+=1
        if not test_mode and i<len(clusters)-1:time.sleep(max(0,pause))
    db.commit();return {"status":"ok","stage":"completed","detail":f"Processed {len(clusters)} clusters; publication requires verified similarity below {ORIGINALITY_TARGET:.0%}; drafts at/above target are rewritten up to {MAX_ORIGINALITY_REWRITES} times","stories_created":created,"freshness_after":freshness_after.isoformat() if freshness_after else None,"fetch_diagnostics":fetch_diagnostics,"cluster_errors":cluster_errors}


def _stale_running(db):
    if get_setting(db,"ingestion_status","idle")!="running": return False
    raw=get_setting(db,"ingestion_started_at","")
    try:
        started=datetime.datetime.fromisoformat(raw.replace("Z","+00:00"));
        if started.tzinfo is None: started=started.replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc)-started).total_seconds()>STALE_INGESTION_SECONDS
    except Exception:return True


def run_ingestion_background(mode="manual",freshness_after=None):
    db=SessionLocal()
    try:
        if get_setting(db,"ingestion_status","idle")=="running":
            if not _stale_running(db): return {"status":"in_progress","detail":"Ingestion is already running","stage":"lock"}
            logger.warning("Recovering stale ingestion lock")
            set_setting(db,"ingestion_status","recovering","Recovered stale ingestion lock");db.commit()
        start_job(db,"ingestion",mode=mode);set_setting(db,"ingestion_status","running","Current background ingestion status");set_setting(db,"ingestion_started_at",datetime.datetime.utcnow().isoformat());set_setting(db,"ingestion_completed_at","");db.commit();result=run_ingestion(db,freshness_after=freshness_after)
        if result.get("status") in {"ok","completed"}:
            set_setting(db,"ingestion_status","ready");set_setting(db,"ingestion_last_result",json.dumps(result));set_setting(db,"ingestion_completed_at",datetime.datetime.utcnow().isoformat());set_setting(db,"last_successful_ingestion_at",datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat());db.commit();complete_job(db,"ingestion",result)
        else:
            error=result.get("detail") or f"Ingestion failed at stage: {result.get('stage','unknown')}";set_setting(db,"ingestion_status","error");set_setting(db,"ingestion_last_result",json.dumps(result));set_setting(db,"ingestion_completed_at",datetime.datetime.utcnow().isoformat());db.commit();fail_job(db,"ingestion",error,result)
        return result
    except Exception as exc:
        logger.exception("Background ingestion crashed: %s",exc);error=str(exc)[:1000];result={"status":"failed","stage":"background_worker","detail":error};set_setting(db,"ingestion_status","error");set_setting(db,"ingestion_last_result",json.dumps(result));set_setting(db,"ingestion_completed_at",datetime.datetime.utcnow().isoformat());db.commit();fail_job(db,"ingestion",error,result);return result
    finally:db.close()
