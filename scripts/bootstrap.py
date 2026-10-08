"""Safely extract the reviewed v1.3 archive in a public GitHub repository."""
from pathlib import Path, PurePosixPath
from stat import S_IFMT, S_IFLNK
from zipfile import ZipFile

package = Path("GameCodeSentinel_v1.3_GitHub_ready.zip")
required = ("app.py", "requirements.txt", "tests/test_core.py", ".github/workflows/build-windows.yml")
allowed = {".github", ".gitignore", "AUDIT_V1.1.txt", "AUDIT_V1.2.txt", "AVVIA.bat",
           "CREA_EXE_WINDOWS.bat", "INSTALLA_WINDOWS.bat", "README.md",
           "README.txt", "app.py", "requirements.txt", "tests"}
with ZipFile(package) as archive:
    members = archive.infolist()
    if len(members) > 100:
        raise SystemExit("Archive contains too many files")
    for item in members:
        name = PurePosixPath(item.filename)
        if (name.is_absolute() or ".." in name.parts or not name.parts
                or name.parts[0] not in allowed
                or name.name.lower() in {"config.json", "codes.db", ".env", "app.log"}
                or S_IFMT(item.external_attr >> 16) == S_IFLNK
                or item.file_size > 5_000_000):
            raise SystemExit(f"Refusing unsafe archive member: {item.filename}")
        if item.is_dir() or item.filename == ".gitignore":
            continue
        output = Path(*name.parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(archive.read(item))
for name in required:
    if not Path(name).is_file():
        raise SystemExit(f"Required file missing after extraction: {name}")
print("Source import complete")
