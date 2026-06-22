"""
main.py — Entry point per le Cloud Functions Firebase.

Contiene:
- nightly_sync: sincronizza dati Garmin ogni notte alle 03:00
- morning_coach: analisi AI readiness ogni mattina alle 06:30
- manual_sync: endpoint HTTP per sync manuale (test/debug)
- manual_coach: endpoint HTTP per coach manuale (test/debug)
"""

import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from firebase_admin import firestore, initialize_app
from firebase_functions import https_fn, options, scheduler_fn
from firebase_functions.params import SecretParam

from coach_brain import assess_readiness
from compute_load import compute_weekly_load
from garmin_sync import GarminSync

# ── Inizializzazione ─────────────────────────────────────────────
# Inizializza Firebase Admin SDK
try:
    initialize_app()
except ValueError:
    pass # App already initialized

def get_db():
    try:
        return firestore.client()
    except Exception as e:
        print(f"Warning: could not initialize firestore client: {e}")
        return None

# Timezone Italia
TZ = ZoneInfo("Europe/Rome")

# Secrets (caricati da Firebase Secret Manager)
GARMIN_EMAIL = SecretParam("GARMIN_EMAIL")
GARMIN_PASSWORD = SecretParam("GARMIN_PASSWORD")
GEMINI_API_KEY = SecretParam("GEMINI_API_KEY")

# User ID costante (progetto single-user)
USER_ID = "athlete_main"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Cloud Function: Nightly Sync ─────────────────────────────────
@scheduler_fn.on_schedule(
    schedule="0 3 * * *",
    timezone=scheduler_fn.Timezone("Europe/Rome"),
    secrets=[GARMIN_EMAIL, GARMIN_PASSWORD],
    memory=options.MemoryOption.MB_512,
    timeout_sec=300,
    region="europe-west1",
)
def nightly_sync(event: scheduler_fn.ScheduledEvent) -> None:
    """
    🌙 Sync notturno: ogni notte alle 03:00 estrae gli ultimi 3 giorni
    di dati da Garmin Connect e li salva su Firestore.
    """
    logger.info("🌙 ═══ NIGHTLY SYNC START ═══")
    db = get_db()

    try:
        # Login Garmin
        garmin = GarminSync(
            email=GARMIN_EMAIL.value,
            password=GARMIN_PASSWORD.value,
            db=db,
            user_id=USER_ID,
        )
        garmin.login()

        # Sync ultimi 3 giorni (per coprire eventuali mancati)
        today = datetime.now(tz=TZ).date()
        for i in range(3):
            day = today - timedelta(days=i)
            day_str = day.isoformat()
            logger.info(f"📅 Sync {day_str}...")
            results = garmin.sync_day(day_str)
            logger.info(f"  Risultati: {results}")

        # Ricalcola carico settimanale
        logger.info("⚡ Ricalcolo carico settimanale...")
        compute_weekly_load(db, USER_ID, today.isoformat())

        # Auto-detect zone HR se profilo non configurato
        _auto_setup_profile(garmin)

        # Log di esecuzione
        db.collection("system").document("last_sync").set({
            "timestamp": firestore.SERVER_TIMESTAMP,
            "status": "success",
            "days_synced": 3,
        })

        logger.info("🌙 ═══ NIGHTLY SYNC COMPLETE ═══")

    except Exception as e:
        logger.error(f"❌ Nightly sync fallito: {e}")
        db.collection("system").document("last_sync").set({
            "timestamp": firestore.SERVER_TIMESTAMP,
            "status": "error",
            "error": str(e),
        })
        raise


# ── Cloud Function: Morning Coach ────────────────────────────────
@scheduler_fn.on_schedule(
    schedule="30 6 * * *",
    timezone=scheduler_fn.Timezone("Europe/Rome"),
    secrets=[GEMINI_API_KEY],
    memory=options.MemoryOption.MB_512,
    timeout_sec=120,
    region="europe-west1",
)
def morning_coach(event: scheduler_fn.ScheduledEvent) -> None:
    """
    ☀️ Coach mattutino: ogni mattina alle 06:30 analizza i dati
    biometrici e genera il briefing di readiness.
    """
    logger.info("☀️ ═══ MORNING COACH START ═══")
    db = get_db()

    try:
        briefing = assess_readiness(
            db=db,
            user_id=USER_ID,
            gemini_api_key=GEMINI_API_KEY.value,
        )

        readiness = briefing.get("readiness", "UNKNOWN")
        emoji = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}.get(readiness, "⚪")
        logger.info(f"{emoji} Readiness: {readiness}")
        logger.info("☀️ ═══ MORNING COACH COMPLETE ═══")

    except Exception as e:
        logger.error(f"❌ Morning coach fallito: {e}")
        # Salva errore come briefing
        today = datetime.now(tz=TZ).strftime("%Y-%m-%d")
        db.collection(f"athletes/{USER_ID}/briefings").document(today).set({
            "date": today,
            "readiness": "UNKNOWN",
            "analysis": f"❌ Errore nella generazione del briefing: {str(e)}",
            "created_at": firestore.SERVER_TIMESTAMP,
        })
        raise


