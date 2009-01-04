// uses MochiKit

// this should be made internal to the player
_mpdLog = {};

/*
Add <li> children to this node for each command we send to mpd
*/
function logMpdCommands(node) {
    var append = function (command, args, result) {
	appendChildNodes(node,
			 LI(null, "Command: " + 
			    serializeJSON(command) + " " +
			    serializeJSON(args) + "-> " + 
			    serializeJSON(result)));
    };

    connect(_mpdLog, 'lastCmd', append);
}

/*
 Call func with a status object whenever the mpd status might have changed.
*/
function observeStatus(func) {
    connect(_mpdLog, 'statusChanged', func);
}

/* 
Call func *with nothing* whenever the playlist might have
changed. Func has to get the playlist itself if it wants to know the
new contents.
*/
function observePlaylist(func) {
   connect(_mpdLog, 'playlistChanged', func);
}

var mpd = {}
mpd.Mpd = function(site) {
    /*
      site is like 'http://localhost:9001/' or '/'
    */
    this.site = site;
};

mpd.Mpd.prototype = {
    __class__: mpd.Mpd,

    /* 
      Run an mpd command. Pass args as a named dict. Set updateStatus to
      follow this call with a 'status' command, whose result would go to
      your status observers

    */
    callMpd: function(command, args, updateStatus) {
      if (!args) {
          args = {};
      }
      var d = doXHR(this.site + "mpd/"+command, {
	  method: "POST", 
          sendContent: serializeJSON(args)
      });
      d.addCallback(method(this, function (xhr) {
          var result = evalJSONRequest(xhr);
  	  signal(_mpdLog, 'lastCmd', command, args, result);

  	  if (command == "status") {
  	      signal(_mpdLog, 'statusChanged', result);
	      this._currentSong(result);
	      this._playState(result);
  	  }
	  
  	  if (updateStatus) {
  	      this.callMpd("status");
  	  }

          return result;
	}));
	d.addErrback(method(this, function (err) {
	    console.log("XHR failed:", err);
	    // TODO: fire statusChanged with the message on an
	    // appropriate attribute of the status obj
	}));
      return d;
    },

    /*
      send 'currentSong' event if the current song has changed. The
      event has one argument, which is some displayable name for the
      song.

      In fact, there are sometimes 3+ relevant titles for what's
      playing, so this may need to be expanded with a richer return
      value.

      We probably need a method that forces a currentSong event, for
      when a UI forgets the last currentSong result.  
    */
    _currentSong: function (status) {
	if (status.songid != this._lastCurrentSongId || 
	    this._isPlayingStream()) {
	    this._lastCurrentSongId = status.songid;
	    player.callMpd("currentsong", {}).addCallback(
		method(this, function (info) {
		    signal(_mpdLog, 'currentSong', 
			   info.Title || info.Name || info.file);
		    this._currentFile = info.file;
		}));
	}
    },


    /*
      send 'playState' event if the play state has changed. The
      event will get a string 'play', 'stop', or 'pause'
    */
    _playState: function (status) {
	if (status.state != this._lastPlayState) {
	    this._lastPlayState = status.state;
	    signal(_mpdLog, 'playState', status.state);
	}
    },

    /*
       Is the currently playing song a stream that could contain changing 
       name/title fields?
    */
    _isPlayingStream: function () {
	return MochiKit.Text.startsWith('http://', this._currentFile);
    },

    /*
      Clear playlist, add the given filename, and start playing it.
    */
    playOne: function (filename) {
	this.callMpd("clear").addCallback(method(this, function (result) {
	    this.callMpd("add", {path: filename}).addCallback(
		method(this, function (result) {
		    signal(_mpdLog, 'playlistChanged');
		    this.callMpd("play", {songnum:0}, true);
		}));
	}));
    },

    /*
      Add the given filename and start playing it. Filename can be a directory.
    */
    addPlay: function (filename) {
	this.callMpd("status").addCallback(method(this, function(status) {
	    var lastPos = status['playlistlength'] - 1;
	    this.callMpd("add", {path: filename}, false).addCallback(
		method(this, function (result) {
		    signal(_mpdLog, 'playlistChanged');
		    this.callMpd("play", {songnum:lastPos+1}, true);
		}));
	}));
    },

    /*
      Play the song with the given playlist position
    */
    playPos: function (pos) {
	this.callMpd("play", {songnum: pos}, true);
    },

    delId: function (id) {
	this.callMpd("deleteid", {songid: id});
	signal(_mpdLog, 'playlistChanged');
	this.callMpd("status");
    },

    /*
      request status every 5 seconds. This fires various mochikit signals
    */
    startPolling: function() {
	Ext.TaskMgr.start({run: function() { this.callMpd("status") },
			   interval: 5000,
			   scope: this});
    },

    // API modeled after extjs's. They have some other args that I'm
    // not taking, yet. I could just use the extjs Observable
    // superclass, but so far this module is independent of extjs.
    on: function(signal, handler) {
	connect(_mpdLog, signal, handler);
    }
    
};
