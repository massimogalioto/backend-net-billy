# Attachment CTE in questo export Netlify

Questa cartella contiene la versione aggiornata pronta da caricare su Netlify.
La modifica riguarda esclusivamente il PDF originale della CTE e il pulsante
"Visualizza CTE" nei risultati bolletta. Colori, CSS, calcoli e coda sono invariati.

## Flusso

Il salvataggio singolo e quello massivo inviano a `/salva-offerta` i campi
esistenti e `cte_pdf: { filename, content_base64 }`. Il contenuto è una codifica
reversibile dei byte del File originale, senza ricostruzioni OCR. Il nome del
file serve come metadato: l'associazione non si basa sul nome del fornitore né
sul nome del PDF. Ogni worker passa il proprio oggetto File alla funzione di
salvataggio. La concorrenza resta 2.

Il backend crea il record con `salva_offerta()` e poi chiama
`Table.upload_attachment(record_id, "CTE", filename, content=pdf,
content_type="application/pdf")`. Con versioni precedenti di pyairtable viene
usato l'endpoint reale `https://content.airtable.com/v0/.../uploadAttachment`,
con lo stesso token ambiente. Nessun nuovo campo o servizio storage.
I client precedenti che inviano solo i campi offerta continuano a funzionare.

Un errore attachment restituisce HTTP 502, fase `attachment`, ID del record
conservato e un token di retry firmato. Il frontend ricorda il token per quel
File; il retry salva l'allegato sullo stesso record. Il backend verifica che
record, dati offerta, filename e hash del PDF coincidano con l'operazione
originale. Non cancella record e non espone credenziali.

Il recupero offerte Airtable già legge tutti i campi: non è necessaria una
seconda ricerca. `confronta_offerte()` aggiunge soltanto `cte`, con filename e
URL HTTPS del primo attachment PDF valido presente nel record, oppure null.
Ogni card con CTE mostra il pulsante in basso. Al click viene aperto un dialog
con iframe, chiusura tramite pulsante/Escape e link alla nuova scheda.

## Limiti

- L'upload diretto Airtable è limitato a 5 MB per file. Oltre 5.000.000 byte,
  l'offerta viene conservata, ma il frontend segnala il fallimento attachment.
  Non sono stati aggiunti storage esterni per aggirare il limite.
- Gli URL attachment Airtable sono temporanei (almeno due ore secondo la
  documentazione); vengono recuperati nuovamente a ogni confronto, senza
  memorizzarli in un database applicativo. Dopo la scadenza ripeti il confronto.
- L'embedding dipende dal browser e dalle intestazioni dell'attachment:
  il link "Apri PDF in una nuova scheda" è sempre disponibile.
- Un'interruzione di rete prima della risposta del salvataggio può lasciare un
  record già creato senza che il browser ne conosca l'ID. In tal caso verifica
  Airtable prima di riprovare. I retry con risposta attachment fallita riusano
  il record; non è stata introdotta una transazione o una coda persistente.
- Questo export e i suoi test sono già ignorati da Git nella configurazione
  preesistente. Non sono stati modificati `.gitignore`, build o sorgenti esterni
  alla cartella, come richiesto. Una nuova build dai sorgenti Next.js originali
  sostituisce l'export e rimuove questa modifica: conserva/carica questa cartella
  aggiornata. Per versionarla con Git è necessario aggiungerla esplicitamente
  con `git add -f frontend/netlify-upload` prima del commit scelto dall'utente.

## File dell'export modificati

- `cte-attachments.js`: trasporto PDF, retry per File e visualizzatore.
- `_next/static/chunks/app/cte/page-8787b378dc14cfed.js`: salvataggi singolo e
  massivo passano il loro PDF; l'errore conserva l'ID Airtable.
- `_next/static/chunks/app/bollette/page-92633f78e3ca860c.js`: pulsante CTE per card.
- HTML e payload di navigazione sotto `cte/` e `bollette/`: riferimenti ai
  nuovi hash degli asset, per non riutilizzare i vecchi file in cache.
- `tests/`: test browser mirati a queste funzionalità.

## Verifiche

Dal repository: `python -m unittest discover -s tests -v` (20 test).
Da `frontend`: `npx playwright test --config
netlify-upload/tests/attachments.playwright.config.ts` (3 test).
I test dei provider usano mock; non sono stati creati record reali Airtable.
La regressione confronta tutti i valori con `cbbd10e:confronto.py`.
Non sono state aggiunte dipendenze.

Fonti: https://pyairtable.readthedocs.io/en/stable/api.html#pyairtable.Table.upload_attachment
https://airtable.com/developers/web/api/upload-attachment
https://support.airtable.com/articles/9671148410-airtable-attachment-url-behavior
