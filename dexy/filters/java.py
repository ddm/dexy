from dexy.filters.pexp import PexpectReplFilter
from dexy.filters.process import SubprocessCompileFilter
from dexy.filters.process import SubprocessStdoutFilter
import os
import platform

class JythonFilter(SubprocessStdoutFilter):
    """
    jython
    """
    ALIASES = ['jython']
    _SETTINGS = {
            'executable' : 'jython',
            'input-extensions' : [".py", ".txt"],
            'output-extensions' : [".txt"],
            'version-command' : "jython --version"
            }

    def is_active(klass):
        if platform.system() in ('Linux', 'Windows'):
            return True
        elif platform.system() in ('Darwin'):
            if hasattr(klass, 'log'):
                klass.log.warn("The jython dexy filter should not be run on MacOS due to a serious bug. This filter is being disabled.")
            return False
        else:
            if hasattr(klass, 'log'):
                klass.log.warn("""Can't detect your system. If you see this message please report this to the dexy project maintainer, your platform.system() value is '%s'. The jython dexy filter should not be run on MacOS due to a serious bug.""" % platform.system())
            return True

class JythonInteractiveFilter(PexpectReplFilter):
    """
    jython in REPL
    """
    ALIASES = ['jythoni']
    _SETTINGS = {
            'check-return-code' : False,
            'executable' : 'jython -i',
            'initial-timeout' : 30,
            'input-extensions' : [".py", ".txt"],
            'output-extensions' : [".pycon"],
            'version-command' : "jython --version"
            }

    def is_active(klass):
        if platform.system() in ('Linux', 'Windows'):
            return True
        elif platform.system() in ('Darwin'):
            print "The jythoni dexy filter should not be run on MacOS due to a serious bug. This filter is being disabled."
            return False
        else:
            print """Can't detect your system. If you see this message please report this to the dexy project maintainer, your platform.system() value is '%s'. The jythoni dexy filter should not be run on MacOS due to a serious bug.""" % platform.system()
            return True

class JavaFilter(SubprocessCompileFilter):
    """
    Compiles java code and runs main method.
    """
    ALIASES = ['java']
    _SETTINGS = {
            'check-return-code' : True,
            'classpath' : ("Custom entries in classpath.", []),
            'executable' : 'javac',
            'input-extensions' : ['.java'],
            'output-extensions' : ['.txt'],
            'main' : ("Main method.", None),
            'version-command' : 'java -version',
            'compiled-extension' : ".class",
            'compiler-command-string' : "%(prog)s %(compiler_args)s %(classpath)s %(script_file)s"
            }

    def setup_cp(self):
        """
        Makes sure the current working directory is on the classpath, also adds
        any specified CLASSPATH elements. Assumes that CLASSPATH elements are either
        absolute paths, or paths relative to the artifacts directory. Also, if
        an input has been passed through the javac filter, its directory is
        added to the classpath.
        """
        self.log.debug("in setup_cp for %s" % self.artifact.key)

        classpath_elements = []

        working_dir = os.path.join(self.artifact.wd(), self.output().parent_dir())
        abs_working_dir = os.path.abspath(working_dir)
        self.log.debug("Adding working dir %s to classpath" % abs_working_dir)
        classpath_elements.append(abs_working_dir)

        for doc in self.processed():
            if (doc.output().ext == ".class") and ("javac" in doc.key):
                classpath_elements.append(doc.output().parent_dir())

        for item in self.setting('classpath'):
            for x in item.split(":"):
                classpath_elements.append(x)

        env = self.setup_env()
        if env and env.has_key("CLASSPATH"):
            for x in env['CLASSPATH'].split(":"):
                classpath_elements.append(x)

        cp = ":".join(classpath_elements)
        self.log.debug("Classpath %s" % cp)
        return cp

    def compile_command_string(self):
        args = self.default_command_string_args()
        args['compiler_args'] = self.setting('compiler-args')

        # classpath
        cp = self.setup_cp()
        if len(cp) == 0:
            args['classpath'] = ''
        else:
            args['classpath'] = "-classpath %s" % cp

        return self.setting('compiler-command-string') % args

    def run_command_string(self):
        args = self.default_command_string_args()
        args['main_method'] = self.setup_main_method()

        # classpath
        cp = self.setup_cp()
        if len(cp) == 0:
            args['classpath'] = ''
        else:
            args['classpath'] = "-cp %s" % cp

        return "java %(args)s %(classpath)s %(main_method)s" % args

    def setup_main_method(self):
        basename = os.path.basename(self.input().name)
        default_main = os.path.splitext(basename)[0]
        if self.setting('main'):
            return self.setting('main')
        else:
            return default_main

class JavacFilter(JavaFilter):
    """
    Compiles java code and returns the .class object
    """
    ALIASES = ['javac']

    _SETTINGS = {
            'executable' : 'javac',
            'input-extensions' : ['.java'],
            'output-extensions' : ['.class'],
            'version-command' : 'java -version'
            }

    def process(self):
        # Compile the code
        command = self.compile_command_string()
        proc, stdout = self.run_command(command, self.setup_env())
        self.handle_subprocess_proc_return(command, proc.returncode, stdout)
        self.copy_canonical_file()
