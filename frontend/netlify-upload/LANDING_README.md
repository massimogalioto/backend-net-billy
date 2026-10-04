# Anteprima commerciale

Caricare su Netlify **l'intera cartella `frontend/netlify-upload`**, con `index.html` alla radice. Non caricare soltanto le nuove pagine: il workspace usa anche `_next`, PDF viewer e gli altri asset esistenti.

- `/`: landing commerciale.
- `/accedi/` e `/registrati/?piano=START`: anteprime disabilitate, senza account, raccolta dati o pagamenti.
- `/workspace/`: panoramica operativa precedente.
- `/cte/` e `/bollette/`: strumenti esistenti, con la configurazione API già prevista dal progetto.

Anteprima locale dalla cartella `frontend`:

```powershell
node scripts/serve-static.mjs
```

Aprire `http://127.0.0.1:4173/`. Il server serve l'export esistente senza ricrearlo. La landing non richiede un backend; le funzioni operative richiedono un backend raggiungibile e la configurazione di connessione corretta.

**Build e Git:** la cartella export è attualmente ignorata da Git e la build statica la ricrea. Un push da solo non include questa consegna e una nuova build non conserva le estensioni manuali. Prima di usare un deploy automatico da GitHub occorre riportare landing ed estensioni operative nei sorgenti e verificare l'export risultante. In questa fase usare l'upload manuale della cartella, come richiesto; non è stato effettuato alcun deploy.

Il vecchio workspace mantiene i payload di navigazione Next: la sua voce Panoramica continua a mostrare la panoramica operativa durante la navigazione interna. Accedere direttamente a `/` apre la landing commerciale.

Proposta del backend SaaS e delle quote: `SAAS_ARCHITECTURE_PROPOSAL.md` nella radice del repository. Tutto il SQL contenuto nel documento è soltanto una proposta e non è stato eseguito.
