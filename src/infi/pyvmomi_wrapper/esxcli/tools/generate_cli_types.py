def generate_cli_data_objects(host):
    dmanager = host.RetrieveDynamicTypeManager()

    data_types = dmanager.DynamicTypeMgrQueryTypeInfo(None).dataTypeInfo
    for data_type in data_types:
        vmodlName = data_type.name
        wsdlName = data_type.wsdlName
        parent = data_type.base[0]
        version = data_type.version
        props = []
        for prop in data_type.property:
            props.append('("{}", "{}", "{}", {})'.format(prop.name, prop.type, prop.version, "F_OPTIONAL"))
        props = "[{}]".format(", ".join(props))
        yield 'CreateDataType("{}", "{}", "{}", "{}", {})'.format(vmodlName, wsdlName, parent, version, props)

if __name__ == '__main__':
    for i in generate_cli_data_objects(host):
        print i