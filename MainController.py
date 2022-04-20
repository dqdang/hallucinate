import os
import sockets
import ssl
import threading
import Utils

status_file = os.path.join(Utils.DataDir, "status")
_incoming = None
_outgoing = None
_connected = False
_last_presence = ""
_createdFakePlayer = False

def StartThreads(incoming, outgoing):
    _incoming = incoming
    _outgoing = outgoing
    _connected = True
    _createdFakePlayer = True
    incoming_thread = threading.Thread(target=IncomingLoop)
    outgoing_thread = threading.Thread(target=OutgoingLoop)
    incoming_thread.start()
    outgoing_thread.start()


def IncomingLoop():
    bytecount = 0
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    # context.load_cert_chain(certfile="mycertfile", keyfile="mykeyfile")

    bindsocket = socket.socket()
    bindsocket.bind('myaddr.mydomain.com', 10023)
    bindsocket.listen(5)

    while True:
        newsocket, fromaddr = bindsocket.accept()
        connstream = context.wrap_socket(newsocket, server_side=True)
        try:
            deal_with_client(connstream)
        finally:
            connstream.shutdown(socket.SHUT_RDWR)
            connstream.close()