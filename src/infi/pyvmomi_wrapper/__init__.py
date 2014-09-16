__import__("pkg_resources").declare_namespace(__name__)
from .client import Client, get_reference_to_managed_object
from .tasks import TaskManager, Task
from .property_collector import CachedPropertyCollector
