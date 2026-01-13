from parser import Node

def resolve_color_value(value: str, node: Node = None) -> str:
    if not value:
        return None
    
    value = value.strip().lower()
    
    if value == 'none':
        return 'none'
    
    if value == 'currentcolor':
        if node:
            color_attr = node.get_attribute('color', 'black')
            return color_attr
        return 'black'
    
    return value

SVG_DEFAULTS = {
    'fill': 'black',
    'stroke': 'none',
    'stroke-width': '1',
    'stroke-linecap': 'butt',
    'stroke-linejoin': 'miter',
    'stroke-miterlimit': '4',
    'stroke-dasharray': 'none',
    'stroke-dashoffset': '0',
    'opacity': '1',
    'fill-opacity': '1',
    'stroke-opacity': '1',
    'fill-rule': 'nonzero',
    'clip-rule': 'nonzero',
    'visibility': 'visible',
    'display': 'inline',
    'color': 'black',
    'font-family': 'serif',
    'font-size': '12',
    'font-weight': 'normal',
    'font-style': 'normal',
    'text-anchor': 'start',
    'preserveAspectRatio': 'xMidYMid meet',
}

def get_attribute_with_default(node: Node, attr_name: str, use_inheritance: bool = True) -> str:
    value = node.get_attribute(attr_name, None, use_inheritance)
    
    if value is not None:
        return value
    
    return SVG_DEFAULTS.get(attr_name, None)

