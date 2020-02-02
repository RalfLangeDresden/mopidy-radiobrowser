from __future__ import unicode_literals

import logging
from mopidy import backend, httpclient
from mopidy.audio import scan
import pykka
import requests
import mopidy_radiobrowser
from .radiobrowser import RadioBrowser
from .library import RadioBrowserLibrary
from .playback import RadioBrowserPlayback


logger = logging.getLogger(__name__)


def get_requests_session(proxy_config, user_agent):
    logger.debug('RadioBrowser: Start backend.get_requests_session')

    proxy = httpclient.format_proxy(proxy_config)
    full_user_agent = httpclient.format_user_agent(user_agent)

    session = requests.Session()
    session.proxies.update({'http': proxy, 'https': proxy})
    session.headers.update({'user-agent': full_user_agent})

    return session


class RadioBrowserBackend(pykka.ThreadingActor, backend.Backend):
    uri_schemes = ['radiobrowser']

    def __init__(self, config, audio):
        logger.debug('RadioBrowser: Start backend.RadioBrowserBackend.__init__')

        super(RadioBrowserBackend, self).__init__()

        self._session = get_requests_session(
            proxy_config = config['proxy'],
            user_agent = '%s/%s' % (
                mopidy_radiobrowser.Extension.dist_name,
                mopidy_radiobrowser.__version__))

        self._timeout = config['radiobrowser']['timeout']

        self._scanner = scan.Scanner(
            timeout = config['radiobrowser']['timeout'],
            proxy_config = config['proxy'])
        self.radiobrowser = RadioBrowser(config['radiobrowser']['timeout'], self._session)
        self.library = RadioBrowserLibrary(self)
        self.playback = RadioBrowserPlayback(audio=audio, backend=self)
