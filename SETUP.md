# L.O.C.U.S — setup & run guide

Everything here is **simulation**: no real BLE anchors exist yet, and nothing has been calibrated against real hardware.
The static demo (`LOCUS-Dashboard.html`, `LOCUS-Staff-App.html`) keeps working on its own with **no backend at all** —
open the files, or the GitHub Pages site, and they run the in-browser simulation and say **"Offline simulation"**.

## 0. One-time install (Windows, PowerShell)

```powershell
cd C:\Users\Mankeshwari\locus
pip install -r requirements.txt
```

(Node.js is only needed for `node test.js` and the JS↔Python cross-check.)

## 1. Start the backend on the laptop

```powershell
cd C:\Users\Mankeshwari\locus
python -m backend
```

It prints a banner like:

```
  This laptop      : http://localhost:8000/
  LAN IP           : 10.115.41.47
  >>> Open on the ANDROID PHONE (same WiFi):  http://10.115.41.47:8000/staff
  >>> Dashboard (laptop or phone)           :  http://10.115.41.47:8000/
```

* First start: Windows Defender Firewall asks whether Python may accept connections → tick **Private networks** → Allow.
  If you missed it, run once in an **Administrator** PowerShell:
  `New-NetFirewallRule -DisplayName "LOCUS backend" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private`
* Laptop and phone must be on the **same WiFi**. Guest/“client isolation” networks block phone→laptop traffic; a phone hotspot
  (laptop joins the phone’s hotspot) always works.
* A different port: `python -m backend --port 8080`.

## 2. Find the LAN IP (if the banner shows several)

```powershell
ipconfig | findstr /i "IPv4"
```

Use the address on your WiFi adapter (usually `192.168.x.x` / `10.x.x.x`). Ignore `192.168.56.1` (VirtualBox) and `172.x` (Docker/WSL).

## 3. Dashboard pointed at the backend

On the laptop open **http://localhost:8000/** (or `http://<LAN-IP>:8000/` from any device).
The header badge turns green: **Live backend**. You now get the CEP50/CEP95 row and error-CDF (from the benchmark endpoint),
record / replay scrubber / CSV+JSON export, and the trust-scorer selector.

Opened the HTML file directly (`file://`) or from GitHub Pages instead? Point it at the laptop explicitly:
`LOCUS-Dashboard.html?backend=<LAN-IP>:8000` (works from `file://` and `http://`; an `https://` page cannot call an `http://` backend —
browser mixed-content rule — so use the backend’s own URL for the live mode).

## 4. Staff app on the Android phone (same WiFi)

1. On the phone open Chrome and go to `http://<LAN-IP>:8000/staff` (e.g. `http://10.115.41.47:8000/staff`).
2. The badge reads **Live backend**. Kill an anchor on the laptop dashboard (click it on the map) → the phone’s *Alerts* tab shows it within a second,
   and vice-versa (“Simulate failure” on the phone shows on the dashboard). Both read **one shared session**.
3. The equipment list comes from the backend (`/api/assets`); offline it falls back to the built-in list.

If the page cannot reach the laptop it silently runs the offline simulation after ~1.5 s — reload once the backend is up.

## 5. Install as an app (PWA)

* **GitHub Pages (HTTPS)** → Chrome on Android: ⋮ → *Install app*; iPhone Safari: Share → *Add to Home Screen*. Works offline (simulation).
* **Laptop backend over plain `http://<LAN-IP>`** is *not* a secure origin: Chrome only offers “Add to Home screen” (a shortcut), no offline
  service worker. To get the full PWA + Web Bluetooth over plain HTTP on the phone, in Chrome go to
  `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, add `http://<LAN-IP>:8000`, set **Enabled**, relaunch Chrome.
* Alternative: `python -m backend --https` serves a self-signed certificate (`https://<LAN-IP>:8000/staff`, accept the warning once).
  This gives a secure context for Web Bluetooth; Chrome may still refuse the *service worker* on a self-signed cert.

## 6. Live BLE scanning (Android Chrome only, optional, off by default)

iPhone/Safari cannot do Web Bluetooth at all (Apple does not implement it); the tab says so. Desktop Chrome works too.

1. Start the backend (`python -m backend --https`, or use the insecure-origins flag from §5) and open the staff app on the Android phone.
2. Chrome: `chrome://flags/#enable-experimental-web-platform-features` → **Enabled** → relaunch. Without it only the single-device fallback
   (**Pick one device**, uses `requestDevice()` + `watchAdvertisements()`) is possible; the tab shows this as a one-line message.
3. Staff app → **BLE** tab → switch **Use real BLE readings** on → **Start scan** → allow the Bluetooth prompt.
4. For each beacon in *Nearby devices* choose the anchor ID (A1…A6) and press **Pair**. Pairings are remembered on the phone.
5. Paired beacons’ RSSI is POSTed to `/api/ingest` (`{anchor_id, rssi, timestamp}`); once readings arrive the backend engine uses them instead of
   the simulator (`mode: "live"`, no ground truth shown). They stop 2 s after the last reading and the simulator resumes.
6. RSSI→range uses `RSSI = rssi_at_1m − 10·n·log10(d)` with defaults −40 dBm / n = 2.2 (the simulator’s constants). **Real beacons need their own
   measured values**: send `rssi_at_1m` / `n` in the ingest body.

This path was tested only with a mocked `navigator.bluetooth` (`scripts/test_ble.py`) — never against real beacons.

## 7. Everything else

```powershell
python build.py                          # rebuild the two HTML files from src/
node test.js                             # original JS benchmark (must still pass)
python scripts/generate_dataset.py       # data/train.csv, data/hidden_public.csv (+ hidden_truth.csv, kept separate)
python scripts/validate_port.py          # Python simulator == JS simulator (same seed)
python scripts/crossval_engine.py        # Python engine == JS engine (docs/crossval_output.txt)
python scripts/train_trust.py            # trains backend/models/* (~8 min)
python scripts/run_benchmark.py          # hidden-set benchmark -> results.json, docs/error_cdf.png (~12 min)

# tests (backend must be running for these two; stop it before the "offline" one)
python scripts/test_backend.py
python scripts/test_ble.py
python scripts/test_frontend.py online
python scripts/test_frontend.py offline  # with NO backend running
python scripts/test_pwa.py
```

Delete `backend/models/` and the system silently uses the original heuristic trust scorer. Delete `backend/locus.db` to reset recordings.
Hidden-set ground truth (`data/hidden_truth.csv`) is deliberately **not** served by the API.

### Known limits (read before quoting numbers)
* Benchmark (hidden simulated set, 6 anchors, all noise levels): LOCUS median ≈ 2.7 m, ≈ 39 % of fixes within 2 m, 90 %-ellipse coverage ≈ 85 %.
  See `results.json` / `docs/benchmark_summary.txt`; the old slide claims (<2 m median, >70 % within 2 m, ~90 % calibration) only hold at low noise.
* The ML trust scorer detects corrupted readings better than the heuristic but did **not** improve end-to-end position error; heuristic is the default.
* Custom floor plans must fit the 40 × 24 m footprint.
* No authentication: local demo network only.
