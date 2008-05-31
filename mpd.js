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

/* 
Run an mpd command. Pass args as a named dict. Set updateStatus to
follow this call with a 'status' command, whose result would go to
your status observers
*/
function callMpd(command, args, updateStatus) {
    if (!args) {
        args = {};
    }
    var d = doXHR("mpd/"+command, {method: "POST", 
                                   sendContent: serializeJSON(args)});
    d.addCallback(function (xhr) {
        var result = evalJSONRequest(xhr);
	signal(_mpdLog, 'lastCmd', command, args, result);

	if (command == "status") {
	    signal(_mpdLog, 'statusChanged', result);
	}

	if (updateStatus) {
	    callMpd("status");
	}

        return result;
    });
    return d;
}

/*
Clear playlist, add the given filename, and start playing it.
*/
function playOne(filename) {
    callMpd("clear").addCallback(function (result) {
        callMpd("add", {path: filename}).addCallback(function (result) {
	    signal(_mpdLog, 'playlistChanged');
	    callMpd("play", {songnum:0}, true);
        });
    });
}

/*
Add the given filename and start playing it
*/
function addPlay(filename) {
    callMpd("add", {path: filename}, false).addCallback(function (result) {
	signal(_mpdLog, 'playlistChanged');
	callMpd("status").addCallback(function(status) {
	    console.log("st")
	    callMpd("play", {songnum:status['playlistlength'] - 1}, true);
	});
    });
}

/*
Play the song with the given playlist position
*/
function playPos(pos) {
    callMpd("play", {songnum: pos}, true);
}

function delId(id) {
    callMpd("deleteid", {songid: id});
    signal(_mpdLog, 'playlistChanged');
    callMpd("status");
}