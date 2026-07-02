# Options Max Pain Web App

Small local web app that fetches delayed options data from Cboe, computes max pain by expiration, and displays the payout table in a browser.

## Run

Use the bundled Codex Python on this machine:

```powershell
& 'C:\Users\wjiho\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' server.py
```

Then open:

```text
http://127.0.0.1:8000
```

No Python packages are required.

## Notes

- Data source: Cboe delayed quote endpoint.
- Default symbol: `SNDK`, with support for other optionable Cboe symbols.
- Max pain is based on open interest, not live intraday positioning.
- This is a market-structure indicator, not a standalone closing-price predictor.

## Host Online

This app needs a Python backend because the browser calls your local `/api/max-pain` endpoint, and the backend fetches Cboe.

### Render

1. Push this folder to a GitHub repository.
2. Go to Render and create a new Web Service.
3. Connect the GitHub repository.
4. Use these settings:
   - Runtime: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `python server.py`
5. Deploy.

The included `render.yaml`, `Procfile`, and `requirements.txt` are already set up for this.

### Railway

1. Push this folder to GitHub.
2. Create a Railway project from the GitHub repository.
3. Railway should detect the `Procfile`.
4. Deploy.
