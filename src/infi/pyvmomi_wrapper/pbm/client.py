from pyVmomi import pbm
from pyVim.connect import SoapStubAdapter


class PbmClient(object):
    def __init__(self, client, version="version2"):
        # https://github.com/vmware/pyvmomi/issues/885
        client_stub = client.service_instance._GetStub().soapStub\
            if client.smart_stub else client.service_instance._GetStub()  # pylint: disable=protected-access
        session_cookie = client_stub.cookie.split('"')[1]
        ssl_context = client_stub.schemeArgs.get('context')
        additional_headers = {'vcSessionCookie': session_cookie}
        stub = SoapStubAdapter(client.host, path="/pbm/sdk", version="pbm.version." + version,
                               sslContext=ssl_context, requestContext=additional_headers)
        self.service_instance = pbm.ServiceInstance("ServiceInstance", stub)