# ── HTTP Endpoint: Manual Sync (per test) ────────────────────────
@https_fn.on_request(
    secrets=[GARMIN_EMAIL, GARMIN_PASSWORD],
    memory=options.MemoryOption.MB_512,
    timeout_sec=300,
    region="europe-west1",
    cors=options.CorsOptions(cors_origins="*", cors_methods=["GET", "POST"]),
)
def manual_sync(req: https_fn.Request) -> https_fn.Response:
    """
    🔧 Endpoint HTTP per sync manuale.
    Uso: GET /manual_sync?days=3
    """
    days = int(req.args.get("days", "3"))
    logger.info(f"🔧 Manual sync per {days} giorni")
    db = get_db()

    try:
        garmin = GarminSync(
            email=GARMIN_EMAIL.value,
            password=GARMIN_PASSWORD.value,
            db=db,
            user_id=USER_ID,
        )
        garmin.login()

        today = datetime.now(tz=TZ).date()
        all_results = {}
        for i in range(days):
            day = today - timedelta(days=i)
            day_str = day.isoformat()
            results = garmin.sync_day(day_str)
            all_results[day_str] = results

        compute_weekly_load(db, USER_ID, today.isoformat())
        _auto_setup_profile(garmin)

        return https_fn.Response(
            response=f"✅ Sync completato per {days} giorni:\n{all_results}",
            status=200,
        )
    except Exception as e:
        return https_fn.Response(
            response=f"❌ Errore: {str(e)}",
            status=500,
        )


# ── HTTP Endpoint: Manual Coach (per test) ───────────────────────
@https_fn.on_request(
    secrets=[GEMINI_API_KEY],
    memory=options.MemoryOption.MB_512,
    timeout_sec=120,
    region="europe-west1",
    cors=options.CorsOptions(cors_origins="*", cors_methods=["GET", "POST"]),
)
def manual_coach(req: https_fn.Request) -> https_fn.Response:
    """
    🔧 Endpoint HTTP per analisi coach manuale.
    Uso: GET /manual_coach
    """
    logger.info("🔧 Manual coach analysis")
    db = get_db()

    try:
        briefing = assess_readiness(
            db=db,
            user_id=USER_ID,
            gemini_api_key=GEMINI_API_KEY.value,
        )

        readiness = briefing.get("readiness", "UNKNOWN")
        analysis = briefing.get("analysis", "Nessuna analisi")

        return https_fn.Response(
            response=f"Readiness: {readiness}\n\n{analysis}",
            status=200,
        )
    except Exception as e:
        return https_fn.Response(
            response=f"❌ Errore: {str(e)}",
            status=500,
        )


# ── Helper: Auto-setup profilo ───────────────────────────────────
def _auto_setup_profile(garmin: GarminSync):
    """Se il profilo atleta non esiste, lo crea automaticamente dai dati Garmin."""
    db = get_db()
    if not db:
        print("Firestore not available")
        return
    
    profile_ref = db.collection("athletes").document(USER_ID)
    profile_doc = profile_ref.get()

    if profile_doc.exists and profile_doc.to_dict().get("z2_ceiling"):
        return  # Profilo già configurato

    logger.info("🔧 Auto-setup profilo atleta dai dati Garmin...")

    zones = garmin.detect_hr_zones()
    if zones:
        profile_data = {
            "name": "Davide",
            "z2_ceiling": zones.get("z2_ceiling", 150),
            "lthr": zones.get("lthr", 170),
            "max_hr": zones.get("max_hr", 190),
            "easy_pace": "6:30",
            "threshold_pace": "4:45",
            "auto_detected": True,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        profile_ref.set(profile_data, merge=True)
        logger.info(f"✅ Profilo creato: Z2={zones.get('z2_ceiling')}, "
                     f"LTHR={zones.get('lthr')}, Max={zones.get('max_hr')}")
    else:
        logger.warning("⚠️ Impossibile rilevare zone HR, usa setup manuale")
