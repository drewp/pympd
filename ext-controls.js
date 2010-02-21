/*
  higher-level mpd controls using extjs

  depends on ext and mochikit
*/


function createVolumeSlider(parent, player, sliderOpts) {

    if (!sliderOpts) {
	sliderOpts = {
	    height: 70,
	    vertical: true
	};
    }

    var volumeSlider = new Ext.Slider(
	MochiKit.Base.merge({
	    renderTo: parent,
	    increment: 3,
	    minValue: 0,
	    maxValue: 100,
	}, sliderOpts));
    volumeSlider.addListener('change', 
			     function (sld, value) {
				 player.callMpd("setvol", {vol: value})
			     });

    player.on('statusChanged', function(status) {
	volumeSlider.setValue(status.volume);
    });

    return volumeSlider;
}


function createSeekSlider(parent, player, sliderOpts) {

    if (!sliderOpts) {
	sliderOpts = {
	    width: 100,
	    vertical: false
	};
    }

    var seekSlider = new Ext.Slider(
	MochiKit.Base.merge({
	    renderTo: parent,
	    increment: 1,
	    minValue: 0,
	    maxValue: 1000,
	}, sliderOpts));
    seekSlider.mpdTotalTime = 0; // update this when the status comes in
    seekSlider.changeFromServer = false;
    seekSlider.addListener(
	'changecomplete', 
 	function (sld, value) {
	    if (!seekSlider.changeFromServer) {
		var sec = seekSlider.mpdTotalTime * value / 1000;
 		player.callMpd('seek', { seconds: Math.round(sec) }, true);
	    }
 	});
    return seekSlider;
}

/* 
  render an ext tree widget in the given element id. There will be
  buttons to add selected songs to the current playlist.  
*/
function setupLibraryTree(player, parent) {
    var selection = new Ext.tree.MultiSelectionModel();
    var tree = new Ext.tree.TreePanel({
        renderTo: parent,
	dataUrl: player.site + 'mpd/lsinfoTree',
        autoScroll:true,
        animate:true,
        containerScroll: true, 
	root: {
	    nodeType: 'async',
	    text: 'Music Library',
	    draggable: false,
	    id: '/',
	},

	selModel: selection,
	tbar: [{text:"Add", 
		handler:function(ev){
		    chain = succeed();
		    forEach(selection.getSelectedNodes(), function (node) {
			chain.addCallback(function (result) {
			    return player.callMpd("add", {path:node.id});
			});
		    });
		    // busy cursor until they're all done?
		    chain.addCallback(function (result) {
			updatePlaylist();
		    });
		},
	       }],
    });
    // oops, this is also trapping attempts to expand albums. those 
    // should probably go back to expand/collapse, not addPlay
    tree.addListener('dblclick', function (node, ev) {
	player.addPlay(node.id);
    });
    // how do i bind return-key to the same action?

    //tree.render();
    tree.getRootNode().expand();

    return tree;
}
