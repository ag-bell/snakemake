__author__ = "Christopher Tomkins-Tinch"
__copyright__ = "Copyright 2015, Christopher Tomkins-Tinch"
__email__ = "tomkinsc@broadinstitute.org"
__license__ = "MIT"

import os, re, ftplib
from itertools import product, chain
from contextlib import contextmanager

# module-specific
from snakemake.remote import AbstractRemoteObject, AbstractRemoteProvider
from snakemake.exceptions import FTPFileException
import snakemake.io 

try:
    # third-party modules
    import ftputil
    import ftputil.session
except ImportError as e:
    raise WorkflowError("The Python 3 package 'ftputil' " + 
        "must be installed to use SFTP remote() file functionality. %s" % e.msg)

class RemoteProvider(AbstractRemoteProvider):
    def __init__(self, *args, **kwargs):
        super(RemoteProvider, self).__init__(*args, **kwargs)

class RemoteObject(AbstractRemoteObject):
    """ This is a class to interact with an FTP server.
    """

    def __init__(self, *args, keep_local=False, provider=None, encrypt_data_channel=False, **kwargs):
        super(RemoteObject, self).__init__(*args, keep_local=keep_local, provider=provider, **kwargs)

        self.encrypt_data_channel = encrypt_data_channel
        
    # === Implementations of abstract class members ===

    @contextmanager #makes this a context manager. after 'yield' is __exit__()
    def ftpc(self):     
        # if args have been provided to remote(), use them over those given to RemoteProvider()
        args_to_use = self.provider.args
        if len(self.args):
            args_to_use = self.args

        # use kwargs passed in to remote() to override those given to the RemoteProvider()
        # default to the host and port given as part of the file, falling back to one specified
        # as a kwarg to remote() or the RemoteProvider (overriding the latter with the former if both)
        kwargs_to_use = {}
        kwargs_to_use["host"] = self.host
        kwargs_to_use["username"] = None
        kwargs_to_use["password"] = None
        kwargs_to_use["port"] = self.port
        kwargs_to_use["encrypt_data_channel"] = self.encrypt_data_channel

        for k,v in self.provider.kwargs.items():
            kwargs_to_use[k] = v
        for k,v in self.kwargs.items():
            kwargs_to_use[k] = v

        ftp_base_class = ftplib.FTP_TLS if kwargs_to_use["encrypt_data_channel"] else ftplib.FTP

        ftp_session_factory = ftputil.session.session_factory(
                       base_class=ftp_base_class,
                       port=kwargs_to_use["port"],
                       encrypt_data_channel= kwargs_to_use["encrypt_data_channel"],
                       debug_level=None)

        conn = ftputil.FTPHost(kwargs_to_use["host"], kwargs_to_use["username"], kwargs_to_use["password"], session_factory=ftp_session_factory)
        yield conn
        conn.close()

    def exists(self):
        if self._matched_address:
            with self.ftpc() as ftpc:
                return ftpc.path.exists(self.remote_path)
                if ftpc.path.exists(self.remote_path):
                    return ftpc.path.isfile(self.remote_path)
            return False
        else:
            raise SFTPFileException("The file cannot be parsed as an FTP path in form 'host:port/abs/path/to/file': %s" % self.file())

    def mtime(self):
        if self.exists():
            with self.ftpc() as ftpc:
                ftpc.synchronize_times()
                return ftpc.path.getmtime(self.remote_path)
        else:
            raise SFTPFileException("The file does not seem to exist remotely: %s" % self.file())

    def size(self):
        if self.exists():
            with self.ftpc() as ftpc:
                return ftpc.path.getsize(self.remote_path)
        else:
            return self._iofile.size_local

    def download(self, make_dest_dirs=True):
        with self.ftpc() as ftpc:
            if self.exists():
                # if the destination path does not exist
                if not os.path.exists(os.path.dirname(self.local_path)) and make_dest_dirs:
                    os.makedirs(os.path.dirname(self.local_path))
                ftpc.synchronize_times()
                ftpc.download(source=self.remote_path, target=self.local_path)
            else:
                raise SFTPFileException("The file does not seem to exist remotely: %s" % self.file())
    def upload(self):
        with self.ftpc() as ftpc:
            ftpc.synchronize_times()
            ftpc.upload(source=self.local_path, target=self.remote_path)

    @property
    def list(self):
        file_list = []

        pattern = os.path.normpath(self.remote_path)
        first_wildcard = re.search("{[^{]", pattern)
        dirname = os.path.dirname(pattern[:first_wildcard.start(
        )]) if first_wildcard else os.path.dirname(pattern)
        if not dirname:
            dirname = "."

        with self.ftpc() as ftpc:
            file_list = [(os.path.join(dirpath, f) if dirpath != "." else f) 
                    for dirpath, dirnames, filenames in ftpc.walk(dirname) 
                    for f in chain(filenames, dirnames)]
            file_list = [file_path[1:] if file_path[0] == "/" else file_path for file_path in file_list]

        return file_list

    # === Related methods ===

    @property
    def name(self):
        return self.path_remainder

    @property
    def _matched_address(self):
        return re.search("^(?P<host>[A-Za-z0-9\-\.]+)(?:\:(?P<port>[0-9]+))?(?P<path_remainder>.*)$", self._iofile._file)
    
    @property
    def protocol(self):
        if self._matched_address:
            return self._matched_address.group("protocol")

    @property
    def host(self):
        if self._matched_address:
            return self._matched_address.group("host")

    @property
    def port(self):
        if self._matched_address.group("port"):
            return int(self._matched_address.group("port"))
        else:
            return 21
    
    @property
    def path_remainder(self):
        if self._matched_address:
            return self._matched_address.group("path_remainder")

    @property
    def local_path(self):
        return self._iofile._file

    @property
    def remote_path(self):
        return self.path_remainder
