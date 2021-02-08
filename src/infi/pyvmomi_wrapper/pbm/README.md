Example for using the PBM client:

```
from infi.pyvmomi_wrapper import Client
from infi.pyvmomi_wrapper.pbm import PbmClient

# first open a "regular" client
client = Client("vcenter-server", username="myuser", password="pass")

pbm_client = PbmClient(client)
pbm_content = pbm_client.PbmRetrieveServiceContent()
```