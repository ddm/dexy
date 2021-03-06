import dexy.plugin
import hashlib

class Metadata(dexy.plugin.Plugin):
    ALIASES = []
    __metaclass__ = dexy.plugin.PluginMeta

    @classmethod
    def is_active(klass):
        return True

    def get_string_for_hash(self):
        ordered = []
        for k in sorted(self.__dict__):
            v = self.__dict__[k]
            ordered.append((k, str(v),))
        return str(ordered)

class Md5(Metadata):
    """
    Class that stores metadata for a task. Uses md5 to calculate hash.
    """
    ALIASES = ['md5']
    def compute_hash(self):
        text = self.get_string_for_hash()
        return hashlib.md5(text).hexdigest()
