import os


def convert_to_comma_seperated(listobject):
    """
    The function converts a list of elements into a comma-separated string.

    :param listobject: The parameter "listobject" is a variable that represents a list of elements
    :return: a comma-separated string if the input is a list, or the input itself if it is a string or a
    list with only one element.
    """
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
