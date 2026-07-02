from __future__ import annotations

import json
import math
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 10000
LOCAL_DISPLAY_HOST = "127.0.0.1"
CONTRACT_SIZE = 100
CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
OPTION_RE = re.compile(r"^(?P<root>.+?)(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<type>[CP])(?P<strike>\d{8})$")


class MaxPainError(Exception):
    pass


def parse_query(path: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urllib.parse.urlparse(path)
    return parsed.path, urllib.parse.parse_qs(parsed.query)


def first_param(params: dict[str, list[str]], name: str, default: str = "") -> str:
    values = params.get(name)
    if not values:
        return default
    return values[0].strip()


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 MaxPainLocal/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise MaxPainError(f"Data source returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise MaxPainError(f"Could not reach data source: {exc.reason}") from exc
    except TimeoutError as exc:
        raise MaxPainError("Data source timed out.") from exc
    except json.JSONDecodeError as exc:
        raise MaxPainError("Data source returned invalid JSON.") from exc


def parse_cboe_option(option_symbol: str) -> dict:
    match = OPTION_RE.match(option_symbol)
    if not match:
        raise MaxPainError(f"Could not parse option symbol {option_symbol}.")

    parts = match.groupdict()
    year = 2000 + int(parts["yy"])
    expiration = f"{year:04d}-{int(parts['mm']):02d}-{int(parts['dd']):02d}"

    strike = int(parts["strike"]) / 1000

    return {
        "root": parts["root"].strip(),
        "expiration": expiration,
        "type": parts["type"],
        "strike": strike,
    }


def numeric_price(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def calculate_max_pain(symbol: str, requested_expiration: str = "") -> dict:
    symbol = re.sub(r"[^A-Za-z0-9._-]", "", symbol).upper() or "SNDK"
    url = CBOE_URL.format(symbol=urllib.parse.quote(symbol))
    payload = fetch_json(url)
    data = payload.get("data") or {}
    options = data.get("options") or []

    if not options:
        raise MaxPainError(f"No options were returned for {symbol}.")

    contracts = []
    expirations = set()

    for item in options:
        option_symbol = str(item.get("option", ""))
        parsed = parse_cboe_option(option_symbol)
        expiration = parsed["expiration"]
        expirations.add(expiration)

        open_interest = float(item.get("open_interest") or 0)
        if open_interest < 0:
            open_interest = 0

        contracts.append(
            {
                "expiration": expiration,
                "type": parsed["type"],
                "strike": parsed["strike"],
                "open_interest": open_interest,
            }
        )

    sorted_expirations = sorted(expirations)
    expiration = requested_expiration or sorted_expirations[0]
    if expiration not in expirations:
        raise MaxPainError(
            f"Expiration {expiration} is not available for {symbol}. "
            f"Available expirations: {', '.join(sorted_expirations)}"
        )

    expiry_contracts = [contract for contract in contracts if contract["expiration"] == expiration]
    strikes = sorted({contract["strike"] for contract in expiry_contracts})

    rows = []
    for price in strikes:
        call_payout = 0.0
        put_payout = 0.0
        call_oi = 0.0
        put_oi = 0.0

        for contract in expiry_contracts:
            strike = contract["strike"]
            open_interest = contract["open_interest"]
            if contract["type"] == "C":
                call_oi += open_interest if strike == price else 0
                call_payout += max(price - strike, 0) * open_interest * CONTRACT_SIZE
            else:
                put_oi += open_interest if strike == price else 0
                put_payout += max(strike - price, 0) * open_interest * CONTRACT_SIZE

        rows.append(
            {
                "price": round(price, 4),
                "call_open_interest": call_oi,
                "put_open_interest": put_oi,
                "call_payout": round(call_payout, 2),
                "put_payout": round(put_payout, 2),
                "total_payout": round(call_payout + put_payout, 2),
            }
        )

    if not rows:
        raise MaxPainError(f"No contracts found for {symbol} expiration {expiration}.")

    best = min(rows, key=lambda row: row["total_payout"])

    return {
        "symbol": symbol,
        "expiration": expiration,
        "expirations": sorted_expirations,
        "source": "Cboe delayed quotes",
        "source_url": url,
        "timestamp": payload.get("timestamp"),
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "underlying_price": numeric_price(data.get("current_price")),
        "max_pain": best,
        "rows": rows,
        "contract_count": len(options),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "MaxPainHTTP/1.0"

    def do_GET(self) -> None:
        path, params = parse_query(self.path)

        if path == "/api/max-pain":
            self.handle_max_pain(params)
            return

        self.serve_static(path)

    def handle_max_pain(self, params: dict[str, list[str]]) -> None:
        symbol = first_param(params, "symbol", "SNDK")
        expiration = first_param(params, "expiration")

        try:
            result = calculate_max_pain(symbol, expiration)
        except MaxPainError as exc:
            self.write_json({"error": str(exc)}, status=502)
            return
        except Exception as exc:
            self.write_json({"error": f"Unexpected server error: {exc}"}, status=500)
            return

        self.write_json(result)

    def serve_static(self, path: str) -> None:
        if path == "/":
            path = "/index.html"

        target = (PUBLIC / path.lstrip("/")).resolve()
        if PUBLIC not in target.parents and target != PUBLIC:
            self.send_error(403)
            return
        if not target.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")


def main() -> None:
    host = os.environ.get("HOST", DEFAULT_HOST)
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    server = ThreadingHTTPServer((host, port), Handler)
    display_host = LOCAL_DISPLAY_HOST if host == DEFAULT_HOST else host
    print(f"Max Pain app running at http://{display_host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
