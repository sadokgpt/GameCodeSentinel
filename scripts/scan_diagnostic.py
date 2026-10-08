"""Public CI-only diagnostic of AION 2 codes from the ephemeral scan database."""
import json
import os
import sqlite3
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("Refusing to read a personal database outside GitHub Actions")

db_path = Path(os.environ["RUNNER_TEMP"]) / "GameCodeSentinelCI" / "GameCodeSentinel" / "codes.db"
details = {"database_present": db_path.is_file(), "game": "AION 2", "codes": []}
if db_path.is_file():
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        for row in con.execute(
            "SELECT code,status,score,confidence,source_count,sources_json "
            "FROM codes WHERE game=? ORDER BY score DESC, code ASC", ("AION 2",)
        ):
            try:
                sources = json.loads(row["sources_json"] or "[]")
            except (ValueError, TypeError):
                sources = []
            details["codes"].append({
                "code": row["code"],
                "status": row["status"],
                "confidence": row["confidence"],
                "score": row["score"],
                "source_count": row["source_count"],
                "sources": [
                    {"name": s.get("name"), "kind": s.get("kind"), "url": s.get("url")}
                    for s in sources if isinstance(s, dict)
                ]
            })

Path("scan-candidates.json").write_text(
    json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(details, ensure_ascii=False, indent=2))
