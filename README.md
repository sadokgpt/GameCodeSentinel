# GameCode Sentinel 1.7.0

Windows tracker for **AION 2**, **Genshin Impact** and **Aniimo** redemption codes. Local SQLite database; notifications are optional. Code detection is probabilistic: a published string is not proof it can be redeemed. Version 1.3.2 rejects common AION 2 reward names accidentally tagged as codes and quarantines previously stored suspicious Reddit entries.

## Windows (without Python)

After a successful GitHub Actions run, download the `GameCodeSentinel-Windows-v1.7.0` artifact from the **Build Windows EXE** workflow, unzip, and run `GameCodeSentinel.exe`. Windows SmartScreen may warn for an unsigned executable. Only install software you trust.

## From source

Install Python 3.11+ and run `INSTALLA_WINDOWS.bat` on Windows, or:

```bash
python -m pip install -r requirements.txt
python app.py --check --headless --game "AION 2" --report-json scan-report.json
```

Exit status 2 means zero sources were reachable. `python app.py --version` only prints the version and leaves the database untouched.

## CI

- **Cross-platform Tests**: automated regression tests on Windows and Ubuntu with Python 3.11 and 3.13. This workflow also performs a live AION 2 HTTP scan on main-branch changes, manual invocation, and daily at 06:37 UTC. Scan reports are public; web sources may rate-limit requests.
- **Build Windows EXE**: native Windows compilation with PyInstaller, executable exit-code smoke test, and SHA-256 checksum. Download the `GameCodeSentinel-Windows-v1.7.0` artifact from a green run; the EXE is not signed.
- **Dependabot**: weekly update proposals for Python dependencies and GitHub Actions; review any proposed changes before merging.
- The GitHub live scan is **stateless**. Your personal code history remains local on your Windows PC. A code mentioned online is not necessarily a redeemable coupon.

Do not commit `config.json`, `codes.db`, `.env`, notification topics, logs or credentials. If running public workflows, all uploaded artifacts/logs may be visible to others.

## Notes

The license has not been selected. Public visibility is not a license granting reuse. Credits and previous technical audit are in `AUDIT_V1.1.txt` and `AUDIT_V1.2.txt`.

## Novità 1.7.0 — liste attive e tabella personalizzabile

### Controllo più intelligente della freschezza (richiesta #1)

- Un codice può avere una **vecchia data di pubblicazione** ma comparire ancora sotto una sezione esplicita **Active/Working/Current/Valid codes** di un **tracker editoriale** visitato oggi. Questo viene salvato come riscontro **"Presente in elenco attivi (non garantito)"**, distinto dalla mera citazione storica. Gli elenchi "Expired/Old/Not working codes" non valgono come conferma.
- Una notizia ufficiale vecchia, un articolo di archivio, la semplice modifica recente della pagina o il fatto che un sito risponda **HTTP 200** **non** rendono di per sé il codice attivo.
- I codici di pagine editoriali senza metadati di pubblicazione e **senza esplicito elenco attivi** restano **Da riverificare**; quando disponibile, nel dettaglio delle fonti appare anche la data dell'ultimo controllo. Reddit continua a usare le date originali del singolo post/commento.
- Una voce precedentemente da riverificare può tornare segnalata attiva se appare in un esplicito elenco corrente, ma il punteggio di una sola fonte resta modesto. Due fonti editoriali indipendenti possono offrire maggior corroborazione.
- Rimangono prioritari gli stati **Scaduto/Non valido** già conosciuti; nessuna fonte web prova che il codice sia riscattabile per uno specifico account.

### Tabella evoluta (richiesta #6)

- **Data post** ora è davvero ordinabile cliccando sull'intestazione: prima i più recenti, al secondo clic i meno recenti; pubblicazione sconosciuta sempre in fondo. Non si usa la data dell'ultima scansione come data del post.
- Checkbox **Solo codici recenti**: mostra solo le voci con almeno una pubblicazione datata entro 30 giorni per Genshin Impact, 90 per AION 2 e Aniimo. Le date ignote vengono escluse **solo quando il filtro è attivo**. Puoi combinarlo con le altre opzioni di visualizzazione.
- Puoi **trascinare le intestazioni** per riordinare le colonne e **trascinare i separatori** per ridimensionarle. Ordine e larghezze vengono salvati in `config.json` **quando chiudi normalmente la finestra** e ripristinati al lancio, con validazione dei valori salvati. Non cambia l'ordine dei campi nel database.
- **Doppio clic su un codice** apre la finestra delle **fonti**; lì puoi aprire il link della fonte con un altro doppio clic. Il pulsante "Copia codice" resta disponibile.

