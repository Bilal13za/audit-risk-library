# Audit Risk and Evidence Library - Windows installation

Offline, local-first application. No AI, no cloud, no paid services, no accounts, no telemetry.

## Requirements
- Windows 10/11 (64-bit), 8 GB RAM
- Internet needed **once** for setup (to install Python packages); afterwards the app runs fully offline.

## Install (first time)
1. Extract the ZIP to a folder, e.g. `C:\AuditRiskLibrary`.
2. Double-click **`run_windows.bat`**.
   - If Python 3.10+ is missing it is installed automatically via winget.
   - A virtual environment is created in `.venv` and dependencies installed from `requirements.txt`.
3. The app opens in your browser at http://localhost:8502.

## Every-day use
Double-click `run_windows.bat`. That's it. The launcher waits for the server and opens the browser itself.

## Data and backups
- The library database is `library.db` in the app folder.
- Rules are editable JSON in `data/rules/` - edit a rule file, then rebuild with `python seed.py` (or ask the app; see docs).
- Use **Backup** in the app sidebar to snapshot `library.db` into `backups/` before editing rules or data.
- `seed.py` automatically backs up the previous database before a full rebuild.

## Offline operation
After setup, disconnect the network: search, risk assessment, exports and backups all work offline. The app makes no external calls.

## Updating the library
1. Edit rule JSON in `data/rules/` or add seed JSON in `data/rules`/`data/seed/`.
2. Run `python seed.py` (rebuilds `library.db`, preserving rule version history).
3. Run `pytest tests/` to confirm nothing broke.
