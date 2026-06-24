"""
coach_brain.py — L'agente AI che analizza i dati biometrici.

Ogni mattina legge i dati da Firestore, costruisce il prompt
con i dati reali, chiama Gemini e salva il briefing.
"""

import logging
from datetime import datetime, timedelta

import google.generativeai as genai
from firebase_admin import firestore

from prompts import get_system_prompt, build_daily_trigger, format_data_table
from compute_load import compute_weekly_load

logger = logging.getLogger(__name__)


def assess_readiness(db, user_id: str, gemini_api_key: str, target_date: str = None) -> dict:
    """
    Valuta la readiness dell'atleta analizzando i dati biometrici.

    1. Legge ultimi 14 giorni di dati da Firestore
    2. Costruisce il prompt con dati reali
    3. Chiama Gemini API
    4. Parsa e salva il briefing

    Args:
        db: Firestore client
        user_id: ID atleta
        gemini_api_key: API key per Gemini

    Returns:
        Dict con il briefing completo
    """
    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")
    
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    start_date = (target_dt - timedelta(days=14)).strftime("%Y-%m-%d")

    logger.info(f"🤖 Avvio analisi readiness per {target_date}...")

    # ── 1. Carica profilo atleta ──────────────────────────────
    profile_doc = db.collection("athletes").document(user_id).get()
    profile = profile_doc.to_dict() if profile_doc.exists else {}

    if not profile:
        logger.warning("⚠️ Profilo atleta non trovato, uso valori di default")
        profile = {
            "name": "Atleta",
            "z2_ceiling": 150,
            "lthr": 170,
            "max_hr": 190,
            "easy_pace": "6:30",
            "threshold_pace": "4:45",
        }

    # ── 2. Carica dati biometrici (ultimi 14 giorni) ──────────
    sleep_docs = _fetch_collection(db, user_id, "sleep", start_date, target_date)
    hrv_docs = _fetch_collection(db, user_id, "hrv", start_date, target_date)
    battery_docs = _fetch_collection(db, user_id, "body_battery", start_date, target_date)
    rhr_docs = _fetch_collection(db, user_id, "resting_hr", start_date, target_date)
    stress_docs = _fetch_collection(db, user_id, "stress", start_date, target_date)
    runs_docs = _fetch_collection(db, user_id, "runs", start_date, target_date)

    logger.info(
        f"📦 Dati caricati: {len(sleep_docs)} sleep, {len(hrv_docs)} HRV, "
        f"{len(battery_docs)} battery, {len(rhr_docs)} RHR, "
        f"{len(stress_docs)} stress, {len(runs_docs)} runs"
    )

    # ── 3. Carica dati di carico per la data specifica ────────
    load_doc = compute_weekly_load(db, user_id, target_date)
    load_data = load_doc if load_doc else {}

    # ── 4. Formatta tabelle per il prompt ─────────────────────
    sleep_table = format_data_table(sleep_docs, [
        ("date", "Data", 12),
        ("duration_h", "Ore", 6),
        ("score", "Score", 6),
        ("deep_min", "Deep", 6),
        ("rem_min", "REM", 6),
    ])

    hrv_table = format_data_table(hrv_docs, [
        ("date", "Data", 12),
        ("rmssd", "RMSSD", 8),
        ("weekly_avg", "Media7gg", 8),
        ("status", "Status", 12),
    ])

    battery_table = format_data_table(battery_docs, [
        ("date", "Data", 12),
        ("morning_value", "Mattina", 8),
        ("low", "Min", 6),
        ("high", "Max", 6),
    ])

    rhr_table = format_data_table(rhr_docs, [
        ("date", "Data", 12),
        ("value", "BPM", 6),
        ("baseline", "Baseline", 8),
    ])

    stress_table = format_data_table(stress_docs, [
        ("date", "Data", 12),
        ("avg_stress", "Media", 8),
        ("max_stress", "Max", 6),
    ])

    activities_table = format_data_table(runs_docs, [
        ("date", "Data", 12),
        ("name", "Nome", 20),
        ("distance_km", "Km", 6),
        ("avg_pace", "Pace", 8),
        ("avg_hr", "HR", 6),
    ])

    # ── 5. Costruisci prompt ──────────────────────────────────
    system_prompt = get_system_prompt(profile)

    trigger_data = {
        "date": target_date,
        "sleep_table": sleep_table,
        "hrv_table": hrv_table,
        "battery_table": battery_table,
        "rhr_table": rhr_table,
        "stress_table": stress_table,
        "activities_table": activities_table,
        "acute_km": load_data.get("acute_km", "N/A"),
        "chronic_km": load_data.get("chronic_km_weekly", "N/A"),
        "acwr": load_data.get("acwr", "N/A"),
        "ramp_rate": load_data.get("ramp_rate_pct", "N/A"),
        "easy_pct": load_data.get("easy_pct", "N/A"),
        "hard_pct": load_data.get("hard_pct", "N/A"),
    }

    daily_trigger = build_daily_trigger(trigger_data)

    # ── 6. Chiama Gemini API ──────────────────────────────────
    logger.info("🤖 Invio prompt a Gemini...")
    genai.configure(api_key=gemini_api_key)

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_prompt,
    )

    response = model.generate_content(daily_trigger)
    ai_response = response.text
    logger.info(f"🤖 Risposta ricevuta ({len(ai_response)} caratteri)")

    # ── 7. Estrai readiness dalla risposta ────────────────────
    readiness = _extract_readiness(ai_response)

    # ── 8. Salva briefing su Firestore ────────────────────────
    briefing = {
        "date": target_date,
        "readiness": readiness,
        "analysis": ai_response,
        "data_summary": {
            "sleep_days": len(sleep_docs),
            "hrv_days": len(hrv_docs),
            "runs": len(runs_docs),
            "acute_km": load_data.get("acute_km"),
            "acwr": load_data.get("acwr"),
        },
        "created_at": firestore.SERVER_TIMESTAMP,
    }

    ref = db.collection(f"athletes/{user_id}/briefings").document(target_date)
    ref.set(briefing)

    logger.info(f"✅ Briefing salvato: {readiness} per {target_date}")
    return briefing


