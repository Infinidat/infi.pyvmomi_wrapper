from ..cli import EsxCLI

class Base(object):
    def __init__(self, host):
        self._cli = EsxCLI(host)
