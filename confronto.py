from database_service import get_offerte
from airtable_service import get_prezzo_mercato
from datetime import datetime

def confronta_offerte(bolletta):
    kwh_totali = bolletta["kwh_totali"]
    mesi_bolletta = bolletta["mesi_bolletta"]
    spesa_vendita_energia = bolletta["spesa_vendita_energia"]
    quota_fissa = bolletta["quota_fissa_vendita"]  # Commercial fixed cost in EUR/month.
    tipo_fornitura = bolletta["tipo_fornitura"]
    tipologia_cliente = bolletta["tipologia_cliente"]
    data = bolletta["data_riferimento"]
   
    
    kwh_mensili = kwh_totali / mesi_bolletta
    spesa_mensile = (spesa_vendita_energia / mesi_bolletta) + quota_fissa
    prezzo_effettivo = spesa_mensile / kwh_mensili

    offerte = get_offerte(tipo_fornitura, tipologia_cliente)
    #prezzo_mercato = get_prezzo_mercato(tipo_fornitura, data)
    dati_mercato = get_prezzo_mercato(tipo_fornitura, data)
    #ricavo sia prezzo del PUN/PSV che spesa per dispacciamento ccr ecc ecc
    prezzo_mercato = dati_mercato["prezzo_medio"]
    disp = dati_mercato["disp"]

    
    confronti = []

    for offerta in offerte:
        fields = offerta.get("fields", {})
        tipo_tariffa = fields.get("Tipo tariffa")
        costo_fisso = fields.get("Costo fisso mensile", 0)
        id_offerta = fields.get("id_offerta")

        if tipo_tariffa == "Fisso":
            prezzo_kwh = fields.get("Prezzo fisso €/kWh", 0) 
        elif tipo_tariffa == "Variabile":
            spread = fields.get("Spread €/kWh", 0)
            prezzo_kwh = prezzo_mercato + spread
        else:
            continue

        if tipo_tariffa == "Fisso":
            costo_stimato = prezzo_kwh * 1.10 * kwh_mensili + costo_fisso
        else:
            costo_stimato = (prezzo_kwh + disp) * kwh_mensili + costo_fisso
        delta = costo_stimato - spesa_mensile

        if delta < 0:
            tipo_diff = "Risparmio"
            percentuale = abs(delta) / spesa_mensile * 100
        else:
            tipo_diff = "Spesa in più"
            percentuale = delta / spesa_mensile * 100 if spesa_mensile else 0

        confronti.append({
            "id": id_offerta,
            "fornitore": fields.get("Fornitore"),  # visibile solo nel backend
            "nome_offerta": fields.get("Nome offerta"),
            "tariffa": tipo_tariffa,
            "prezzo_kwh": round(prezzo_kwh, 4),
            "costo_fisso": costo_fisso,
            "totale_simulato": round(costo_stimato, 2),
            "risparmio_annuo": round(-delta * 12, 2),
            "prezzo_effettivo_pagato": round(prezzo_effettivo, 4),
            "differenza_mensile": round(delta, 2),
            "tipo_differenza": tipo_diff,
            "percentuale": round(percentuale, 2),
            # The URL is internal to this API; credentials and object keys never reach clients.
            "cte": ({"filename": fields.get("pdf_filename"), "url": f"https://backend-net-billy-production.up.railway.app/cte-offers/{offerta['id']}/pdf"}
                    if fields.get("has_pdf") else None)
        })

    confronti.sort(key=lambda x: x["totale_simulato"])
    return confronti
