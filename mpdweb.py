"""
HTTP interface to mpd. All commands are JSON, so you can easily make
javascript-based players.

todo:
most commands should accept POST only; status/etc should be GET

status should be able to return a 304 Not Modified


"""
import sys, optparse, inspect, logging, os, urlparse, socket
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
            try:
                return json.serialize(ret)
            except TypeError:
                # out of sync with mpd? let supervisor restart us
                raise SystemExit

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
        inevow.IRequest(ctx).setHeader("Content-Type", "application/json")
        host, port = self.mpd.conn.transport.addr
        return json.serialize({
            u"host" : socket.gethostname().decode('ascii'),
            u"mpd" : {u"host" : host.decode('ascii'), u"port" : port}})
        
    def locateChild(self, ctx, segments):
        methodName = segments[0]
        if methodName == 'lsinfoTree':
            return self.child_lsinfoTree(ctx), []
        local = getattr(self, 'child_' + methodName, None)
        if local is not None:
            return local(ctx), []
        if methodName.startswith('_'):
            raise ValueError("command: %s" % methodName)

        mpdMethod = getattr(self.mpd, methodName)
        callArgs = argsFromPostOrGet(mpdMethod, postDataFromCtx(ctx), ctx)
        log.debug("Command: %s(%r)", mpdMethod.__name__, callArgs)
        return JsonResult(mpdMethod(**callArgs)), []

    def child_playlists(self, ctx):
        d = self.mpd.lsinfo("")
        def findPlaylists(result):
            request = inevow.IRequest(ctx)
            request.setHeader("Content-Type", "application/json")
            return json.serialize({u'playlists' : [
                {u'name' : row[1].decode('utf8')}
                for row in result if row[0] == 'playlist']})

        return d.addCallback(findPlaylists)

    def child_currentPlaylist(self, ctx):
        req = inevow.IRequest(ctx)
        if req.method in "PUT":
            playlist = postDataFromCtx(ctx)
            if playlist.startswith("{"):
                # preferred mode sends json
                playlist = json.parse(playlist)['name'].encode('utf8')
            if not playlist:
                raise ValueError("need name=playlist")
            return self.mpd.clear().addCallback(
                lambda result: self.mpd.load(playlist))
        else:
            raise NotImplementedError

    def child_volume(self, ctx):
        req = inevow.IRequest(ctx)
        if req.method in "PUT":
            return self.mpd.setvol(int(postDataFromCtx(ctx))).addCallback(
                lambda result: "ok")
        else:
            raise NotImplementedError

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

    @defer.inlineCallbacks
    def child_getMusicState(self, ctx):
        """returns a json object suitable for passing to
        setMusicState. The consumer will now have the same playlist
        and current song/position as the producer.

        post this with a stop=0 arg if you also want to stop the
        playback, which might be suitable if you're passing the
        playback from one mpd instance to another. The value to stop
        is the delay in seconds before stopping.
        """
        req = inevow.IRequest(ctx)
            
        status = yield self.mpd.status()
        pl = yield self.mpd.playlistinfo()

        if ctx.arg('stop') is not None:
            if req.method != 'POST':
                raise ValueError("must use POST to affect playback")
            reactor.callLater(float(ctx.arg('stop')), self.mpd.stop)
        
        defer.returnValue(json.serialize({
            u'status' : status.jsonState(),
            u'playlist' : pl.jsonState()}))

    @defer.inlineCallbacks
    def child_setMusicState(self, ctx):
        """
        post a json object from a getMusicState call. The current
        playlist will be cleared and replaced with the input
        one. Playback will pick up where the input says to
        """
        data = json.parse(postDataFromCtx(ctx))
        yield self.mpd.clear()
        startNum = None
        for num, row in enumerate(data['playlist']):
            yield self.mpd.add(row['file'].encode('utf-8'))
            if row['Id'] == data['status']['songid']:
                startNum = num
        if startNum is not None and data['status']['state'] == 'play':
            yield self.mpd.seek(int(data['status']['time'].split(':')[0]),
                                startNum)
        defer.returnValue('ok')
        

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
                 'static',
                 ]:
    f = static.File(os.path.join('ui', filename))
    f.contentTypes = {'.html':'application/xhtml+xml',
                      '.css':'text/css'}

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
                 'jquery-1.4.3.min.js',
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

