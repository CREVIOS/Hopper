from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = {"kind": "PodList", "apiVersion": "v1", "items": []}
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
    def do_POST(self): self.do_GET()
    def do_DELETE(self): self.do_GET()
    def log_message(self, *_): pass
HTTPServer(("0.0.0.0", 6443), Handler).serve_forever()
