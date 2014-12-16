from pyVmomi import vim
from logging import getLogger
from infi.pyutils.lazy import cached_method, clear_cache

logger = getLogger(__name__)

from .errors import ExtensionAlreadyRegisteredException, ExtensionNotRegisteredException
from .resources import ExtensionResourceFactory

class ExtensionFacade(object):
    DESCRIPTION = "Extention Test"
    VERSION = "1.0"

    def __init__(self, client, key):
        super(ExtensionFacade, self).__init__()
        self._client = client
        self._managed_object = self._client.service_content.extensionManager
        self._resources_dict = ExtensionResourceFactory.get_dict(self._client, key)
        self._key = key

    # Extension Registration

    @cached_method
    def is_registered(self):
        return len(self._get_extensions_data_objects()) > 0

    def register(self):
        if self.is_registered():
            raise ExtensionAlreadyRegisteredException()
        extension = self._new_extension()
        self._managed_object.RegisterExtension(extension)
        clear_cache(self)

    # Tasks management

    def is_task_registered(self, task_name):
        return task_name in self._get_tasks().values()

    def get_task_id(self, task_name):
        if not self.is_registered():
            raise ExtensionNotRegisteredException()
        if not self.is_task_registered(task_name):
            raise KeyError(task_name)
        tasks = self._get_tasks()
        reverted = {value: key for key, value in tasks.items()}
        return reverted[task_name]

    def register_task(self, task_name):
        task_id = self._generate_id()
        self._add_id(task_id, task_name)
        self._add_task(task_id, task_name)

    # Utility methods

    def _generate_id(self):
        from uuid import uuid4
        id = str(uuid4())
        return id if id not in self._get_ids() else self._generate_id()

    @cached_method
    def _get_extensions_data_objects(self):
        return [extension for extension in self._managed_object.extensionList
                if extension.key == self._key]

    def _get_ids(self):
        return self._resources_dict

    def _get_tasks(self):
        ids = self._get_ids()
        return {task.taskID: ids[task.taskID]
                for task in self._get_extensions_data_objects()[0].taskList
                if ids.get(task.taskID)}

    def _workaround_vcenter_restart(self, extension):
        # HIPVM-670 VMWare resets some unset fields to empty strings upon restart, and then fails on UpdateExtension
        # due to "incorrect parameters". So we need to re-unset empty fields
        extension.extendedProductInfo.companyUrl = extension.extendedProductInfo.companyUrl or None
        extension.extendedProductInfo.productUrl = extension.extendedProductInfo.productUrl or None
        extension.extendedProductInfo.managementUrl = extension.extendedProductInfo.managementUrl or None
        extension.solutionManagerInfo.smallIconUrl = extension.solutionManagerInfo.smallIconUrl or None
        return extension

    def _add_task(self, task_id, task_name):
        extension = self._get_extensions_data_objects()[0]
        tasks = self._get_tasks()
        tasks[task_id] = task_name
        extension.taskList = [self._new_task_type_info(task_id) for task_id in tasks.keys()]
        task_resources = [("{}.label".format(key), value) for key, value in tasks.items()]
        # TODO events
        extension.resourceList = [self._new_task_extension_resource_info('en', 'task', task_resources)]
        extension = self._workaround_vcenter_restart(extension)
        self._managed_object.UpdateExtension(extension)
        clear_cache(self)

    def _add_id(self, key, value):
        self._resources_dict[key] = value

    def _new_extension(self):
        description = vim.Description(label=self.DESCRIPTION, summary='')
        return vim.Extension(description=description, key=self._key,
                             lastHeartbeatTime=self._get_heartbeat(),
                             version=self.VERSION)

    def _get_heartbeat(self):
        return self._client.service_instance.CurrentTime()

    def _new_task_type_info(self, task_id):
        return vim.ExtensionTaskTypeInfo(taskID=task_id)

    def _new_task_extension_resource_info(self, locale, module, items):
        data = [vim.KeyValue(key=key, value=value) for key, value in items]
        return vim.ExtensionResourceInfo(locale=locale, module=module, data=data)
