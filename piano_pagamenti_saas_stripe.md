# Piano del sistema pagamenti SaaS

**Modello scelto:** abbonamento fisso con un numero di analisi incluse e addebito delle analisi eccedenti  
**Stato:** specifica funzionale e tecnica da riutilizzare quando verrà sviluppata l'interfaccia pagamenti  
**Ultimo aggiornamento:** 9 ottobre 2026

---

## 1. Obiettivo

Realizzare un sistema di pagamento semplice per il cliente e controllabile dall'amministrazione, composto da:

1. un canone ricorrente mensile o annuale;
2. un numero prestabilito di analisi incluse in ogni periodo di fatturazione;
3. un prezzo unitario per ogni analisi aggiuntiva;
4. un'unica fattura periodica contenente canone ed eventuali eccedenze;
5. gestione automatica di rinnovi, pagamenti falliti, annullamenti e aggiornamento della carta;
6. emissione della fattura fiscale tramite Fatture in Cloud, mantenendo Stripe come sistema di incasso.

Il principio fondamentale è separare tre responsabilità:

- **l'applicazione** stabilisce chi può usare il servizio e registra ogni analisi;
- **Stripe** gestisce abbonamenti, metodo di pagamento, incassi e stato economico;
- **Fatture in Cloud** emette e conserva il documento fiscale secondo la configurazione concordata con il commercialista.

---

## 2. Formula commerciale

### 2.1 Piano iniziale

| Elemento | Valore da decidere |
| --- | --- |
| Nome del piano | `[es. Piano Professional]` |
| Canone mensile | `[€ X + IVA/mese]` |
| Analisi incluse | `[N analisi per mese]` |
| Costo analisi eccedente | `[€ Y + IVA per analisi]` |
| Periodo di prova | `[nessuno / N giorni]` |
| Limite massimo di spesa | `[nessuno / soglia concordata]` |
| Piano annuale | `[da introdurre subito / in una fase successiva]` |
| Clienti ammessi | `[solo B2B / anche consumatori]` |

### 2.2 Regola consigliata

Il canone si paga all'inizio del periodo; le analisi extra maturate nel periodo si addebitano sulla fattura successiva o alla chiusura del periodo, secondo il meccanismo di fatturazione a consumo scelto in fase di implementazione.

Non conviene effettuare una transazione sulla carta per ogni singola analisi extra: moltiplicherebbe commissioni, contestazioni e complessità. È preferibile accumulare le eccedenze e inserirle come riga separata nella fattura periodica.

Esempio puramente illustrativo:

- canone mensile: €29;
- 50 analisi incluse;
- 12 analisi extra a €0,50;
- totale imponibile del periodo: €29 + €6 = €35, oltre IVA se applicabile.

Gli importi dell'esempio non costituiscono una decisione commerciale.

### 2.3 Possibili evoluzioni

Solo dopo aver validato il primo piano si potranno aggiungere:

- piano Base, Professional ed Enterprise;
- pagamento annuale scontato;
- pacchetti prepagati di analisi;
- più utenti per organizzazione;
- limiti personalizzati e contratti Enterprise;
- coupon, prova gratuita e promozioni.

Per la prima versione è preferibile un solo piano: meno casi speciali, meno errori e dati commerciali più facili da interpretare.

---

## 3. Definizione esatta di “analisi”

Prima di scrivere il codice deve essere stabilito che cosa genera consumo. La regola consigliata è:

> Un'analisi viene conteggiata solo quando il sistema completa con successo un'elaborazione richiesta dal cliente e rende disponibile un risultato utilizzabile.

### 3.1 Eventi da conteggiare

- nuova analisi completata correttamente;
- nuova elaborazione intenzionale di un documento già analizzato, se richiesta dall'utente;
- eventuale analisi avviata via API da un cliente, se prevista dal contratto.

### 3.2 Eventi da non conteggiare

