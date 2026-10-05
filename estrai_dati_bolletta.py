import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def estrai_dati_bolletta(testo: str) -> dict:
    try:
        prompt = (
            " sei un esperto di fatturazione energia elettrica e gas, Estrai i dati principali da una bolletta di energia elettrica o gas e restituiscili in formato JSON con i seguenti campi:\n\n"
            "- cliente (nome e cognome o ragione sociale)\n"
            "- indirizzo (completo del punto di fornitura)\n"
            "- pod (codice POD o PDR, se presente)\n"
            "- kwh_totali (consumo totale nel periodo, potrebbe essere scritto come KWH fatturati o consumi rilevati o quanto ho consumato o similari solo numero intero ad esempio 1,2,3)\n"
            "- mesi_bolletta (cerca periodo di fatturazione e restituisci il numero dei mesi ad esempio gennaio-febbraio 2025 è uguale a 2 , marzo 2025 uguale a 1, 01/05/2025-30/06/2025 uguale a 2 non mettere altro testo)\n"
            "- spesa_materia_energia (importo totale del periodo relativo ESCLUSIVAMENTE alla vendita dell'energia per consumi, esclusi rete, trasporto, distribuzione, oneri di sistema, componenti regolate e quota fissa. Applica le priorità SPESA VENDITA ENERGIA sotto indicate. Restituisci l'importo in euro, NON il prezzo unitario €/kWh o €/Smc, come numero con punto decimale; se non identificabile restituisci null)\n"
            "- spesa_vendita_energia (stesso importo commerciale per consumi di spesa_materia_energia, mantenuto anche con questo nome per il confronto: applica le stesse priorità e restituisci lo stesso valore numerico, oppure null se non identificabile)\n"
            "- quota_fissa_vendita (sola quota fissa COMMERCIALE di vendita nella sezione Quota fissa, escludendo rete/oneri. Restituisci euro AL MESE: se indicata mensilmente usa quel valore, se indicata come totale del periodo dividila per mesi_bolletta una sola volta. Non includerla in spesa_vendita_energia. Se non identificabile restituisci null, senza inventare importi)\n"
            "- tipo_fornitura ('Luce' o 'Gas')\n"
            "- tipologia_cliente  (restituisci esclusivamente Residenziale se non è Altri Usi, Business se è altri usi)\n"
            "SPESA VENDITA ENERGIA ELETTRICA (o equivalente per gas):\n"
            "PRIORITÀ 1: se nella sezione Quota per consumi è presente 'di cui spesa per la vendita di energia elettrica', estrai SEMPRE l'importo in euro associato a quella sottovoce, non il totale superiore del riquadro e non la quota fissa dell'omonima sezione.\n"
            "PRIORITÀ 2: accetta diciture semanticamente equivalenti come 'spesa per la vendita di energia elettrica', 'componente vendita energia', 'spesa vendita energia', 'materia energia relativa alla vendita', 'componente energia del venditore', quando identificano la componente commerciale per consumi distinta da rete/oneri/trasporto/distribuzione.\n"
            "PRIORITÀ 3: usa un valore generale come 'spesa materia energia' o 'quota consumi' SOLO se non esiste una scomposizione più precisa e la voce identifica esclusivamente la vendita energia per consumi. Non usare un totale che include componenti regolate; se la sola vendita non è identificabile restituisci null.\n"
            "La sottovoce specifica di vendita ha SEMPRE priorità sul totale e sull'ordine di comparsa nel documento. NON usare il totale Quota per consumi quando comprende rete, trasporto, distribuzione, oneri di sistema o componenti regolate.\n"
            "CONTROLLO DI COERENZA: se vendita energia + rete/oneri è circa uguale al totale Quota per consumi, il totale è composto: restituisci SEMPRE la vendita energia in entrambi i campi spesa_materia_energia e spesa_vendita_energia. Questa relazione serve solo a disambiguare: estrai direttamente l'importo della sottovoce, NON ricavarlo con sottrazioni o altre formule.\n"
            "ESEMPIO ILLUSTRATIVO (non copiare questi importi se diversi dalla bolletta da analizzare):\n"
            "INPUT BOLLETTA:\nQuota per consumi: 459 kWh; prezzo medio 0,276819 €/kWh; importo 127,06 €.\n"
            "di cui spesa per la vendita di energia elettrica: 0,228954 €/kWh; importo 105,09 €.\n"
            "di cui spesa per la rete e gli oneri di sistema: 0,047865 €/kWh; importo 21,97 €.\n"
            "OUTPUT (estratto dei soli campi energia): {\"spesa_materia_energia\": 105.09, \"spesa_vendita_energia\": 105.09}\n"
            "OUTPUT ERRATO: {\"spesa_materia_energia\": 127.06, \"spesa_vendita_energia\": 127.06}. Anche 0.228954 è errato: è il prezzo unitario, non l'importo del periodo.\n"
            "Per gli ALTRI campi, se trovi più corrispondenze restituisci il primo che trovi. Rispondi con tutti i campi richiesti in JSON valido, senza commenti, testo extra o simboli come ```json. Ecco il testo da analizzare:\n\n"
            f"{testo[:7000]}" # AGGIUNGI  "- quota_fissa_vendita (cerca subito dopo la sezione Quota fissa il corrispondente importo dopo la dicitura 'di cui spesa per vendita energia elettrica' deve essere una quota euro al mese solo il valore numerico con punto decimale se non lo trovi metti 10)\n"  #modifica 05-09-2025
        )

        response = client.chat.completions.create(
            model="gpt-3.5-turbo-0125",   #gpt-4-turbo # gpt-3.5-turbo-0125
            messages=[
                {"role": "system", "content": "Sei un assistente esperto in bollette di luce e gas."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1700
        )

        content = response.choices[0].message.content

        # Rimuove eventuali blocchi markdown ```json
        json_text = re.sub(r"```json|```", "", content).strip()
        return json.loads(json_text)

    except Exception as e:
        return {
            "errore": "Formato non riconosciuto o parsing fallito",
            "output": content if 'content' in locals() else str(e)
        }
