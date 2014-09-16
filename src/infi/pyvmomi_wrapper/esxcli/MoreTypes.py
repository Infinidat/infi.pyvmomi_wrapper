from pyVmomi.VmomiSupport import CreateDataType,  CreateManagedType,  CreateEnumType,  AddVersion,  AddVersionParent,  F_LINK,  F_LINKABLE,  F_OPTIONAL


#### Ugly hack to patch vim.HostSystem, add RetrieveManagedMethodExecuter method

from pyVmomi import vim
from pyVmomi.VmomiSupport import Capitalize, ManagedMethod, GetWsdlNamespace, LazyObject
from pyVmomi.VmomiSupport import _SetWsdlMethod, _dependencyMap
def AddWsdlMethod(_type, mVmodl, mWsdl, mVersion, mParams, mResult, mPrivilege, mFaults):
    vmodlName = _type.__name__

    if mFaults is None:
        mFaults = []
    mName = Capitalize(mVmodl)
    params = tuple([LazyObject(name=p[0], typeName=p[1], version=p[2], flags=p[3],
                    privId=p[4]) for p in mParams])
    info = LazyObject(name=mName, typeName=vmodlName, wsdlName=mWsdl,
                      version=mVersion, params=params, isTask=False,
                      resultFlags=mResult[0], resultName=mResult[1],
                      methodResultName=mResult[2], privId=mPrivilege, faults=mFaults)
    mm = ManagedMethod(info)
    ns = GetWsdlNamespace(info.version)
    method = _SetWsdlMethod(ns, info.wsdlName, mm)
    _type._methodInfo[mName] = info
    setattr(_type, mWsdl, mm)
    _dependencyMap[vmodlName].add(info.wsdlName)

patch = ("retrieveManagedMethodExecuter", "RetrieveManagedMethodExecuter", "vim.version.version7", (),
         (F_OPTIONAL, "vmodl.reflect.ManagedMethodExecuter", "vmodl.reflect.ManagedMethodExecuter"),
         "System.Read", None)
AddWsdlMethod(vim.HostSystem, *patch)

####



# TODO missing some ~120 CLI-related data types - see infi.pyvisdk
CreateDataType("vim.VimEsxCLIstoragenmpsatprulelistStorageArrayTypePluginRule", "VimEsxCLIstoragenmpsatprulelistStorageArrayTypePluginRule", "vmodl.DynamicData", "vmodl.reflect.version.version1", [('ClaimOptions', "string", "vmodl.reflect.version.version1", F_OPTIONAL), ('DefaultPSP', "string", "vmodl.reflect.version.version1", F_OPTIONAL), ('Description', "string", "vmodl.reflect.version.version1", F_OPTIONAL), ('Device', "string", "vmodl.reflect.version.version1", F_OPTIONAL), ('Driver', "string", "vmodl.reflect.version.version1", F_OPTIONAL), ('Model', "string", "vmodl.reflect.version.version1", F_OPTIONAL), ('Name', "string", "vmodl.reflect.version.version1", F_OPTIONAL), ('Options', "string", "vmodl.reflect.version.version1", F_OPTIONAL), ('PSPOptions', "string", "vmodl.reflect.version.version1", F_OPTIONAL), ('RuleGroup', "string", "vmodl.reflect.version.version1", F_OPTIONAL), ('Transport', "string", "vmodl.reflect.version.version1", F_OPTIONAL), ('Vendor', "string", "vmodl.reflect.version.version1", F_OPTIONAL),])
