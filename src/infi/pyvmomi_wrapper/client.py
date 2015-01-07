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
        # create a copy of 'tasks', because we're going to use 'remove' and we don't want to change the user's list
        tasks = tasks[:]
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

    def _create_traversal_spec(self, name, managed_object_type, property_name, next_selector_names=[]):
        return vim.TraversalSpec(name=name, type=managed_object_type, path=property_name,
           selectSet=[vim.SelectionSpec(name=selector_name) for selector_name in next_selector_names])

    def _build_full_traversal(self):
        rpToRp = self._create_traversal_spec("rpToRp", vim.ResourcePool, "resourcePool", ["rpToRp", "rpToVm"])
        rpToVm = self._create_traversal_spec("rpToVm", vim.ResourcePool, "vm")
        crToRp = self._create_traversal_spec("crToRp", vim.ComputeResource, "resourcePool", ["rpToRp", "rpToVm"])
        crToH = self._create_traversal_spec("crToH", vim.ComputeResource, "host")
        dcToHf = self._create_traversal_spec("dcToHf", vim.Datacenter, "hostFolder", ["visitFolders"])
        dcToVmf = self._create_traversal_spec("dcToVmf", vim.Datacenter, "vmFolder", ["visitFolders"])
        HToVm = self._create_traversal_spec("HToVm", vim.HostSystem, "vm", ["visitFolders"])
        dcToDs = self._create_traversal_spec("dcToDs", vim.Datacenter, "datastore", ["visitFolders"])
        visitFolders = self._create_traversal_spec("visitFolders", vim.Folder, "childEntity",
            ["visitFolders", "dcToHf", "dcToVmf", "crToH", "crToRp", "HToVm", "dcToDs"])
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
        while retrieve_result is not None and retrieve_result.token:
            objects.extend(retrieve_result.objects)
            retrieve_result = collector.ContinueRetrievePropertiesEx(retrieve_result.token)
        if retrieve_result is not None:
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
