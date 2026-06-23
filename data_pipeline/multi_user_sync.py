#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multi_user_sync.py — Orchestratore per il sync multi-utente
=========================================================

Esegue la pipeline di sincronizzazione per ogni utente presente nel database
che ha impostato le credenziali Garmin. Lancia `auto_fetch.py` con i
parametri corretti per isolare gli ambienti (cartelle temporanee).
"""

import sys
import os
import shutil
import subprocess
import logging
from pathlib import Path
from firebase_admin import credentials, firestore, initialize_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MultiUserSync")

root_dir = Path(__file__).parent.parent
data_pipeline_dir = root_dir / "data_pipeline"

def run_auto_fetch(uid, email, pwd, is_admin=False):
    logger.info(f"\n{'='*60}\nAvvio Sincronizzazione per: {uid} ({'ADMIN' if is_admin else 'USER'})\n{'='*60}")
    
    cmd = [
        sys.executable, str(data_pipeline_dir / "auto_fetch.py"),
        "--user_id", uid,
        "--email", email,
        "--password", pwd
    ]
    
    if not is_admin:
        # Cartella isolata
        work_dir = Path(f"/tmp/garmin_users/{uid}")
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--work_dir", str(work_dir)])
        
    logger.info(f"Esecuzione: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    
    if not is_admin and 'work_dir' in locals() and work_dir.exists():
        # Pulisci dopo aver finito per non lasciare dati in chiaro di altri sul server
        shutil.rmtree(work_dir)
        
    return result.returncode == 0

def main():
    sa_path = root_dir / "service-account.json"
    if not sa_path.exists():
        sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        if not sa_path or not os.path.exists(sa_path):
            logger.error("Impossibile trovare il Service Account.")
            sys.exit(1)
            
    cred = credentials.Certificate(str(sa_path))
    try:
        initialize_app(cred)
    except ValueError:
        pass
        
    db = firestore.client()
    
    # Utenti che hanno salvato le credenziali nel loro profilo
    users_ref = db.collection("users").stream()
    
    users = []
    for doc in users_ref:
        data = doc.to_dict()
        uid = doc.id
        email = data.get("garmin_email")
        pwd = data.get("garmin_password")
        
        if not email or not pwd:
            logger.debug(f"Credenziali mancanti per {uid}. Salto.")
            continue
            
        users.append({
            "uid": uid,
            "email": email,
            "pwd": pwd,
        })
        
    # Inoltre, controlliamo le credenziali ENV per l'admin (athlete_main)
    # Se non c'è nel database users, lo eseguiamo via variabili di ambiente
    admin_email = os.environ.get("GARMIN_EMAIL")
    admin_pwd = os.environ.get("GARMIN_PASSWORD")
    if admin_email and admin_pwd:
        if not any(u["uid"] == "athlete_main" for u in users):
            users.insert(0, {
                "uid": "athlete_main",
                "email": admin_email,
                "pwd": admin_pwd
            })
            
    if not users:
        logger.warning("Nessun utente con credenziali valide trovato.")
        sys.exit(0)
        
    logger.info(f"Trovati {len(users)} utenti da sincronizzare.")
    
    success_count = 0
    for u in users:
        is_admin = (u["uid"] == "athlete_main")
        if run_auto_fetch(u["uid"], u["email"], u["pwd"], is_admin):
            success_count += 1
            
    logger.info(f"Fine sync globale. {success_count}/{len(users)} utenti completati con successo.")
    
if __name__ == "__main__":
    main()
