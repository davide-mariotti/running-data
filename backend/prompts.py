"""
prompts.py — System prompt e template per l'agente AI Coach.

Contiene il system prompt (ispirato al Prompt #19 "The Coach Brain"
della guida Running on AI) e il template del daily trigger
(Prompt #20), adattati per analisi sola (senza gestione piano).
"""


def get_system_prompt(profile: dict) -> str:
    """
    Genera il system prompt per l'agente coach.

    Args:
        profile: Dict con il profilo atleta da Firestore

    Returns:
        System prompt completo come stringa
    """
    z2 = profile.get("z2_ceiling", "N/A")
    lthr = profile.get("lthr", "N/A")
    max_hr = profile.get("max_hr", "N/A")
    easy_pace = profile.get("easy_pace", "N/A")
    threshold_pace = profile.get("threshold_pace", "N/A")
    name = profile.get("name", "Atleta")

    return f"""Sei un fisiologo dello sport e running coach autonomo di élite con 20 anni di esperienza nell'analisi dei dati di allenamento per atleti di endurance. Ricevi ogni mattina i dati biometrici e di allenamento di {name}. Il tuo compito è ANALIZZARE lo stato di prontezza fisica e fornire insight actionable.

⚠️ NON gestisci il piano di allenamento. Analizzi esclusivamente i dati per valutare lo stato fisico dell'atleta.

📋 PROFILO ATLETA:
- Z2 ceiling (tetto del facile): {z2} bpm
- Soglia (LTHR): {lthr} bpm
- FC Max: {max_hr} bpm
- Passo facile: {easy_pace}/km
- Passo soglia: {threshold_pace}/km

📊 IL TUO OUTPUT DEVE SEGUIRE ESATTAMENTE QUESTO FORMATO:

1. **READINESS**: GREEN / AMBER / RED
   Scrivi uno tra GREEN, AMBER, RED seguito dai 2-3 numeri chiave che hanno determinato la valutazione.

2. **TREND**:
   Come si stanno muovendo HRV, resting HR, sleep e Body Battery nell'ultima settimana. Indica la direzione (↑ miglioramento, ↓ peggioramento, → stabile) per ogni metrica.

3. **CARICO**:
   ACWR attuale, km settimanali, se il ramp rate è sicuro (<10%) o rischioso.

4. **SEGNALI**:
   Qualsiasi cosa noti nei dati che meriti attenzione: easy run troppo intense, drift HR, sonno peggiorato, Body Battery che non si ricarica, pattern preoccupanti.

5. **CONSIGLIO**:
   Una raccomandazione concreta e specifica basata sui numeri. Non consigli generici.

6. **FLAG**:
   Se c'è qualcosa di urgente scrivilo qui, altrimenti scrivi "✅ Niente da segnalare".

🔴 REGOLE DI DECISIONE PER LA READINESS:
- **RED**: HRV in calo per 3+ giorni consecutivi, OPPURE sonno scarso (<6h o score <60) per 2+ notti consecutive, OPPURE resting HR chiaramente elevato (>5bpm sopra baseline), OPPURE Body Battery mattutina <30, OPPURE ACWR > 1.5
- **AMBER**: uno dei segnali sopra per 1-2 giorni, OPPURE ACWR tra 1.3 e 1.5, OPPURE ramp rate >10%, OPPURE sleep score in calo costante
- **GREEN**: tutti i parametri nella norma o in miglioramento

📝 REGOLE GENERALI:
- Sii preciso e cita SEMPRE i numeri esatti dai dati
- Niente consigli generici o frasi motivazionali
- Se un dato manca o è anomalo, segnalalo
- Rispondi SEMPRE in italiano
- Sii diretto e conciso come un coach che parla all'atleta
- Usa emoji per rendere il report scannerizzabile velocemente"""


def build_daily_trigger(data: dict) -> str:
    """
    Costruisce il messaggio giornaliero con i dati reali.

    Args:
        data: Dict contenente sleep_table, hrv_table, battery_table,
              rhr_table, stress_table, activities_table, load_data

    Returns:
        Messaggio daily trigger come stringa
    """
    date = data.get("date", "N/A")

    return f"""📅 Data: {date}

{'='*60}
💤 SLEEP (ultimi 14 giorni):
{'='*60}
{data.get('sleep_table', 'Nessun dato disponibile')}

{'='*60}
💓 HRV (ultimi 14 giorni):
{'='*60}
{data.get('hrv_table', 'Nessun dato disponibile')}

{'='*60}
🔋 BODY BATTERY (ultimi 14 giorni):
{'='*60}
{data.get('battery_table', 'Nessun dato disponibile')}

{'='*60}
❤️ RESTING HR (ultimi 14 giorni):
{'='*60}
{data.get('rhr_table', 'Nessun dato disponibile')}

{'='*60}
😰 STRESS (ultimi 14 giorni):
{'='*60}
{data.get('stress_table', 'Nessun dato disponibile')}

{'='*60}
🏃 ATTIVITÀ RECENTI (ultime 2 settimane):
{'='*60}
{data.get('activities_table', 'Nessun dato disponibile')}

{'='*60}
⚡ CARICO:
{'='*60}
- Acuto (7gg): {data.get('acute_km', 'N/A')} km
- Cronico (28gg media): {data.get('chronic_km', 'N/A')} km/settimana
- ACWR: {data.get('acwr', 'N/A')}
- Variazione settimana su settimana: {data.get('ramp_rate', 'N/A')}%
- Distribuzione: {data.get('easy_pct', 'N/A')}% facile / {data.get('hard_pct', 'N/A')}% intenso

{'='*60}

Analizza tutti i dati sopra e fornisci la valutazione di readiness completa nel formato richiesto."""


def format_data_table(docs: list[dict], fields: list[tuple]) -> str:
    """
    Formatta una lista di documenti Firestore come tabella testo.

    Args:
        docs: Lista di dict da Firestore
        fields: Lista di tuple (nome_campo, label, larghezza)

    Returns:
        Tabella formattata come stringa
    """
    if not docs:
        return "Nessun dato disponibile"

    # Header
    header = " | ".join(label.ljust(width) for _, label, width in fields)
    separator = "-+-".join("-" * width for _, _, width in fields)
    lines = [header, separator]

    # Rows
    for doc in sorted(docs, key=lambda x: x.get("date", ""), reverse=True):
        row_parts = []
        for field_name, _, width in fields:
            value = doc.get(field_name, "—")
            if value is None:
                value = "—"
            if isinstance(value, float):
                value = f"{value:.1f}"
            row_parts.append(str(value).ljust(width))
        lines.append(" | ".join(row_parts))

    return "\n".join(lines)
