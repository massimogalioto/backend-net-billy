# NET BILLY — preparazione manuale di staging

Questi file non sono stati eseguiti contro Railway. Non configurano Railway,
Stripe, storage o applicazione. Nessun dump incluso. Non ricostruiscono lo schema.

## Risultato dell'analisi locale

`database_service.py` usa psycopg e `DATABASE_URL`; non esiste un ORM o una
migration iniziale completa. Le query usano almeno otto tabelle:
`tenants`, `users`, `plans`, `subscriptions`, `cte_offers`, `market_prices`,
`auth_sessions`, `comparison_events`. Le ultime due hanno migration in
`migrations/`; gli SQL in radice aggiungono colonne potenza CTE e PUN/PSV.
Non applicare questi SQL in aggiunta al dump: il dump dello schema reale ne
contiene gia gli effetti, se presenti in produzione.

`create_test_user.py` crea/aggiorna dati usando `DATABASE_URL`, non inizializza
lo schema e non deve essere eseguito in questa procedura. Non esiste un runner
di migration individuato nel repository. Le query presuppongono UUID/default,
vincoli di stato, relazioni e unicita del mercato/data, ma il codice non prova
la configurazione effettiva del database. Enum, trigger, funzioni, policy RLS,
sequence, estensioni e vincoli vanno verificati dal catalogo e dal dump.

## Prerequisiti e identificazione

Eseguire da una workstation amministrativa fidata, nella radice del repository,
solo dopo approvazione. Python con `psycopg` gia previsto da requirements;
`psql` e `pg_dump` nel PATH. Usare client PostgreSQL della stessa major del
server production e staging; il wrapper richiede server della stessa major.
Non installare o cambiare dipendenze del progetto per questa procedura.

In Railway leggere, senza modificare, per ciascun ambiente:

1. Progetto e nome ambiente (`production` oppure `staging`).
2. ID del servizio **PostgreSQL**, host, porta, database e URL di connessione.
3. Accertare che servizi e istanze siano distinti. Con proxy TCP usare endpoint
   pubblici distinti della workstation: gli hostname privati Railway possono
   essere uguali in ambienti diversi e non bastano a identificare il servizio.

Il wrapper richiede URL con input nascosto, endpoint attesi digitati separatamente,
ID distinti dei servizi e conferma della verifica nel Dashboard. Controlla anche
database reale e indirizzo/porta server. L'identita Railway non e certificabile
dal solo protocollo PostgreSQL: il controllo umano e obbligatorio; in caso di
dubbio fermarsi. Una coincidenza degli indirizzi server blocca conservativamente
anche istanze che potrebbero essere isolate da reti differenti.

Non mettere URL in argomenti shell, file .env versionati o messaggi chat.
Il wrapper passa le credenziali solo nell'ambiente temporaneo del processo figlio,
non nella riga di comando. Usare credenziali production con privilegi minimi di
lettura dei metadati; tutte le sue sessioni sono impostate read-only.
Non utilizzare terminali con trascrizione della sessione o account condivisi.

## Comandi, ambiente e ordine

Tutti i comandi seguenti si lanciano **localmente**, dalla radice del repository.
Non usare `railway run`, non eseguire gli script nel servizio backend, non cambiare
la sua `DATABASE_URL`. Ogni comando richiede nuovamente le identita, senza salvarle.

### 1. Ispezione dei soli cataloghi production

`inspect` genera prima il report locale riservato, senza dichiarazioni preventive
su un report inesistente. Il report non e automaticamente approvato: puo contenere
letterali sensibili in default/espressioni. Non mostrarlo in chat o condividerlo.
Revisionarlo localmente prima di utilizzarlo. Se contiene segreti, fermarsi,
gestirlo secondo le procedure locali di sicurezza e non procedere all'export.
`--schema-only` non rimuove segreti incorporati nel DDL.

```powershell
python scripts/staging/procedure.py inspect
```

Connessioni production e staging in sola lettura; query cataloghi solo production.
Aprire localmente `scripts/staging/artifacts/production-catalog.txt`. Confrontare
`plans` con il candidato `seed_plans.sql`: colonne/tipi, default UUID o identity,
ulteriori colonne obbligatorie, CHECK, enum, indici unici, trigger e RLS. Se non
corrisponde, **non eseguire seed**: adattare il file al DDL reale e farlo rivedere.
La struttura reale non e stata verificata in questa sessione.
`export` e `seed` richiedono il report gia generato e la conferma della sua
revisione digitando SHA256; l'assenza del report blocca l'esecuzione. Il catalogo
non include i corpi delle funzioni: prima dell'export resta necessaria anche la
verifica amministrativa del DDL sorgente per segreti in funzioni/altri oggetti.

### 2. Esportazione dello schema production

```powershell
python scripts/staging/procedure.py export
```

Esegue esclusivamente su production:

```text
pg_dump --no-password --schema-only --no-owner --no-acl --no-comments --no-security-labels --no-tablespaces --no-publications --no-subscriptions --lock-wait-timeout=5s
```

Nessun filtro `--table`/`--schema`: preserva dipendenze di tutti gli schemi utente,
vincoli, indici, sequence (definizioni, non contatori correnti), enum, funzioni,
trigger, policy ed estensioni. Esclude dati, ACL, owner, commenti e configurazioni
di replica. Non usa `--create`, `--clean`, `--if-exists` o `pg_dumpall`.
FDW/user mapping presenti bloccano l'esportazione per il rischio credenziali.

