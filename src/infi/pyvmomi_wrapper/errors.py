class PyvmomiWrapperException(Exception):
    pass

class ExtensionNotRegisteredException(PyvmomiWrapperException):
    pass

class ExtensionAlreadyRegisteredException(PyvmomiWrapperException):
    pass

class CreateTaskException(PyvmomiWrapperException):
    pass

class TimeoutException(PyvmomiWrapperException):
    pass

class CLITypeException(PyvmomiWrapperException):
    pass