- caricamento rifiutato prima dell'elaborazione;
- formato non riconosciuto;
- errore interno o timeout;
- risultato non prodotto;
- nuovo tentativo automatico della stessa richiesta;
- doppio clic o richiesta duplicata;
- rielaborazione eseguita dall'assistenza per correggere un problema del sistema;
- test interni e account amministrativi.

### 3.3 Identificativo univoco

Ogni tentativo deve possedere un `analysis_id` univoco. Lo stesso `analysis_id` non può generare due consumi né due addebiti. Questa è la protezione principale contro doppi conteggi dovuti a retry, webhook duplicati o problemi di rete.

### 3.4 Momento del conteggio

L'unità si registra dopo il completamento tecnico dell'analisi e prima di restituire definitivamente il risultato al frontend, usando una transazione applicativa. Se la registrazione fallisce, il sistema deve poter recuperare l'operazione senza duplicarla.

---

## 4. Esperienza completa del cliente

### 4.1 Registrazione

1. Il cliente crea l'account nell'applicazione.
2. Conferma l'indirizzo email.
3. Indica se è azienda/professionista o consumatore, se entrambi sono ammessi.
4. Inserisce i dati necessari alla fatturazione:
   - nome o ragione sociale;
   - indirizzo;
   - Paese;
   - codice fiscale e/o partita IVA;
   - codice destinatario o PEC, quando richiesto;
   - email amministrativa.
5. Accetta condizioni del servizio, informativa privacy e condizioni economiche con versione e data registrate.

L'account in questa fase esiste, ma le funzioni a pagamento rimangono bloccate.

### 4.2 Scelta del piano e Checkout

1. Il frontend mostra chiaramente canone, analisi incluse, prezzo delle eccedenze, periodicità e modalità di recesso.
2. Il backend crea o recupera il cliente Stripe associato all'account interno.
3. Il backend crea una sessione di Stripe Checkout in modalità abbonamento.
4. Il browser viene indirizzato alla pagina ospitata da Stripe.
5. Stripe raccoglie i dati della carta e gestisce eventuale autenticazione 3D Secure/SCA.
6. Il cliente torna alla pagina di esito dell'applicazione.

La pagina di ritorno non deve attivare da sola l'abbonamento: l'applicazione aspetta la conferma firmata inviata da Stripe tramite webhook.

### 4.3 Attivazione

Quando il backend riceve la conferma del primo pagamento:

- collega `stripe_customer_id` e `stripe_subscription_id` all'account;
- registra il periodo corrente;
- assegna le analisi incluse;
- imposta lo stato interno su `active`;
- abilita le funzioni a pagamento;
- avvia il processo di emissione della fattura fiscale;
- invia l'email di conferma.

### 4.4 Utilizzo durante il mese

Per ogni analisi riuscita:

1. viene scritto un evento immutabile nel registro consumi;
2. il contatore del periodo viene aggiornato;
3. l'interfaccia mostra:
   - analisi incluse usate;
   - analisi incluse residue;
   - analisi extra già maturate;
   - stima del prossimo addebito;
4. al superamento della quota inclusa, il cliente riceve un avviso chiaro prima o immediatamente dopo la prima eccedenza, secondo la scelta commerciale;
5. il consumo eccedente viene comunicato al sistema di billing in modo idempotente.

### 4.5 Rinnovo

Alla chiusura del periodo:

- si determina il consumo definitivo;
- si calcolano le analisi eccedenti;
- Stripe genera l'addebito periodico secondo la configurazione attiva;
- dopo il pagamento confermato parte un nuovo periodo con una nuova quota inclusa;
- le analisi non utilizzate scadono, salvo diversa scelta commerciale esplicitata nel contratto;
- viene emessa la fattura fiscale del nuovo addebito.

### 4.6 Area “Abbonamento e fatturazione”

L'utente deve poter:

- vedere piano e stato dell'abbonamento;
- consultare consumo corrente e stima della prossima fattura;
- aggiornare il metodo di pagamento;
- scaricare ricevute/documenti messi a disposizione;
- modificare i dati di fatturazione;
- annullare il rinnovo;
- vedere la data effettiva di cessazione;
- riattivare un abbonamento ancora nel periodo pagato.

