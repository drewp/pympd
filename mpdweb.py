"""
HTTP interface to mpd. All commands are JSON, so you can easily make
javascript-based players.

todo:
most commands should accept POST only; status/etc should be GET

status should be able to return a 304 Not Modified


"""
import sys, optparse, inspect, logging, os, urlparse
from twisted.internet import reactor, defer
import twisted.python.log
from zope.interface import implements
from nevow import json, rend, appserver, inevow, loaders, static, tags as T
import pympd

log = logging.getLogger()

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
            log.debug("result %s", str(ret)[:1000])
            return json.serialize(ret)

        request = inevow.IRequest(ctx)
        request.setHeader("Content-Type", "application/json")

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
        if methodName == 'lsinfoTree':
            return self.child_lsinfoTree(ctx), []
        if methodName.startswith('_'):
            raise ValueError("command: %s" % methodName)

        mpdMethod = getattr(self.mpd, methodName)
        callArgs = argsFromPostOrGet(mpdMethod, postDataFromCtx(ctx), ctx)
        log.debug("Command: %s(%r)", mpdMethod.__name__, callArgs)
        return JsonResult(mpdMethod(**callArgs)), []

    def child_lsinfoTree(self, ctx):
        """extjs tree makes POST requests with a 'node' arg, and
        expects child node definitions
        http://extjs.com/deploy/dev/docs/output/Ext.tree.TreeLoader.html
        """
        d = self.mpd.lsinfo(directory=ctx.arg('node')) # untrusted
        def formatChildren(result):
            ret = []
            for child in result:
                name = child[1].decode('utf-8')
                base = name.rsplit('/',1)[-1]
                ret.append({u'id':name,
                            u'text':base,
                            u'leaf':child[0] == 'file'})
            return json.serialize(ret)
            
        return d.addCallback(formatChildren)

        return "[{id:1,text:'hi',leaf:true}]"

def argsFromPostOrGet(method, postData, ctx):
    """return an args dict based on the json-encoded postdata (or form urlencoded),
    considering only args that the method callable accepts"""
    postArgs = {}
    if postData:

        if inevow.IRequest(ctx).getHeader('Content-Type').startswith("application/x-www-form-urlencoded"):
            postArgs = dict(urlparse.parse_qsl(postData))
        else:
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
        elif ctx.arg(name):
            callArgs[name] = ctx.arg(name)
    return callArgs

class Mpdweb(rend.Page):
    docFactory = loaders.stan(T.html[T.body[
        T.h1["mpdweb server"],
        T.directive('pages'),
        ]])
    pages = []
    def __init__(self):
        rend.Page.__init__(self)
        self.mpd = pympd.Mpd(requireFloatTimes=False)
        # i forget why the caller has to do this connect. Maybe to
        # control auto-reconnect behavior?
        reactor.connectTCP('localhost', 6600, self.mpd)

    def render_pages(self, ctx, data):
        for p in self.pages:
            yield T.li[T.a(href=p)[p]]
        
    def child_mpd(self, ctx):
        """e.g. /mpd/pause"""
        return MpdCommand(self.mpd)        

for filename in ['ctl.html',
                 'gadget.html',
                 'library.html',
                 'playlist.html',
                 'volume.html',
                 'current.html',
                 'tiny.html',
                 'ctl.css',
                 ]:
    f = static.File(os.path.join('ui', filename))

    # i'll need this content-type if I do inline SVG graphics, but it
    # causes some things to break, like the extjs tree widget. Some
    # innerHTML gets set that's not valid XML, I think. Konqueror
    # seems to do fine.
    # https://bugzilla.mozilla.org/show_bug.cgi?id=155723
    # and https://bugzilla.mozilla.org/show_bug.cgi?id=466751
    #f.type, f.encoding = 'application/xhtml+xml', 'UTF-8'

    shortName = filename.replace('.html', '')
    setattr(Mpdweb, 'child_' + shortName, f)
    Mpdweb.pages.append(shortName)

for filename in ['MochiKit-custom1.js',
                 'mpd.js',
                 'ext-controls.js',
                 'ext-2.2',
                 'priv.js',
                 ]:
    setattr(Mpdweb, 'child_'+filename, static.File(filename))

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = optparse.OptionParser()
    parser.add_option('-p', '--port', help='port to listen on',
                      type='int', default=9003)
    parser.add_option('-d', '--debug', help='log all commands',
                      action='store_true')
    opts, args = parser.parse_args()

    if opts.debug:
        log.setLevel(logging.DEBUG)

    twisted.python.log.startLogging(sys.stdout)

    reactor.listenTCP(opts.port, appserver.NevowSite(Mpdweb()))
    reactor.run()

