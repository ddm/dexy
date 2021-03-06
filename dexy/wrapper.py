from dexy.utils import s
from dexy.utils import file_exists
import dexy.batch
import dexy.database
import dexy.doc
import dexy.parser
import dexy.reporter
import logging
import logging.handlers
import os
import shutil
import posixpath

class Wrapper(object):
    """
    Class that assists in interacting with dexy, including running dexy.
    """
    DEFAULTS = {
        'artifacts_dir' : 'artifacts',
        'config_file' : 'dexy.conf',
        'danger' : False,
        'db_alias' : 'sqlite3',
        'db_file' : 'dexy.sqlite3',
        'disable_tests' : False,
        'dont_use_cache' : False,
        'dry_run' : False,
        'encoding' : 'utf-8',
        'exclude' : '.git, .svn, tmp, cache',
        'exclude_also' : '',
        'full' : False,
        'globals' : '',
        'hashfunction' : 'md5',
        'ignore_nonzero_exit' : False,
        'log_dir' : 'logs',
        'log_file' : 'dexy.log',
        'log_format' : "%(name)s - %(levelname)s - %(message)s",
        'log_level' : "INFO",
        'plugins': '',
        'profile' : False,
        'recurse' : True,
        'reports' : '',
        'siblings' : False,
        'silent' : False,
        'strace' : False,
        'target' : False,
        'timing' : True,
        'uselocals' : False
    }

    LOG_LEVELS = {
        'DEBUG' : logging.DEBUG,
        'INFO' : logging.INFO,
        'WARN' : logging.WARN
    }

    def __init__(self, *args, **kwargs):
        self.args = args
        self.initialize_attribute_defaults()
        self.update_attributes_from_kwargs(kwargs)
        self.filemap = {}
        self.project_root = os.path.abspath(os.getcwd())

    def initialize_attribute_defaults(self):
        for name, value in self.DEFAULTS.iteritems():
            setattr(self, name, value)

    def update_attributes_from_kwargs(self, kwargs):
        for key, value in kwargs.iteritems():
            if not key in self.DEFAULTS:
                raise Exception("invalid kwargs %s" % key)
            setattr(self, key, value)

    def setup(self, setup_dirs=False, log_config=True):
        self.walk()
        if setup_dirs:
            self.setup_dexy_dirs()
        self.check_dexy_dirs()
        self.setup_log()
        self.setup_db()
        if log_config:
            self.log_dexy_config()

    def run(self):
        self.setup()

        self.batch = self.init_batch()
        self.batch.run(self.target)

        self.save_db()
        self.log.debug("batch %s complete" % self.batch.batch_id)

    def log_dexy_config(self):
        self.log.debug("dexy has config:")
        for k in sorted(self.__dict__):
            if not k in ('ast', 'args', 'db', 'log', 'tasks'):
                self.log.debug("  %s: %s" % (k, self.__dict__[k]))

    def db_path(self):
        return os.path.join(self.artifacts_dir, self.db_file)

    def log_path(self):
        return os.path.join(self.log_dir, self.log_file)

    def setup_batch(self):
        """
        Shortcut method for calling init_batch and assigning to batch instance variable.
        """
        self.batch = self.init_batch()

    def init_batch(self):
        batch = dexy.batch.Batch(self)

        if len(self.args) > 0:
            batch.tree = self.docs_from_args()
            batch.create_lookup_table()
        else:
            ast = self.load_doc_config()
            batch.load_ast(ast)

        return batch

    def run_docs(self, *docs):
        self.args = docs
        self.run()

    def setup_read(self, batch_id=None):
        self.setup(log_config=False)

        if batch_id:
            self.batch_id = batch_id
        else:
            self.batch_id = self.db.max_batch_id()

    def check_dexy_dirs(self):
        if not (file_exists(self.artifacts_dir) and file_exists(self.log_dir)):
            raise dexy.exceptions.UserFeedback("You need to run 'dexy setup' in this directory first.")

    def setup_dexy_dirs(self):
        if not file_exists(self.artifacts_dir):
            os.mkdir(self.artifacts_dir)
        if not file_exists(self.log_dir):
            os.mkdir(self.log_dir)

    def remove_dexy_dirs(self, reports=False):
        if file_exists(self.artifacts_dir):
            shutil.rmtree(self.artifacts_dir)
        if file_exists(self.log_dir):
            shutil.rmtree(self.log_dir)

        if reports:
            if isinstance(reports, bool):
                reports=dexy.reporter.Reporter

            for report in reports:
                report.remove_reports_dir()

    def logging_log_level(self):
        try:
            return self.LOG_LEVELS[self.log_level.upper()]
        except KeyError:
            msg = "'%s' is not a valid log level, check python logging module docs."
            raise dexy.exceptions.UserFeedback(msg % self.log_level)

    def setup_log(self):
        if not hasattr(self, 'log') or not self.log:
            self.log = logging.getLogger('dexy')
            self.log.setLevel(self.logging_log_level())

            handler = logging.handlers.RotatingFileHandler(
                    self.log_path(),
                    encoding="utf-8")

            formatter = logging.Formatter(self.log_format)
            handler.setFormatter(formatter)

            self.log.addHandler(handler)

    def setup_db(self):
        self.db = dexy.database.Database.create_instance(self.db_alias, self)

    def docs_from_args(self):
        """
        Creates document objects from argument strings, returns array of newly created docs.
        """
        docs = []
        for arg in self.args:
            self.log.debug("Processing arg %s" % arg)
            doc = self.create_doc_from_arg(arg)
            if not doc:
                raise Exception("no doc created for %s" % arg)
            doc.wrapper = self
            docs.append(doc)
        return docs

    def create_doc_from_arg(self, arg, **kwargs):
        if isinstance(arg, dexy.task.Task):
            return arg

        elif isinstance(arg, list):
            if not isinstance(arg[0], basestring):
                msg = "First arg in %s should be a string" % arg
                raise dexy.exceptions.UserFeedback(msg)

            if not isinstance(arg[1], dict):
                msg = "Second arg in %s should be a dict" % arg
                raise dexy.exceptions.UserFeedback(msg)

            if kwargs:
                raise Exception("Shouldn't have kwargs if arg is a list")

            alias, pattern = dexy.parser.Parser(self).qualify_key(arg[0])
            return dexy.task.Task.create(alias, pattern, **arg[1])

        elif isinstance(arg, basestring):
            alias, pattern = dexy.parser.Parser.qualify_key(arg[0])
            return dexy.task.Task.create(alias, pattern, **kwargs)

        else:
            raise Exception("unknown arg type %s for arg %s" % (arg.__class__.__name__, arg))

    def save_db(self):
        self.db.save()

    def reports_dirs(self):
        return [i.setting('dir') for i in dexy.reporter.Reporter]

    def report(self):
        if self.reports:
            self.log.debug("generating user-specified reports '%s'" % self.reports)
            reporters = []
            for alias in self.reports.split():
                reporter = dexy.reporter.Reporter.create_instance(alias)
                reporters.append(reporter)
        else:
            self.log.debug("no reports specified, generating all reports for which 'default' setting is True")
            reporters = [i for i in dexy.reporter.Reporter if i.setting('default')]

        for reporter in reporters:
            batch_ok = (self.batch.state != 'failed')
            run_on_failed_batch = reporter.setting('run-on-failed-batch')
            if batch_ok or run_on_failed_batch:
                self.log.debug("running reporter %s" % reporter.ALIASES[0])
                reporter.run(self)

    def is_valid_dexy_dir(self, dirpath, dirnames):
        nodexy_file = os.path.join(dirpath, '.nodexy')
        pip_delete_this_dir_file = os.path.join(dirpath, "pip-delete-this-directory.txt")
        if file_exists(nodexy_file):
            self.log.debug("  skipping directory '%s' and its children because .nodexy file found" % dirpath)
            dirnames[:] = []
            return False
        else:
            if file_exists(pip_delete_this_dir_file):
                print s("""WARNING pip left an old build/ file lying around!
                You probably want to cancel this dexy run (ctrl+c) and remove this directory first!
                Dexy will continue running unless you stop it...""")

            for x in self.exclude_dirs():
                if x in dirnames:
                    skipping_dir = os.path.join(dirpath, x)
                    self.log.debug("  skipping directory '%s' because it matches exclude '%s'" % (skipping_dir, x))
                    dirnames.remove(x)

            return True

    def load_doc_config(self):
        """
        Look for document config files in current working tree and load them.
        """
        ast = dexy.parser.AbstractSyntaxTree(self)

        config_files_used = []
        dirs_with_config_files = []
        for alias in dexy.parser.Parser.plugins.keys():
            for filepath, fileinfo in self.filemap.iteritems():
                if filepath.endswith(alias):
                    os_filepath = fileinfo['ospath']
                    self.log.debug("loading config from '%s'" % os_filepath)

                    with open(os_filepath, "r") as f:
                        config_text = f.read()

                    parent_dir = os.path.dirname(os_filepath)
                    if parent_dir in dirs_with_config_files:
                        msg = "more than one config file found in dir %s" % parent_dir
                        raise dexy.exceptions.UserFeedback(msg)
                    dirs_with_config_files.append(parent_dir)

                    config_files_used.append(os_filepath)
    
                    parser = dexy.parser.Parser.create_instance(alias, self, ast)
                    parser.build_ast(parent_dir, config_text)

        if len(config_files_used) == 0:
            msg = "WARNING: Didn't find any document config files (like %s)"
            print msg % (", ".join(dexy.parser.Parser.plugins.keys()))
        self.log.debug("AST completed:")
        ast.debug(self.log)

        return ast

    def setup_config(self):
        self.setup_dexy_dirs()
        self.setup_log()
        self.load_doc_config()

    def cleanup_partial_run(self):
        if hasattr(self, 'db'):
            # TODO remove any entries which don't have
            self.db.save()

    def exclude_dirs(self):
        exclude_str = self.exclude
        if self.exclude_also:
            exclude_str += ",%s" % self.exclude_also
        exclude = [d.strip() for d in exclude_str.split(",")]

        exclude.append(self.artifacts_dir)
        exclude.append(self.log_dir)
        exclude.extend(self.reports_dirs())

        return exclude

    def parse_globals(self):
        globals_dict = {}
        if len(self.globals) > 0:
            for pair in self.globals.split(","):
                x, y = pair.split("=")
                globals_dict[x] = y

        return globals_dict

    def walk(self):
        """
        Generates a complete list of files present in the project directory.
        """
        exclude = self.exclude_dirs()

        for dirpath, dirnames, filenames in os.walk('.'):
            for x in exclude:
                if x in dirnames:
                    dirnames.remove(x)

            if '.nodexy' in filenames:
                dirnames[:] = []
            else:
                for filename in filenames:
                    filepath = posixpath.normpath(posixpath.join(dirpath, filename))
                    self.filemap[filepath] = {}
                    self.filemap[filepath]['stat'] = os.stat(os.path.join(dirpath, filename))
                    self.filemap[filepath]['ospath'] = os.path.normpath(os.path.join(dirpath, filename))
