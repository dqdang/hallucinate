import ConfigProxy
from http.server import HTTPServer
import logging
import os
import socket
import ssl
import subprocess
import sys
import time
import Utils


HallucinateTitle = "Hallucinate" + Utils.HallucinateVersion


def main():
    # try:
    StartHallucinate(sys.argv)
    # except Exception as e:
    #     print(e)
    #     return


def deal_with_client(connstream):
    data = connstream.recv(1024)
    # empty data means the client is finished with us
    while data:
        if not do_something(connstream, data):
            # we'll assume do_something returns False
            # when we're finished with client
            break
        data = connstream.recv(1024)
    # finished with client


def StartHallucinate(args):
    allow_multiple_clients = False
    lor = False
    valorant = False
    for arg in args:
        if "--allow-multiple-clients" in arg.lower():
            allow_multiple_clients = True
        if "lor" in arg.lower():
            lor = True
        if "valorant" in arg.lower():
            valorant = True
    if (Utils.IsClientRunning() and not allow_multiple_clients):
        print("The Riot Client is currently running. In order to mask your online status, the Riot Client needs to be started by Hallucinate.")
        res = input("Do you want Deceive to stop the Riot Client and games launched by it, so that it can restart with the proper configuration? [y/N]").lower()
        if res != "y" or res != "yes":
            return
        Utils.KillProcesses()
        time.sleep(2000)

    try:
        logger = logging.getLogger("Hallucinate")
        logger.setLevel(logging.DEBUG)
        # create file handler which logs even debug messages
        fh = logging.FileHandler('debug.log')
        fh.setLevel(logging.DEBUG)
        # create console handler with a higher log level
        ch = logging.StreamHandler()
        ch.setLevel(logging.ERROR)
        # create formatter and add it to the handlers
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        # add the handlers to the logger
        logger.addHandler(fh)
        logger.addHandler(ch)
        print(HallucinateTitle)
    except:
        print(HallucinateTitle)
        # ignored; just don't save logs if file is already being accessed
        pass

    # Step 0: Make directory for data if doesn't exist
    if not os.path.exists(Utils.DataDir):
        os.mkdir(Utils.DataDir)

    # Step 1: Open a port for our chat proxy, so we can patch chat port into clientconfig
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('', 0))
    serverPort = sock.getsockname()[1]

    # Step 2: Find the Riot Client
    riotClientPath = Utils.GetRiotClientPath()
    if not riotClientPath:
        print("Hallucinate was unable to find the path to the Riot Client. If you have the game and it is working properly, \
            please file a bug report through GitHub (https://github.com/molenzwiebel/deceive) or Discord.")
        return

    # Step 3: Start proxy web server for clientconfig
    proxyServer = ConfigProxy.ConfigProxyFactory(serverPort)

    # Step 4: Start the Riot Client and wait for a connect
    game = "league_of_legends"
    if lor:
        game = "bacon"
    if valorant:
        game = "valorant"

    startArgs = "\"" + riotClientPath + "\"" + " --client-config-url=\"http://127.0.0.1:{}\" --launch-product={} --launch-patchline=live".format(serverPort, game)
    if allow_multiple_clients:
        startArgs += "--allow-multiple-clients"
    riotClient = subprocess.Popen(startArgs, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    if not riotClient:
        print("Exiting on Riot Client exit.")
        return
    
    # Step 5: Get chat server and port for this player by listening to even from ConfigProxy
    chatHost = None
    chatPort = 0
    proxyServer.PatchedChatServer.on_change(proxyServer.ChatServerEventArgs(ChatHost=chatHost, ChatPort=chatPort))
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile="Resources/cert.pem", keyfile="Resources/server.key")

    if not chatHost:
        print("Hallucinate was unable to find Riot's chat server, please try again later.")
        return

    # Step 6: Connect sockets.
    bindsocket = socket.socket()
    bindsocket.bind((chatHost, chatPort))
    bindsocket.listen(5)

    # Step 7: All sockets are now connected
    while True:
        newsocket, fromaddr = bindsocket.accept()
        connstream = context.wrap_socket(newsocket, server_side=True)
        try:
            deal_with_client(connstream)
        finally:
            connstream.shutdown(socket.SHUT_RDWR)
            connstream.close()

if __name__ == "__main__":
    main()
