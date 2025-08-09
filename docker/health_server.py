import http.server
import socketserver


class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            super().do_GET()


if __name__ == "__main__":
    PORT = 8000
    with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
        print(f"Serving health check at port {PORT}")
        httpd.serve_forever()
