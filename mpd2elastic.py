#!/usr/bin/python
"""
read /var/lib/mpd/tag_cache and fill an elasticsearch database
"""

import restkit, jsonlib

index = restkit.Resource("http://plus:9200/")

try:
    index.delete('/mpd/')
except restkit.errors.RequestFailed:
    pass

index.put("mpd/")
index.put("mpd/_mapping", payload=jsonlib.write({
    "song" : {
        # this was meant to make highlighting work, but i can't use HL
        # with fuzzy matching, it seems
        "_all" : {"type" : "string",
                  "store" : "yes", "term_vector" : "with_positions_offsets"},
        "properties" : {
            "title" : {"type" : "string",
                  "store" : "yes", "term_vector" : "with_positions_offsets"},
            }
        }
    }))

class TagCacheParser(object):
    def __init__(self, index, tagCachePath="/var/lib/mpd/tag_cache"):
        self.currentSong = {}
        for line in open(tagCachePath):
            line = line.strip()
            if ': ' in line:
                key, value = line.split(': ', 1)
                if key == 'begin':
                    self.directory = value
                elif key == 'key':
                    self.finishSong()
                self.currentSong[key.lower()] = value

            if line == 'songList end':
                self.finishSong()
                
    def finishSong(self):
        if not self.currentSong:
            return

        if 'file' in self.currentSong:
            index.post("mpd/song/", payload=jsonlib.write(self.currentSong))
        
        self.currentSong = {}

TagCacheParser(index, "/var/lib/mpd/tag_cache")

