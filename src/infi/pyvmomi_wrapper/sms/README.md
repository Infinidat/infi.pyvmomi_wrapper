Example for using the SMS client:

```
from infi.pyvmomi_wrapper import Client
from infi.pyvmomi_wrapper.sms import SmsClient

# first open a "regular" client
client = Client("vcenter-server", username="myuser", password="pass")

sms_client = SmsClient(client)
storage_manager = sms_client.service_instance.QueryStorageManager()
storage_providers = storage_manager.QueryProvider()
```