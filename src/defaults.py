class FieldType:
    # Enum for the type of the field
    NUMBER = 0
    TIME = 1
    TEXT = 2


NUMBER_BASELINE = {
    "conf_thresh": 0.5,
    "cleanup_thresh": 0.0,
    "dilate": 1,
    "skew": 0,
    "vscale": 10,
    "rescale_patch": True,
    "binarization_method": 2,
}

TIME_BASELINE = {
    "conf_thresh": 0.5,
    "cleanup_thresh": 0.0,
    "dilate": 1,
    "skew": 2,
    "vscale": 10,
    "rescale_patch": True,
    "binarization_method": 2,
}

TEXT_BASELINE = {
    "conf_thresh": 0.5,
    "cleanup_thresh": 0.0,
    "dilate": 1,
    "skew": 0,
    "vscale": 10,
    "rescale_patch": True,
    "binarization_method": 0,
}


# 0 - Time MM:ss and ss.m
# 1 - Time MM:ss
# 2 - Time ss.m
# 3 - Time 00-59
# 4 - Shotclock 00-39
# 5 - Score 1dd
# 6 - Score ddd
# 7 - Period 1-4
# 8 - Period d
# 9 - Alphanumeric
# 10 - Any text
# 11 - Any number
# 12 - Custom
format_prefixes = [
    "^(?:(?:[0-5]?\\d:[0-5]\\d)|(?:[0-5]?\\d\\.\\d))$",  # Time MM:ss and ss.m
    "^[0-5]?\\d:[0-5]\\d$",  # Time MM:ss
    "^[0-5]?\\d\\.\\d$",  # Time ss.m
    "^[0-5]\\d$",  # Time 00-59
    "^[0-3]\\d$",  # Shotclock 00-39
    "^1?\\d{1,2}$",  # Score 1dd
    "^\\d{1,3}$",  # Score ddd
    "^[1-4]{1}$",  # Period 1-4
    "^\\d{1}$",  # Period d
    "^[A-Za-z0-9]*$",  # Alphanumeric
    "^.*$",  # Any text
    "^\\d*$",  # Any number
    "^.*$",  # Custom
]


# Default values for the scoreboard
default_boxes = [
    {
        "name": "Home Score",
        "type": FieldType.NUMBER,
        "x": 0,
        "y": 0,
        "width": 120,
        "height": 100,
        "obs_source_name": "Home score",
        "format_regex": format_prefixes[5],
        **NUMBER_BASELINE,
        "ordinal_indicator": False,
        "is_custom": False,
    },
    {
        "name": "Away Score",
        "type": FieldType.NUMBER,
        "x": 0,
        "y": 0,
        "width": 120,
        "height": 100,
        "obs_source_name": "Away score",
        "format_regex": format_prefixes[5],
        **NUMBER_BASELINE,
        "ordinal_indicator": False,
        "is_custom": False,
    },
    {
        "name": "Time",
        "type": FieldType.TIME,
        "x": 0,
        "y": 0,
        "width": 170,
        "height": 100,
        "obs_source_name": "Clock",
        "format_regex": format_prefixes[0],
        **TIME_BASELINE,
        "ordinal_indicator": False,
        "is_custom": False,
    },
    {
        "name": "Period",
        "type": FieldType.NUMBER,
        "x": 0,
        "y": 0,
        "width": 50,
        "height": 80,
        "obs_source_name": "Period",
        "format_regex": format_prefixes[7],
        **NUMBER_BASELINE,
        "ordinal_indicator": True,
        "is_custom": False,
    },
    {
        "name": "Home Fouls",
        "type": FieldType.NUMBER,
        "x": 0,
        "y": 0,
        "width": 80,
        "height": 80,
        "obs_source_name": "#Home Fouls",
        "format_regex": format_prefixes[11],
        **NUMBER_BASELINE,
        "ordinal_indicator": False,
        "is_custom": False,
    },
    {
        "name": "Away Fouls",
        "type": FieldType.NUMBER,
        "x": 0,
        "y": 0,
        "width": 80,
        "height": 80,
        "obs_source_name": "#Away Fouls",
        "format_regex": format_prefixes[11],
        **NUMBER_BASELINE,
        "ordinal_indicator": False,
        "is_custom": False,
    },
    {
        "name": "Shot Clock",
        "type": FieldType.NUMBER,
        "x": 0,
        "y": 0,
        "width": 150,
        "height": 100,
        "obs_source_name": "shotclock",
        "format_regex": format_prefixes[4],
        **NUMBER_BASELINE,
        "ordinal_indicator": False,
        "is_custom": False,
    },
]
default_custom_box_info = {
    "type": FieldType.NUMBER,
    "x": 0,
    "y": 0,
    "width": 150,
    "height": 100,
    "obs_source_name": "",
    "format_regex": format_prefixes[11],
    **NUMBER_BASELINE,
    "ordinal_indicator": False,
    "is_custom": True,
}


