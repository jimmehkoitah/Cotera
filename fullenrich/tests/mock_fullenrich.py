#!/usr/bin/env python3
"""A stand-in FullEnrich bulk API, for exercising enrich_phones.py offline.

Serves the two endpoints the script uses and returns a plausible mix of
outcomes: a mobile hit, a mobile + company-HQ hit, a no-phone miss, and a
record whose `custom` blob came back as a JSON string rather than an object.
The first poll reports ENRICHING so the polling path gets exercised too.

    python3 tests/mock_fullenrich.py 877 &
    FULLENRICH_API_KEY=test python3 enrich_phones.py \
        --api-base http://127.0.0.1:8777/api/v1 --limit 4
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

SUBMITTED = {}
POLL_COUNT = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep test output clean

    def _send(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.path.endswith("/contact/enrich/bulk"):
            return self._send(404, {"error": "not found"})
        if not self.headers.get("Authorization", "").startswith("Bearer "):
            return self._send(401, {"error": "missing bearer token"})

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or "{}")
        enrichment_id = f"mock-{len(SUBMITTED) + 1}"
        SUBMITTED[enrichment_id] = body.get("datas", [])
        POLL_COUNT[enrichment_id] = 0
        self._send(200, {"enrichment_id": enrichment_id})

    def do_GET(self):
        enrichment_id = self.path.rstrip("/").split("/")[-1]
        if enrichment_id not in SUBMITTED:
            return self._send(404, {"error": "unknown enrichment id"})

        POLL_COUNT[enrichment_id] += 1
        if POLL_COUNT[enrichment_id] == 1:
            return self._send(200, {"id": enrichment_id, "status": "ENRICHING"})

        sent = SUBMITTED[enrichment_id]
        records = []
        for i, contact in enumerate(sent):
            record = {
                "firstname": contact.get("firstname"),
                "lastname": contact.get("lastname"),
                "custom": contact.get("custom"),
            }
            if i % 4 == 0:
                record["contact"] = {
                    "phones": [
                        {"number": f"+1415555{1000 + i:04d}", "type": "mobile", "confidence": 0.93}
                    ]
                }
            elif i % 4 == 1:
                record["contact"] = {
                    "phones": [
                        {"number": f"+1415555{2000 + i:04d}", "type": "mobile", "confidence": 0.81},
                        {"number": "+18005550100", "type": "company_hq"},
                    ]
                }
            elif i % 4 == 2:
                record["contact"] = {"phones": []}
            else:
                # custom echoed back as a JSON *string*, and a bare phone field
                record["custom"] = json.dumps(contact.get("custom"))
                record["contact"] = {"phone": f"+1415555{3000 + i:04d}"}
            records.append(record)

        self._send(200, {"id": enrichment_id, "status": "FINISHED", "datas": records})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8777
    print(f"mock FullEnrich on 127.0.0.1:{port}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
