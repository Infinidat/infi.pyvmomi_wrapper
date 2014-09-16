Example for using EsxCLI:

```
from infi.pyvmomi_wrapper import Client
from infi.pyvmomi_wrapper.esxcli import EsxCLI

# first open a "regular" client
client = Client("vcenter-server", username="myuser", password="pass")
# get a host to run on
host = client.get_host_systems()[0]

cli = EsxCLI(host)

# get time
time_cli = cli.get("system.time")
print time_cli.Get()

# list SATP rules
rule_cli = cli.get("storage.nmp.satp.rule")
print rule_cli.List()
```