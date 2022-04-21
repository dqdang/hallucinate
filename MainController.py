import xml.etree.ElementTree as ET
import os
import socket
import ssl
import threading
import Utils


status_file = os.path.join(Utils.DataDir, "status")
_incoming = None
_outgoing = None
_connected = False
_last_presence = ""
_createdFakePlayer = False
_status = "Offline"


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
    while _connected:
        newsocket, fromaddr = _incoming.accept()
        connstream = context.wrap_socket(newsocket, server_side=True)
        try:
            data = connstream.recv(8192)
            while data and _connected:
                content = str(data.decode("utf-8"))

                # If this is possibly a presence stanza, rewrite it.
                if "<presence" in content:
                    PossiblyRewriteAndResendPresence(content, _status)
                    print("<!--RC TO SERVER ORIGINAL-->\n" + content)
                # Don't send anything involving our fake user to chat servers
                elif "41c322a1-b328-495b-a004-5ccd3e45eae8@eu1.pvp.net" in content:
                    print("<!--RC TO SERVER REMOVED-->\n" + content)
                else:
                    _outgoing.send(data)
                    print("<!--RC TO SERVER-->\n" + content)
                data = connstream.recv(1024)
        except Exception as e:
            print(e)
        finally:
            print("Incoming closed.")
            connstream.shutdown(socket.SHUT_RDWR)
            connstream.close()
            if _connected:
                OnConnectionError()


def OutgoingLoop():
    while _connected:
        try:
            data = _outgoing.recv(8192)
            while data and _connected:
                content = str(data.decode("utf-8"))
                _incoming.send(data)
        except Exception as e:
            print("Outgoing errored.")
            if _connected:
                OnConnectionError()
        finally:
            print("Outgoing closed.")
            connstream.shutdown(socket.SHUT_RDWR)
            connstream.close()


def PossiblyRewriteAndResendPresence(content, targetStatus):
    try:
        _last_presence = content
        wrappedContent = "<xml>" + content + "</xml>"
        xml = ET.ElementTree(ET.fromstring(xmlstring))
        root = xml.getroot()
        if not root:
            return
        if not root.getchildren():
            return

        for presence in root.getchildren():
            if presence.name != "presence":
                continue
            if presence.attrib("to"):
                presence.remove()

            if not _createdFakePlayer:
                CreateFakePlayer()

            if targetStatus != "chat" or root.find("./games/league_of_legends[@st='dnd']"):
                presence.attrib["show"] = targetStatus
                root.attrib["./games/league_of_legends[@st='dnd']"] = targetStatus

            if targetStatus == "chat":
                continue

            presence.remove("status")

            if targetStatus == "mobile":
                root.remove("./games/leagueoflegends/p")
                root.remove("./games/leagueoflegends/m")
            else:
                root.remove("./games/leagueoflegends")

            root.remove("./games/bacon")
            root.remove("./games/valorant")

        xmlstr = ElementTree.tostring(xml, encoding='utf8', method='xml')
        payload = xmlstr.encode("utf-8")
        _outgoing.send(payload)
        print("<!--DECEIVE TO SERVER-->\n" + xmlstr)

    except Exception as e:
        print(e)
        print("Error rewriting presence.")


def CreateFakePlayer():
    _createdFakePlayer = True

    subscriptionMessage = "<iq from='41c322a1-b328-495b-a004-5ccd3e45eae8@eu1.pvp.net' id='fake-player' type='set'>" + \
        "<query xmlns='jabber:iq:riotgames:roster'>" + \
        "<item jid='41c322a1-b328-495b-a004-5ccd3e45eae8@eu1.pvp.net' name='&#9;Hallucinate Active!' subscription='both' puuid='41c322a1-b328-495b-a004-5ccd3e45eae8'>" + \
        "<group priority='9999'>Deceive</group>" + \
        "<id name='&#9;Deceive Active!' tagline=''/> <lol name='&#9;Hallucinate Active!'/>" + \
        "</item>" + \
        "</query>" + \
        "</iq>"
    presenceMessage = "<presence from='41c322a1-b328-495b-a004-5ccd3e45eae8@eu1.pvp.net/RC-Deceive' id='fake-player-2'>" + \
        "<games>" + \
        "<keystone><st>chat</st><s.p>keystone</s.p></keystone>" + \
        "<league_of_legends><st>chat</st><s.p>league_of_legends</s.p><p>{&quot;pty&quot;:true}</p></league_of_legends>" + \
        "<valorant><st>chat</st><s.p>valorant</s.p><p>ewoJImlzVmFsaWQiOiB0cnVlLAoJInBhcnR5SWQiOiAiMDAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAwIiwKCSJwYXJ0eUNsaWVudFZlcnNpb24iOiAicmVsZWFzZS0wMS4wNS1zaGlwcGluZy0xMC00NjAxMjkiCn0=</p></valorant>" + \
        "<bacon><st>chat</st><s.l>bacon_availability_online</s.l><s.p>bacon</s.p><s.t>1596633825489</s.t></bacon>" + \
        "</games>" + \
        "<show>chat</show>" + \
        "</presence>"

    data = subscriptionMessage.encode("utf-8")
    _incoming.send(data)
    print("<!--DECEIVE TO RC-->\n" + subscriptionMessage)