Il file risultante e `scripts/staging/artifacts/production-schema.sql`; il wrapper
stampa SHA256 e rifiuta sovrascritture. Gli artifact sono ignorati da Git, ma
restano file locali riservati: non caricarli su chat, repository o servizi esterni.

### 3. Revisione obbligatoria, nessuna scrittura

Aprire il dump localmente. Verificare che sia solo DDL e non contenga dati,
`COPY`, INSERT applicativi, `setval`, segreti, destinazioni esterne, `\\connect`,
comandi shell psql o SQL distruttivo. Le direttive `\\restrict`/`\\unrestrict`
emesse dai client recenti sono normali. Esaminare eventuali istruzioni DATABASE,
funzioni, trigger e SECURITY DEFINER: non devono redirigere o produrre effetti
esterni. Il wrapper non e un validatore di SQL arbitrario; importa solo dump
fidati appena generati e revisionati.

Controllare che gli schemi contengano solo strutture pertinenti a NET BILLY.
Confrontare estensioni/versioni con `pg_available_extensions` e
`pg_available_extension_versions` in staging (query read-only nel suo SQL editor).
Verificare che siano installabili dal ruolo di import. Se mancano o il dump
contiene oggetti estranei, fermarsi per revisione; non rimuoverli automaticamente.
Non installare estensioni separatamente aggirando la conferma di scrittura.

Mettere in pausa **operativamente** le attivita applicative su staging durante
import e seed; non chiamare API/importatori/registrazione. Questa procedura non
modifica Railway per farlo. Se non si puo garantire assenza di scritture concorrenti,
fermarsi. Non usare il bucket production: non eseguire test upload/download in
questa fase. Schema solo non rende ancora staging pronto per i test applicativi.

### 4. Importazione esclusivamente staging

```powershell
python scripts/staging/procedure.py import --schema scripts/staging/artifacts/production-schema.sql
```

Il wrapper ricontrolla entrambe le identita in lettura, esige staging senza oggetti
applicativi e richiede una frase di conferma con endpoint e ID del servizio.
Richiede prima la revisione del dump gia esistente con conferma SHA256.
Esegue solo su staging `psql -X --no-password --single-transaction -v ON_ERROR_STOP=1 -f -`,
passando su stdin una copia in memoria degli stessi byte revisionati, senza
rileggere un file che potrebbe essere cambiato dopo la conferma.
Errore SQL: transazione annullata; nessun reset o cancellazione automatica.
Estensioni preinstallate possono richiedere revisione se creano schemi propri.
Non ripetere l'import dopo il successo: il controllo di vuoto lo blocchera.
Ripetibile significa stesso processo per un nuovo staging vuoto, senza cancellare
database o oggetti. Dopo una perdita di connessione verificare prima l'esito.

### 5. Verifica schema e assenza dati

```powershell
python scripts/staging/procedure.py verify
```

Controlla tutte le otto tabelle attese e l'assenza di righe in tutte le altre
tabelle/materialized view utente. `plans` deve essere ancora vuota a questo punto;
il risultato della query dei tre piani mostrera righe mancanti (`matches` NULL).
Confrontare anche il catalogo staging eseguendo `inspect_schema.sql` nel suo
editor SQL in sola lettura: colonne, vincoli, indici, sequence, enum ed estensioni
devono corrispondere a production salvo differenze deliberate documentate
(owner/ACL/commenti/replica). Non leggere righe applicative production.

### 6. Seed piani, solo dopo verifica DDL reale

```powershell
python scripts/staging/procedure.py seed
```

Seconda conferma manuale di scrittura, distinta dall'import. SQL separato con
revisione esplicita del catalogo e del seed tramite SHA256, prima della conferma.
Anche il seed viene eseguito dagli stessi byte revisionati conservati in memoria.
SQL con
guardie su colonne e default obbligatori, lock e transazione unica. Non presume
un vincolo UNIQUE non verificato: il lock serializza la verifica e l'inserimento.
Inserisce soltanto piani mancanti, non aggiorna piani diversi e non duplica quelli
gia conformi. Un piano esistente con importo/limiti/stato diversi blocca tutto.
Nessuna tabella Stripe e nessun collegamento Stripe creato.

### 7. Verifica finale

```powershell
python scripts/staging/procedure.py verify
```

Attesi FREE 0.00/2/4, START 14.99/20/120, TOP 45.00/100/300, attivi,
una sola riga per codice, `matches = t` per tutti, nessun'altra tabella popolata.
Non creare tenant, utenti, subscription, sessioni o dati di mercato in questa fase.
Se un controllo fallisce, fermarsi e indagare senza correzioni automatiche.

## Limiti e arresto

Non sono stati eseguiti dump, import, INSERT o connessioni Railway durante la
preparazione. L'esecuzione richiede approvazione separata dell'utente e le conferme
manuali indicate. Nessun commit, push, deploy, modifica applicativa o storage.
In caso di errore il wrapper non stampa dettagli potenzialmente sensibili; una
diagnosi approfondita va fatta localmente da un amministratore senza condividere
credenziali o output SQL sensibili.

La regex delle versioni accetta esclusivamente output riconoscibile di `psql`
o `pg_dump` con prefisso PostgreSQL e major numerica; output sconosciuto blocca
l'esecuzione. Se il terminale non supporta input nascosto, lo script si arresta
senza accettare un fallback che mostrerebbe le credenziali.

Controllo sintattico offline, senza avviare main o importare psycopg:

```powershell
python -m py_compile scripts/staging/procedure.py
```

Riferimenti: https://www.postgresql.org/docs/current/app-pgdump.html e
https://www.postgresql.org/docs/current/app-psql.html.
