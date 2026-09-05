"""Production ingestion: fetch -> rank candidates -> cluster -> generate -> originality -> verify -> publish."""
import datetime
import json
import logging
import time
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from .. import models
from ..config import settings
from ..database import SessionLocal
from ..seed import get_setting,set_setting
from ..services.job_status import start_job,complete_job,fail_job,cancel_job,get_job
from ..services.editorial_compliance import mandatory_human_review
from ..services.quality_benchmark import get_benchmark, story_has_safety_block
from .rss_fetcher import fetch_all_active_sources
from .candidate_ranker import select_candidates
from .clustering import cluster_articles
from .verification_layers import run_verification_pipeline
from .verification import compute_max_similarity
from ..llm.groq_client import summarize_cluster
from ..llm.originality import rewrite_for_originality

logger=logging.getLogger("morning_brief.pipeline")
STALE_INGESTION_SECONDS=45*60
MAX_ORIGINALITY_REWRITES=2
DB_WRITE_RETRIES=3
SETTING_READ_RETRIES=3

class IngestionCancelled(Exception):
    """Raised when an administrator requests a running ingestion to stop."""

def _edition_date(db):
    try:tz=ZoneInfo(get_setting(db,"admin_timezone","Asia/Kolkata"))
    except Exception:tz=ZoneInfo("Asia/Kolkata")
    return datetime.datetime.now(tz).date().isoformat()

def _persist_story_with_retry(story_data,articles):
    last_error=None
    for attempt in range(1,DB_WRITE_RETRIES+1):
        write_db=SessionLocal()
        try:
            story=models.Story(**story_data);write_db.add(story);write_db.flush();seen=set()
            for article in articles:
                if article.link in seen:continue
                seen.add(article.link);write_db.add(models.Citation(story_id=story.id,source_name=article.source_name,title=article.title,url=article.link))
            write_db.commit();return story.id
        except OperationalError as exc:
            last_error=exc;write_db.rollback();logger.warning("Transient database error saving story (attempt %s/%s): %s",attempt,DB_WRITE_RETRIES,exc)
            if attempt<DB_WRITE_RETRIES:time.sleep(min(2**(attempt-1),4))
        finally:write_db.close()
    raise last_error

def _cancel_requested():
    """Read the stop flag with a fresh connection and retry transient SSL failures."""
    last_error=None
    for attempt in range(1,SETTING_READ_RETRIES+1):
        db=SessionLocal()
        try:
            return get_setting(db,"ingestion_cancel_requested","false").lower()=="true"
        except OperationalError as exc:
            last_error=exc
            logger.warning("Transient database error reading ingestion stop flag (attempt %s/%s): %s",attempt,SETTING_READ_RETRIES,exc)
            try: db.rollback()
            except Exception: pass
            if attempt<SETTING_READ_RETRIES: time.sleep(min(2**(attempt-1),3))
        except Exception:
            return False
        finally: db.close()
    logger.error("Could not read ingestion stop flag after retries: %s",last_error)
    return False

def _heartbeat(stage,cluster_index=0,total_clusters=0):
    db=SessionLocal()
    try:
        set_setting(db,"ingestion_heartbeat_at",datetime.datetime.utcnow().isoformat());set_setting(db,"ingestion_current_stage",stage);set_setting(db,"ingestion_current_cluster",str(cluster_index));set_setting(db,"ingestion_total_clusters",str(total_clusters));db.commit()
    except Exception:db.rollback()
    finally:db.close()

def _check_cancel(stage,cluster_index=0,total_clusters=0):
    _heartbeat(stage,cluster_index,total_clusters)
    if _cancel_requested():raise IngestionCancelled(f"Ingestion stopped by administrator during {stage}")

