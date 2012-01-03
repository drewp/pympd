$(function () {
    
    function albumFromSongFile(f) {
        return f.replace(/\/[^/]+$/, "");
}
  function strip(s) {
      return s.replace(/^\s+/,"").replace(/\s+$/, "");
  }
  
  
  function mpdAjax(method, url, dataObj, success) {
      return $.ajax({
          type: method,
          url: url,
          data: JSON.stringify(dataObj),
          headers: {"content-type" : "application/json"},
          success: success
      });
  }
  
  var mpfResource = {root: "mpdpandorafeeder/",
                     stations: "mpdpandorafeeder/stations/",
                     currentSong: "mpdpandorafeeder/currentSong",
                     currentStation: "mpdpandorafeeder/currentStation"};

  {
      var volume = new (Backbone.Model.extend({
          url: "mpd/status",
          parse: function (response) {
              return {volume: response.volume};
          },
          save: function (attrs, options) {
              options || (options = {});
              if (attrs && !this.set(attrs, options)) return false;
              var model = this;
              var success = options.success;
              options.success = function(resp, status, xhr) {
                  if (!model.set(model.parse(resp, xhr), options)) return false;
                  if (success) success(model, resp, xhr);
              };
              options.error = wrapError(options.error, model, options);
              var method = this.isNew() ? 'create' : 'update';
              return mpdAjax("post", this.url, model.toJSON(), 
                             function () {});
          }
      }));

      var incr = 3;
      var volumeView = new (Backbone.View.extend({
          el: $(".volumeStack"),
          model: volume,
          events: { 
              "click button": "button",
          },
          initialize: function () {
              this.model.bind('change', function (vol) {
                  this.render();
              }, this);
          },
          render: function () {
              var v = this.model.get("volume")
              this.$(".current").text(v);
              this.$(".upper button").text(Math.min(100, v+incr));
              this.$(".lower button").text(Math.max(0, v-incr));
          },
          button: function (ev, a, b) {
              mpdAjax("put", "mpd/setvol", 
                      {vol: parseInt($(ev.target).text())},
                      function () { updateStatus(); });
          }
      }));
  }

  {
      window.Playlist = Backbone.Model.extend({});
      
      var playlists = new (Backbone.Collection.extend({
          model: Playlist,
          url: "mpd/playlists",
          parse: function (response) {
              return response.playlists;
          }
      }));

      playlists.bind('reset', function() {
          $("#playlists").empty();
          playlists.each(function(pl) {
              var view = new PlaylistView({model: pl});
              $("#playlists").append(view.render().el);
          });
      }, this);
      playlists.fetch();

      window.PlaylistView = Backbone.View.extend({
          tagName: "div",
          events : {
              "click" : "loadPlaylist"
          },
          render: function () { 
              var div = $("<button>").addClass("playlist").text(
                  this.model.get("name"));
              $(this.el).html(div);
              return this;
          },
          loadPlaylist: function () {
              var name = this.model.get("name");
              $.ajax({
                  type: "delete",
                  url: mpfResource.currentStation,
                  success: function () {
                      mpdAjax("put", "mpd/currentPlaylist", 
                              {name: name}, 
                              function () {
                                  currentPlaylist.fetch();
                                  $.ajax({
                                      type: "post",
                                      url: "mpd/play",
                                      success: function () {
                                          updateStatus();
                                      }
                                  });
                              });
                  }});
          }
      });
  }

  {
      window.Station = Backbone.Model.extend({});

      var stations = new (Backbone.Collection.extend({
          model: Station,
          url: mpfResource.stations,
          parse: function (response) {
              return response.stations;
          }
      }));

      window.StationView = Backbone.View.extend({
          tagName: "div",
          events: { 
              "click" : "loadStation"
          },
          render: function () {
              $(this.el).html($("<button>").addClass("station").text(
                  this.model.get("name")));
              return this;
          },
          loadStation: function () {
              var model = this.model;
              mpdAjax("post", "mpd/clear", {}, function  () {
                  $.ajax({
                      type: "put",
                      url: mpfResource.currentStation,
                      data: JSON.stringify(model.attributes),
                      success: function () {
                          updateStatus();
                      }
                  });
              });
          }
      });

      stations.bind("reset", function () {
          $("#stations").empty();
          stations.each(function (s) {
              $("#stations").append(
                  new StationView({model: s}).render().el);
          });
      });
      stations.fetch();
  }
  
  {
      var playState = new (Backbone.Model.extend({
          // this is all set by the global /status request
      }));

      var playStateView = new (Backbone.View.extend({
          el: $("#transport"),
          model: playState,
          initialize: function () {
              this.model.bind("change:time", function (ev, pos) {
                  $("#position").text(
                      pos[0] + " of " + pos[1] + " sec");
              });
              this.model.bind("change:state", function (ev, state) {
                  $("#pause").text(state == "play" ? "pause" : "play");
              });
          },
          events: {
              "click #pause" : "click",
              "click #prevSong" : "prev",
              "click #nextSong" : "next"
          },
          click: function () {
              $.post("mpd/pause", function () {
                  updateStatus();
              });
          },
          // if these take you between pandora songs, we need to refresh the contents of the magic pandora item, which is not yet happening (since this is not a playlist version change)
          prev: function () {
              $.post("mpd/previous", function () { updateStatus(); });
          },
          next: function () {
              $.post("mpd/next", function () { updateStatus(); });
          },

      }));
  }


  var pandoraSongs = {}; // audioUrl : Song

  {
      window.Song = Backbone.Model.extend({
          isPandora: function () {
              return this.get("file").match(
                      /http:\/\/.*?\.pandora\.com\//)
          },
          initialize: function (attr) {
              pandoraSongs[attr.file] = this;
          }
      });

      var nowPlaying = -1;

      var currentPlaylist = new (Backbone.Collection.extend({
          model: Song,
          url: "mpd/playlistinfo",
          parse: function (response) {
              $.each(response, function (i, rec) {
                  rec.id = rec.Pos;
              });
              return response;
          },
          setSong: function (num) {
              var np = this.get(nowPlaying);
              if (np) np.set({isPlaying: false});
              nowPlaying = num;
              var np = this.get(nowPlaying);
              if (np) np.set({isPlaying: true});
          },
          initialize: function () {
              this.bind("reset", 
                        function () { this.setSong(nowPlaying); }, 
                        this);
          }
      }));

      window.SongView = Backbone.View.extend({
          tagName: "li",
          events: {
              "click" : "click"
          },
          initialize: function () { 
              this.model.bind("change:isPlaying", this.setPlaying, 
                              this);
              this.model.bind("change:pandoraData", 
                              this.updatePandoraData, this);
          },
          setPlaying: function (_, ip) {
              if (ip) {
                  $(this.el).addClass("playing");
              } else {
                  $(this.el).removeClass("playing");
              }
          },
          updatePandoraData: function (_, p) {
              $(this.el).children("div").text(
                  p.title + " / " + p.artist + " / " + p.album);
          },
          render: function () { 
              var div = $("<div>");
              if (this.model.isPandora()) {
                  div.addClass("currentPandoraSong");
                  div.text("(a song from Pandora)");
                  updatePandoraCurrentSong();
              } else {
                  var displayName = (this.model.get("Title") || 
                                     this.model.get("file"));
                  div.addClass("song").text(displayName);
              }
              $(this.el).html(div);
              this.setPlaying(null, this.model.get("isPlaying"));
              return this;
          },
          remove: function() {
              $(this.el).remove();
          },
          click: function () {
              mpdAjax("post", "mpd/play", 
                      {songnum: this.model.get("Pos")},
                      function () {
                          updateStatus();
                      });
          }
      });

      var currentPlaylistView = new (Backbone.View.extend({
          el: $("#currentPlaylist"),
          model: currentPlaylist,
          initialize: function () {
              this.model.bind('reset', function() {
                  var el = $(this.el);
                  el.empty();
                  this.model.each(function(song) {
                      var view = new SongView({model: song});
                      el.append(view.render().el);
                  });
              }, this);
          }
      }));
  }

  window.updateStatus = function(whenDone) {
      $.getJSON("mpd/status", function (response) {
          volume.set({volume: response.volume});
          var p = {state: response.state, 
                   random: response.random};
          if (response.time) {
              p.time = response.time.split(":");
          }
          playState.set(p);

          currentPlaylist.setSong(response.song);
          if (response.playlist != currentPlaylist.version) {
              currentPlaylist.fetch();
              // not sure how to get the version of the one i
              // fetched. this one is close
              currentPlaylist.version = response.playlist;
          }
          if (whenDone) {
              whenDone();
          }
      });
  }
  function statusLoop() {
      updateStatus(function () {
          // todo: use requestAnimFrame where available
          setTimeout(statusLoop, 2000);
      });
  }
  statusLoop();
  //updateStatus();

  function updatePandoraCurrentSong() {
      // todo: only relevant if the pandora song is being played now.

      // This is getting over-called. It would be cool if the
      // request url was like /mpf/{the-pandora-url-here}, and
      // then the browser cache could remind us if we'd already
      // asked about that pandora urlq
      $.getJSON(mpfResource.currentSong, function (data) {
          var p = data.song.pandora;
          if (p) {
              if (pandoraSongs[p.audioUrl]) {
                  pandoraSongs[p.audioUrl].set({pandoraData: p});
              }
          }
      });
  }

  $.getJSON("mpd", function (data) {
      $("#mpdWebConfig").text(
          "mpdweb running on "+data.host+" talking to mpd at "+
              data.mpd.host+":"+data.mpd.port);
  });
  $.getJSON(mpfResource.root, function (data) {
      $("#mpdPandoraFeederConfig").text(
          "mpdpandorafeeder running on "+data.host+
              " talking to mpd at "+data.mpd.host+":"+data.mpd.port);
  });

  function Search(inputElem, resultElem) {

      inputElem.bind("keyup", updateSearch);

      function addAndPlayForm(path) {
          return $("<form>").ajaxForm(closeSearch).attr({
              method: "POST", 
              action: "addAndPlay/"+escape(path)
          }).append($("<button>").text("Play")) ;
      }

      function albumRow(row) {
          return $("<li>").append(
              addAndPlayForm(albumFromSongFile(row.file))
                  .append($("<span>").text(
                      "Album: "+row.Album+ " " + row.Artist)));
      }

      function songRow(row) {
          return $("<li>").append(
              addAndPlayForm(row.file)
                  .append($("<span>").text(
                      row.Track + " " + row.Title)));
      }

      function updateSearch() {
          resultElem.show();

          var ol = resultElem.find("ol");

          function currentQuery() {
              return strip(inputElem.val());
          }

          var q = currentQuery();
          if (q == "") {
              closeSearch();
              return;
          }
          if (q.length < 3) {
              ol.text("Enter search");
              return;
          }
          ol.empty();
          resultElem.find(".status").text("Searching...");

          var albumsShown = 0;

          $.getJSON(
              "multiSearch", {q: q}, 
              function (data) {
                  if (q != currentQuery()) {
                      return; // too late
                  }
                  resultElem.find(".status").text("");
                  var lastAlbum = null;
                  var currentSection = null;
                  $.each(data, function (i, row) {
                      if (albumsShown > 5) {
                          return;
                      }
                      if (lastAlbum === null || row.Album != lastAlbum) {
                          ol.append(albumRow(row));
                          albumsShown += 1;
                          currentSection = $("<ul>");
                          ol.append(currentSection);
                          lastAlbum = row.Album;
                      }
                      currentSection.append(songRow(row));
                  });
                  if (albumsShown == 0) {
                      ol.text("No matches");
                  }
              });
      }

      function closeSearch() {
          inputElem.val("");
          resultElem.hide();
      }
  }

  new Search($("input[name=q]"), $(".search > .results"));
  
 });
