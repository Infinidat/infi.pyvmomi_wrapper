# Copy of SmartConnect + Connect, but login is optional and keyfile/certfile passed all the way

from pyVim.connect import GetServiceVersions, __FindSupportedVersion, SoapStubAdapter
from pyVim.connect import versionMap, _rx
from pyVmomi import vim
import re
import sys
from six import reraise
from logging import getLogger

## Uber patch of doom - fixes issue #163 in pyvmomi
logger = getLogger(__name__)


class SoapStubAdapterWithLogging(SoapStubAdapter):
    def _debug(self, messsage, *args, **kwargs):
        try:
            logger.debug(messsage.format(*args, **kwargs))
        except:
            pass

    def InvokeMethod(self, mo, info, args, outerStub=None):
        self._debug("{} --> {}", mo, info.wsdlName)
        try:
            return SoapStubAdapter.InvokeMethod(self, mo, info, args, outerStub)
        finally:
            self._debug("{} <-- {}", mo, info.wsdlName)


def my_ssl_tunnel_call_patch(self, path, key_file=None, cert_file=None, **kwargs):
    from six.moves import http_client
    from pyVmomi.SoapAdapter import _SocketWrapper
    # Don't pass any keyword args that HTTPConnection won't understand.
    for arg in kwargs.keys():
        if arg not in ("port", "strict", "timeout", "source_address"):
            del kwargs[arg]
    tunnel = http_client.HTTPConnection(path, **kwargs)
    tunnel.request('CONNECT', self.proxyPath)
    resp = tunnel.getresponse()
    if resp.status != 200:
        raise http_client.HTTPException("{0} {1}".format(resp.status, resp.reason))
    retval = http_client.HTTPSConnection(path)
    retval.sock = _SocketWrapper(tunnel.sock,
                                 keyfile=key_file, certfile=cert_file)
    return retval

from pyVmomi.SoapAdapter import SSLTunnelConnection
SSLTunnelConnection.__call__ = my_ssl_tunnel_call_patch

## End hack

def _create_stub(host, protocol="https", port=443,
                 namespace=None, path="/sdk",
                 version=None, keyfile=None, certfile=None):

    port = protocol == "http" and -int(port) or int(port)

    try:
        info = re.match(_rx, host)
        if info is not None:
            host = info.group(1)
            if host[0] == '[':
                host = info.group(1)[1:-1]
            if info.group(2) is not None:
                port = int(info.group(2)[1:])
    except ValueError:
        pass

    if namespace:
        assert(version is None)
        version = versionMap[namespace]
    elif not version:
        version = "vim.version.version6"

    # Create the SOAP stub adapter
    if certfile is not None and keyfile is not None:
        # SSL Tunnel
        return SoapStubAdapterWithLogging('sdkTunnel', 8089, version=version, path=path,
                               certKeyFile=keyfile, certFile=certfile, httpProxyHost=host)
    else:
        return SoapStubAdapterWithLogging(host, port, version=version, path=path)

def Connect(host, protocol="https", port=443, user=None, pwd=None,
            namespace=None, path="/sdk",
            preferredApiVersions=None, keyfile=None, certfile=None):
    """
    Determine the most preferred API version supported by the specified server,
    then connect to the specified server using that API version, login and return
    the service instance object.

    Throws any exception back to caller. The service instance object is
    also saved in the library for easy access.

    @param host: Which host to connect to.
    @type  host: string
    @param protocol: What protocol to use for the connection (e.g. https or http).
    @type  protocol: string
    @param port: Port
    @type  port: int
    @param user: User
    @type  user: string
    @param pwd: Password
    @type  pwd: string
    @param namespace: Namespace *** Deprecated: Use version instead ***
    @type  namespace: string
    @param path: Path
    @type  path: string
    @param preferredApiVersions: Acceptable API version(s) (e.g. vim.version.version3)
                                 If a list of versions is specified the versions should
                                 be ordered from most to least preferred.  If None is
                                 specified, the list of versions support by pyVmomi will
                                 be used.
    @type  preferredApiVersions: string or string list
    @param keyfile: ssl key file path
    @type  keyfile: string
    @param certfile: ssl cert file path
    @type  certfile: string
    """

    if preferredApiVersions is None:
        preferredApiVersions = GetServiceVersions('vim25')

    supportedVersion = __FindSupportedVersion(protocol,
                                              host,
                                              port,
                                              path,
                                              preferredApiVersions)
    if supportedVersion is None:
        raise Exception("%s:%s is not a VIM server" % (host, port))
    version = supportedVersion

    stub = _create_stub(host, protocol, port, namespace, path, version, keyfile, certfile)

    # Get Service instance
    si = vim.ServiceInstance("ServiceInstance", stub)
    try:
        content = si.RetrieveContent()
    except vim.MethodFault:
        raise
    except Exception as e:
        # NOTE (hartsock): preserve the traceback for diagnostics
        # pulling and preserving the traceback makes diagnosing connection
        # failures easier since the fault will also include where inside the
        # library the fault occurred. Without the traceback we have no idea
        # why the connection failed beyond the message string.
        (type, value, traceback) = sys.exc_info()
        if traceback:
            fault = vim.fault.HostConnectFault(msg=str(e))
            reraise(vim.fault.HostConnectFault, fault, traceback)
        else:
            raise vim.fault.HostConnectFault(msg=str(e))

    if user is not None and pwd is not None:
        content.sessionManager.Login(user, pwd, None)

    return si
