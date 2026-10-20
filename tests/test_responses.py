"""Contract test only: local SSE fixture, never a claim of real AI inference."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from runtime import ResponsesLLM


class ResponsesContract(unittest.TestCase):
    def test_stream_contract_and_provider_usage(self):
        captured = []

        class Fixture(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                payload = {
                    "type": "response.completed",
                    "response": {
                        "id": "fixture",
                        "object": "response",
                        "created_at": 1,
                        "status": "completed",
                        "model": "fixture",
                        "output": [
                            {
                                "id": "msg_fixture",
                                "type": "message",
                                "role": "assistant",
                                "status": "completed",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "Final Answer: A clear answer.",
                                        "annotations": [],
                                    }
                                ],
                            }
                        ],
                        "usage": {
                            "input_tokens": 17,
                            "output_tokens": 6,
                            "total_tokens": 23,
                        },
                    },
                }
                item = payload["response"]["output"][0]
                self.wfile.write(
                    (
                        "data: "
                        + json.dumps(
                            {"type": "response.output_item.done", "output_index": 0, "item": item}
                        )
                        + "\n\n"
                    ).encode()
                )
                payload["response"]["output"] = []
                self.wfile.write(("data: " + json.dumps(payload) + "\n\n").encode())

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Fixture)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            events = []
            llm = ResponsesLLM(
                {
                    "provider": "api",
                    "api_key": "fixture-only",
                    "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "model": "fixture",
                },
                lambda k, d: events.append((k, d)),
            )
            self.assertEqual(llm.call("Hello"), "Final Answer: A clear answer.")
            self.assertFalse(captured[0]["store"])
            self.assertTrue(captured[0]["stream"])
            self.assertEqual(events[0][1]["input"], 17)
            self.assertEqual(events[0][1]["output"], 6)
        finally:
            server.shutdown()
            server.server_close()

    def test_native_function_call_and_tool_result_round_trip(self):
        captured = []

        class Fixture(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                item = (
                    {
                        "id": "fc_fixture",
                        "type": "function_call",
                        "call_id": "call_fixture",
                        "name": "image_generator",
                        "arguments": '{"request":"A dog in a balloon"}',
                        "status": "completed",
                    }
                    if len(captured) == 1
                    else {
                        "id": "msg_fixture",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Generated image attached.",
                                "annotations": [],
                            }
                        ],
                    }
                )
                payload = {
                    "type": "response.completed",
                    "response": {
                        "id": "fixture",
                        "object": "response",
                        "created_at": 1,
                        "status": "completed",
                        "model": "fixture",
                        "output": [item],
                        "usage": {"input_tokens": 5, "output_tokens": 6, "total_tokens": 11},
                    },
                }
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(("data: " + json.dumps(payload) + "\n\n").encode())

            def log_message(self, *args):
                pass

        service = HTTPServer(("127.0.0.1", 0), Fixture)
        threading.Thread(target=service.serve_forever, daemon=True).start()
        try:
            llm = ResponsesLLM(
                {
                    "provider": "api",
                    "api_key": "fixture-only",
                    "model": "fixture",
                    "base_url": f"http://127.0.0.1:{service.server_port}/v1",
                    "nativeTools": True,
                    "requireImage": True,
                },
                lambda *args: None,
            )
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "image_generator",
                        "description": "Generate an image",
                        "parameters": {
                            "type": "object",
                            "properties": {"request": {"type": "string"}},
                        },
                    },
                }
            ]
            calls = llm.call("Create an image", tools=tools)
            self.assertEqual(calls[0]["function"]["name"], "image_generator")
            self.assertEqual(
                captured[0]["tool_choice"], {"type": "function", "name": "image_generator"}
            )
            self.assertEqual(captured[0]["tools"][0]["name"], "image_generator")
            llm.generated_images.append({"url": "/artifacts/fixture/actual.png"})
            result = llm.call(
                [
                    {"role": "user", "content": "Create an image"},
                    {"role": "assistant", "content": None, "tool_calls": calls},
                    {
                        "role": "tool",
                        "tool_call_id": "call_fixture",
                        "content": '{"artifacts":["/artifacts/fixture/actual.png"]}',
                    },
                ],
                tools=tools,
            )
            self.assertEqual(result, "Generated image attached.")
            self.assertEqual(captured[1]["input"][-1]["type"], "function_call_output")
            self.assertEqual(captured[1]["input"][-1]["call_id"], "call_fixture")
            self.assertIn("actual.png", captured[1]["input"][-1]["output"])
            self.assertNotIn("tool_choice", captured[1])
        finally:
            service.shutdown()
            service.server_close()
