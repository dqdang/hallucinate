from http.server import BaseHTTPRequestHandler, HTTPServer
from events import Events
import json
import jwt
import os
import requests
import socket
import time
import Utils


hostName = "localhost"


def ConfigProxyFactory(serverPort):
    class ConfigProxy(BaseHTTPRequestHandler):

        def do_GET(self):
            self.proxy_and_write_responses()

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
            # print("ORIGINAL CLIENTCONFIG:", content)
            modifiedContent = json.dumps(content)
            # try:
            if result.ok:
                configObject = result.json()

                riotChatHost = None
                riotChatPort = 0

                # Set fallback host to localhost
                if "chat.host" in configObject:
                    riotChatHost = str(configObject["chat.host"])
                    configObject["chat.host"] = "127.0.0.1"

                if "chat.port" in configObject:
                    riotChatPort = int(str(configObject["chat.port"]))
                    configObject["chat.port"] = serverPort

                if "chat.affinities" in configObject:
                    affinities = configObject["chat.affinities"]
                    if bool(configObject["chat.affinity.enabled"]):
                        pas_url = "https://riot-geo.pas.si.riotgames.com/pas/v1/service/chat"
                        pas_header = {
                            "Authorization": self.headers["authorization"]
                        }
                        pasJWT = requests.get(pas_url, headers=pas_header)
                        affinity = jwt.decode(pasJWT.text, options={
                                              "verify_signature": False})["affinity"]
                        riotChatHost = str(affinities[affinity])

                    for key in affinities.keys():
                        affinities[key] = "127.0.0.1"

                # Allow an invalid cert.
                if "chat.allow_bad_cert.enabled" in configObject:
                    configObject["chat.allow_bad_cert.enabled"] = True

                modifiedContent = json.dumps(configObject)
                # print("MODIFIED CLIENTCONFIG:", modifiedContent)

                if riotChatHost != None and riotChatPort != 0:
                    h = hash(riotChatHost + str(riotChatPort))
                    if h < 0:
                        h = -1 * h
                    with open(os.path.join(Utils.DataDir, str(h) + ".cht"), "w+") as f:
                        lines = f.readlines()
                        if len(lines) == 0:
                            f.write(riotChatHost + "\n")
                            f.write(str(riotChatPort))
                        elif len(lines) > 1 and lines[0].strip() != riotChatHost or lines[1].strip() != riotChatPort:
                            f.write(riotChatHost + "\n")
                            f.write(str(riotChatPort))

            # except Exception as e:
            #     print(e)

            responseBytes = bytes(modifiedContent, "utf-8")
            self.send_response(int(result.status_code))
            self.send_header("Content-type", "application/json")
            self.send_header("Content-Length", len(responseBytes))
            self.end_headers()
            self.wfile.write(responseBytes)

    return ConfigProxy
