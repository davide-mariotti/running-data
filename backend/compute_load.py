"""
compute_load.py — Calcolo del carico di allenamento.

Calcola carico acuto (7 giorni), cronico (28 giorni), ACWR
e ramp rate dalla collection runs su Firestore.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from firebase_admin import firestore

logger = logging.getLogger(__name__)


def compute_weekly_load(db, user_id: str, reference_date: str) -> dict[str, Any]:
    """
    Calcola e salva il carico settimanale.

    Args:
        db: Firestore client
        user_id: ID atleta
        reference_date: Data di riferimento (YYYY-MM-DD)

    Returns:
        Dict con le metriche di carico calcolate
    """
    ref_date = datetime.strptime(reference_date, "%Y-%m-%d").date()

    # Carica tutti i run degli ultimi 35 giorni
    start_date = (ref_date - timedelta(days=35)).isoformat()
    runs_ref = (
        db.collection(f"athletes/{user_id}/runs")
        .where("date", ">=", start_date)
        .where("date", "<=", reference_date)
        .order_by("date")
    )

    runs = [doc.to_dict() for doc in runs_ref.stream()]
    logger.info(f"📊 Trovati {len(runs)} run negli ultimi 35 giorni")

    # ── Calcola carico acuto (ultimi 7 giorni) ────────────────
    acute_start = (ref_date - timedelta(days=7)).isoformat()
    acute_runs = [r for r in runs if r.get("date", "") > acute_start]
    acute_km = sum(r.get("distance_km", 0) for r in acute_runs)
    acute_time = sum(r.get("duration_min", 0) for r in acute_runs)
    acute_count = len(acute_runs)

    # ── Calcola carico cronico (ultimi 28 giorni, media settimanale) ──
    chronic_start = (ref_date - timedelta(days=28)).isoformat()
    chronic_runs = [r for r in runs if r.get("date", "") > chronic_start]
    chronic_km_total = sum(r.get("distance_km", 0) for r in chronic_runs)
    chronic_km_weekly = round(chronic_km_total / 4, 2)  # media su 4 settimane

    # ── ACWR (Acute:Chronic Workload Ratio) ───────────────────
    acwr = round(acute_km / chronic_km_weekly, 2) if chronic_km_weekly > 0 else 0

    # ── Ramp rate (variazione % settimana precedente) ─────────
    prev_week_start = (ref_date - timedelta(days=14)).isoformat()
    prev_week_end = (ref_date - timedelta(days=7)).isoformat()
    prev_week_runs = [
        r for r in runs
        if r.get("date", "") > prev_week_start and r.get("date", "") <= prev_week_end
    ]
    prev_week_km = sum(r.get("distance_km", 0) for r in prev_week_runs)
    ramp_rate = 0
    if prev_week_km > 0:
        ramp_rate = round(((acute_km - prev_week_km) / prev_week_km) * 100, 1)

    # ── Distribuzione easy/hard (basata su HR se disponibile) ──
    # Utilizziamo il profilo atleta per le zone se disponibile
    profile_doc = db.collection("athletes").document(user_id).get()
    z2_ceiling = 150  # default
    if profile_doc.exists:
        profile = profile_doc.to_dict()
        z2_ceiling = profile.get("z2_ceiling", 150)

    easy_runs = [r for r in acute_runs if (r.get("avg_hr") or 999) <= z2_ceiling]
    hard_runs = [r for r in acute_runs if (r.get("avg_hr") or 0) > z2_ceiling]
    easy_time = sum(r.get("duration_min", 0) for r in easy_runs)
    hard_time = sum(r.get("duration_min", 0) for r in hard_runs)
    total_time = easy_time + hard_time
    easy_pct = round((easy_time / total_time) * 100, 1) if total_time > 0 else 0
    hard_pct = round((hard_time / total_time) * 100, 1) if total_time > 0 else 0

    # ── Calcola settimana ISO ─────────────────────────────────
    iso_year, iso_week, _ = ref_date.isocalendar()
    week_key = f"{iso_year}-W{iso_week:02d}"

    # ── Salva su Firestore ────────────────────────────────────
    load_doc = {
        "week_key": week_key,
        "reference_date": reference_date,
        "acute_km": round(acute_km, 2),
        "acute_time_min": round(acute_time, 1),
        "acute_runs": acute_count,
        "chronic_km_weekly": chronic_km_weekly,
        "chronic_km_total": round(chronic_km_total, 2),
        "acwr": acwr,
        "ramp_rate_pct": ramp_rate,
        "prev_week_km": round(prev_week_km, 2),
        "easy_pct": easy_pct,
        "hard_pct": hard_pct,
        "easy_time_min": round(easy_time, 1),
        "hard_time_min": round(hard_time, 1),
        "updated_at": firestore.SERVER_TIMESTAMP,
    }

    ref = db.collection(f"athletes/{user_id}/weekly_load").document(week_key)
    ref.set(load_doc, merge=True)

    # Salva anche come "latest" per accesso rapido dalla dashboard
    latest_ref = db.collection(f"athletes/{user_id}/weekly_load").document("latest")
    latest_ref.set(load_doc, merge=True)

    logger.info(
        f"⚡ Carico: {acute_km:.1f}km (7gg) / "
        f"{chronic_km_weekly:.1f}km/sett (28gg) / "
        f"ACWR {acwr} / Ramp {ramp_rate:+.1f}%"
    )

    return load_doc