def run_ingestion(db:Session,test_mode=False,max_clusters=None,freshness_after=None):
    today=_edition_date(db)
    benchmark=get_benchmark(db)
    similarity_threshold=float(get_setting(db,"cluster_similarity_threshold","0.35"))
    max_sentences=int(get_setting(db,"summary_max_sentences","3"))
    auto_approval_threshold=float(benchmark["max_similarity"])
    benchmark_min_confidence=float(benchmark["min_confidence"])
    skip_verification=get_setting(db,"skip_all_verification","false").lower()=="true"
    bilingual=get_setting(db,"bilingual_generation","true").lower()=="true"
    blocked={d.strip().lower() for d in get_setting(db,"blocked_source_domains","").split(",") if d.strip()}
    thresholds={"near_verbatim_similarity_threshold":float(get_setting(db,"near_verbatim_similarity_threshold","0.55")),"long_phrase_overlap_threshold":float(get_setting(db,"long_phrase_overlap_threshold","0.20")),"long_phrase_words":int(get_setting(db,"long_phrase_words","6")),"min_confidence_score":benchmark_min_confidence}
    categories=[c.slug for c in db.query(models.Category).filter(models.Category.is_active.is_(True)).all()] or ["general"]
    layers=db.query(models.VerificationLayer).filter(models.VerificationLayer.is_enabled.is_(True)).order_by(models.VerificationLayer.sort_order).all()
    stage="rss_fetch";_check_cancel(stage,0,0)
    try:articles,fetch_diagnostics=fetch_all_active_sources(db,blocked_domains=blocked,published_after=freshness_after);db.commit()
    except IngestionCancelled:raise
    except Exception as exc:db.rollback();logger.exception("Fetch stage failed: %s",exc);return {"status":"error","stage":stage,"detail":str(exc),"stories_created":0}
    _check_cancel("rss_fetch_complete",0,0)
    if not articles:return {"status":"ok","stage":"rss_fetch","detail":"No new articles fetched after the configured freshness cutoff (or check source feeds)","stories_created":0,"fetch_diagnostics":fetch_diagnostics,"freshness_after":freshness_after.isoformat() if freshness_after else None}
    raw_article_count=len(articles)
    try:
        per_source=max(1,min(int(get_setting(db,"candidate_articles_per_source","6")),20));pool_size=max(per_source,min(int(get_setting(db,"candidate_pool_size","60")),300));articles=select_candidates(articles,per_source=per_source,pool_size=pool_size)
        fetch_diagnostics.update({"raw_articles":raw_article_count,"candidate_articles":len(articles),"candidate_articles_per_source":per_source,"candidate_pool_size":pool_size})
        logger.info("Candidate pre-ranking retained %s/%s RSS articles for expensive processing",len(articles),raw_article_count)
    except Exception as exc:
        logger.exception("Candidate ranking failed; falling back to fetched articles: %s",exc)
        fetch_diagnostics.update({"raw_articles":raw_article_count,"candidate_articles":raw_article_count,"candidate_ranking_error":str(exc)[:500]})
    _check_cancel("candidate_ranking_complete",0,0)
    stage="clustering"
    try:clusters=cluster_articles(articles,similarity_threshold=similarity_threshold)
    except Exception as exc:logger.exception("Clustering stage failed: %s",exc);return {"status":"error","stage":stage,"detail":str(exc),"stories_created":0,"fetch_diagnostics":fetch_diagnostics}
    cluster_limit=(max_clusters or 3) if test_mode else (max_clusters or int(get_setting(db,"max_clusters_per_run","100")));clusters=clusters[:cluster_limit];total_clusters=len(clusters);_check_cancel("clustering_complete",0,total_clusters)
    if not test_mode:
        try:db.query(models.Story).filter(models.Story.edition_date==today,models.Story.is_pinned.is_(False),models.Story.publication_status!="approved",models.Story.is_test_content.is_(False)).delete(synchronize_session=False);db.commit()
        except Exception:db.rollback();raise
    created=0;pause=max(0,float(get_setting(db,"llm_pause_seconds","1")));cluster_errors=[]
    for i,cluster in enumerate(clusters):
        cluster_no=i+1;_check_cancel(f"starting_cluster_{cluster_no}",cluster_no,total_clusters);snippets=[{"title":a.title,"summary":a.summary,"source":a.source_name} for a in cluster.articles];stage=f"generation_cluster_{cluster_no}"
        try:draft=summarize_cluster(snippets,categories,max_sentences=max_sentences,bilingual=bilingual)
        except IngestionCancelled:raise
        except Exception as exc:logger.exception("Generation failed for cluster %s",cluster_no);return {"status":"error","stage":stage,"detail":str(exc),"stories_created":created,"fetch_diagnostics":fetch_diagnostics,"cluster_errors":cluster_errors}
        _check_cancel(f"generation_complete_cluster_{cluster_no}",cluster_no,total_clusters);originals=[f"{a.title} {a.summary}" for a in cluster.articles];rewrite_count=0
        if not skip_verification:
            try:
                for rewrite_no in range(MAX_ORIGINALITY_REWRITES):
                    _check_cancel(f"originality_cluster_{cluster_no}_pass_{rewrite_no+1}",cluster_no,total_clusters);current_similarity=compute_max_similarity(draft["summary"],originals)
                    if current_similarity<auto_approval_threshold:break
                    revised=rewrite_for_originality(draft["summary"],originals,max_sentences)
                    if not revised or revised.strip()==draft["summary"].strip():break
                    revised_similarity=compute_max_similarity(revised,originals)
                    if revised_similarity >= current_similarity:break
                    draft["summary"]=revised;rewrite_count+=1
            except IngestionCancelled:raise
            except Exception as exc:logger.warning("Originality rewrite check failed: %s",exc);cluster_errors.append({"cluster":cluster_no,"stage":"originality","error":str(exc)[:500]})
        stage=f"verification_cluster_{cluster_no}"
        try:
            _check_cancel(f"before_verification_cluster_{cluster_no}",cluster_no,total_clusters)
            if skip_verification:flags=[];max_similarity=0.0;long_phrase=0.0;report=None;verification_blocked=False
            else:
                context={"cluster_articles":cluster.articles,"draft":draft,"original_snippets":originals,"thresholds":thresholds,"blocked_domains":blocked};result=run_verification_pipeline(layers,context);flags=result["all_flags"];max_similarity=context.get("max_similarity",0.0);long_phrase=context.get("max_long_phrase_overlap",0.0);report=context.get("verifier_report");blocking_layer_keys={layer.key for layer in layers if layer.is_blocking};failed_blocking_layers=[key for key,row in result["layer_results"].items() if key in blocking_layer_keys and (not row.get("passed",False) or not row.get("available",False))];flags.extend([f"blocking_layer:{key}" for key in failed_blocking_layers]);verification_blocked=bool(failed_blocking_layers)
            compliance_required,compliance_flags=mandatory_human_review(draft.get("headline","")+" "+draft.get("hook","")+" "+draft.get("summary",""),len(cluster.articles),report,max_similarity,auto_approval_threshold);flags=list(dict.fromkeys(flags+compliance_flags));benchmark_pass=(float(draft.get("confidence",0.0))>=benchmark_min_confidence and max_similarity<=auto_approval_threshold);auto_approved=(not test_mode and benchmark_pass and not verification_blocked and not compliance_required and not story_has_safety_block(type("StoryProxy",(),{"verification_flags":json.dumps(flags),"contradiction_flag":bool(report and report.get("contradiction_found"))})()));status="approved" if auto_approved else "pending";published=status=="approved"
        except IngestionCancelled:raise
        except Exception as exc:logger.exception("Verification stage failed for cluster %s",cluster_no);return {"status":"error","stage":stage,"detail":str(exc),"stories_created":created,"fetch_diagnostics":fetch_diagnostics,"cluster_errors":cluster_errors}
        _check_cancel(f"verification_complete_cluster_{cluster_no}",cluster_no,total_clusters);countries={getattr(a,"country_code","GLOBAL") for a in cluster.articles};country=next(iter(countries)) if len(countries)==1 else "GLOBAL";story_data={"edition_date":today,"headline":draft["headline"],"hook":draft["hook"],"summary":draft["summary"],"headline_hi":draft.get("headline_hi"),"hook_hi":draft.get("hook_hi"),"summary_hi":draft.get("summary_hi"),"category_slug":draft["category_slug"],"country_code":country,"confidence_score":draft["confidence"],"needs_review":status=="pending","is_published":published,"is_test_content":test_mode,"publication_status":status,"pipeline_stage":"pending_human_review" if status=="pending" else "published","verification_flags":json.dumps(flags) if flags else None,"max_source_similarity":max_similarity,"max_long_phrase_overlap":long_phrase,"originality_rewrite_applied":rewrite_count>0,"generator_model":f"groq:{settings.GROQ_MODEL}","verifier_model":f"gemini:{settings.GEMINI_MODEL}" if report else None,"verifier_report":json.dumps(report) if report else None,"contradiction_flag":bool(report and report.get("contradiction_found")),"citation_complete":bool(cluster.articles)}
        try:_persist_story_with_retry(story_data,cluster.articles)
        except Exception as exc:logger.exception("Story persistence failed for cluster %s",cluster_no);return {"status":"error","stage":"database_persist","detail":str(exc)[:1000],"stories_created":created,"fetch_diagnostics":fetch_diagnostics,"cluster_errors":cluster_errors}
        created+=1;_check_cancel(f"completed_cluster_{cluster_no}",cluster_no,total_clusters)
        if not test_mode and i<len(clusters)-1:time.sleep(pause)
    return {"status":"ok","stage":"completed","detail":f"Ranked {raw_article_count} fetched articles down to {len(articles)} candidates, then processed {len(clusters)} clusters; publication benchmark is confidence >= {benchmark_min_confidence:.0%} and similarity <= {auto_approval_threshold:.0%}","stories_created":created,"freshness_after":freshness_after.isoformat() if freshness_after else None,"fetch_diagnostics":fetch_diagnostics,"cluster_errors":cluster_errors}

