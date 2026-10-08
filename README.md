# GameCode Sentinel 1.3

Windows tracker for AION 2, Genshin Impact and Aniimo redemption codes.

## Stato

Repository pubblico. I sorgenti v1.3 con i workflow per compilazione Windows e test sono disponibili nel pacchetto ZIP preparato in ChatGPT. I workflow devono essere caricati insieme ai sorgenti prima di essere eseguiti.

## Utilizzo

Installare Python 3.11+ ed eseguire `INSTALLA_WINDOWS.bat`, oppure usare il workflow **Build Windows EXE** dopo il caricamento del progetto.

Verifica CLI: `python app.py --version`. Scansione AION 2: `python app.py --check --headless --game "AION 2" --report-json scan-report.json`.

**Privacy:** mai pubblicare `config.json`, `codes.db`, topic ntfy o credenziali. I log e gli artifact delle Actions di un repository pubblico possono essere visibili a terzi.

La pubblicazione non equivale a una licenza per il riutilizzo del software.
