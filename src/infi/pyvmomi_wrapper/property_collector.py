from pyVmomi import vim
from infi.pyutils.decorators import wraps
from infi.pyutils.lazy import cached_method
from logging import getLogger
from munch import Munch
from copy import deepcopy, copy

try:
    from gevent.lock import Semaphore as Lock
except ImportError:
    from threading import Lock

logger = getLogger(__name__)

INITIAL_VERSION = ''

# foo.bar
# foo.arProp["key val"]
# foo.arProp["key val"].baz
PROPERTY_NAME_PATTERN = r'\w+|\["[^"\]]+"\]'


def locking_decorator(wrapped):
    @wraps(wrapped)
    def wrapper(self, *args, **kwargs):
        self._lock.acquire()
        try:
            return wrapped(self, *args, **kwargs)
        finally:
            self._lock.release()
    return wrapper


class CachedPropertyCollector(object):
    """
    Facade for using PropertyCollectors to fetch a list of properties from all instances of a specific object_type

    :param client: :py:class:`Client` instance
    :param managed_object_type: A managed object type, e.g. vim.HostSystem
    :param properties_list: A list of properties to fetch, can be nested, e.g. config.storageDevice
    """
    def __init__(self, client, managed_object_type, properties_list):
        super(CachedPropertyCollector, self).__init__()
        self._client = client
        self._property_collector = None
        self._managed_object_type = managed_object_type
        self._properties_list = properties_list
        self._version = INITIAL_VERSION
        self._result = {}
        self._lock = Lock()

    def __del__(self):
        if self._property_collector is not None:
            try:
                self._property_collector.Destroy()
            except vim.ManagedObjectNotFound:
                # in case session ended, property collector may already be destroyed
                pass
            self._property_collector = None

    def __repr__(self):
        args = (self.__class__.__name__, getattr(self, '_managed_object_type', None),
                getattr(self, '_properties_list', []), getattr(self, '_version', repr('')))
        return "<{}: object_type={!r}, properties={!r}, version={}>".format(*args)

    def _create_traversal_spec(self, name, managed_object_type, property_name, next_selector_names=[]):
        return self._client._create_traversal_spec(name, managed_object_type, property_name, next_selector_names)

    @cached_method
    def _get_container_view(self):
        kwargs = dict(container=self._client.root, type=[self._managed_object_type], recursive=True)
        return self._client.service_content.viewManager.CreateContainerView(**kwargs)

    @cached_method
    def _get_object_set(self):
        return [vim.ObjectSpec(obj=self._get_container_view(), selectSet=self._get_select_set())]

    @cached_method
    def _get_prop_set(self):
        return [vim.PropertySpec(type=self._managed_object_type, pathSet=self._properties_list)]

    @cached_method
    def _get_property_collector(self):
        self._property_collector = self._client.service_content.propertyCollector.CreatePropertyCollector()
        self._property_filter = self._property_collector.CreateFilter(self._get_property_filter_spec(), partialUpdates=True)
        return self._property_collector

    @cached_method
    def _get_property_filter_spec(self):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.FilterSpec.html
        return vim.PropertyFilterSpec(propSet=self._get_prop_set(), objectSet=self._get_object_set())

    @cached_method
    def _get_select_set(self):
        """This method returns a SelectSet that travels the entire heirarchy.
        If you want to go over heirarchy in a more efficient way, overload this method"""
        select_set = list(self._client._build_full_traversal())
        select_set.append(self._create_traversal_spec('container', vim.ContainerView, "container",
                          [select.name for select in select_set]))
        return select_set

    def _get_changes(self, time_in_seconds=0, truncated_version=None):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.html#WaitForUpdatesEx
        from pyVmomi import vim
        property_collector = self._get_property_collector()
        wait_options = vim.WaitOptions(maxWaitSeconds=time_in_seconds)
        logger.debug("Checking for updates on property collector {!r}".format(self))
        try:
            update = property_collector.WaitForUpdatesEx(truncated_version or self._version, wait_options)
            logger.debug("There is {} pending update".format('no' if update is None else 'indeed an'))
            return update
        except vim.InvalidCollectorVersion:
            logger.error("caught InvalidCollectorVersion fault, collector version is out of date or invalid")
            self._version = INITIAL_VERSION
            return self._get_changes(time_in_seconds=time_in_seconds)

    def _merge_object_update_into_cache__enter(self, object_ref_key, objectUpdate):
        # Rebuild the properties dict
        properties = {propertyChange.name: propertyChange.val
                      for propertyChange in filter(lambda propertyChange: propertyChange.op in ['add', 'assign'],
                                                   objectUpdate.changeSet)}
        message = "Replacing cache for object_ref_key {} with a dictionary of the following keys {}"
        logger.debug(message.format(object_ref_key, properties.keys()))
        self._result = dict(self._result)  # copy
        self._result[object_ref_key] = properties

    def _merge_object_update_into_cache__leave(self, object_ref_key, objectUpdate=None):
        # the object no longer exists, we drop it from the result dictionary
        logger.debug("Removing object_ref_key {} from cache".format(object_ref_key))
        self._result = dict(item for item in self._result.iteritems() if item[0] != object_ref_key)

    def _walk_on_property_path(self, path):
        from re import findall
        matches = [Munch(value=item) for item in findall(PROPERTY_NAME_PATTERN, path)]
        for match in matches:
            if match.value.startswith('['):
                match.type = "key"
                match.value = match.value[2:-2]
            else:
                match.type = "property"
        return matches

    def _get_list_or_object_to_update(self, object_ref_key, property_dict, path, value, last=False):
        for key in property_dict.keys():
            if path.startswith(key):
                break
        else:
            raise Exception("HIPVM-665 property collector is trying to modify an empty dict")
        # key is a prefix of path
        if path == key:
            # we want to return the top-level 'property_dict', but we need to clone it from and replace it in
            # self._result, in order for the result to actually update (and without replacing the reference)
            # for code that use it
            new_dict = dict(self._result[object_ref_key])
            self._result[object_ref_key] = new_dict
            return new_dict
        object_to_update = property_dict[key]
        path = path.replace(key, '').lstrip('.')
        walks = self._walk_on_property_path(path)
        parent_object = property_dict
        key_to_update = key
        for item in walks if last else walks[:-1]:
            key_to_update = item.value
            parent_object = object_to_update
            if item.type == "key":
                object_to_update = [element for element in object_to_update if element.key == key_to_update][0]
            else:
                if isinstance(object_to_update, (dict, Munch)):
                    object_to_update = object_to_update.get(key_to_update)
                else:
                    object_to_update = getattr(object_to_update, key_to_update)

        new_object = copy(object_to_update)
        if isinstance(parent_object, dict):
            parent_object[key_to_update] = new_object
        elif isinstance(parent_object, list):
            parent_object[parent_object.index(object_to_update)] = new_object
        else:
            setattr(parent_object, key_to_update, new_object)
        return new_object

    def _get_property_name_to_update(self, property_dict, path):
        for key in property_dict.keys():
            if path == key:
                return key
        return self._walk_on_property_path(path)[-1].value

    def _get_key_to_remove(self, key):
        return self._walk_on_property_path(key)[-1].value

    def _merge_property_change__add(self, object_ref_key, property_dict, key, value):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.Change.html
        list_to_update = self._get_list_or_object_to_update(object_ref_key, property_dict, key, value)
        list_to_update.insert(-1, value)

    def _merge_property_change__assign(self, object_ref_key, property_dict, key, value):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.Change.html
        object_to_update = self._get_list_or_object_to_update(object_ref_key, property_dict, key, value, key.endswith(']'))
        name = self._get_property_name_to_update(property_dict, key)
        assignment_method = getattr(object_to_update, "__setitem__", object_to_update.__setattr__)
        assignment_method(name, value)

    def _merge_property_change__remove(self, object_ref_key, property_dict, key, value):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.Change.html
        list_to_update = self._get_list_or_object_to_update(object_ref_key, property_dict, key, value)
        key_to_remove = self._get_key_to_remove(key)
        value_list = [item for item in list_to_update if item.key == key_to_remove]
        if value_list:
            value = value_list[0]
            list_to_update.remove(value)

    def _merge_object_update_into_cache__modify(self, object_ref_key, objectUpdate):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.ObjectUpdate.html
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.Change.html
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.MissingProperty.html
        properties = self._result[object_ref_key]
        logger.debug("Modifying cache for object_ref_key {}".format(object_ref_key))
        updatemethods = dict(add=self._merge_property_change__add,
                             assign=self._merge_property_change__assign,
                             remove=self._merge_property_change__remove,
                             indirectRemove=self._merge_property_change__remove)
        for propertyChange in objectUpdate.changeSet:
            logger.debug("Modifying property {}, operation {}".format(propertyChange.name, propertyChange.op))
            updatemethods[propertyChange.op](object_ref_key, properties, propertyChange.name, propertyChange.val)
        for missingSet in objectUpdate.missingSet:
            logger.debug("Removing from cache a property that has gone missing {}".format(missingSet.path))
            self._merge_property_change__remove(object_ref_key, properties, missingSet.path, None)

    def _merge_object_update_into_cache(self, objectUpdate):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.ObjectUpdate.html
        updateMethods = dict(enter=self._merge_object_update_into_cache__enter,
                             leave=self._merge_object_update_into_cache__leave,
                             modify=self._merge_object_update_into_cache__modify)
        object_ref_key = self._client.get_reference_to_managed_object(objectUpdate.obj)
        logger.debug("Update kind {} on cache key {}".format(objectUpdate.kind, object_ref_key))
        updateMethods[objectUpdate.kind](object_ref_key, objectUpdate)

    def _remove_missing_object_from_cache(self, missingObject):
        key = self._client.get_reference_to_managed_object(missingObject.obj)
        logger.debug("Removing key {} from cache because it is missing in the filterSet".format(key))
        self._result = dict(item for item in self._result.iteritems() if item[0] != key)

    def _merge_changes_into_cache(self, update):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.UpdateSet.html
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.FilterUpdate.html
        for filterSet in update.filterSet:
            for missingObject in filterSet.missingSet:
                self._remove_missing_object_from_cache(missingObject)
            for objectUpdate in filterSet.objectSet:
                self._merge_object_update_into_cache(objectUpdate)
        if update.truncated:
            self._merge_changes_into_cache(self._get_changes(0, update.version))
        else:
            self._version = update.version
            logger.debug("Cache of {!r} is updated for version {}".format(self, self._version))

    def _reset_and_update(self):
        self._version = INITIAL_VERSION
        self._result = {}
        update = self._get_changes()
        self._merge_changes_into_cache(update)

    def check_for_updates(self):
        """:returns: True if the cached data is not up to date"""
        return self.wait_for_updates(0)

    @locking_decorator
    def get_properties(self):
        """This method checks first if there are changes in the server.
        If there are, the changes are merged into the cache and then returned from the cache.
        If there are not, the data is returned from the cache.
        :rtype: a dictionary with MoRefs as keys, and propertyName=propertyValue dictionary as values"""

        update = self._get_changes()
        if update is not None:
            try:
                self._merge_changes_into_cache(update)
            except:
                logger.exception("Caught unexpected exception during property collector update merge. Resetting.")
                self._reset_and_update()
        return self.get_properties_from_cache()

    def get_properties_from_cache(self):
        """:returns: the cached properties immediately from the cache.
        :rtype: a dictionary with MoRefs as keys, and propertyName=propertyValue dictionary as values"""
        return self._result

    @locking_decorator
    def wait_for_updates(self, time_in_seconds):
        """This method is blocking a maximum time of time_in_seconds, depending if there are changes on the server.
        This method does not update the cache with the changes, if there are any.
        :returns: True if there are updates on the server, False if there are not."""
        update = self._get_changes(time_in_seconds)
        return update is not None


