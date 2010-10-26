#!/usr/bin/python
"""
web app to query an elasticsearch database, edit mpd playlist
"""

import restkit, jsonlib, logging, web
from web.contrib.template import render_genshi
logging.basicConfig()
log = logging.getLogger()

render = render_genshi('.', auto_reload=True)

elastic = restkit.Resource("http://plus:9200/")

urls = (r"/", "index",
        r"/search", "search",
        r"/jquery-1.4.2.min.js", "jquery",
        )

class index(object):
    def GET(self):
        web.header("Content-Type", "application/xhtml+xml")
        return render.searchelastic(
            )
    
class search(object):
    def GET(self):
        q = web.input()["q"]
        elasticQuery = {
            "filtered" : {
                "query" :
            # highlight seems to not work with fuzzy
                {"fuzzy" : {"_all" : {"value" : q, "prefix_length" : 2}}},
                "filter" : {
                    "or" : [
                        {"prefix" : {"value" : q, "boost" : 2.0}},
                        ]
                    }
                }
            }
        response = elastic.request(method="get", path="mpd/song/_search",
                                   payload=jsonlib.write(elasticQuery))
        result = jsonlib.read(response.body_string())
        web.header("Content-Type", "application/json")
        return jsonlib.write(result)

class jquery(object):
    def GET(self):
        return open("jquery-1.4.2.min.js").read()

w = web.application(urls, globals(), autoreload=True)
application = w.wsgifunc()
if __name__ == '__main__':
    w.run()
