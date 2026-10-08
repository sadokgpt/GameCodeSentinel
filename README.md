# GameCode Sentinel 1.3

Windows tracker for **AION 2**, **Genshin Impact** and **Aniimo** redemption codes. Local SQLite database; notifications are optional. Code detection is probabilistic: a published string is not proof it can be redeemed.

## Windows (without Python)

After a successful GitHub Actions run, download the `GameCodeSentinel-Windows` artifact from the **Build Windows EXE** workflow, unzip, and run `GameCodeSentinel.exe`. Windows SmartScreen may warn for an unsigned executable. Only install software you trust.

## From source

Install Python 3.11+ and run `INSTALLA_WINDOWS.bat` on Windows, or:

```bash
python -m pip install -r requirements.txt
python app.py --check --headless --game "AION 2" --report-json scan-report.json
```

Exit status 2 means zero sources were reachable. `python app.py --version` only prints the version and leaves the database untouched.

## CI

- **Unit Tests**: Windows and Ubuntu, Python 3.11 and 3.13, no network needed.
- **Build Windows EXE**: build on real Windows, then run `--version` to smoke-test the binary. Download the artifact; the executable is not signed.
- **Live Scan**: manual read-only HTTP scan without notification credentials, no upload of the user's local DB. Website rate limits, anti-bot challenges and HTML changes may interfere.
- **Dependency Review**: automated checks for dependency vulnerabilities in pull requests when supported.

Do not commit `config.json`, `codes.db`, `.env`, notification topics, logs or credentials. If running public workflows, all uploaded artifacts/logs may be visible to others.

## Notes

The license has not been selected. Public visibility is not a license granting reuse. Credits and previous technical audit are in `AUDIT_V1.1.txt` and `AUDIT_V1.2.txt`.
