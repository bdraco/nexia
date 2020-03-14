"""Utils."""


def is_number(string):
    """String is a number."""
    try:
        float(string)
        return True
    except ValueError:
        return False


def find_dict_with_keyvalue_in_json(json_dict, key_in_subdict, value_to_find):
    """
    Searches a json_dict for the key key_in_subdict that matches value_to_find
    :param json_dict: dict
    :param key_in_subdict: str - the name of the key in the subdict to find
    :param value_to_find: str - the value of the key in the subdict to find
    :return: The subdict to find
    """
    for data_group in json_dict:
        if data_group[key_in_subdict] == value_to_find:
            return data_group

    raise KeyError
