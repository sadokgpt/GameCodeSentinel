# GameCode Sentinel 1.5.0

Windows tracker for **AION 2**, **Genshin Impact** and **Aniimo** redemption codes. Local SQLite database; notifications are optional. Code detection is probabilistic: a published string is not proof it can be redeemed. Version 1.3.2 rejects common AION 2 reward names accidentally tagged as codes and quarantines previously stored suspicious Reddit entries.

## Windows (without Python)

After a successful GitHub Actions run, download the `GameCodeSentinel-Windows-v1.5.0` artifact from the **Build Windows EXE** workflow, unzip, and run `GameCodeSentinel.exe`. Windows SmartScreen may warn for an unsigned executable. Only install software you trust.

## From source

Install Python 3.11+ and run `INSTALLA_WINDOWS.bat` on Windows, or:

```bash
python -m pip install -r requirements.txt
python app.py --check --headless --game "AION 2" --report-json scan-report.json
```

Exit status 2 means zero sources were reachable. `python app.py --version` only prints the version and leaves the database untouched.

## CI

- **Cross-platform Tests**: automated regression tests on Windows and Ubuntu with Python 3.11 and 3.13. This workflow also performs a live AION 2 HTTP scan on main-branch changes, manual invocation, and daily at 06:37 UTC. Scan reports are public; web sources may rate-limit requests.
- **Build Windows EXE**: native Windows compilation with PyInstaller, executable exit-code smoke test, and SHA-256 checksum. Download the `GameCodeSentinel-Windows-v1.4.0` artifact from a green run; the EXE is not signed.
- **Dependabot**: weekly update proposals for Python dependencies and GitHub Actions; review any proposed changes before merging.
- The GitHub live scan is **stateless**. Your personal code history remains local on your Windows PC. A code mentioned online is not necessarily a redeemable coupon.

Do not commit `config.json`, `codes.db`, `.env`, notification topics, logs or credentials. If running public workflows, all uploaded artifacts/logs may be visible to others.

## Notes

The license has not been selected. Public visibility is not a license granting reuse. Credits and previous technical audit are in `AUDIT_V1.1.txt` and `AUDIT_V1.2.txt`.

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
