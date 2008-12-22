// uses MochiKit

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
  	  }
	  
  	  if (updateStatus) {
  	      this.callMpd("status");
  	  }

          return result;
	}));
	d.addErrback(method(this, function (err) {
	    console.log("XHR failed:", err.message);
	    // TODO: fire statusChanged with the message on an
	    // appropriate attribute of the status obj
	}));
      return d;
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
};
