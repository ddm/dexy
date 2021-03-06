import dexy.filters.api
import dexy.filters.archive
import dexy.filters.boto
import dexy.filters.deprecated
import dexy.filters.example
import dexy.filters.idio
import dexy.filters.java
import dexy.filters.latex
import dexy.filters.md
import dexy.filters.pexp
import dexy.filters.phantomjs
import dexy.filters.pydoc
import dexy.filters.pyg
import dexy.filters.rst
import dexy.filters.split
import dexy.filters.standard
import dexy.filters.fluid_html
import dexy.filters.sub
import dexy.filters.templating
import dexy.filters.wordpress
import dexy.filters.yamlargs

import dexy.filter
import os
yaml_file = os.path.join(os.path.dirname(__file__), "filters.yaml")
dexy.filter.Filter.register_plugins_from_yaml(yaml_file)

import pkg_resources
# Automatically register plugins in any python package named like dexy_*
for dist in pkg_resources.working_set:
    if dist.key.startswith("dexy-"):
        import_pkg = dist.egg_name().split("-")[0]
        try:
            __import__(import_pkg)
        except ImportError as e:
            print "plugin", import_pkg, "not registered because", e
