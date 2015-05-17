from sys import exc_info
from logging import getLogger
from infi.pyutils.decorators import wraps
from infi.pyutils.contexts import contextmanager
from pyVmomi import vim
from .errors import CreateTaskException
from .extension import ExtensionFacade

# The only valuable reference for how to use custom tasks is:
# http://www.doublecloud.org/2010/09/creating-your-own-task-and-event-in-vsphere/

"""
This facade allows developers to easily create Tasks in vSphere.

To create tasks, use the TaskManager:

>>> manager = TaskManager(client, "myapp")
>>> with manager.task("Doing this"):
...     pass
"""

logger = getLogger(__name__)

class TaskManager(object):
    def __init__(self, client, extension_key=__name__):
        super(TaskManager, self).__init__()
        self._client = client
        self._managed_object = self._client.service_content.taskManager
        self._extension = ExtensionFacade(self._client, extension_key)

    def task(self, managed_object, name, parent=None):
        if not self._extension.is_registered():
            self._extension.register()
        if not self._extension.is_task_registered(name):
            self._extension.register_task(name)
        task_id = self._extension.get_task_id(name)
        task_managed_object = self._create_task(managed_object, task_id, parent)
        task = Task(self._client, task_managed_object)
        return task

    def _create_task(self, managed_object, type_id, parent=None):
        kwargs = dict(obj=managed_object, taskTypeId=type_id, cancelable=False, initiatedBy=None)
        kwargs['parentTaskKey'] = getattr(parent, 'get_id', lambda: None)()
        logger.info("Creating task {!r}".format(kwargs))
        try:
            task_managed_object = self._managed_object.CreateTask(**kwargs).task
        except:
            logger.exception("Failed to create task")
            raise CreateTaskException, None, exc_info()[-1]
        return task_managed_object

class Task(object):
    def __init__(self, client, managed_object):
        super(Task, self).__init__()
        self._client = client
        self._managed_object = managed_object

    def update_progress(self, percentage):
        self._managed_object.UpdateProgress(percentage)

    def step(self, steps):
        for _ in self.iter(steps):
            pass

    def iter(self, steps):
        percentage = 0
        increment = 100 / len(steps)
        with self:
            for step in steps:
                step()
                percentage += increment
                self.update_progress(percentage)
                yield percentage
            self.update_progress(100)

    def wraps(self, func):
        @wraps(func)
        def callable(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return callable

    @contextmanager
    def silent_context(self):
        try:
            with self:
                yield
        except Exception:
            pass

    def __enter__(self):
        self.set_state('running')
        return self

    def __exit__(self, *exc_info):
        exception_has_been_raised = exc_info != (None, None, None)
        if exception_has_been_raised:
            self.set_state('error')
            self.set_description(str(exc_info[1].message))
            logger.error("Exception has been raised inside the task context", exc_info=exc_info)
            raise exc_info[0], exc_info[1], exc_info[2]
        self.set_state('success')
        self.set_description("")

    def get_name(self):
        data_object = self._get_info()
        return data_object.name or ''

    def set_state(self, state):
        fault = None
        if state == 'error':
            fault = vim.VimFault()
        self._managed_object.SetTaskState(state, None, fault)

    def set_description(self, message):
        msg = vim.LocalizableMessage(key=self._managed_object.info.key, message=message)
        self._managed_object.SetTaskDescription(msg)

    def get_id(self):
        return self._get_info().key

    def _get_info(self):
        return self._managed_object.info

    def __repr__(self):
        return "<Task id={!r}>".format(self.get_id())
