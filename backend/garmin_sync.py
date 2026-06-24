"""
garmin_sync.py — Pipeline di estrazione dati da Garmin Connect.

Usa python-garminconnect per estrarre sleep, HRV, Body Battery,
stress, resting HR e attività. Salva tutto su Firestore.
I token OAuth vengono cachati su Firestore per persistenza tra
invocazioni Cloud Functions.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta

from firebase_admin import firestore
from garminconnect import Garmin

logger = logging.getLogger(__name__)


class GarminSync:
    """Sincronizza dati da Garmin Connect a Firestore."""

    def __init__(self, email: str, password: str, db, user_id: str):
        self.email = email
        self.password = password
        self.db = db
        self.user_id = user_id
        self.client = None
        self._token_dir = os.path.join(tempfile.gettempdir(), ".garminconnect")

    # ── Auth & Token Management ──────────────────────────────────

    def login(self):
        """Login a Garmin Connect con token caching su Firestore."""
        os.makedirs(self._token_dir, exist_ok=True)

        # Prova a caricare token salvati da Firestore
        self._load_tokens_from_firestore()

        self.client = Garmin(self.email, self.password)
        try:
            self.client.login(self._token_dir)
            logger.info("✅ Login Garmin riuscito con token salvati")
        except Exception as e:
            logger.warning(f"⚠️ Token scaduti o non trovati ({e}), re-login...")
            try:
                self.client = Garmin(self.email, self.password)
                self.client.login()
                logger.info("✅ Re-login Garmin riuscito")
            except Exception as login_err:
                logger.error(f"❌ Login Garmin fallito: {login_err}")
                raise

        # Salva token aggiornati su Firestore
        self._save_tokens_to_firestore()

    def _load_tokens_from_firestore(self):
        """Carica token OAuth salvati da Firestore nella dir temporanea."""
        try:
            doc = self.db.collection("system").document("garmin_tokens").get()
            if doc.exists:
                data = doc.to_dict()
                token_data = data.get("token_data")
                if token_data:
                    # Salva come file nella dir temporanea
                    token_file = os.path.join(self._token_dir, "garth_tokens.json")
                    with open(token_file, "w", encoding="utf-8") as f:
                        f.write(token_data)
                    logger.info("📥 Token Garmin caricati da Firestore")
        except Exception as e:
            logger.warning(f"⚠️ Impossibile caricare token da Firestore: {e}")

    def _save_tokens_to_firestore(self):
        """Salva token OAuth su Firestore per persistenza."""
        try:
            # Cerca file token nella dir
            token_files = {}
            if os.path.exists(self._token_dir):
                for fname in os.listdir(self._token_dir):
                    fpath = os.path.join(self._token_dir, fname)
                    if os.path.isfile(fpath):
                        with open(fpath, "r", encoding="utf-8") as f:
                            token_files[fname] = f.read()

            # Prova anche a salvare il token serializzato dal client
            token_data = None
            try:
                if hasattr(self.client, "garth") and self.client.garth:
                    token_data = self.client.garth.dumps()
            except Exception:
                pass

            self.db.collection("system").document("garmin_tokens").set({
                "token_data": token_data or json.dumps(token_files),
                "files": token_files,
                "updated_at": firestore.SERVER_TIMESTAMP,
            })
            logger.info("💾 Token Garmin salvati su Firestore")
        except Exception as e:
            logger.warning(f"⚠️ Impossibile salvare token su Firestore: {e}")

    # ── Sync Orchestrator ────────────────────────────────────────

    def sync_day(self, date_str: str):
        """Sincronizza tutti i dati di un singolo giorno."""
        logger.info(f"🔄 Sync giorno {date_str}...")
        results = {}

        sync_methods = [
            ("sleep", self._sync_sleep),
            ("hrv", self._sync_hrv),
            ("body_battery", self._sync_body_battery),
            ("stress", self._sync_stress),
            ("resting_hr", self._sync_resting_hr),
            ("activities", self._sync_activities),
        ]

        for name, method in sync_methods:
            try:
                method(date_str)
                results[name] = "✅"
                logger.info(f"  ✅ {name} sincronizzato")
            except Exception as e:
                results[name] = f"❌ {e}"
                logger.error(f"  ❌ {name} fallito: {e}")

        return results

    # ── Sleep ────────────────────────────────────────────────────

    def _sync_sleep(self, date_str: str):
        """Estrae e salva dati sonno."""
        data = self.client.get_sleep_data(date_str)
        if not data:
            logger.warning(f"  ⚠️ Nessun dato sonno per {date_str}")
            return

        # Estrai campi principali dal JSON Garmin
        daily_sleep = data.get("dailySleepDTO", data)

        doc = {
            "date": date_str,
            "duration_h": round(daily_sleep.get("sleepTimeSeconds", 0) / 3600, 2),
            "score": daily_sleep.get("sleepScores", {}).get("overall", {}).get("value")
                     or data.get("sleepScores", {}).get("overall", {}).get("value"),
            "deep_min": round(daily_sleep.get("deepSleepSeconds", 0) / 60, 1),
            "rem_min": round(daily_sleep.get("remSleepSeconds", 0) / 60, 1),
            "light_min": round(daily_sleep.get("lightSleepSeconds", 0) / 60, 1),
            "awake_min": round(daily_sleep.get("awakeSleepSeconds", 0) / 60, 1),
            "source": "garmin",
            "synced_at": firestore.SERVER_TIMESTAMP,
        }

        ref = self.db.collection(f"athletes/{self.user_id}/sleep").document(date_str)
        ref.set(doc, merge=True)

    # ── HRV ──────────────────────────────────────────────────────

    def _sync_hrv(self, date_str: str):
        """Estrae e salva HRV notturno."""
        data = self.client.get_hrv_data(date_str)
        if not data:
            return

        # Garmin HRV data structure
        hrv_summary = data.get("hrvSummary", data)

        doc = {
            "date": date_str,
            "rmssd": hrv_summary.get("lastNightAvg")
                     or hrv_summary.get("weeklyAvg"),
            "weekly_avg": hrv_summary.get("weeklyAvg"),
            "status": hrv_summary.get("status", "UNKNOWN"),
            "baseline_low": hrv_summary.get("baselineLowUpper"),
            "baseline_high": hrv_summary.get("baselineBalancedUpper"),
            "source": "garmin",
            "synced_at": firestore.SERVER_TIMESTAMP,
        }

        ref = self.db.collection(f"athletes/{self.user_id}/hrv").document(date_str)
        ref.set(doc, merge=True)

    # ── Body Battery ─────────────────────────────────────────────

    def _sync_body_battery(self, date_str: str):
        """Estrae e salva Body Battery."""
        data = self.client.get_body_battery(date_str)
        if not data:
            return

        # Body Battery restituisce una lista di dict
        bb_list = data[0].get("bodyBatteryValuesArray", []) if isinstance(data, list) and len(data) > 0 else []

        if not bb_list:
            return

        values = []
        for item in bb_list:
            # item is [timestamp, value]
            if isinstance(item, list) and len(item) == 2:
                val = item[1]
                if val is not None and isinstance(val, (int, float)):
                    values.append(val)

        if not values:
            return

        doc = {
            "date": date_str,
            "morning_value": max(values) if values else None,
            "low": min(values),
            "high": max(values),
            "source": "garmin",
            "synced_at": firestore.SERVER_TIMESTAMP,
        }

        ref = self.db.collection(f"athletes/{self.user_id}/body_battery").document(date_str)
        ref.set(doc, merge=True)

    # ── Stress ───────────────────────────────────────────────────

    def _sync_stress(self, date_str: str):
        """Estrae e salva dati stress."""
        data = self.client.get_stress_data(date_str)
        if not data:
            return

        doc = {
            "date": date_str,
            "avg_stress": data.get("overallStressLevel")
                          or data.get("avgStressLevel"),
            "max_stress": data.get("maxStressLevel"),
            "rest_stress": data.get("restStressDuration"),
            "high_stress_duration": data.get("highStressDuration"),
            "source": "garmin",
            "synced_at": firestore.SERVER_TIMESTAMP,
        }

        ref = self.db.collection(f"athletes/{self.user_id}/stress").document(date_str)
        ref.set(doc, merge=True)

    # ── Resting HR ───────────────────────────────────────────────

    def _sync_resting_hr(self, date_str: str):
        """Estrae e salva resting HR."""
        data = self.client.get_heart_rates(date_str)
        if not data:
            return

        doc = {
            "date": date_str,
            "value": data.get("restingHeartRate"),
            "baseline": data.get("minHeartRate"),
            "source": "garmin",
            "synced_at": firestore.SERVER_TIMESTAMP,
        }

        ref = self.db.collection(f"athletes/{self.user_id}/resting_hr").document(date_str)
        ref.set(doc, merge=True)

    # ── Activities (Runs) ────────────────────────────────────────

    def _sync_activities(self, date_str: str):
        """Estrae e salva attività di corsa del giorno."""
        activities = self.client.get_activities_by_date(date_str, date_str)
        if not activities:
            return

        for activity in activities:
            # Filtra solo attività di corsa
            activity_type = activity.get("activityType", {})
            type_key = activity_type.get("typeKey", "")
            if "running" not in type_key.lower() and "run" not in type_key.lower():
                continue

            activity_id = str(activity.get("activityId", ""))
            if not activity_id:
                continue

            # Converti pace da m/s a min/km
            avg_speed = activity.get("averageSpeed", 0)  # m/s
            avg_pace = ""
            if avg_speed and avg_speed > 0:
                pace_seconds = 1000 / avg_speed
                pace_min = int(pace_seconds // 60)
                pace_sec = int(pace_seconds % 60)
                avg_pace = f"{pace_min}:{pace_sec:02d}"

            doc = {
                "date": date_str,
                "activity_id": activity_id,
                "name": activity.get("activityName", ""),
                "distance_km": round(activity.get("distance", 0) / 1000, 2),
                "duration_min": round(activity.get("duration", 0) / 60, 1),
                "avg_hr": activity.get("averageHR"),
                "max_hr": activity.get("maxHR"),
                "avg_pace": avg_pace,
                "avg_speed_ms": avg_speed,
                "elevation_m": activity.get("elevationGain"),
                "calories": activity.get("calories"),
                "type": type_key,
                "training_effect_aerobic": activity.get("aerobicTrainingEffect"),
                "training_effect_anaerobic": activity.get("anaerobicTrainingEffect"),
                "source": "garmin",
                "synced_at": firestore.SERVER_TIMESTAMP,
            }

            doc_id = f"{date_str}_{activity_id}"
            ref = self.db.collection(f"athletes/{self.user_id}/runs").document(doc_id)
            ref.set(doc, merge=True)

    # ── Auto-detect HR Zones ─────────────────────────────────────

    def detect_hr_zones(self):
        """Estrae le zone HR da Garmin per impostare il profilo base usando il Metodo Karvonen."""
        try:
            profile = self.client.get_user_profile()
            user_data = profile.get("userData", {})
            lthr = user_data.get("lactateThresholdHeartRate")
            max_hr = user_data.get("maxHeartRate")
            resting_hr = user_data.get("restingHeartRate")
            
            # Se FC Max o Riposo mancano dal profilo principale, proviamo le metriche di oggi
            if not max_hr or not resting_hr:
                try:
                    today = datetime.now().strftime("%Y-%m-%d")
                    hr_zones_data = self.client.get_heart_rates(today)
                    if hr_zones_data:
                        max_hr = max_hr or hr_zones_data.get("maxHeartRate")
                        resting_hr = resting_hr or hr_zones_data.get("restingHeartRate")
                except Exception as e:
                    logger.debug(f"Impossibile leggere max/rest hr giornalieri: {e}")
                    
            if not max_hr:
                max_hr = 190
            if not resting_hr:
                resting_hr = 50
                
            reserve = max_hr - resting_hr
            
            # Metodo Karvonen
            z1 = int(resting_hr + reserve * 0.50)
            z2 = int(resting_hr + reserve * 0.60)
            z3 = int(resting_hr + reserve * 0.70)
            z4 = int(resting_hr + reserve * 0.80)
            z5 = int(resting_hr + reserve * 0.90)
            
            z2_ceiling = z3  # Il tetto della zona 2 coincide col fondo della zona 3
            lthr_est = lthr or int(resting_hr + reserve * 0.85)
                
            return {
                "max_hr": max_hr,
                "resting_hr": resting_hr,
                "lthr": lthr_est,
                "z2_ceiling": z2_ceiling,
                "z1_bottom": z1,
                "z2_bottom": z2,
                "z3_bottom": z3,
                "z4_bottom": z4,
                "z5_bottom": z5
            }
        except Exception as e:
            logger.warning(f"⚠️ Impossibile rilevare zone HR: {e}")
            return None
