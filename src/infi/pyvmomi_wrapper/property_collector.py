from pyVmomi import vim
from infi.pyutils.decorators import wraps
from infi.pyutils.lazy import cached_method
from logging import getLogger
from munch import Munch
from copy import deepcopy

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
            self._property_collector.Destroy()
            self._property_collector = None

    def __repr__(self):
        args = (self.__class__.__name__, getattr(self, '_managed_object_type', None),
                getattr(self, '_properties_list', []), getattr(self, '_version', repr('')))
        return "<{}: object_type={!r}, properties={!r}, version={}>".format(*args)

    def _guess_traversal_spec_name(self, managed_object_type, property_name):
        """:returns: A guessable name of a TraversalSpec being used in this facade"""
        managed_object_type_name = managed_object_type.__name__.split(".")[-1]      # strip "vim." prefix
        name = "{}.{}".format(managed_object_type_name, property_name)
        return name

    def _create_traversal_spec(self, managed_object_type, property_name, next_selector_names=[]):
        """:returns: a TravelSpec object whose name is '{managed_object_type}.{property_name}'"""
        return vim.TraversalSpec(name=self._guess_traversal_spec_name(managed_object_type, property_name),
                                 type=managed_object_type, path=property_name,
                                 selectSet=[vim.SelectionSpec(name=name) for name in next_selector_names])

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
        select_set.append(self._create_traversal_spec(vim.ContainerView, 'container',
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
        self._result[object_ref_key] = properties

    def _merge_object_update_into_cache__leave(self, object_ref_key, objectUpdate=None):
        # the object no longer exists, we drop it from the result dictionary
        logger.debug("Removing object_ref_key {} from cache".format(object_ref_key))
        self._result.pop(object_ref_key, None)

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

    def _get_list_and_object_to_update(self, property_dict, path, value, last=False):
        for key in property_dict.keys():
            if path.startswith(key):
                break
        # key is a prefix of path
        if path == key:
            return property_dict
        object_to_update = property_dict[key]
        path = path.replace(key, '').lstrip('.')
        walks = self._walk_on_property_path(path)
        for item in walks if last else walks[:-1]:
            if item.type == "key":
                object_to_update = [element for element in object_to_update if element.key == item.value][0]
            else:
                if isinstance(object_to_update, (dict, Munch)):
                    object_to_update = object_to_update.get(item.value)
                else:
                    object_to_update = getattr(object_to_update, item.value)
        return object_to_update

    def _get_property_name_to_update(self, property_dict, path):
        for key in property_dict.keys():
            if path == key:
                return key
        return self._walk_on_property_path(path)[-1].value

    def _get_key_to_remove(self, key):
        return self._walk_on_property_path(key)[-1].value

    def _merge_property_change__add(self, property_dict, key, value):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.Change.html
        list_to_update = self._get_list_and_object_to_update(property_dict, key, value)
        logger.debug("Appending {}".format(value.__class__))
        list_to_update.insert(-1, value)

    def _merge_property_change__assign(self, property_dict, key, value):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.Change.html
        object_to_update = self._get_list_and_object_to_update(property_dict, key, value, key.endswith(']'))
        name = self._get_property_name_to_update(property_dict, key)
        logger.debug("Assigning {} to {}".format(value.__class__, name))
        assignment_method = getattr(object_to_update, "__setitem__", object_to_update.__setattr__)
        assignment_method(name, value)

    def _merge_property_change__remove(self, property_dict, key, value):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.Change.html
        list_to_update = self._get_list_and_object_to_update(property_dict, key, value)
        key_to_remove = self._get_key_to_remove(key)
        value_list = [item for item in list_to_update if item.key == key_to_remove]
        if not value_list:
            msg = "No item with key {!r} in list {!r}, original value is {!r}, original key is {!r}"
            logger.warn(msg.format(key_to_remove, list_to_update, value, key))
        else:
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
            updatemethods[propertyChange.op](properties, propertyChange.name, propertyChange.val)
        for missingSet in objectUpdate.missingSet:
            logger.debug("Removing from cache a property that has gone missing{}".format(missingSet.path))
            self._merge_property_change__remove(properties, missingSet.path, None)

    def _merge_object_update_into_cache(self, objectUpdate):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.ObjectUpdate.html
        updateMethods = dict(enter=self._merge_object_update_into_cache__enter,
                             leave=self._merge_object_update_into_cache__leave,
                             modify=self._merge_object_update_into_cache__modify)
        object_ref_key = self._client.get_reference_to_managed_object(objectUpdate.obj)
        logger.debug("Update kind {} on cache key {}".format(objectUpdate.kind, object_ref_key))
        updateMethods[objectUpdate.kind](object_ref_key, objectUpdate)

    def _merge_changes_into_cache(self, update):
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.UpdateSet.html
        # http://vijava.sourceforge.net/vSphereAPIDoc/ver5/ReferenceGuide/vmodl.query.PropertyCollector.FilterUpdate.html
        logger.debug("Merging changes into cache; the following log messages contain the current cache and the incoming update")
        logger.debug(repr(self._result))
        logger.debug(repr(update))
        for filterSet in update.filterSet:
            for key in map(lambda missing_object: self._client.get_reference_to_managed_object(missing_object.obj), filterSet.missingSet):
                logger.debug("Removing key {} from cache because it is missing in the filterSet".format(key))
                self._result.pop(key, None)
            for objectUpdate in filterSet.objectSet:
                self._merge_object_update_into_cache(objectUpdate)
        if update.truncated:
            self._merge_changes_into_cache(self._get_changes(0, update.version))
        else:
            self._version = update.version
            logger.debug("Cache of {!r} is updated for version {}".format(self, self._version))
            logger.debug("Updated cached after merge follows")
            logger.debug(repr(self._result))

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
            self._result = deepcopy(self._result)
            self._merge_changes_into_cache(update)
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
        select_set = list()
        select_set.append(self._create_traversal_spec(vim.ClusterComputeResource, 'host'))
        select_set.append(self._create_traversal_spec(vim.ComputeResource, 'host'))
        select_set.append(self._create_traversal_spec(vim.Datacenter, 'hostFolder',
                          ['Folder.childEntity']))
        select_set.append(self._create_traversal_spec(vim.Folder, 'childEntity',
                          ['Datacenter.hostFolder', 'ClusterComputeResource.host', 'ComputeResource.host']))
        select_set.append(self._create_traversal_spec(vim.ContainerView, 'container',
                          [select.name for select in select_set]))
        return select_set


class VirtualMachinePropertyCollector(CachedPropertyCollector):
    def __init__(self, client, properties):
        super(VirtualMachinePropertyCollector, self).__init__(client, vim.VirtualMachine, properties)

    @cached_method
    def _get_select_set(self):
        select_set = list()
        select_set.append(self._create_traversal_spec(vim.Datacenter, 'vmFolder',
                                                    ["Folder.childEntity"]))
        select_set.append(self._create_traversal_spec(vim.Folder, 'childEntity',
                                                    ['Datacenter.vmFolder', "Folder.childEntity"]))
        select_set.append(self._create_traversal_spec(vim.ContainerView, 'container',
                          [select.name for select in select_set]))
        return select_set

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