def _fetch_collection(db, user_id: str, collection: str,
                      start_date: str, end_date: str) -> list[dict]:
    """Fetch documenti da una subcollection filtrando per data."""
    try:
        query = (
            db.collection(f"athletes/{user_id}/{collection}")
            .where("date", ">=", start_date)
            .where("date", "<=", end_date)
            .order_by("date")
        )
        return [doc.to_dict() for doc in query.stream()]
    except Exception as e:
        logger.error(f"❌ Errore fetch {collection}: {e}")
        return []


def _extract_readiness(response_text: str) -> str:
    """Estrai il livello di readiness dal testo della risposta AI."""
    text_upper = response_text.upper()

    # Cerca pattern espliciti
    if "READINESS: RED" in text_upper or "READINESS:** RED" in text_upper:
        return "RED"
    if "READINESS: AMBER" in text_upper or "READINESS:** AMBER" in text_upper:
        return "AMBER"
    if "READINESS: GREEN" in text_upper or "READINESS:** GREEN" in text_upper:
        return "GREEN"

    # Fallback: cerca la parola chiave
    if "RED" in text_upper.split("READINESS")[0:2] if "READINESS" in text_upper else []:
        return "RED"

    # Default basato su keyword count
    red_signals = text_upper.count("RED") + text_upper.count("🔴")
    amber_signals = text_upper.count("AMBER") + text_upper.count("🟡")
    green_signals = text_upper.count("GREEN") + text_upper.count("🟢")

    if red_signals > amber_signals and red_signals > green_signals:
        return "RED"
    if amber_signals > green_signals:
        return "AMBER"
    return "GREEN"
