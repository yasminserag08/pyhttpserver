import socket

# Create a socket IPv4 and TCP
listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Bind
HOST, PORT = '', 8888
listen_socket.bind((HOST, PORT))

# Listen
listen_socket.listen()

while True:
    # Accept
    conn, addr = listen_socket.accept()
    print("Connected to ", addr)
    
    # Read some data
    data = conn.recv(1024)

    print("Received data: ")
    print(data)

    # Send a response
    response = b"""\
HTTP/1.1 200 0K

Hello, World!
"""
    conn.sendall(response)
    conn.close()