def _stale_running(db):
    if get_setting(db,"ingestion_status","idle")!="running":return False
    raw=get_setting(db,"ingestion_heartbeat_at","") or get_setting(db,"ingestion_started_at","")
    try:
        started=datetime.datetime.fromisoformat(raw.replace("Z","+00:00"));started=started.replace(tzinfo=datetime.timezone.utc) if started.tzinfo is None else started;return (datetime.datetime.now(datetime.timezone.utc)-started).total_seconds()>STALE_INGESTION_SECONDS
    except Exception:return True

def run_ingestion_background(mode="manual",freshness_after=None):
    db=SessionLocal()
    try:
        if get_setting(db,"ingestion_status","idle")=="running":
            if not _stale_running(db):return {"status":"in_progress","detail":"Ingestion is already running","stage":"lock"}
            logger.warning("Recovering stale ingestion lock");set_setting(db,"ingestion_status","recovering","Recovered stale ingestion lock");db.commit()
        set_setting(db,"ingestion_cancel_requested","false");set_setting(db,"ingestion_current_stage","starting");set_setting(db,"ingestion_current_cluster","0");set_setting(db,"ingestion_total_clusters","0");set_setting(db,"ingestion_heartbeat_at",datetime.datetime.utcnow().isoformat());start_job(db,"ingestion",mode=mode);set_setting(db,"ingestion_status","running","Current background ingestion status");set_setting(db,"ingestion_started_at",datetime.datetime.utcnow().isoformat());set_setting(db,"ingestion_completed_at","");db.commit();result=run_ingestion(db,freshness_after=freshness_after)
        if result.get("status") in {"ok","completed"}:
            set_setting(db,"ingestion_status","ready");set_setting(db,"ingestion_last_result",json.dumps(result));set_setting(db,"ingestion_completed_at",datetime.datetime.utcnow().isoformat());set_setting(db,"last_successful_ingestion_at",datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat());set_setting(db,"ingestion_cancel_requested","false");db.commit();complete_job(db,"ingestion",result)
        else:
            error=result.get("detail") or f"Ingestion failed at stage: {result.get('stage','unknown')}";set_setting(db,"ingestion_status","error");set_setting(db,"ingestion_last_result",json.dumps(result));set_setting(db,"ingestion_completed_at",datetime.datetime.utcnow().isoformat());set_setting(db,"ingestion_cancel_requested","false");db.commit();fail_job(db,"ingestion",error,result)
        return result
    except IngestionCancelled as exc:
        logger.info("Ingestion cancelled: %s",exc);db.rollback();result={"status":"cancelled","stage":"cancelled","detail":str(exc)}
        try:set_setting(db,"ingestion_status","cancelled");set_setting(db,"ingestion_last_result",json.dumps(result));set_setting(db,"ingestion_completed_at",datetime.datetime.utcnow().isoformat());set_setting(db,"ingestion_cancel_requested","false");db.commit();cancel_job(db,"ingestion",result)
        except Exception:logger.exception("Unable to persist ingestion cancellation")
        return result
    except Exception as exc:
        logger.exception("Background ingestion crashed: %s",exc);db.rollback();error=str(exc)[:1000];result={"status":"failed","stage":"background_worker","detail":error}
        try:set_setting(db,"ingestion_status","error");set_setting(db,"ingestion_last_result",json.dumps(result));set_setting(db,"ingestion_completed_at",datetime.datetime.utcnow().isoformat());set_setting(db,"ingestion_cancel_requested","false");db.commit();fail_job(db,"ingestion",error,result)
        except Exception:logger.exception("Unable to persist ingestion failure")
        return result
    finally:db.close()
