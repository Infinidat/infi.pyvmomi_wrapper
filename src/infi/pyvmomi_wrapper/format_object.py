
from pyVmomi.VmomiSupport import Object, DataObject, ManagedObject, ManagedMethod, UncallableManagedMethod
from pyVmomi.VmomiSupport import F_LINK, datetime, binary, base64, Iso8601, FormatObject


def FormatObject(val, info=Object(name="", type=object, flags=0)):
    if val is None:
        return None
    elif isinstance(val, DataObject):
        if info.flags & F_LINK:
            return "<%s:%s>" % (val.__class__.__name__, val.key)
        else:
            result = dict()
            for prop in val._GetPropertyList():
                if prop.name in ('dynamicType', 'dynamicProperty'):
                    continue
                _obj = getattr(val, prop.name)
                if _obj is None:
                    continue
                _val = FormatObject(_obj, prop)
                if _val is None or (isinstance(_val, (list, tuple, dict)) and not len(_val)):
                    continue
                result[prop.name] = _val
            return result
    elif isinstance(val, ManagedObject):
        if val._serverGuid is None:
            return "%s:%s" % (val.__class__.__name__, val._moId)
        else:
            return "%s:%s:%s" % (val.__class__.__name__, val._serverGuid, val._moId)
    elif isinstance(val, list):
        itemType = getattr(val, 'Item', getattr(info.type, 'Item', object))
        item = Object(name="", type=itemType, flags=info.flags)
        result = [FormatObject(obj, item) for obj in val if obj]
        return [item for item in result if item is not None]
    elif isinstance(val, type):
        return val.__name__
    elif isinstance(val, UncallableManagedMethod):
        return val.name
    elif isinstance(val, ManagedMethod):
        return '%s.%s' % (val.info.type.__name__, val.info.name)
    elif isinstance(val, bool):
        return val
    elif isinstance(val, datetime):
        return Iso8601.ISO8601Format(val)
    elif isinstance(val, binary):
          return base64.b64encode(val)
    return val
