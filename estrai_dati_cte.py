import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _normalize_optional_power_kw(value):
    """Accept only explicit numeric kW values; unknown or invalid values stay null."""
    if value is None or value == "":
        return None
    try:
        normalized = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return normalized if normalized >= 0 else None


def estrai_dati_offerta_cte(testo: str) -> dict:
    try:
        prompt = (
            "Estrai i dati principali dell'offerta luce o gas da questa CTE (Condizione Tecnico Economica) e restituiscili in formato JSON.\n\n"
            "Campi richiesti:\n"
            "- fornitore (es. Enel Energia)\n"
            "- nome_offerta (nome commerciale dell'offerta)\n"
            "- tipologia_cliente (Residenziale o Business)\n"
            "- tariffa (Fisso o Variabile)\n"
            "- prezzo_kwh (considera il prezzo della materia energia sia essa energia elettica o gas solo se tariffa Fisso, es. 0.145) oppure 0\n"
            "- spread (considera il prezzo della materia energia sia essa energia elettrica o gas solo se tariffa Variabile, potresti trovarlo scritto anche come contributo al consumo o parametro alfa es. 0.0135) oppure 0\n"
            "- costo_fisso (potresti trovarlo scritto anche come  commercializzazione o CCV, se l'importo è maggiore di 30 euro dividilo per 12 e mostra il risultato)\n"
            "- validita (data in formato 'YYYY-MM-DD', oppure se non disponibile aggiungi 3 mesi alla data di caricamento)\n"
            "- vincoli (es. 'Durata minima 12 mesi') o null\n"
            "- tipo_fornitura (Luce o Gas se sono presenti tutti e due scegli sempre solo LUCE)\n"
            "- min_power_kw (numero decimale o null: limite minimo esplicito di potenza impegnata, contrattuale o disponibile, normalizzato in kW)\n"
            "- max_power_kw (numero decimale o null: limite massimo esplicito di potenza impegnata, contrattuale o disponibile, normalizzato in kW)\n\n"
            "Cerca condizioni come 'da 25 kW in su', 'fino a 15 kW' o 'da 10 kW a 30 kW'. Se non esiste un limite chiaramente dichiarato, restituisci entrambi null. Non inventare limiti.\n\n"
            "Rispondi solo con JSON valido, senza commenti o testo extra. Ecco il testo da analizzare:\n\n"
            "Testo da analizzare:\n"
            f"{testo[:7000]}"
        )

        response = client.chat.completions.create(
            model="gpt-3.5-turbo-0125",
            messages=[
                {"role": "system", "content": "Sei un assistente esperto in offerte luce e gas."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=600
        )

        content = response.choices[0].message.content

        # Rimuove eventuali blocchi markdown tipo ```json
        json_text = re.sub(r"```json|```", "", content).strip()

        dati = json.loads(json_text)
        dati["min_power_kw"] = _normalize_optional_power_kw(dati.get("min_power_kw"))
        dati["max_power_kw"] = _normalize_optional_power_kw(dati.get("max_power_kw"))
        return dati

    except Exception as e:
        return {
            "errore": "Formato non riconosciuto o parsing fallito",
            "output": content if 'content' in locals() else str(e)
        }
