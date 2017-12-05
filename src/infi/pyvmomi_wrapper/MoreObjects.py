# these objects may be returned from vSphere but pyvmomi does not include them in ServerObjects.py
# See https://github.com/vmware/pyvmomi/issues/514

from pyVmomi.VmomiSupport import CreateDataType,  CreateManagedType,  CreateEnumType,  AddVersion,  AddVersionParent,  F_LINK,  F_LINKABLE,  F_OPTIONAL

CreateDataType("vim.vm.device.VirtualNVDIMM", "VirtualNVDIMM", "vim.vm.device.VirtualDevice", "vim.version.version11", None)
CreateDataType("vim.vm.device.VirtualNVDIMM.DeviceBackingInfo", "VirtualNVDIMMBackingInfo", "vim.vm.device.VirtualDevice.DeviceBackingInfo", "vim.version.version11", None)
CreateDataType("vim.vm.device.VirtualNVDIMMController", "VirtualNVDIMMController", "vim.vm.device.VirtualController", "vim.version.version11", None)
CreateDataType("vim.vm.device.VirtualNVDIMMOption", "VirtualNVDIMMOption", "vim.vm.device.VirtualDeviceOption", "vim.version.version11", None)