Per carta, fatture Stripe e cancellazione si userà preferibilmente lo Stripe Customer Portal, evitando di sviluppare e mantenere schermate sensibili non necessarie.

---

## 5. Regole di accesso al servizio

Lo stato dell'accesso non deve dipendere da ciò che il frontend mostra, ma dallo stato salvato e aggiornato dal backend.

| Stato interno | Accesso consigliato |
| --- | --- |
| `pending_checkout` | Nessun accesso alle funzioni a pagamento |
| `active` | Accesso completo nei limiti del piano |
| `trialing` | Accesso previsto dalla prova |
| `past_due` | Breve periodo di tolleranza e avvisi |
| `payment_action_required` | Accesso limitato; richiesta autenticazione/pagamento |
| `suspended` | Nuove analisi bloccate; dati consultabili |
| `cancel_at_period_end` | Accesso fino alla fine del periodo già pagato |
| `canceled` | Nessuna nuova analisi; conservazione/esportazione secondo contratto |
| `refunded` | Gestione manuale o sospensione secondo il caso |

La durata dell'eventuale periodo di tolleranza deve essere decisa prima del lancio, ad esempio 3, 5 o 7 giorni.

---

## 6. Architettura logica

### 6.1 Componenti

- **Frontend SaaS**: pagine piano, Checkout, consumo e fatturazione.
- **Backend applicativo**: autorizzazioni, creazione sessioni Stripe, registro consumi e webhook.
- **Database PostgreSQL**: fonte operativa per utenti, abbonamenti e analisi.
- **Stripe Billing/Checkout**: pagamento ricorrente e riscossione.
- **Motore di billing a consumo corrente supportato da Stripe**: valorizzazione delle eccedenze.
- **Fatture in Cloud**: documento fiscale e invio elettronico, se applicabile.
- **Servizio email**: conferme, soglie, pagamento fallito e cancellazione.

### 6.2 Fonti autorevoli

- Il database interno è la fonte autorevole per **quali analisi sono state effettivamente eseguite**.
- Stripe è la fonte autorevole per **pagamenti, fatture Stripe e stato economico dell'abbonamento**.
- Fatture in Cloud è la fonte autorevole per **documenti fiscali emessi e loro stato**.

Non bisogna usare il semplice contatore mostrato nel browser come fonte per la fatturazione.

### 6.3 Modello ibrido consigliato

Per una nuova integrazione, la documentazione Stripe aggiornata indica Metronome come piattaforma principale per il billing a consumo, anche quando si aggiunge una componente variabile a un abbonamento fisso. Il progetto dovrà quindi verificare, al momento dell'implementazione, la soluzione Stripe corrente e scegliere tra:

1. **Stripe + Metronome**, scelta indicata dalla documentazione attuale per nuove integrazioni usage-based;
2. **funzionalità native Stripe Billing allora disponibili**, se nel frattempo il prodotto viene semplificato o modificato;
3. **calcolo interno dell'eccedenza e riga aggregata in fattura**, solo se accuratamente progettato e più conveniente per il volume previsto.

La specifica commerciale non cambia: una sola fattura con canone più eccedenze. Non bisogna vincolare oggi il codice a un'API destinata a cambiare prima dell'implementazione.

---

## 7. Struttura dati concettuale

### 7.1 `billing_customers`

- `user_id` o `organization_id`;
- `stripe_customer_id`;
- tipo cliente B2B/B2C;
- dati fiscali essenziali;
- `fatture_in_cloud_entity_id`, se utilizzato;
- date di creazione e aggiornamento.

### 7.2 `subscriptions`

- identificativo interno;
- cliente interno;
- `stripe_subscription_id`;
- codice del piano;
- stato interno;
- inizio e fine periodo corrente;
- data di cancellazione programmata;
- quantità inclusa;
- prezzo extra applicato e relativa versione;
- valuta;
- timestamp ultimo evento Stripe elaborato.

I valori economici applicati al cliente vanno storicizzati: modificare il listino futuro non deve alterare retroattivamente un periodo già iniziato.

