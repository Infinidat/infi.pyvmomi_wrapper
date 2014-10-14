from pyVmomi import vim
from .connect import Connect
from .errors import TimeoutException


def get_reference_to_managed_object(mo):
    motype = mo.__class__.__name__.split(".")[-1]       # stip "vim." prefix
    return "{}:{}".format(motype, mo._moId)


class Client(object):
    def __init__(self, vcenter_address, username=None, password=None, certfile=None, keyfile=None):
        self.service_instance = Connect(vcenter_address,
            user=username, pwd=password,
            certfile=certfile, keyfile=keyfile)
        self.service_content = self.service_instance.content
        self.session_manager = self.service_content.sessionManager
        self.root = self.service_content.rootFolder
        self.host = vcenter_address
        self.property_collectors = {}

    def login(self, user, pwd):
        self.session_manager.Login(user, pwd, None)
        self.property_collectors = {}

    def login_extension_by_certificate(self, extension_key, locale=None):
        if not locale:
            locale = getattr(self.session_manager, 'defaultLocale', 'en_US')
        self.session_manager.LoginExtensionByCertificate(extension_key, locale)
        self.property_collectors = {}

    def logout(self):
        self.session_manager.Logout()
        self.property_collectors = {}

    def wait_for_tasks(self, tasks, timeout=None):
        from time import time
        from .property_collector import TaskPropertyCollector
        if len(tasks) == 0:
            return
        property_collector = TaskPropertyCollector(self, tasks)
        start_time = time()
        remaining_timeout = None
        while len(tasks) > 0:
            if timeout is not None:
                remaining_timeout = int(timeout - (time() - start_time))
                if remaining_timeout <= 0:
                    raise TimeoutException("Time out while waiting for tasks")
            update = property_collector.iter_task_states_changes(timeout_in_seconds=remaining_timeout)
            for task, state in update:
                if state == vim.TaskInfo.State.success and task in tasks:
                    tasks.remove(task)
                elif state == vim.TaskInfo.State.error:
                    raise task.info.error

    def wait_for_task(self, task, timeout=None):
        return self.wait_for_tasks([task], timeout)

    def _build_full_traversal(self):
        from pyVmomi import vim

        # Recurse through all ResourcePools
        rpToRp = vim.TraversalSpec(name="rpToRp", type=vim.ResourcePool, path="resourcePool",
            selectSet=[vim.SelectionSpec(name="rpToRp"),
                       vim.SelectionSpec(name="rpToVm")])

        # Recurse through all ResourcePools
        rpToVm = vim.TraversalSpec(name="rpToVm", type=vim.ResourcePool, path="vm")

        # Traversal through ResourcePool branch
        crToRp = vim.TraversalSpec(name="crToRp", type=vim.ComputeResource, path="resourcePool",
           selectSet=[vim.SelectionSpec(name="rpToRp"),
                      vim.SelectionSpec(name="rpToVm")])

        # Traversal through host branch
        crToH = vim.TraversalSpec(name="crToH", type=vim.ComputeResource, path="host")

        # Traversal through hostFolder branch
        dcToHf = vim.TraversalSpec(name="dcToHf", type=vim.Datacenter, path="hostFolder",
           selectSet=[vim.SelectionSpec(name="visitFolders")])

        # Traversal through vmFolder branch
        dcToVmf = vim.TraversalSpec(name="dcToVmf", type=vim.Datacenter, path="vmFolder",
           selectSet=[vim.SelectionSpec(name="visitFolders")])

        # Recurse through all Hosts
        HToVm = vim.TraversalSpec(name="HToVm", type=vim.HostSystem, path="vm",
           selectSet=[vim.SelectionSpec(name="visitFolders")])

        # Recurse through all Datacenter Datastores
        dcToDs = vim.TraversalSpec(name="dcToDs", type=vim.Datacenter, path="datastore",
           selectSet=[vim.SelectionSpec(name="visitFolders")])

        # Recurse through the folders
        visitFolders = vim.TraversalSpec(name="visitFolders", type=vim.Folder, path="childEntity",
           selectSet=[vim.SelectionSpec(name="visitFolders"),
                      vim.SelectionSpec(name="dcToHf"),
                      vim.SelectionSpec(name="dcToVmf"),
                      vim.SelectionSpec(name="crToH"),
                      vim.SelectionSpec(name="crToRp"),
                      vim.SelectionSpec(name="HToVm"),
                      vim.SelectionSpec(name="dcToDs"),
                      vim.SelectionSpec(name="rpToVm"),
                     ])

        return [visitFolders, dcToVmf, dcToHf, crToH, crToRp, rpToRp, HToVm, rpToVm, dcToDs]

    def _retrieve_properties(self, managed_object_type, props=[], collector=None, root=None, recurse=True):
        if not collector:
            collector = self.service_content.propertyCollector
        if not root:
            root = self.service_content.rootFolder

        property_spec = vim.PropertySpec(type=managed_object_type, pathSet=props)
        selection_specs = list(self._build_full_traversal()) if recurse else []
        object_spec = vim.ObjectSpec(obj=root, selectSet=selection_specs)

        spec = vim.PropertyFilterSpec(propSet=[property_spec], objectSet=[object_spec])
        options = vim.RetrieveOptions()
        objects = []
        retrieve_result = collector.RetrievePropertiesEx(specSet=[spec], options=options)
        while retrieve_result.token:
            objects.extend(retrieve_result.objects)
            retrieve_result = collector.ContinueRetrievePropertiesEx(retrieve_result.token)
        objects.extend(retrieve_result.objects)
        return objects

    def retrieve_properties(self, managed_object_type, props=[], collector=None, root=None, recurse=True):
        retrieved_properties = self._retrieve_properties(managed_object_type, props, collector, root, recurse)
        data = []
        for obj in retrieved_properties:
            properties = dict((prop.name, prop.val) for prop in obj.propSet)
            properties['obj'] = obj.obj
            data.append(properties)
        return data

    def get_decendents_by_name(self, managed_object_type, name=None):
        retrieved_properties = self._retrieve_properties(managed_object_type, ["name"])
        objects = [item.obj for item in retrieved_properties]
        if not name:
            return objects
        for obj in objects:
            if obj.name == name:
                return obj

    def get_host_systems(self):
        return self.get_decendents_by_name(vim.HostSystem)

    def get_host_system(self, name):
        return self.get_decendents_by_name(vim.HostSystem, name=name)

    def get_datacenters(self):
        return self.get_decendents_by_name(vim.Datacenter)

    def get_datacenter(self, name):
        return self.get_decendents_by_name(vim.Datacenter, name=name)

    def get_resource_pools(self):
        return self.get_decendents_by_name(vim.ResourcePool)

    def get_resource_pool(self, name):
        return self.get_decendents_by_name(vim.ResourcePool, name=name)

    def get_virtual_machines(self):
        return self.get_decendents_by_name(vim.VirtualMachine)

    def get_virtual_machine(self, name):
        return self.get_decendents_by_name(vim.VirtualMachine, name=name)

    def get_virtual_apps(self):
        return self.get_decendents_by_name(vim.VirtualApp)

    def get_virtual_app(self, name):
        return self.get_decendents_by_name(vim.VirtualApp, name=name)

    def get_folders(self):
        return self.get_decendents_by_name(vim.Folder)

    def get_folder(self, name):
        return self.get_decendents_by_name(vim.Folder, name=name)

    def get_host_clusters(self):
        return self.get_decendents_by_name(vim.ClusterComputeResource)

    def get_host_cluster(self, name):
        return self.get_decendents_by_name(vim.ClusterComputeResource, name=name)

    def get_datastores(self):
        return self.get_decendents_by_name(vim.Datastore)

    def get_datastore(self, name):
        return self.get_decendents_by_name(vim.Datastore, name=name)

    def get_reference_to_managed_object(self, mo):
        return get_reference_to_managed_object(mo)

    def get_managed_object_by_reference(self, moref):
        motype, moid = moref.split(":")
        moclass = getattr(vim, motype)
        return moclass(moid, stub=self.service_instance._stub)
