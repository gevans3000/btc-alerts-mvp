
import socket
import base64
import hashlib
import json
import time

def test_ws():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("localhost", 8000))
    
    key = base64.b64encode(b"test").decode()
    handshake = (
        "GET /ws HTTP/1.1\r\n"
        "Host: localhost:8000\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: {}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).format(key).encode()
    
    sock.send(handshake)
    response = sock.recv(1024)
    print("Handshake received")
    
    # Read one frame
    data = sock.recv(4096)
    if not data:
        print("No data")
        return
        
    # Simple WS frame decoder (ignoring mask since server to client shouldn't be masked)
    byte1 = data[0]
    byte2 = data[1]
    length = byte2 & 127
    payload = data[2:2+length].decode("utf-8")
    
    msg = json.loads(payload)
    print(f"WS Keys: {list(msg.keys())}")
    if "flows" in msg:
        print(f"Flows: {msg['flows']}")
    if "derivatives" in msg:
        print(f"Derivatives: {msg['derivatives']}")

if __name__ == "__main__":
    test_ws()