### 7.3 `usage_events`

- `analysis_id` univoco;
- cliente/organizzazione;
- abbonamento e periodo;
- data e ora;
- tipo di analisi;
- quantità, normalmente `1`;
- stato: `recorded`, `reported`, `reversed`, `ignored`;
- motivo di un eventuale storno;
- identificativo/idempotency key inviato al billing;
- timestamp di invio e risposta.

Questa tabella è un registro append-only: le correzioni si fanno con un evento di storno, non cancellando silenziosamente la riga originale.

### 7.4 `billing_periods`

- cliente e abbonamento;
- inizio/fine periodo;
- quota inclusa;
- consumo totale;
- consumo eccedente;
- importo stimato e definitivo;
- stato di chiusura;
- fattura Stripe collegata;
- fattura fiscale collegata.

### 7.5 `webhook_events`

- provider;
- event ID univoco;
- tipo evento;
- data ricezione;
- firma verificata;
- stato elaborazione;
- numero tentativi;
- errore eventuale.

Serve a rendere l'elaborazione idempotente e diagnosticabile.

### 7.6 `fiscal_documents`

- pagamento/fattura Stripe di origine;
- documento Fatture in Cloud;
- imponibile, IVA e totale;
- stato di creazione/invio;
- eventuale nota di credito;
- ultimo errore e tentativi.

---

## 8. Configurazione iniziale di Stripe

1. Creare l'account Stripe intestato al soggetto che vende il SaaS.
2. Completare verifica aziendale, titolare effettivo, documento, conto corrente e dati fiscali.
3. Attivare prima la modalità test.
4. Creare il prodotto SaaS nel catalogo.
5. Creare il prezzo ricorrente del canone.
6. Configurare la componente a consumo con lo strumento Stripe corrente scelto.
7. Configurare valuta, IVA/tassazione e descrizioni mostrate al cliente.
8. Configurare Stripe Checkout.
9. Configurare il Customer Portal.
10. Configurare le regole di sollecito e nuovi tentativi di pagamento.
11. Registrare l'endpoint webhook HTTPS del backend.
12. Salvare le chiavi e il segreto webhook solo nelle variabili protette del backend.
13. Definire ruoli e autenticazione a due fattori per gli operatori Stripe.
14. Completare tutti i test prima di attivare la modalità live.

Le chiavi segrete Stripe non devono mai entrare nel frontend, nel repository Git o nei log.

---

## 9. Funzioni backend da realizzare

Nomi indicativi, da adattare al progetto:

- `POST /billing/checkout-session`  
  Crea la sessione Checkout per l'utente autenticato.

- `POST /billing/customer-portal`  
  Crea un accesso temporaneo al Customer Portal.

- `GET /billing/subscription`  
  Restituisce piano, stato, rinnovo e cancellazione.

- `GET /billing/usage`  
  Restituisce quota, consumo, extra e stima del periodo.

- `POST /billing/webhooks/stripe`  
  Riceve e verifica gli eventi Stripe.

- `POST /billing/webhooks/fatture-in-cloud`  
  Riceve eventuali aggiornamenti sui documenti fiscali.

- servizio interno `record_successful_analysis(analysis_id, customer_id)`  
  Registra il consumo una sola volta.

- job `report_pending_usage`  
  Comunica gli eventi non ancora inviati al motore di billing e gestisce i retry.

- job `reconcile_billing`  
  Confronta periodicamente database, Stripe e documenti fiscali, segnalando differenze.

Il frontend non deve poter inviare direttamente a Stripe il numero di analisi consumate.

---

## 10. Webhook Stripe minimi

L'elenco esatto va verificato sulla versione API adottata. Concettualmente servono eventi per:

- Checkout completato;
- sottoscrizione creata o aggiornata;
- sottoscrizione cancellata;
- fattura creata/finalizzata;
- fattura pagata;
- pagamento fattura fallito;
- pagamento che richiede un'azione del cliente;
- rimborso;
- contestazione/chargeback, se rilevante.

