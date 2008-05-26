"""
HTTP interface to mpd. All commands are JSON, so you can easily make
javascript-based players.

todo:
most commands should accept POST only; status/etc should be GET




"""
import sys, optparse, inspect
from twisted.web import http, server, client
from twisted.web.resource import Resource
from twisted.internet import reactor, defer
import twisted.web
from twisted.python import log
from zope.interface import implements, providedBy
from nevow import json, rend, appserver, inevow, tags as T, loaders, static
import pympd


def postDataFromCtx(ctx):
    content = inevow.IRequest(ctx).content
    content.seek(0)
    return content.read()

class JsonResult(object):
    """make a pympd result object serve as JSON"""
    implements(inevow.IResource)
    def __init__(self, result):
        self.result = result
        
    def locateChild(self, ctx, segments):
        raise NotImplementedError

    def renderHTTP(self, ctx):
        def convert(result):
            if hasattr(result, 'jsonState'):
                ret = result.jsonState()
            else:
                ret = result
            print "result", ret
            return json.serialize(ret)

        request = inevow.IRequest(ctx)
        request.setHeader("Content-Type", "text/javascript")

        if isinstance(self.result, defer.Deferred):
            self.result.addCallback(convert)
            return self.result
        return convert(self.result)

class MpdCommand(object):
    """run an mpd command like 'seek', where the postdata is a JSON
    dict of args to pass to the mpd method. The (deferred) result of
    the mpd call is returned as a JSON resource."""
    implements(inevow.IResource)
    def __init__(self, mpd):
        self.mpd = mpd
        
    def renderHTTP(self, ctx):
        raise NotImplementedError
        
    def locateChild(self, ctx, segments):
        methodName = segments[0]
        if methodName.startswith('_'):
            raise ValueError("command: %s" % methodName)

        mpdMethod = getattr(self.mpd, methodName)
        callArgs = argsFromPost(mpdMethod, postDataFromCtx(ctx))
        return JsonResult(mpdMethod(**callArgs)), []

def argsFromPost(method, postData):
    """return an args dict based on the json-encoded postdata,
    considering only args that the method callable accepts"""
    postArgs = {}
    if postData:
        postArgs = json.parse(postData)

    acceptedArgs, _, _, _ = inspect.getargspec(method)
    callArgs = {}
    for name in acceptedArgs:
        if name == 'self':
            continue
        if name in postArgs:
            v = postArgs[name]
            if isinstance(v, unicode):
                v = v.encode('utf-8')
            callArgs[name] = v
    return callArgs

class Mpdweb(rend.Page):
    docFactory = loaders.stan(["mpdweb server"])
    def __init__(self):
        rend.Page.__init__(self)
        self.mpd = pympd.Mpd(requireFloatTimes=False)
        # i forget why the caller has to do this connect. Maybe to
        # control auto-reconnect behavior?
        reactor.connectTCP('localhost', 6600, self.mpd)

    def child_ctl(self, ctx):
        return static.File("ctl.html")

    def child_mpd(self, ctx):
        """e.g. /mpd/pause"""
        return MpdCommand(self.mpd)        

setattr(Mpdweb, 'child_MochiKit-r1383.js', static.File('MochiKit-r1383.js'))

if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option('-p', '--port', help='port to listen on',
                      type='int', default=9003)
    opts, args = parser.parse_args()

    log.startLogging(sys.stdout)

    reactor.listenTCP(opts.port, appserver.NevowSite(Mpdweb()))
    reactor.run()

