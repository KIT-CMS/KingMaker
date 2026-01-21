from functools import cache
import os
import re
from XRootD.client import FileSystem
from XRootD.client.flags import StatInfoFlags


def convert_to_comma_seperated(listobject):
    """
    The function converts a list of elements into a comma-separated string.

    :param listobject: The parameter "listobject" is a variable that represents a list of elements
    :return: a comma-separated string if the input is a list, or the input itself if it is a string or a
    list with only one element.
    """
    if isinstance(listobject, set):
        listobject = list(listobject)
    if isinstance(listobject, str):
        return listobject
    elif len(listobject) == 1:
        return listobject[0]
    else:
        return ",".join(listobject)


def ensure_dir(file_path):
    """
    The function `ensure_dir` creates a directory if it does not already exist, given a file path.

    :param file_path: The `file_path` parameter is a string that represents the path to a file or
    directory
    """
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)


def create_abspath(file_path):
    """
    The function creates an absolute path if it does not already exist.

    :param file_path: The file_path parameter is a string that represents the path to a file or
    directory
    """
    if not os.path.exists(file_path):
        os.makedirs(file_path)


@cache
def get_xrootd_client(xrootd_server: str) -> FileSystem:
    """
    Get the `XRootD.client.FileSystem` for an `xrootd_server`.

    The returned object is only created once. After that, a reference to the
    cached object is returned by this function.

    :param xrootd_server: Address of an XRootD server.

    :returns: An `XRootD.client.FileSystem`, providing a file system-like
        interface to the server.
    """
    return FileSystem(xrootd_server)


def get_alternate_file_uri(
    file: str,
    xrootd_servers: list[str],
) -> str:
    """
    Get an alternative path to the file via a list of perferred XRootD servers.

    If `file` is consistent with the pattern of an XRootD path, the base server
    address is exchanged and it is checked whether the file is accessible from
    a server in the list `xrootd_servers`. The availability of the file is
    checked in the order of appearance of the servers in the list. For the
    first server, for which the file can be accessed, the new file URI is
    returned.

    To check if the `file` has a XRootD-like URI, the following regular
    expression is used:

    ```python
    re.match(r"^root:\/\/[^\/]\/+(.*)$", file)
    ```

    If `file` is not consistent with a XRootD URI or the file is not found on
    any of the servers in the `xrootd_servers` list, the original file is
    returned.

    :param file: File URI for a file on an XRootD server.

    :param xrootd_servers: List of XRootD server URIs, for which the function
        tests the availability of the file.

    :returns: The final file name.
    """

    # Check whether the file fulfills the pattern of a usual XRootD file path.
    # If not, just return the file without modifying the path. Otherwise,
    # extract the file path without the server address.
    m = re.match(r"^(root://[^/]+)/+(.+)$", file)
    if m is None:
        return file
    path = f"/{m.group(2).rstrip('/')}"

    # Cycle through the given XRootD servers and check if the file exists
    # there. Return the first one that is found. If no file is found on the
    # servers given in the list, the original file is returned.
    for xrootd_server in xrootd_servers:
        status, stat_info = get_xrootd_client(xrootd_server).stat(path)
        if status.ok:
            if (stat_info.flags & StatInfoFlags.IS_READABLE) > 0:
                return f"{xrootd_server.rstrip('/')}///{path.lstrip('/')}"

    return file
