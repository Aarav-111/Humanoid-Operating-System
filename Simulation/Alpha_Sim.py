from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import webbrowser
import os
import mimetypes
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

import urllib.request

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = "/WebData" + self.path
        if path == "/WebData/":
            path = "/WebData/index.html"
        
        file_path = os.path.join(os.getcwd(), path.lstrip("/"))

        if os.path.exists(file_path) and os.path.isfile(file_path):
            self.send_response(200)
            
            content_type, _ = mimetypes.guess_type(file_path)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.end_headers()
            
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"File Not Found")

    def do_POST(self):
        if self.path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            system_prompt = body.get("system", "")
            messages = body.get("messages", [])
            oai_messages = [{"role": "system", "content": system_prompt}] + messages
            payload = json.dumps({
                "model": "gpt-4o",
                "messages": oai_messages,
                "max_tokens": 1000,
                "temperature": 0
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {OPENAI_API_KEY}"
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read())
                reply = data["choices"][0]["message"]["content"]
                result = json.dumps({"reply": reply}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(result)
            except Exception as e:
                err = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    print("K3D Simulator → http://localhost:8080")
    webbrowser.open("http://localhost:8080")
    server.serve_forever()
