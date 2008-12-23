/*
  higher-level mpd controls using extjs

  depends on ext and mochikit
*/


function startPolling(player) {
    Ext.TaskMgr.start({run: function() { player.callMpd("status") },
		       interval: 5000});
}

function createVolumeSlider(parent, player, sliderOpts) {

    if (!sliderOpts) {
	sliderOpts = {
	    height: 70,
	    vertical: true
	};
    }

    var volumeSlider = new Ext.Slider(
	merge({
	    renderTo: parent,
	    increment: 3,
	    minValue: 0,
	    maxValue: 100,
	}, sliderOpts));
    volumeSlider.addListener('change', 
			     function (sld, value) {
				 player.callMpd("setvol", {vol: value})
			     });
    return volumeSlider;
}
