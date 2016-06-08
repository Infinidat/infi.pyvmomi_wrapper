from pyVmomi import vim, sms
from pyVim.connect import SoapStubAdapter
import time
from ..errors import TimeoutException


class SmsClient(object):
    def __init__(self, client, version="version4"):
        import re
        # https://github.com/vmware/pyvmomi/pull/165#issuecomment-213623822
        client_stub = client.service_instance._GetStub()
        session_cookie = client_stub.cookie.split('"')[1]
        ssl_context = client_stub.schemeArgs.get('context')
        additional_headers = {'vcSessionCookie': session_cookie}
        stub = SoapStubAdapter(client.host, path="/sms/sdk", version="sms.version." + version,
            sslContext=ssl_context, requestContext=additional_headers)
        self.service_instance = sms.ServiceInstance("ServiceInstance", stub)

    def wait_for_task(self, task, timeout=None):
        t0 = time.time()
        while task.QuerySmsTaskInfo().state in [sms.SmsTaskState.running, ]:
            time.sleep(0.1)
            t1 = time.time()
            if timeout is not None and (t1 - t0) > timeout:
                raise TimeoutException("Timeout waiting for task")

        if task.QuerySmsTaskInfo().state == sms.SmsTaskState.error:
            raise task.QuerySmsTaskInfo().error

        return task.QuerySmsTaskInfo().state