class HostSystemCachedPropertyCollector(CachedPropertyCollector):
    """
    Facade for fetching host attributes by using a faster traversal (e.g no need to traverse inside HostSystem)
    """

    def __init__(self, client, host_properties):
        super(HostSystemCachedPropertyCollector, self).__init__(client, vim.HostSystem, host_properties)

    @cached_method
    def _get_select_set(self):
        crToH = self._create_traversal_spec("crToH", vim.ComputeResource, "host")
        dcToHf = self._create_traversal_spec("dcToHf", vim.Datacenter, "hostFolder", ["visitFolders"])
        visitFolders = self._create_traversal_spec("visitFolders", vim.Folder, "childEntity",
            ["visitFolders", "dcToHf", "crToH"])
        container = self._create_traversal_spec("container", vim.ContainerView, "container", ["visitFolders"])
        return [container, visitFolders, dcToHf, crToH]


class VirtualMachinePropertyCollector(CachedPropertyCollector):
    def __init__(self, client, properties):
        super(VirtualMachinePropertyCollector, self).__init__(client, vim.VirtualMachine, properties)

    @cached_method
    def _get_select_set(self):
        rpToRp = self._create_traversal_spec("rpToRp", vim.ResourcePool, "resourcePool", ["rpToRp", "rpToVm"])
        rpToVm = self._create_traversal_spec("rpToVm", vim.ResourcePool, "vm")
        crToRp = self._create_traversal_spec("crToRp", vim.ComputeResource, "resourcePool", ["rpToRp", "rpToVm"])
        dcToHf = self._create_traversal_spec("dcToHf", vim.Datacenter, "hostFolder", ["visitFolders"])
        visitFolders = self._create_traversal_spec("visitFolders", vim.Folder, "childEntity",
            ["visitFolders", "dcToHf", "crToRp"])
        container = self._create_traversal_spec("container", vim.ContainerView, "container", ["visitFolders"])
        return [container, visitFolders, dcToHf, crToRp, rpToRp, rpToVm]


class TaskPropertyCollector(CachedPropertyCollector):
    def __init__(self, client, tasks, properties=["info.state"]):
        super(TaskPropertyCollector, self).__init__(client, vim.Task, properties)
        self.tasks = tasks

    def _get_object_set(self):
        return [vim.ObjectSpec(obj=task) for task in self.tasks]

    def iter_task_states_changes(self, timeout_in_seconds=None):
        update = self._get_changes(time_in_seconds=timeout_in_seconds)
        if update is None:
            return
        for filter_set in update.filterSet:
            for obj_set in filter_set.objectSet:
                task = obj_set.obj
                for change in obj_set.changeSet:
                    if change.name == 'info.state':    # we don't look for any other changes so this should be true
                        yield task, change.val