### Regole obbligatorie del gestore webhook

1. verificare la firma Stripe sul corpo originale della richiesta;
2. rifiutare firme non valide;
3. registrare l'event ID prima dell'elaborazione;
4. ignorare in sicurezza gli eventi già elaborati;
5. non presupporre l'ordine di arrivo;
6. recuperare da Stripe l'oggetto corrente quando lo stato è ambiguo;
7. rispondere rapidamente e delegare le operazioni lente a una coda/job;
8. registrare errori senza salvare dati di carta o segreti;
9. prevedere retry e riconciliazione.

I webhook sono indispensabili perché molti eventi di pagamento sono asincroni. Non è sufficiente fidarsi del redirect del browser dopo Checkout.

---

## 11. Fatturazione con Fatture in Cloud

### 11.1 Flusso consigliato

1. Stripe conferma il pagamento della fattura.
2. Il backend salva l'evento in modo idempotente.
3. Viene costruito il documento fiscale con righe separate:
   - canone SaaS del periodo;
   - analisi eccedenti, quantità e prezzo unitario;
   - eventuali sconti o rettifiche.
4. Il backend crea il documento tramite API Fatture in Cloud.
5. Se previsto, il documento viene inviato al Sistema di Interscambio.
6. L'identificativo e lo stato sono salvati in `fiscal_documents`.
7. Gli aggiornamenti successivi arrivano via webhook.

### 11.2 Regole operative

- non creare due documenti per lo stesso `stripe_invoice_id`;
- non considerare la ricevuta Stripe come sostituto automatico della fattura fiscale italiana;
- concordare con il commercialista momento di emissione, numerazione, IVA, natura dell'operazione e gestione B2B/B2C/estero;
- emettere nota di credito quando necessaria, non cancellare semplicemente una fattura già emessa;
- avere una coda di documenti da verificare quando l'API fiscale non è disponibile;
- mantenere un pulsante amministrativo di reinvio controllato.

Fatture in Cloud espone API per creare documenti emessi e webhook per aggiornamenti; la mappatura fiscale definitiva va comunque validata con il commercialista.

---

## 12. Pagamenti falliti e recupero credito

Flusso suggerito:

1. Stripe tenta l'addebito.
2. Se fallisce, l'app imposta `past_due` e invia un avviso.
3. Il cliente viene indirizzato al Customer Portal per aggiornare la carta o completare l'autenticazione.
4. Durante il periodo di tolleranza può consultare i dati; la possibilità di avviare nuove analisi dipende dalla politica scelta.
5. Stripe esegue i nuovi tentativi configurati.
6. Se il pagamento riesce, l'accesso torna automaticamente `active`.
7. Se tutti i tentativi falliscono, l'abbonamento viene sospeso o cancellato secondo la regola commerciale.

Da decidere prima del lancio:

- durata della tolleranza;
- numero e cadenza dei tentativi;
- accesso consentito durante `past_due`;
- gestione dell'eccedenza già maturata;
- quando affidare il caso a un operatore.

---

## 13. Cancellazioni, cambi piano e rimborsi

### 13.1 Cancellazione ordinaria

Regola consigliata: cancellazione alla fine del periodo già pagato.

- il rinnovo viene disattivato;
- il servizio resta disponibile fino alla data indicata;
- il cliente vede chiaramente la data di cessazione;
- alla chiusura vengono comunque fatturate le eccedenze maturate e contrattualmente dovute;
- dopo la cessazione le nuove analisi sono bloccate.

### 13.2 Cancellazione immediata

Riservata ad amministrazione, frode, violazioni o casi contrattuali specifici. Devono essere definite le conseguenze su rimborsi, crediti ed eccedenze.

### 13.3 Cambio piano

Per la prima versione può essere gestito dall'assistenza. Quando verranno introdotti più piani, si deciderà se applicare il cambio:

- subito, con conguaglio;
- dal rinnovo successivo, soluzione più semplice;
- con riallineamento della quota inclusa in proporzione.

### 13.4 Rimborso

