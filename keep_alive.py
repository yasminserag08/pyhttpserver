import socket
import time

# Target server details
HOST = '127.0.0.1'
PORT = 8888

# 1. Forge two requests. Request 2 is glued right to the tail of Request 1.
# Both must use Connection: keep-alive
request_1 = (
    b"GET / HTTP/1.1\r\n"
    b"Host: 127.0.0.1:8888\r\n"
    b"Connection: keep-alive\r\n\r\n"
)

request_2 = (
    b"GET /profile HTTP/1.1\r\n"
    b"Host: 127.0.0.1:8888\r\n"
    b"Connection: keep-alive\r\n\r\n"
)

# Clump them into a single packet stream
clumped_packet = request_1 + request_2

print(f"[*] Connecting to server at {HOST}:{PORT}...")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))

print("[*] Sending BOTH requests simultaneously in one single packet...")
s.sendall(clumped_packet)

# Give the server a brief moment to process, then read the response channel
time.sleep(0.5)
response = s.recv(4096)

print("\n[+] Raw Data Received Back From Server:")
print("-" * 50)
print(response.decode('utf-8', errors='ignore'))
print("-" * 50)

s.close()
print("[*] Connection closed cleanly.")