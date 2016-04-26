from pyVmomi import vim, sms
from pyVim.connect import SoapStubAdapter
import time
from ..errors import TimeoutException


class SmsClient(object):
    def __init__(self, client):
        import re
        # https://github.com/vmware/pyvmomi/pull/165#issuecomment-213623822
        session_cookie = client.service_instance._GetStub().cookie.split('"')[1]
        additional_headers = {'vcSessionCookie': session_cookie}
        stub = SoapStubAdapter(client.host, path="/sms/sdk", ns="sms/4.0", requestContext=additional_headers)
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
