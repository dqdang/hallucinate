from http.server import BaseHTTPRequestHandler, HTTPServer
from events import Events
import json
import jwt
import requests
import socket
import time

hostName = "localhost"

def ConfigProxyFactory(chatPort):
    class ConfigProxy(BaseHTTPRequestHandler):
        PatchedChatServer = Events()
        class ChatServerEventArgs:
            def __init__(self, ChatHost, ChatPort):
                self.ChatHost = ChatHost
                self.ChatPort = ChatPort

        def do_GET(self):
            self.proxy_and_write_responses()
            self.wfile.write(bytes("<html><head><title>Config Proxy</title></head>", "utf-8"))
            self.wfile.write(bytes("<p>Request: %s</p>" % self.path, "utf-8"))
            self.wfile.write(bytes("<body>", "utf-8"))
            self.wfile.write(bytes("<p>Hallucinate</p>", "utf-8"))
            self.wfile.write(bytes("</body></html>", "utf-8"))
            # self.wfile.write(bytes(json.dumps({'hello': 'world', 'received': 'ok'}), "utf-8"))

        def proxy_and_write_responses(self):
            '''
            Proxies any request made to this web server to the clientconfig service. Rewrites the response
            to have any chat servers point to localhost at the specified port.
            '''
            url = "https://clientconfig.rpg.riotgames.com" + self.path
            headers = {
                "User-Agent": self.headers["User-Agent"],
            }

            # Add authorization headers for player config
            if self.headers["x-riot-entitlements-jwt"]:
                headers["X-Riot-Entitlements-JWT"] = self.headers["x-riot-entitlements-jwt"]
            if self.headers["authorization"]:
                headers["Authorization"] = self.headers["authorization"]

            result = requests.get(url, headers=headers)
            content = result.text
            print("ORIGINAL CLIENTCONFIG:", content)
            modifiedContent = content
            try:
                if result.ok:
                    configObject = result.json()

                    riotChatHost = None
                    riotChatPort = 0

                    # Set fallback host to localhost
                    if configObject["chat.host"]:
                        riotChatHost = str(configObject["chat.host"])
                        configObject["chat.host"] = "127.0.0.1"

                    if configObject["chat.port"]:
                        riotChatPort = int(str(configObject["chat.port"]))
                        configObject["chat.port"] = chatPort

                    if configObject["chat.affinities"]:
                        affinities = configObject["chat.affinities"]
                        if bool(configObject["chat.affinity.enabled"]):
                            pas_url = "https://riot-geo.pas.si.riotgames.com/pas/v1/service/chat"
                            pas_header = {
                                "Authorization": self.headers["authorization"]
                            }
                            pasJWT = requests.get(pas_url, headers=pas_header)
                            # print("PAS TOKEN:", pasJWT)
                            affinity = jwt.decode(pasJWT.json(), options={"verify_signature": False})["affinity"]
                            riotChatHost = str(affinities[affinity])

                    for key in affinities.keys():
                        affinities[key] = "127.0.0.1"

                    # Allow an invalid cert.
                    if configObject["chat.allow_bad_cert.enabled"]:
                        configObject["chat.allow_bad_cert.enabled"] = True

                    modifiedContent = json.decode(configObject)
                    # print("MODIFIED CLIENTCONFIG:", modifiedContent)

                    if riotChatHost != None and riotChatPort != 0:
                        self.PatchedChatServer.on_change(self.ChatServerEventArgs(ChatHost=riotChatHost, ChatPort=riotChatPort))

            except Exception as e:
                print(e)

            responseBytes = bytes(modifiedContent, "utf-8")
            self.send_response(result.status_code)
            self.send_header("Content-type", "application/json")
            self.send_header("Content-Length", len(responseBytes))
            self.end_headers()
            self.wfile.write(responseBytes)

    return ConfigProxy


if __name__ == "__main__":
    chatPort = 9070
    sock = socket.socket()
    sock.bind(('', 0))
    serverPort = sock.getsockname()[1]
    proxy = ConfigProxyFactory(chatPort)
    webServer = HTTPServer((hostName, serverPort), proxy)
    print("Server started http://%s:%s" % (hostName, serverPort))
    try:
        webServer.serve_forever()
    except KeyboardInterrupt:
        pass

    webServer.server_close()
    print("Server stopped.")