Ogni rimborso deve collegare:

- operazione Stripe;
- motivazione;
- utente amministratore;
- eventuale nota di credito;
- rettifica del registro utilizzi, solo se necessaria.

---

## 14. Sicurezza e protezione dei dati

- Usare Checkout e Customer Portal ospitati da Stripe per ridurre la gestione diretta dei dati carta.
- Non memorizzare PAN, CVC o dati completi della carta.
- Conservare solo identificativi Stripe e dati strettamente necessari.
- Verificare sempre autenticazione e appartenenza dell'utente prima di creare sessioni Checkout/Portal.
- Usare HTTPS in produzione.
- Proteggere chiavi Stripe, segreti webhook e token Fatture in Cloud come secret di ambiente.
- Separare completamente chiavi test e live.
- Applicare idempotenza alle richieste che creano sessioni, consumi, fatture e rimborsi.
- Tenere audit log delle azioni amministrative.
- Limitare nei log dati personali, token e payload sensibili.
- Definire tempi di conservazione, esportazione e cancellazione dei dati.
- Aggiornare informativa privacy e registro dei trattamenti; verificare ruoli e accordi con i fornitori.

---

## 15. Aspetti contrattuali e fiscali da validare

Questo documento definisce il sistema, non sostituisce il parere del commercialista o del consulente legale. Prima della vendita devono essere approvati almeno:

- soggetto giuridico che vende il SaaS e incassa;
- regime IVA per clienti italiani, UE ed extra-UE;
- dati obbligatori in fattura;
- trattamento di privati, imprese e professionisti;
- condizioni generali del servizio;
- rinnovo automatico, durata e recesso;
- descrizione inequivocabile di quota inclusa ed eccedenze;
- momento in cui un'analisi diventa addebitabile;
- eventuale diritto di ripensamento per consumatori e relativo flusso;
- consenso all'avvio immediato del servizio, quando necessario;
- politica rimborsi;
- sospensione per mancato pagamento;
- utilizzo accettabile e divieto di abuso;
- privacy, cookie e trattamento dei documenti caricati;
- tempi di conservazione dei risultati dopo la cessazione;
- procedura reclami e contatti dell'assistenza.

Se la prima versione è destinata esclusivamente ad aziende e professionisti, va impedita o disciplinata coerentemente la registrazione di consumatori. Non basta scrivere “B2B” nel listino se il flusso accetta chiunque senza controlli.

---

## 16. Interfacce da progettare

### Pagine pubbliche

- prezzi;
- confronto sintetico del piano;
- FAQ su quota ed eccedenze;
- condizioni del servizio;
- privacy.

### Pagine cliente

- scelta piano;
- dati di fatturazione;
- avvio Checkout;
- pagamento riuscito/in elaborazione/non riuscito;
- riepilogo abbonamento;
- barra consumo;
- storico periodi e addebiti;
- collegamento al Customer Portal;
- conferma cancellazione.

### Area amministrativa

- ricerca cliente;
- stato Stripe e stato interno;
- consumo dettagliato e aggregato;
- eventi non inviati;
- webhook falliti;
- documenti fiscali da emettere o in errore;
- azioni controllate: reinvio, storno, sospensione, rimborso;
- report di riconciliazione.

### Messaggi essenziali al cliente

- “Hai utilizzato X di N analisi incluse.”
- “Hai maturato X analisi aggiuntive per un costo stimato di €Y.”
- “La stima può variare fino alla chiusura del periodo.”
- “Il prossimo rinnovo è previsto il …”
- “Il pagamento non è riuscito: aggiorna il metodo di pagamento.”
- “Il rinnovo è annullato; il servizio resterà disponibile fino al …”

---

## 17. Notifiche consigliate

- benvenuto e attivazione;
- raggiungimento dell'80% della quota;
- esaurimento della quota inclusa;
- prima analisi extra del periodo;
- eventuale soglia economica scelta dal cliente;
- fattura/addebito imminente con stima, se opportuno;
- pagamento riuscito;
- pagamento fallito;
- carta in scadenza, se il servizio lo consente;
- cancellazione programmata;
- cessazione avvenuta.

