from pyVmomi.VmomiSupport import CreateAndLoadManagedType, CreateDataType, CreateEnumType
from pyVmomi.ManagedMethodExecutorHelper import MMESoapStubAdapter
from pyVmomi.VmomiSupport import F_OPTIONAL, F_LINKABLE, F_LINK
from ..errors import CLITypeException

# esxcli property annotations -> pyVmomi field flags
_ANNOTATION_FLAGS = {"optional": F_OPTIONAL, "linkable": F_LINKABLE, "link": F_LINK}


def _annotation_flags(annotations):
    flags = 0
    for annotation in (annotations or []):
        flags |= _ANNOTATION_FLAGS.get(annotation.name, 0)
    return flags


class EsxCLI(object):
    _loaded_types = {}

    def __init__(self, host):
        self._host = host
        self._host_api_version = host.summary.config.product.apiVersion

    def _load_type(self, type_info):
        if type_info.name not in self._loaded_types:
            methods = []
            for method in type_info.method:
                params = [(param.name, param.type, param.version, F_OPTIONAL, method.privId) for param in method.paramTypeInfo]
                return_type = (0, method.returnTypeInfo.type, method.returnTypeInfo.type)
                methods.append((method.name, method.wsdlName, method.version, params, return_type, method.privId, list(method.fault)))

            cls = CreateAndLoadManagedType(type_info.name, type_info.wsdlName, type_info.base[0], type_info.version, [], methods)
            self._loaded_types[type_info.name] = cls
        return self._loaded_types[type_info.name]

    def _register_types(self, type_info_result):
        # Register the esxcli data/enum types the live host reports, so response parsing
        # matches the host's actual ESXi version. The statically-bundled definitions
        # (MoreTypes) lag newer ESXi fields - e.g. ESXi 9 adds 'Vital' to advanced-setting
        # options - which otherwise makes the deserializer raise on the unknown element.
        for enum_type in (type_info_result.enumTypeInfo or []):
            try:
                CreateEnumType(enum_type.name, enum_type.wsdlName, enum_type.version, enum_type.value)
            except Exception:
                pass  # keep any already-registered definition for this version
        for data_type in (type_info_result.dataTypeInfo or []):
            try:
                props = [(p.name, p.type, p.version, _annotation_flags(p.annotation)) for p in (data_type.property or [])]
                CreateDataType(data_type.name, data_type.wsdlName, data_type.base[0], data_type.version, props)
            except Exception:
                pass

    def get(self, name):
        type_name = "vim.EsxCLI." + name
        mme = self._host.RetrieveManagedMethodExecuter()
        stub = MMESoapStubAdapter(mme)
        stub.versionId = 'urn:vim25/{}'.format(self._host_api_version)
        dm = self._host.RetrieveDynamicTypeManager()
        type_to_moId = {moi.moType: moi.id for moi in dm.DynamicTypeMgrQueryMoInstances()}
        if type_name in type_to_moId:
            moId = type_to_moId[type_name]
            ti = dm.DynamicTypeMgrQueryTypeInfo()
            self._register_types(ti)
            for type_info in ti.managedTypeInfo:
                if type_info.name == type_name:
                    cls = self._load_type(type_info)
                    return cls(moId, stub)
        raise CLITypeException("CLI type '{}' not found".format(name))