### Installazione

Apri [Releases](https://github.com/sadokgpt/GameCodeSentinel/releases), scegli `v1.7.0` e scarica `GameCodeSentinel.exe` e, per controllarne l'integrità, `SHA256SUMS.txt`. L'EXE non è firmato digitalmente. La release viene pubblicata dal workflow Windows su `main` **solo dopo** test, compilazione e smoke test superati.

## Novità 1.6.0 — filtro anti-post vecchi, con date verificabili

- Ogni codice ricavato da un articolo HTML conserva la data **originale** del post quando disponibile (`article:published_time`, `datePublished` JSON-LD o `time` esplicito). Se la pagina riporta anche `dateModified`, resta separata: aggiornare una pagina **non prova** che un codice sia nuovo.
- Reddit JSON usa `created_utc` dei post; i codici nei commenti utilizzano **la data del singolo commento** anziché quella della discussione. Il fallback RSS usa il campo `published` della voce.
- Soglie prudenziali di **anzianità della segnalazione**: 30 giorni per Genshin Impact, 90 per AION 2 e Aniimo. Superata la soglia, una segnalazione **non vale come conferma corrente**; se non ci sono altre fonti recenti o senza data ma presenti in elenco corrente, il codice va in **Da riverificare** (non dichiarato scaduto). Sono soglie di priorità, **non durate ufficiali dei codici**.
- Nuova colonna **Data post** e data di pubblicazione per ciascuna fonte nel dettaglio. **Data non nota** significa che la pagina non ha fornito metadati utilizzabili; non significa codice recente.
- Nessun codice viene riattivato se era già scaduto soltanto perché riappare in un vecchio post. Codici vecchi e dati preesistenti restano conservati nel database, ma non generano nuovi avvisi in assenza di riscontri sufficienti.
- **Aggiornamento da versioni precedenti:** i codici attivi non ancora usati, privi di date storiche nel database, sono portati una sola volta in **Da riverificare** finché le fonti non li confermano nuovamente. Prima della modifica viene creato un backup SQLite coerente; codici, fonti e flag personali non vengono cancellati. Per consultare queste voci abilita **Storico e scaduti**.
- Ulteriori test con casi di post Reddit vecchi, commenti recenti, articoli aggiornati a distanza di anni e scadenze pregresse.

**Esiste un validatore rapido affidabile?** Non è stato integrato alcun validatore esterno non ufficiale. Il [supporto HoYoverse](https://support.hoyoverse.com/hc/en-us/articles/51005644306585-Why-am-I-getting-an-error-message-that-my-redemption-code-is-invalid-or-has-already-been-used) segnala che la validità può dipendere anche da regione, scadenza e utilizzo già effettuato e avverte sui software di terze parti che riscattano i codici. La data di pubblicazione, la presenza su una pagina e il punteggio di confidenza **non certificano** la riscattabilità sull'account dell'utente. Il riscatto resta assistito sul [sito ufficiale](https://genshin.hoyoverse.com/en/gift).

## Novità 1.5.0 — interfaccia desktop e riscatto assistito

- **Dashboard dark professionale**, progettata senza dipendenze GUI aggiuntive: sidebar, pulsante di controllo, tre indicatori (codici visibili, attivi, punteggio ≥85), tabella leggibile, filtri e scrollbar orizzontale.
- **Ricerca ottimizzata**: la digitazione è ritardata di 240 ms (debounce) prima di aggiornare SQLite; si evitano riletture inutili per ogni tasto.
- **Genshin Impact**: seleziona una sola riga attiva e premi **Apri riscatto**. Il programma copia il codice e apre nel browser predefinito la pagina ufficiale `https://genshin.hoyoverse.com/en/gift?code=CODICE`. Il sito può precompilare il campo, ma il comportamento dipende da HoYoverse.
- **Login, CAPTCHA, server, personaggio e conferma finale** restano **manuali** sul sito ufficiale. Il programma non chiede né salva credenziali, non automatizza la conferma e non marca automaticamente un codice come utilizzato. Premi **Segna usati** solo dopo aver verificato il successo.
- **Correzione stabilità**: gestione degli errori dei thread della scansione nella GUI.

**Motivo del riscatto assistito:** [HoYoverse Help Center](https://support.hoyoverse.com/hc/en-us/articles/51005644306585-Why-am-I-getting-an-error-message-that-my-redemption-code-is-invalid-or-has-already-been-used) precisa che il riscatto effettuato mediante software di terze parti può violare i termini e comportare penalizzazioni sull'account. Per proteggere l'account, la soluzione si limita ad aprire il sito ufficiale con il codice e non esegue login, invio di richieste private, CAPTCHA o click automatici. Il flusso ufficiale è documentato in [How do I redeem a gift code?](https://support.hoyoverse.com/hc/en-us/articles/50333794943513-How-do-I-redeem-a-gift-code).

### Verifica della versione
```bash
python app.py --version
python -m pytest -q
```

La dashboard richiede un desktop con Tkinter. I comandi `--headless` rimangono compatibili con ambienti senza interfaccia grafica. Nessun test automatico esegue un riscatto reale o interagisce con l'account di gioco.

## Novita' 1.4.0 - affidabilita' e diagnostica

- **Stato fonti**: elenco degli ultimi esiti (OK/errore), codici individuati, latenza e dettagli del fallimento.
- **Controlli concorrenti**: al massimo tre fonti alla volta, senza condividere sessioni HTTP, e un solo scan locale alla volta. L'invocazione CLI occupata esce con stato 3.
- **Tracker soft-404**: una pagina non riconoscibile che riporta zero codici non fa avanzare automaticamente l'assenza di codici precedentemente rilevati.
- **Backup**: snapshot SQLite consistente, incluso WAL, automatico ogni 24 ore e rotazione ultime 7 copie. GUI: pulsante Backup; CLI: `python app.py --backup`. Le copie restano solo nel profilo Windows locale, in `%LOCALAPPDATA%\\GameCodeSentinel\\backups`.
- **Notifiche**: elaborazione protetta da lock, nuova verifica dello stato del codice prima dell'invio e flag separati per PC/telefono.
- **Scadenze**: le date senza orario vengono considerate fino alle 23:59; le scadenze EU esplicite AION 2 sono confrontate usando Europe/Rome.
- **Tabella**: ricerca per codice/ricompensa, clic sull'intestazione per ordinare, colonna Ultima vista.
- **Distribuzione**: EXE Windows collaudato in CI disponibile per 30 giorni fra gli artifact. Il workflow `release-windows.yml` pubblica un rilascio duraturo quando viene creato un tag Git `v1.4.0` corrispondente a `APP_VERSION`.

### Aggiornamento e limiti

Prima di sostituire un EXE precedente esegui un backup del database. Le installazioni mantengono lo stesso file `codes.db` e gli stati già usati. Un backup può essere verificato/ripristinato con gli strumenti SQLite: il pulsante di ripristino guidato non è ancora presente nell'interfaccia. Una fonte che risponde HTTP 200 può comunque aver cambiato semantica pur mantenendo testi simili: la verifica delle pagine non è una garanzia assoluta. La notifica è ritentabile quando fallisce, ma un arresto tra il recapito effettivo e il salvataggio del flag può causare un duplicato.

## Gestione multipla dei codici (1.3.3)

- Usa **Ctrl+clic** per righe separate, **Maiusc+clic** per un intervallo, oppure **Ctrl+A** / **Seleziona tutti visibili** per selezionare tutti i codici filtrati.
- **Segna usati** nasconde tutti i codici selezionati dalla vista principale, senza eliminarli dal database. Per operazioni su piu' righe viene chiesta conferma.
- Per annullare una marcatura errata, abilita **Mostra usati**, seleziona le righe, poi premi **Ripristina usati**. I codici marcati **Non valido** non vengono riattivati dal ripristino.
- **Deseleziona** cancella la selezione. Copia, riscatta e fonti continuano a operare su un solo codice.
- Database, notifiche e scansione delle fonti restano invariati.

## Expired-code safeguards (1.3.2)

- A historical/reposted code does not become redeemable merely because it was found again.
- Once an explicit expiry date has passed, only a newly published *official deadline extension* can reactivate it automatically; undated community or tracker reposts do not.
- An undated expired entry requires reliable fresh corroboration. Without a precise expiration, **Segnalato (non garantito)** means only that a source lists the string, not that redemption will succeed.
- When multiple equally authoritative expiry dates disagree, the earlier deadline is used conservatively. Yearless dates are anchored to the current calendar year, not automatically pushed into the future.
- Existing local history and redemption flags remain intact. Use **Mostra storico/scaduti** to review hidden items.

These checks cannot directly query your game account to verify that a code can still be redeemed. Publisher sites may change formats or apply regional/account restrictions.