def default_info_for_box_name(name):
    # Get the info for a box name
    for box in default_boxes:
        if box["name"] == name:
            return box
    return default_custom_box_info


def _setting_or_default(settings, key, default_value):
    return settings[key] if key in settings else default_value


def normalize_settings_dict(settings, box_info):
    # Normalize the settings dict with default values if they are not present
    if not settings:
        settings = {}
    if not box_info:
        box_info = {
            "obs_source_name": "",
            "format_regex": format_prefixes[11],
            "type": FieldType.NUMBER,
            "ordinal_indicator": False,
            "is_custom": True,
        }
    return {
        "is_custom": (
            _setting_or_default(settings, "is_custom", box_info["is_custom"])
        ),
        "obs_source_name": (
            _setting_or_default(settings, "obs_source_name", box_info["obs_source_name"])
        ),
        "format_regex": (
            _setting_or_default(settings, "format_regex", box_info["format_regex"])
        ),
        "type": (_setting_or_default(settings, "type", box_info["type"])),
        "smoothing": (
            _setting_or_default(settings, "smoothing", box_info.get("smoothing", False))
        ),
        "skip_empty": (
            _setting_or_default(settings, "skip_empty", box_info.get("skip_empty", True))
        ),
        "conf_thresh": (
            _setting_or_default(settings, "conf_thresh", box_info.get("conf_thresh", 0.5))
        ),
        "cleanup_thresh": (
            _setting_or_default(
                settings, "cleanup_thresh", box_info.get("cleanup_thresh", 0)
            )
        ),
        "dilate": (_setting_or_default(settings, "dilate", box_info.get("dilate", 1))),
        "skew": (_setting_or_default(settings, "skew", box_info.get("skew", 0))),
        "vscale": (_setting_or_default(settings, "vscale", box_info.get("vscale", 10))),
        "autocrop": (
            _setting_or_default(settings, "autocrop", box_info.get("autocrop", False))
        ),
        "skip_similar_image": (
            _setting_or_default(
                settings, "skip_similar_image", box_info.get("skip_similar_image", False)
            )
        ),
        "remove_leading_zeros": (
            _setting_or_default(
                settings, "remove_leading_zeros", box_info.get("remove_leading_zeros", False)
            )
        ),
        "rescale_patch": (
            _setting_or_default(
                settings, "rescale_patch", box_info.get("rescale_patch", True)
            )
        ),
        "normalize_wh_ratio": (
            _setting_or_default(
                settings, "normalize_wh_ratio", box_info.get("normalize_wh_ratio", False)
            )
        ),
        "invert_patch": (
            _setting_or_default(
                settings, "invert_patch", box_info.get("invert_patch", False)
            )
        ),
        "dot_detector": (
            _setting_or_default(settings, "dot_detector", box_info.get("dot_detector", False))
        ),
        "binarization_method": (
            _setting_or_default(
                settings, "binarization_method", box_info.get("binarization_method", 0)
            )
        ),
        "ordinal_indicator": (
            _setting_or_default(
                settings, "ordinal_indicator", box_info["ordinal_indicator"]
            )
        ),
        "templatefield": (
            _setting_or_default(settings, "templatefield", box_info.get("templatefield", False))
        ),
        "templatefield_text": (
            _setting_or_default(
                settings, "templatefield_text", box_info.get("templatefield_text", "")
            )
        ),
        "composite_box": (
            _setting_or_default(settings, "composite_box", box_info.get("composite_box", False))
        ),
    }
