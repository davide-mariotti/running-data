"""
setup_garmin.py — Script per il primo login Garmin Connect.

Esegui questo script localmente una volta per:
1. Fare il primo login a Garmin Connect (gestisce MFA)
2. Salvare i token OAuth su Firestore
3. Rilevare automaticamente le zone HR
4. Creare il profilo atleta su Firestore

Uso:
    cd scripts
    pip install garminconnect firebase-admin
    python setup_garmin.py
"""

import json
import os
import sys
from datetime import datetime

# Aggiungi la directory functions al path per importare i moduli
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'functions'))

import firebase_admin
from firebase_admin import credentials, firestore


def main():
    print("=" * 60)
    print("🏃 AGENTIC RUNNING COACH — Setup Iniziale")
    print("=" * 60)
    print()

    # ── 1. Firebase Init ──────────────────────────────────────
    print("🔥 Inizializzazione Firebase...")
    print("   ℹ️  Assicurati di aver scaricato il file service account:")
    print("   Firebase Console → ⚙️ → Account di servizio → Genera nuova chiave")
    print()

    print("📁 Percorso del file service-account.json: (usando default)")
    sa_path = ""
    if not sa_path:
        sa_path = os.path.join(os.path.dirname(__file__), '..', 'service-account.json')

    if not os.path.exists(sa_path):
        print(f"❌ File non trovato: {sa_path}")
        print("   Scaricalo dalla Firebase Console e riprova.")
        return

    cred = credentials.Certificate(sa_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("   ✅ Firebase connesso!")
    print()

    # ── 2. Garmin Login ───────────────────────────────────────
    print("🏅 Login Garmin Connect...")
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")

    try:
        from garminconnect import Garmin

        client = Garmin(
            email=email,
            password=password,
            prompt_mfa=lambda: input("🔐 Codice MFA (se richiesto): "),
        )
        client.login()
        print("   ✅ Login Garmin riuscito!")
    except Exception as e:
        print(f"   ❌ Login fallito: {e}")
        print("   Verifica email e password e riprova.")
        return

    # ── 3. Salva Token ────────────────────────────────────────
    print()
    print("💾 Salvataggio token su Firestore...")
    try:
        token_data = None
        if hasattr(client, 'garth') and client.garth:
            token_data = client.garth.dumps()

        db.collection("system").document("garmin_tokens").set({
            "token_data": token_data,
            "email": email,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        print("   ✅ Token salvati!")
    except Exception as e:
        print(f"   ⚠️ Errore salvataggio token: {e}")

    # ── 4. Rileva Zone HR ─────────────────────────────────────
    print()
    print("💓 Rilevamento zone HR da Garmin...")
    max_hr = None
    resting_hr = None
    z2_ceiling = None
    lthr = None

    try:
        # Prova user settings
        user_settings = client.get_user_settings()
        if user_settings:
            max_hr = user_settings.get("userData", {}).get("maxHeartRate")
            resting_hr = user_settings.get("userData", {}).get("restingHeartRate")
    except Exception:
        pass

    try:
        # Prova HR zones
        hr_zones_data = client.get_heart_rates(datetime.now().strftime("%Y-%m-%d"))
        if hr_zones_data:
            resting_hr = resting_hr or hr_zones_data.get("restingHeartRate")
            max_hr = max_hr or hr_zones_data.get("maxHeartRate")
    except Exception:
        pass

    if max_hr and resting_hr:
        reserve = max_hr - resting_hr
        # Karvonen method
        z1 = int(resting_hr + reserve * 0.50)
        z2 = int(resting_hr + reserve * 0.60)
        z3 = int(resting_hr + reserve * 0.70)
        z4 = int(resting_hr + reserve * 0.80)
        z5 = int(resting_hr + reserve * 0.90)
        
        z2_ceiling = z3
        lthr = int(resting_hr + reserve * 0.85)
        print(f"   ✅ FC Max: {max_hr} bpm")
        print(f"   ✅ FC a Riposo: {resting_hr} bpm")
        print(f"   ✅ Zone Karvonen: Z1 {z1}+ | Z2 {z2}+ | Z3 {z3}+ | Z4 {z4}+ | Z5 {z5}+")
        print(f"   ✅ Z2 Ceiling: {z2_ceiling} bpm")
        print(f"   ✅ Soglia LTHR: {lthr} bpm")
    else:
        print("   ⚠️ Impossibile rilevare automaticamente le zone HR (manca FC Max o Riposo)")
        print("   Inserisci manualmente:")
        try:
            max_hr = int(input("   FC Max: "))
            resting_hr = int(input("   FC a Riposo: "))
            
            reserve = max_hr - resting_hr
            z1 = int(resting_hr + reserve * 0.50)
            z2 = int(resting_hr + reserve * 0.60)
            z3 = int(resting_hr + reserve * 0.70)
            z4 = int(resting_hr + reserve * 0.80)
            z5 = int(resting_hr + reserve * 0.90)
            
            z2_ceiling = int(input(f"   Z2 Ceiling (es. {z3}): ") or z3)
            lthr = int(input(f"   Soglia LTHR (es. {int(resting_hr + reserve * 0.85)}): ") or int(resting_hr + reserve * 0.85))
        except ValueError:
            print("   ⚠️ Valori non validi, uso default")
            max_hr = 190
            resting_hr = 50
            reserve = max_hr - resting_hr
            z1 = int(resting_hr + reserve * 0.50)
            z2 = int(resting_hr + reserve * 0.60)
            z3 = int(resting_hr + reserve * 0.70)
            z4 = int(resting_hr + reserve * 0.80)
            z5 = int(resting_hr + reserve * 0.90)
            z2_ceiling = z3
            lthr = 170

    # ── 5. Crea Profilo Atleta ────────────────────────────────
    print()
    print("👤 Creazione profilo atleta...")

    name = "Davide"
    easy_pace = "6:30"
    threshold_pace = "4:45"

    user_id = "athlete_main"
    profile = {
        "name": name,
        "max_hr": max_hr,
        "resting_hr": resting_hr,
        "lthr": lthr,
        "z2_ceiling": z2_ceiling,
        "z1_bottom": z1,
        "z2_bottom": z2,
        "z3_bottom": z3,
        "z4_bottom": z4,
        "z5_bottom": z5,
        "easy_pace": easy_pace,
        "threshold_pace": threshold_pace,
        "auto_detected": max_hr is not None,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }

    db.collection("athletes").document(user_id).set(profile, merge=True)
    print("   ✅ Profilo creato con successo!")

    # ── 6. Test: Primo Sync ───────────────────────────────────
    print()
    do_sync = "s"

    if do_sync == 's':
        print("   Sincronizzazione ultimi 7 giorni...")
        from garmin_sync import GarminSync

        sync = GarminSync(email, password, db, user_id)
        sync.client = client  # Riusa il client già loggato

        today = datetime.now().date()
        from datetime import timedelta

        for i in range(7):
            day = today - timedelta(days=i)
            day_str = day.isoformat()
            print(f"   📅 {day_str}...", end=" ")
            try:
                results = sync.sync_day(day_str)
                statuses = [f"{k}:{v}" for k, v in results.items()]
                print(" ".join(statuses))
            except Exception as e:
                print(f"❌ {e}")

        # Calcola carico
        from compute_load import compute_weekly_load
        compute_weekly_load(db, user_id, today.isoformat())
        print("   ✅ Primo sync completato!")

    # ── Riepilogo ─────────────────────────────────────────────
    print()
    print("=" * 60)
    print("🎉 SETUP COMPLETATO!")
    print("=" * 60)
    print()
    print("📋 Prossimi passi:")
    print("   1. Configura i segreti Firebase:")
    print(f"      firebase functions:secrets:set GARMIN_EMAIL")
    print(f"      firebase functions:secrets:set GARMIN_PASSWORD")
    print(f"      firebase functions:secrets:set GEMINI_API_KEY")
    print()
    print("   2. Configura Firebase Auth:")
    print("      Firebase Console → Authentication → Metodi di accesso")
    print("      → Attiva Email/Password")
    print("      → Aggiungi il tuo utente manualmente")
    print()
    print("   3. Configura la dashboard:")
    print("      Copia il config Firebase in hosting/js/app.js")
    print("      Firebase Console → ⚙️ → Le tue app → Config")
    print()
    print("   4. Deploy:")
    print("      firebase deploy")
    print()


if __name__ == "__main__":
    main()
