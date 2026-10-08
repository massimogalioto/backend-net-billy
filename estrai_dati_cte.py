import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI
from cte_notes import format_cte_notes
from cte_validity import normalize_cte_validity

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
            "- fornitore (es. Enel Energia, ACEA, IREN, ENI Plenitude)\n"
            "- nome_offerta (nome commerciale dell'offerta)\n"
            "- tipologia_cliente (Residenziale o Business)\n"
            "- tariffa (Fisso o Variabile)\n"
            "- prezzo_kwh (considera il prezzo della materia energia sia essa energia elettica o gas solo se tariffa Fisso, es. 0.145) oppure 0\n"
            "- spread (considera il prezzo della materia energia sia essa energia elettrica o gas solo se tariffa Variabile, potresti trovarlo scritto anche come contributo al consumo o parametro alfa es. 0.0135) oppure 0\n"
            "- costo_fisso (potresti trovarlo scritto anche come  commercializzazione o CCV, se l'importo è maggiore di 30 euro dividilo per 12 e mostra il risultato)\n"
            "- valid_from: data in formato 'YYYY-MM-DD' solo se il documento indica esplicitamente l'inizio della validità commerciale, ad esempio 'condizioni valide dal 01/10/2026 al 31/10/2026 oppure Validità per adesioni entro il'. Non usare date di documento, emissione, caricamento, decorrenza del cliente o date odierne. Se non è presente un vero inizio, restituisci null.\n"
            "- valid_until: data in formato 'YYYY-MM-DD' per scadenza dell'offerta, 'valida fino al', 'sottoscrivibile entro/fino al', condizioni economiche valide fino al, fine validità commerciale, disponibilità fino al o scadenza. Se esiste una sola data associata genericamente a validità/scadenza dell'offerta, assegnala qui e lascia valid_from null. Non inventare date e non aggiungere mesi alla data di caricamento.\n"
            "- vincoli (es. 'Durata minima 12 mesi') o null\n"
            "- tipo_fornitura: restituisci esclusivamente 'Luce', 'Gas' oppure null se non determinabile. Usa tutto il contenuto della CTE: Luce se trovi energia elettrica, POD, kWh, €/kWh, PUN, potenza impegnata/disponibile; Gas se trovi gas naturale, PDR, Smc, €/Smc o PSV. Non inventare il valore se ambiguo.\n"
            "- min_power_kw (numero decimale o null: limite minimo esplicito di potenza impegnata, contrattuale o disponibile, normalizzato in kW)\n"
            "- max_power_kw (numero decimale o null: limite massimo esplicito di potenza impegnata, contrattuale o disponibile, normalizzato in kW)\n"
            "- fatturazione: restituisci solo 'Mensile', 'Bimestrale' oppure 'Non indicata'. Cerca in tutto il documento espressioni quali fatturazione mensile/bimestrale, fattura ogni mese/due mesi, ciclo o periodicità di fatturazione, emissione mensile/bimestrale. Non dedurre nulla se non è esplicito o ragionevolmente indicato.\n"
            "- recesso_anticipato: riporta in modo conciso solo la clausola esplicitamente trovata; se il documento dichiara assenza di penali usa esattamente 'Nessuna penale rilevata'; se non trovi una clausola usa esattamente 'Non indicato'. Cerca anche costo/corrispettivo/onere di recesso, indennizzo, risoluzione anticipata, durata o permanenza minima, recupero sconti o bonus e restituzione di vantaggi economici. Non inventare durata, importi, formule o condizioni.\n"
            "- altre_note: eventuali altre note contrattuali utili, oppure null. Non ripetere qui fatturazione o recesso.\n\n"
            "Cerca condizioni come 'da 25 kW in su', 'fino a 15 kW' o 'da 10 kW a 30 kW'. Se non esiste un limite chiaramente dichiarato, restituisci entrambi null. Non inventare limiti.\n\n"
            "Rispondi solo con JSON valido, senza commenti o testo extra. Ecco il testo da analizzare:\n\n"
            "Testo da analizzare:\n"
            f"{testo[:7000]}"
        )

        response = client.chat.completions.create(
            model="gpt-3.5-turbo-0125", # era precedentemente gpt-3.5-turbo-0125  gpt-6-luna
            messages=[
                {"role": "system", "content": "Sei un assistente esperto in offerte luce e gas."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=900
        )

        content = response.choices[0].message.content

        # Rimuove eventuali blocchi markdown tipo ```json
        json_text = re.sub(r"```json|```", "", content).strip()

        dati = normalize_cte_validity(json.loads(json_text))
        dati["min_power_kw"] = _normalize_optional_power_kw(dati.get("min_power_kw"))
        dati["max_power_kw"] = _normalize_optional_power_kw(dati.get("max_power_kw"))
        dati["notes"] = format_cte_notes(
            dati.get("fatturazione"), dati.get("recesso_anticipato"),
            dati.get("altre_note"), dati.get("vincoli"),
        )
        return dati

    except Exception as e:
        return {
            "errore": "Formato non riconosciuto o parsing fallito",
            "output": content if 'content' in locals() else str(e)
        }