Per evitare sorprese, è utile offrire una soglia di avviso e, in futuro, un limite di spesa o un blocco volontario delle eccedenze.

---

## 18. Test obbligatori

### Checkout e abbonamento

- primo pagamento riuscito;
- carta rifiutata;
- autenticazione 3D Secure;
- utente che chiude Checkout;
- doppio clic sul pulsante di acquisto;
- webhook ricevuto più volte;
- redirect riuscito ma webhook ritardato.

### Consumi

- analisi inclusa;
- prima analisi eccedente;
- più analisi contemporanee;
- retry della stessa analisi;
- errore dopo l'avvio;
- storno amministrativo;
- analisi a cavallo del cambio periodo;
- fuso orario e mesi di diversa durata.

### Rinnovi

- rinnovo senza extra;
- rinnovo con extra;
- pagamento fallito e successivamente riuscito;
- cancellazione a fine periodo;
- cambio di carta;
- rimborso e nota di credito.

### Integrazione fiscale

- cliente italiano con partita IVA;
- consumatore, se ammesso;
- dati fiscali incompleti;
- API Fatture in Cloud indisponibile;
- evento duplicato;
- fattura rifiutata o da correggere;
- riconciliazione tra imponibile Stripe e documento fiscale.

### Sicurezza

- firma webhook errata;
- utente che tenta di aprire il Portal di un altro cliente;
- chiavi test usate per errore in produzione;
- replay di richieste;
- permessi amministrativi.

Stripe mette a disposizione modalità test e strumenti per simulare gli eventi. Il passaggio live deve avvenire solo dopo una prova completa dell'intero ciclo, inclusa la fatturazione.

---

## 19. Monitoraggio e riconciliazione

Il sistema deve controllare almeno ogni giorno:

- abbonamenti Stripe non allineati con il database;
- eventi consumo non comunicati;
- webhook in errore;
- pagamenti riusciti senza fattura fiscale;
- fatture fiscali senza pagamento collegato;
- importi diversi tra periodo interno, Stripe e documento fiscale;
- clienti attivi senza abbonamento valido;
- clienti paganti con accesso erroneamente sospeso.

Va previsto un report mensile con:

- ricavi da canone;
- ricavi da eccedenze;
- analisi incluse utilizzate;
- analisi extra;
- tasso di fallimento pagamenti;
- cancellazioni;
- rimborsi e contestazioni;
- costo medio dell'AI per cliente e margine lordo stimato.

Il costo per analisi extra deve essere confrontato con il costo reale di elaborazione AI, storage, assistenza e commissioni. Un prezzo “sembra conveniente” non basta: va verificato il margine sui dati reali.

---

## 20. Fasi di realizzazione

### Fase 1 — Decisioni commerciali e fiscali

- fissare canone, quota inclusa e prezzo extra;
- scegliere mensile/annuale;
- decidere B2B o B2B+B2C;
- definire tolleranza, cancellazione e rimborsi;
- validare IVA e fatturazione con il commercialista;
- approvare condizioni e privacy.

### Fase 2 — Fondamenta backend

- aggiungere tabelle billing;
- registrare le analisi con idempotenza;
- creare contatore e periodi;
- implementare autorizzazioni basate sullo stato;
- creare audit e riconciliazione.

### Fase 3 — Stripe in modalità test

- account, prodotto e prezzi;
- Checkout;
- Customer Portal;
- webhook;
- ciclo rinnovo e pagamenti falliti;
- componente a consumo corrente raccomandata da Stripe.

### Fase 4 — Fatture in Cloud

- autorizzazione API;
- anagrafiche;
- creazione documento;
- invio elettronico se previsto;
- webhook e riconciliazione;
- note di credito.

### Fase 5 — Interfaccia

- pagina prezzi;
- acquisto;
- esito pagamento;
- consumo e stima;
- gestione abbonamento;
- messaggi e notifiche.

### Fase 6 — Collaudo

