from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = b'DCGM_FI_DEV_GPU_UTIL{gpu="0"} 42\nDCGM_FI_DEV_FB_USED{gpu="0"} 1024\nDCGM_FI_DEV_GPU_TEMP{gpu="0"} 55\n'
        self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers(); self.wfile.write(data)
    def log_message(self, *_): pass
HTTPServer(("0.0.0.0", 9400), Handler).serve_forever()
