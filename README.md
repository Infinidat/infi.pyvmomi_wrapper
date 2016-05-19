Overview
========
infi.pyvmomi_wrapper provides a simple way to use the VMware vSphere API, using the official Python binding package, pyvmomi.
This wrapper provides a more object oriented approach to interfacing with the VMware API.

Usage
-----
* Use the `Client` object to connect to a vCenter server.
* A client instance provides methods to get a specific object or all objects of a certain type.
For example, `get_virtual_machine`, `get_virtual_machines`, or get host systems,
datacenters, folders, datastores, etc.
* Wait for vCenter tasks using Client.wait_for_task (or wait_for_tasks)
* Retrive properties from a property collector using a simple interface - the Client.retrieve_properties method
for a simple get operation, or CachedPropertyCollector for a live collector that receives updates over time.
* The `TaskManager` class provides a method to create a custom vCenter task, and the `Task` object provides
a simple interface to manipulate a task.

And more...

Example
-------
```python
from infi.pyvmomi_wrapper import Client
from pyVmomi import vim

client = Client("vcenter", username="user", password="pass")

vm = client.get_virtual_machine("test_vm")

# take a snapshot
create_task = vm.CreateSnapshot_Task(name="test", memory=False, quiesce=True)
client.wait_for_task(create_task)
snapshot = create_task.info.result

# remove the snapshot
remove_task = snapshot.RemoveSnapshot_Task(removeChildren=False)
client.wait_for_task(remove_task)

# take a look at virtual disk file locations
for dev in vm.config.hardware.device:
    if isinstance(dev, vim.VirtualDisk):
        print dev.backing.fileName

# get power state of all Virtual Machines
name_and_power_state = client.retrieve_properties(vim.VirtualMachine, ['name', 'runtime.powerState'])
```

Installation
============
infi.pyvmomi_wrapper is available on PyPI. You can install it with pip or with easy_install:

    easy_install infi.pyvmomi_wrapper

Development
===========
To check out the code for development purposes, clone the git repository and run the following commands:

    easy_install -U infi.projector
    projector devenv build
