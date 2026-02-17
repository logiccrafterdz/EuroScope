"""
Minimal HTTP Health Check Server
"""
import http.server
import threading
import logging

logger = logging.getLogger("euroscope.utils.health_check")

class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silence default logging to avoid cluttering bot logs
        pass

class HealthCheckServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        try:
            self.server = http.server.HTTPServer((self.host, self.port), HealthCheckHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logger.info(f"Health check server started on {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start health check server: {e}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            logger.info("Health check server stopped")
