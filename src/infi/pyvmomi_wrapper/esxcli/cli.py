from pyVmomi import vmodl
from pyVmomi.SoapAdapter import Serialize, Deserialize

ReflectManagedMethodExecuterSoapArgument = vmodl.reflect.ManagedMethodExecuter.SoapArgument
SOAP_VERSION = "urn:vim25/5.0"      # vim.version.version7

class EsxCLI(object):
    def __init__(self, host):
        self._host = host

    def _generate_arguments(self, **kwargs):
        sorted_keys = sorted(kwargs.keys())
        sorted_kwargs = [(key, kwargs[key]) for key in sorted_keys]
        return [ReflectManagedMethodExecuterSoapArgument(name=key, val=Serialize(value))
                for key, value in sorted_kwargs if value is not None]

    def execute(self, moid, method, **kwargs):
        moe = self._host.RetrieveManagedMethodExecuter()
        response = moe.ExecuteSoap(moid=moid, version=SOAP_VERSION, method=method,
                                   argument=self._generate_arguments(**kwargs))
        if response is None:
            return

        if response.response is None and response.fault.faultMsg is not None:
            raise response.fault
        return Deserialize(response.response)
