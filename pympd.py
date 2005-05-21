# python interface to mpd using twisted

from twisted.internet import defer, protocol, reactor
from twisted.protocols import basic
import logging
logging.basicConfig()
log = logging.getLogger("mpd")
#log.setLevel(logging.DEBUG)

class QueueingCommandClientFactory(protocol.ReconnectingClientFactory):

    """protocol to send commands to a server, even if the connection
    sometimes gets lost. Commands can receive responses.

    There should be a setting to describe if a response could come
    after a reconnection (unlikely) or whether we should forget about
    all pending responses if there's a reconnection."""

    # set this to a protocol that can send commands and return their
    # results. the command sender method shall be called 'send' and
    # the responses should go to 'self.factory.response'
    protocol = None

    def __init__(self):
        self.commands = []
        self.responseDeferreds = []
        self.conn = None

    def buildProtocol(self, addr):
        self.resetDelay()
        self.conn = self.protocol(self.responseReceived,
                                  self.errorReceived)
        
        self.conn.connectionMade = self.trySendingCommands

        return self.conn

    def trySendingCommands(self):
        while self.commands:
            if self.conn is not None and self.conn.connected:
                self.conn.send(self.commands.pop(0))
            else:
                break        
    
    def send(self,command):
        """returns a deferred which will be called with the response
        for this command"""
        
        self.commands.append(command)
        d = defer.Deferred()
        self.responseDeferreds.append(d)

        self.trySendingCommands()
        return d

    def responseReceived(self,resp,_err=False):
        """connection calls this when the server gives us a response"""
        if self.responseDeferreds:
            d = self.responseDeferreds.pop(0)
            if not _err:
                d.callback(resp)
            else:
                d.errback(resp)
        else:
            log.info("Received a stray response for which we had no command deferred waiting: %r",resp)

    def errorReceived(self,resp):
        """connection calls this when the server gives an error"""
        self.responseReceived(resp,_err=True)

    def queuedCommands(self):
        """list of the commands that have not been sent yet (the head
        of the list will get sent next)"""
        return self.commands

class MpdError(Exception):
    pass

class MpdConnection(basic.LineReceiver):
    delimiter = "\n"

    def __init__(self, responseReceived, errorReceived):
        self.responseReceived = responseReceived
        self.errorReceived = errorReceived
        self.resp = []
        
    def connectionMade(self):
        log.debug("connected")
        self.transport.write("status\n")

    def send(self,command):
        self.transport.write(command+"\n")

    def lineReceived(self, data):
        if data.startswith("OK MPD"):
            log.debug("server greets with %s",data)
            return
        
        if data == "OK":
            log.debug("got full response %r" % self.resp)
            self.responseReceived(self.resp)
            self.resp = []
        elif data.startswith("ACK"):
            log.error("mpd said %r %r" % (self.resp,data))
            self.errorReceived(MpdError(data))
            self.resp = []
        else:
            self.resp.append(data)

def colonDictParse(lines,obj):
    """sets attributes of obj based on lines of 'key: value'. auto
    conversion to float/int"""
    for line in lines:
        try:
            key,val = line.split(": ",1)
        except ValueError:
            log.error("couldnt parse mpd line: %r",line)
            raise

        try:
            val = int(val)
        except ValueError:
            try:
                val = float(val)
            except ValueError:
                pass

        if not key.startswith('_'):
            setattr(obj,key,val)

class Mpd(QueueingCommandClientFactory):
    """http://mpd.wikicities.com/wiki/MusicPlayerDaemonCommands
    (someone should put those descriptions into docstrings here, for
    better pydoc"""
    
    protocol = MpdConnection

    def play(self,songnum=None):
        songpart = ""
        if songnum is not None:
            songpart = " %d" % songnum
        return self.send("play" + songpart)

    def pause(self):
        return self.send("pause")

    def stop(self):
        return self.send("stop")

    def clear(self):
        return self.send("clear")

    def add(self,path):
        return self.send("add %s" % path)

    def seek(self,seconds,song=None):
        """please note reverse order of arguments from the protocol.
        If you omit song, the current song number will be retrieved
        and used."""

        def finish(song,seconds):
            return self.send("seek %s %s" % (song, seconds))

        # this would err if seconds was a float and mpd was not
        # patched to accept those. you'll get the error as an errback
        # with a good message, i think
        
        if song is None:
            return self.status().addCallback(lambda s:
                                             finish(s.song,seconds))
        else:
            return finish(song,seconds)

    def currentsong(self):
        def parse(result):
            class Song:
                pass
            s = Song()
            colonDictParse(result,s)
            return s
        return self.send("currentsong").addCallback(parse)
        
    def status(self):
        """returns Status obj with attributes based on mpd status,
        plus extra attributes time_elapsed, time_total"""
        def parse(result):
            class Status:
                def __repr__(self):
                    return repr(self.__dict__)
            d = Status()
            colonDictParse(result, d)
            if hasattr(d,'timefloat'):
                d.time_elapsed, d.time_total = [float(t) for t in
                                                d.timefloat.split(':')]
            else:
                if hasattr(d,'time'):
                    raise RuntimeError("your mpd has not been patched to deliver the timefloat status attribute")
            return d
        return self.send("status").addCallback(parse)

if __name__ == '__main__':
    f = Mpd()
    def printer(x): print x
    f.status().addCallback(printer)
    f.play()
    f.seek(0)
    reactor.connectTCP('localhost', 6600, f)
    reactor.callLater(1,f.pause)
    reactor.run()
