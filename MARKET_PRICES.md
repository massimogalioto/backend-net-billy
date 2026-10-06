# Prezzi mercato PostgreSQL

Il confronto importa `market_price_service.get_prezzo_mercato`, senza leggere
PUN/PSV da Airtable. Restano invariati import GME, cron PUN e formule economiche.

- **PUN:** media mensile ponderata `SUM(value_eur_kwh * observation_count) / SUM(observation_count)` dei giorni disponibili precedenti alla data di confronto. Il giorno di confronto e quelli successivi sono esclusi. Se il mese non ha righe utilizzabili, cerca solo il mese precedente. Se una riga inclusa ha conteggio NULL/non valido o prezzo mancante, restituisce un errore di reimportazione senza ripiegare su una media non pesata o su un altro mese. `disp` mantiene la media dei valori giornalieri, considerando NULL come zero.
- **PSV:** cerca la riga `market = 'PSV'` datata al primo giorno del mese della
  data di confronto, poi solo quella del mese precedente. Il valore base è
  `value_eur_smc`; `disp` è il CCR, restituito separatamente (NULL equivale a zero).
- Se mancano entrambi i mesi, il reader solleva un errore che identifica i mesi.
  Le offerte variabili continuano a sommare `disp` una sola volta.

## Verifica e migration Railway

Lo schema live non è verificabile senza `DATABASE_URL`. Nel repository non è
presente il DDL originario di `market_prices`; il codice dell'import PUN si
aspetta già `UNIQUE (market, reference_date)` e la colonna `disp`.

In Railway eseguire prima le SELECT di `market_prices_psv.sql` e verificare:

1. `value_eur_smc` esiste ed è numerica;
2. `value_eur_mwh` e `value_eur_kwh` sono nullable;
3. esiste il vincolo/indice univoco `(market, reference_date)`;
4. eventuali CHECK di `market` ammettono anche `PSV`.

Se la colonna Smc manca o i campi PUN sono NOT NULL, eseguire l'ALTER nello
stesso file. La migration non è stata applicata automaticamente. Se un CHECK
ammette solo PUN o manca il vincolo univoco, correggere il vincolo rilevato
prima di utilizzare il PSV; il suo nome/schema non è deducibile dal codice.

## Conteggi orari PUN

Eseguire manualmente su Railway `market_prices_observation_count.sql` PRIMA
del deploy del nuovo importer/reader. L'ALTER aggiunge `observation_count INTEGER NULL`;
nessuna migration viene eseguita dall'applicazione.

Il calcolo GME passa all'UPSERT il numero effettivo delle osservazioni validate
(23/24/25), aggiornandolo anche sui record gi? esistenti. Non viene inventato 24
per i record storici. Dopo la migration, reimportare dal GME i giorni necessari
con conteggio assente usando il comando esistente, per esempio:

```text
python import_market_prices.py --date 2026-10-01
```

Ripetere per i giorni segnalati dalla SELECT diagnostica della migration.
Il conteggio non viene richiesto o utilizzato per il PSV.

## API

`GET /market-prices-psv` restituisce `previous` e `current` con `mese`,
`value_eur_smc`, `disp`, `totale`; per un mese assente i valori sono NULL.
Il mese corrente è determinato sul backend nel fuso Europe/Rome.

`POST /market-prices-psv` accetta il mese corrente o precedente, con valori finiti
non negativi. Esempio per ottobre 2026:

```json
{"mese":"2026-10","value_eur_smc":0.800,"disp":0.035}
```

L'UPSERT usa `(market, reference_date)`, salva `market = 'PSV'`, data al primo
giorno e `source = 'MANUAL'`, senza valorizzare le colonne MWh/kWh.
La risposta indica `action: insert` oppure `action: update`.

Il pannello nella pagina bollette mostra i due mesi e consente inserimento/update
del corrente e del precedente. Sono aggiornati sia il frontend Next sia l'esportazione Netlify;
il pannello statico è isolato in `market-prices.js` e non modifica i bundle CTE.

## Test

```text
python -m unittest discover -s tests -p test_market_price_reader.py -v
python -m unittest discover -s tests -p test_market_price_import.py -v
python -m unittest discover -s tests -p test_pun_weighted_price.py -v
python -m unittest discover -s tests -p test_comparison_economics.py -v
cd frontend
npm run typecheck
node netlify-upload/tests/market-prices.test.mjs
```

Il test browser usa Playwright con risposte simulate; se necessario impostare
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` al browser Chromium/Chrome installato.
I test database verificano query e contratti con connessioni simulate: non
provano la migration né l'UPSERT sul database Railway reale.
