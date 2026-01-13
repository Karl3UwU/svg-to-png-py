from __future__ import annotations
import math
import re
from parser import Node

INCHES_TO_PX = 96.0
CM_TO_PX = INCHES_TO_PX / 2.54
MM_TO_PX = CM_TO_PX / 10
PT_TO_PX = INCHES_TO_PX / 72.0
PC_TO_PX = PT_TO_PX * 12

def parse_number_with_unit(value: str) -> tuple[float, str]:
    if not value or not isinstance(value, str):
        return (0.0, "")
    
    value = value.strip()
    if not value:
        return (0.0, "")
    
    number_pattern = re.compile(r'^([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([a-zA-Z%]*)$') # Stolen from stackoverflow
    match = number_pattern.match(value)
    
    if match:
        num_str = match.group(1)
        unit = match.group(2) if match.group(2) else ""
        try:
            num_value = float(num_str)
            return (num_value, unit)
        except ValueError:
            return (0.0, "")
    
    try:
        return (float(value), "")
    except ValueError:
        return (0.0, "")

def normalize_unit(value: str, unit_type: str = "length", 
                   viewport_width: float = None, viewport_height: float = None,
                   font_size: float = None, parent_font_size: float = None) -> float:
    num_value, unit = parse_number_with_unit(value)
    
    if unit == "":
        if unit_type == "angle":
            return num_value
        return num_value
    
    unit = unit.lower()
    
    if unit == "px":
        return num_value
    elif unit == "pt":
        return num_value * PT_TO_PX
    elif unit == "pc":
        return num_value * PC_TO_PX
    elif unit == "in":
        return num_value * INCHES_TO_PX
    elif unit == "cm":
        return num_value * CM_TO_PX
    elif unit == "mm":
        return num_value * MM_TO_PX
    elif unit == "em":
        if font_size is not None:
            return num_value * font_size
        elif parent_font_size is not None:
            return num_value * parent_font_size
        else:
            return num_value * 16.0
    elif unit == "ex":
        em_value = normalize_unit(value.replace("ex", "em"), unit_type, 
                                 viewport_width, viewport_height, font_size, parent_font_size)
        return em_value * 0.5
    elif unit == "%":
        if unit_type == "angle":
            return (num_value / 100.0) * 360.0
        elif viewport_width is not None and viewport_height is not None:
            return (num_value / 100.0) * ((viewport_width + viewport_height) / 2.0)
        else:
            return num_value
    elif unit == "deg":
        return num_value
    elif unit == "rad":
        return math.degrees(num_value)
    elif unit == "grad":
        return num_value * 0.9  # 1 grad = 0.9 degrees
    elif unit == "turn":
        return num_value * 360.0
    
    return num_value

def get_normalized_attribute(node: Node, attr_name: str, default: float = 0.0,
                            viewport_width: float = None, viewport_height: float = None,
                            use_inheritance: bool = True) -> float:
    value = node.get_attribute(attr_name, None, use_inheritance)
    if value is None:
        return default
    
    return normalize_unit(value, "length", viewport_width, viewport_height)

def get_normalized_attribute_with_default(node: Node, attr_name: str, 
                                         viewport_width: float = None, 
                                         viewport_height: float = None,
                                         use_inheritance: bool = True) -> float:
    from attributes import get_attribute_with_default
    value = get_attribute_with_default(node, attr_name, use_inheritance)
    if value is None:
        return 0.0
    
    return normalize_unit(value, "length", viewport_width, viewport_height)

def mapRange(x, frommin, frommax, tomin, tomax):
    return ((x-frommin)/(frommax-frommin))*(tomax-tomin)+tomin

def clamp(x, minx, maxx):
    return max(min(x, maxx), minx)

