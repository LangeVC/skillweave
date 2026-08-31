import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class MockFaigateServer(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/v1/chat/completions":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            req = json.loads(post_data.decode('utf-8'))
            requested_model = req.get("model", "unknown")
            
            # Simulate silent fallback: Requested gpt-4o, but actually served by deepseek-v4-flash
            if requested_model in ("gpt-4o", "openai-gpt4o"):
                answering_model = "gpt-4o"
                served_by = "deepseek-v4-flash"
            else:
                answering_model = requested_model
                served_by = requested_model

            response = {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": 1677652288,
                "model": answering_model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Mock response"
                    },
                    "finish_reason": "stop"
                }]
            }

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('x-faigate-served-by', served_by)
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            
    def do_GET(self):
        if self.path == "/v1/models":
            models = {
                "object": "list",
                "data": [
                    {
                        "id": "gpt-4o",
                        "object": "model",
                        "owned_by": "openai"
                    },
                    {
                        "id": "deepseek-v4-flash",
                        "object": "model",
                        "owned_by": "deepseek"
                    }
                ]
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(models).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def run_server(port=0):
    server = HTTPServer(('127.0.0.1', port), MockFaigateServer)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server, thread