- test automatici;
- test Stripe end-to-end;
- prova con account interno;
- controllo fattura con commercialista;
- verifica di sicurezza;
- simulazione rinnovo, insoluto e cancellazione.

### Fase 7 — Produzione controllata

- passaggio alle chiavi live;
- primo gruppo ristretto di clienti;
- monitoraggio quotidiano;
- confronto dei margini reali;
- correzione dei casi limite prima del lancio generale.

---

## 21. Criteri per considerare il modulo completato

Il sistema è pronto quando:

- nessun dato carta transita o viene memorizzato dall'applicazione;
- un pagamento confermato abilita il cliente una sola volta;
- un'analisi riuscita viene conteggiata una sola volta;
- un errore tecnico non consuma la quota;
- quota ed eccedenze mostrate coincidono con il registro interno;
- il rinnovo produce l'importo previsto;
- webhook duplicati o fuori ordine non alterano il risultato;
- il pagamento fallito modifica correttamente l'accesso;
- la cancellazione mantiene l'accesso fino alla data pattuita;
- ogni pagamento ha un documento fiscale o una segnalazione di errore;
- esiste una riconciliazione automatica e una procedura manuale controllata;
- il cliente vede sempre prezzo, consumo e prossima scadenza in modo comprensibile.

---

## 22. Decisioni ancora aperte

Compilare questa sezione prima di iniziare lo sviluppo:

- [ ] prezzo del canone;
- [ ] analisi incluse;
- [ ] prezzo unitario extra;
- [ ] IVA inclusa o esclusa nel prezzo visualizzato;
- [ ] solo mensile o anche annuale;
- [ ] prova gratuita;
- [ ] solo B2B o anche B2C;
- [ ] durata della tolleranza per insoluto;
- [ ] accesso durante `past_due`;
- [ ] cancellazione a fine periodo o immediata;
- [ ] eventuale limite/blocco delle eccedenze;
- [ ] scadenza o riporto delle analisi non usate;
- [ ] momento fiscale di emissione della fattura;
- [ ] gestione clienti esteri;
- [ ] strumento Stripe definitivo per il consumo, da verificare all'implementazione;
- [ ] contenuto definitivo delle condizioni di servizio.

---

## 23. Riferimenti ufficiali da ricontrollare in fase di sviluppo

- [Stripe — funzionamento degli abbonamenti](https://docs.stripe.com/billing/subscriptions/overview)
- [Stripe — Checkout](https://docs.stripe.com/payments/checkout)
- [Stripe — Customer Portal](https://docs.stripe.com/customer-management)
- [Stripe — webhook](https://docs.stripe.com/webhooks)
- [Stripe — billing a consumo e indicazione per nuove integrazioni](https://docs.stripe.com/billing/subscriptions/usage-based/implementation-guide)
- [Stripe — Strong Customer Authentication](https://docs.stripe.com/strong-customer-authentication)
- [Fatture in Cloud — creazione fattura tramite API](https://developers.fattureincloud.it/docs/guides/invoice-creation/)
- [Fatture in Cloud — gestione fattura elettronica](https://developers.fattureincloud.it/docs/guides/e-invoice-management/)
- [Fatture in Cloud — tipi di notifiche webhook](https://developers.fattureincloud.it/docs/webhooks/notification-types/)

Questi riferimenti sono aggiornati alla data del documento. API, prodotti e regole fiscali devono essere ricontrollati immediatamente prima dell'implementazione.

---

## 24. Decisione sintetica da conservare

> Il SaaS adotterà un abbonamento ricorrente con una quota mensile di analisi incluse. Le analisi completate oltre la quota saranno conteggiate singolarmente ma aggregate nell'addebito periodico. Il database interno conserverà il registro immutabile dei consumi; Stripe gestirà abbonamento e pagamento; Fatture in Cloud gestirà la fattura fiscale. L'interfaccia mostrerà in tempo reale quota, eccedenze e stima del prossimo addebito. Ogni integrazione sarà idempotente, guidata dai webhook e sottoposta a riconciliazione.
