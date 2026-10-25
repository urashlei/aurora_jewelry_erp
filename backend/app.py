"""
AURORA JEWELRY ERP & AI COPILOT
Main Python Application Server (Flask with automatic fallback)
"""

import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

try:
    from ai_agent import ask_gemini_or_local
except ImportError:
    from backend.ai_agent import ask_gemini_or_local


def create_flask_app():
    from flask import Flask, render_template, request, jsonify, send_from_directory

    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "frontend" / "templates"),
        static_folder=str(BASE_DIR / "frontend" / "static"),
        static_url_path="/static"
    )

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "online",
            "system": "AURORA JEWELRY ERP & AI COPILOT",
            "version": "2.5.0",
            "runtime": "Python Flask"
        })

    @app.route("/api/chat", methods=["POST"])
    @app.route("/api/ai/chat", methods=["POST"])
    def chat():
        data = request.get_json(silent=True) or {}
        message = data.get("message", "").strip()
        history = data.get("history", [])
        erp_context = data.get("erpContext") or data.get("erp_context") or {}

        if not message:
            return jsonify({"error": "Message cannot be empty"}), 400

        result = ask_gemini_or_local(message, history, erp_context)
        return jsonify(result)

    return app


def run_standalone_server(port=3000):
    """Fallback using Python standard library http.server if Flask is not installed."""
    import http.server
    import socketserver
    import urllib.parse

    template_file = BASE_DIR / "frontend" / "templates" / "index.html"
    static_dir = BASE_DIR / "frontend" / "static"

    class ErpHttpHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            parsed_path = urllib.parse.urlparse(self.path).path
            if parsed_path in ["/", "/index.html"]:
                if template_file.exists():
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    with open(template_file, "rb") as f:
                        self.wfile.write(f.read())
                    return
            elif parsed_path.startswith("/static/"):
                rel_path = parsed_path[8:]
                target_file = static_dir / rel_path
                if target_file.exists() and target_file.is_file():
                    content_type = "text/css" if target_file.suffix == ".css" else "application/octet-stream"
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.end_headers()
                    with open(target_file, "rb") as f:
                        self.wfile.write(f.read())
                    return
            elif parsed_path == "/api/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "online", "runtime": "Python stdlib"}).encode())
                return

            self.send_error(404, "Not Found")

        def do_POST(self):
            parsed_path = urllib.parse.urlparse(self.path).path
            if parsed_path in ["/api/chat", "/api/ai/chat"]:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                try:
                    data = json.loads(body)
                except Exception:
                    data = {}

                message = data.get("message", "").strip()
                history = data.get("history", [])
                erp_context = data.get("erpContext") or data.get("erp_context") or {}

                result = ask_gemini_or_local(message, history, erp_context)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                return

            self.send_error(404, "Not Found")

    with socketserver.TCPServer(("0.0.0.0", port), ErpHttpHandler) as httpd:
        print(f"[AURORA JEWELRY ERP] Standalone Python server active at http://localhost:{port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


def main():
    port = int(os.environ.get("PORT", 3000))
    print("=" * 60)
    print("  AURORA JEWELRY ERP & AI COPILOT")
    print(f"  Starting server on port {port}...")
    print("=" * 60)

    try:
        import flask
        app = create_flask_app()
        app.run(host="0.0.0.0", port=port, debug=False)
    except ImportError:
        print("[Notice] Flask not detected. Running high-performance built-in Python HTTP server.")
        run_standalone_server(port=port)


if __name__ == "__main__":
    main()
