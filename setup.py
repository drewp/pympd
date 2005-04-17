from distutils.core import setup
from distutils.extension import Extension
from Pyrex.Distutils import build_ext
setup(
  name = "pympd",
  version="1.0",
  description="twisted interface to MPD (www.musicpd.org)",
  
  long_description="""An alternative to the commonly-used mpdclient
module (http://mpd.wikicities.com/wiki/ClientLib:py-libmpdclient)
which uses twisted for the TCP communications. Important differences
between mpdclient and pympd:

- pympd doesn't fall into 'not done processing current command' loops

- pympd doesn't block, due to its use of the twisted communications libs

- pympd has a very incomplete implementation of the mpd commands, but
  they are easy to add

- pympd supports my mpd patch for fractional-second accurate times,
  and might even reject unpatched mpds

""",
  
  author="Drew Perttula",
  author_email="drewp@bigasterisk.com",
  url="http://bigasterisk.com",
  download_url="http://projects.bigasterisk.com/pympd-1.0.tar.gz",
  classifiers=[
    'Development Status :: 5 - Production/Stable',
    'Operating System :: POSIX :: Linux',
    'Programming Language :: Python',
    'Topic :: Software Development :: Libraries :: Python Modules',
    'Topic :: Multimedia :: Sound/Audio :: Players',
    'License :: OSI Approved :: GNU General Public License (GPL)',
    ],
  py_modules = ['pympd'],

)
