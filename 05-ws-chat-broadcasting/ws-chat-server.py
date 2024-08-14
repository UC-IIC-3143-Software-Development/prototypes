import asyncio
import json
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

import websockets

clients = set()

chat_history = []


async def handle_client(websocket, path):
    # Agregar cliente al set
    clients.add(websocket)
    username = "Anonymous"
    try:
        async for message in websocket:
            data = json.loads(message)
            if data["type"] == "join":
                username = data["username"]
                join_message = {
                    "type": "message",
                    "username": "System",
                    "content": f"{username} has joined the chat.",
                    "timestamp": datetime.now().isoformat(),
                }
                await broadcast(json.dumps(join_message))
            elif data["type"] == "message":
                chat_message = {
                    "type": "message",
                    "username": username,
                    "content": data["content"],
                    "timestamp": datetime.now().isoformat(),
                }
                chat_history.append(chat_message)
                await broadcast(json.dumps(chat_message))
    finally:
        # Remover cliente del set
        clients.remove(websocket)
        leave_message = {
            "type": "message",
            "username": "System",
            "content": f"{username} has left the chat.",
            "timestamp": datetime.now().isoformat(),
        }
        await broadcast(json.dumps(leave_message))


async def broadcast(message):
    # Envia mensaje a todos los clientes conectados
    for client in clients:
        try:
            await client.send(message)
        except websockets.exceptions.ConnectionClosed:
            pass


def run_http_server():
    handler = SimpleHTTPRequestHandler
    httpd = TCPServer(("", 8000), handler)
    print("Serving HTTP on port 8000...")
    httpd.serve_forever()


async def main():
    http_thread = threading.Thread(target=run_http_server)
    http_thread.start()

    server = await websockets.serve(handle_client, "localhost", 8765)
    print("Chat server started on ws://localhost:8765")
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
