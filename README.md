# GameCode Sentinel 1.3.3

Windows tracker for **AION 2**, **Genshin Impact** and **Aniimo** redemption codes. Local SQLite database; notifications are optional. Code detection is probabilistic: a published string is not proof it can be redeemed. Version 1.3.2 rejects common AION 2 reward names accidentally tagged as codes and quarantines previously stored suspicious Reddit entries.

## Windows (without Python)

After a successful GitHub Actions run, download the `GameCodeSentinel-Windows-v1.3.3` artifact from the **Build Windows EXE** workflow, unzip, and run `GameCodeSentinel.exe`. Windows SmartScreen may warn for an unsigned executable. Only install software you trust.

## From source

Install Python 3.11+ and run `INSTALLA_WINDOWS.bat` on Windows, or:

```bash
python -m pip install -r requirements.txt
python app.py --check --headless --game "AION 2" --report-json scan-report.json
```

Exit status 2 means zero sources were reachable. `python app.py --version` only prints the version and leaves the database untouched.

## CI

- **Cross-platform Tests**: 54 regression tests on Windows and Ubuntu with Python 3.11 and 3.13. This workflow also performs a live AION 2 HTTP scan on main-branch changes, manual invocation, and daily at 06:37 UTC. Scan reports are public; web sources may rate-limit requests.
- **Build Windows EXE**: native Windows compilation with PyInstaller, executable exit-code smoke test, and SHA-256 checksum. Download the `GameCodeSentinel-Windows-v1.3.3` artifact from a green run; the EXE is not signed.
- **Dependabot**: weekly update proposals for Python dependencies and GitHub Actions; review any proposed changes before merging.
- The GitHub live scan is **stateless**. Your personal code history remains local on your Windows PC. A code mentioned online is not necessarily a redeemable coupon.

Do not commit `config.json`, `codes.db`, `.env`, notification topics, logs or credentials. If running public workflows, all uploaded artifacts/logs may be visible to others.

## Notes

The license has not been selected. Public visibility is not a license granting reuse. Credits and previous technical audit are in `AUDIT_V1.1.txt` and `AUDIT_V1.2.txt`.

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
