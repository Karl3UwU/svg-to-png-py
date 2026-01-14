from __future__ import annotations
import re
from parser import Node
from attributes import resolve_color_value, get_attribute_with_default

NAMED_COLORS = { # I AI generated this shit ✌
    'aliceblue': (240, 248, 255),
    'antiquewhite': (250, 235, 215),
    'aqua': (0, 255, 255),
    'aquamarine': (127, 255, 212),
    'azure': (240, 255, 255),
    'beige': (245, 245, 220),
    'bisque': (255, 228, 196),
    'black': (0, 0, 0),
    'blanchedalmond': (255, 235, 205),
    'blue': (0, 0, 255),
    'blueviolet': (138, 43, 226),
    'brown': (165, 42, 42),
    'burlywood': (222, 184, 135),
    'cadetblue': (95, 158, 160),
    'chartreuse': (127, 255, 0),
    'chocolate': (210, 105, 30),
    'coral': (255, 127, 80),
    'cornflowerblue': (100, 149, 237),
    'cornsilk': (255, 248, 220),
    'crimson': (220, 20, 60),
    'cyan': (0, 255, 255),
    'darkblue': (0, 0, 139),
    'darkcyan': (0, 139, 139),
    'darkgoldenrod': (184, 134, 11),
    'darkgray': (169, 169, 169),
    'darkgreen': (0, 100, 0),
    'darkgrey': (169, 169, 169),
    'darkkhaki': (189, 183, 107),
    'darkmagenta': (139, 0, 139),
    'darkolivegreen': (85, 107, 47),
    'darkorange': (255, 140, 0),
    'darkorchid': (153, 50, 204),
    'darkred': (139, 0, 0),
    'darksalmon': (233, 150, 122),
    'darkseagreen': (143, 188, 143),
    'darkslateblue': (72, 61, 139),
    'darkslategray': (47, 79, 79),
    'darkslategrey': (47, 79, 79),
    'darkturquoise': (0, 206, 209),
    'darkviolet': (148, 0, 211),
    'deeppink': (255, 20, 147),
    'deepskyblue': (0, 191, 255),
    'dimgray': (105, 105, 105),
    'dimgrey': (105, 105, 105),
    'dodgerblue': (30, 144, 255),
    'firebrick': (178, 34, 34),
    'floralwhite': (255, 250, 240),
    'forestgreen': (34, 139, 34),
    'fuchsia': (255, 0, 255),
    'gainsboro': (220, 220, 220),
    'ghostwhite': (248, 248, 255),
    'gold': (255, 215, 0),
    'goldenrod': (218, 165, 32),
    'gray': (128, 128, 128),
    'green': (0, 128, 0),
    'greenyellow': (173, 255, 47),
    'grey': (128, 128, 128),
    'honeydew': (240, 255, 240),
    'hotpink': (255, 105, 180),
    'indianred': (205, 92, 92),
    'indigo': (75, 0, 130),
    'ivory': (255, 255, 240),
    'khaki': (240, 230, 140),
    'lavender': (230, 230, 250),
    'lavenderblush': (255, 240, 245),
    'lawngreen': (124, 252, 0),
    'lemonchiffon': (255, 250, 205),
    'lightblue': (173, 216, 230),
    'lightcoral': (240, 128, 128),
    'lightcyan': (224, 255, 255),
    'lightgoldenrodyellow': (250, 250, 210),
    'lightgray': (211, 211, 211),
    'lightgreen': (144, 238, 144),
    'lightgrey': (211, 211, 211),
    'lightpink': (255, 182, 193),
    'lightsalmon': (255, 160, 122),
    'lightseagreen': (32, 178, 170),
    'lightskyblue': (135, 206, 250),
    'lightslategray': (119, 136, 153),
    'lightslategrey': (119, 136, 153),
    'lightsteelblue': (176, 196, 222),
    'lightyellow': (255, 255, 224),
    'lime': (0, 255, 0),
    'limegreen': (50, 205, 50),
    'linen': (250, 240, 230),
    'magenta': (255, 0, 255),
    'maroon': (128, 0, 0),
    'mediumaquamarine': (102, 205, 170),
    'mediumblue': (0, 0, 205),
    'mediumorchid': (186, 85, 211),
    'mediumpurple': (147, 112, 219),
    'mediumseagreen': (60, 179, 113),
    'mediumslateblue': (123, 104, 238),
    'mediumspringgreen': (0, 250, 154),
    'mediumturquoise': (72, 209, 204),
    'mediumvioletred': (199, 21, 133),
    'midnightblue': (25, 25, 112),
    'mintcream': (245, 255, 250),
    'mistyrose': (255, 228, 225),
    'moccasin': (255, 228, 181),
    'navajowhite': (255, 222, 173),
    'navy': (0, 0, 128),
    'oldlace': (253, 245, 230),
    'olive': (128, 128, 0),
    'olivedrab': (107, 142, 35),
    'orange': (255, 165, 0),
    'orangered': (255, 69, 0),
    'orchid': (218, 112, 214),
    'palegoldenrod': (238, 232, 170),
    'palegreen': (152, 251, 152),
    'paleturquoise': (175, 238, 238),
    'palevioletred': (219, 112, 147),
    'papayawhip': (255, 239, 213),
    'peachpuff': (255, 218, 185),
    'peru': (205, 133, 63),
    'pink': (255, 192, 203),
    'plum': (221, 160, 221),
    'powderblue': (176, 224, 230),
    'purple': (128, 0, 128),
    'red': (255, 0, 0),
    'rosybrown': (188, 143, 143),
    'royalblue': (65, 105, 225),
    'saddlebrown': (139, 69, 19),
    'salmon': (250, 128, 114),
    'sandybrown': (244, 164, 96),
    'seagreen': (46, 139, 87),
    'seashell': (255, 245, 238),
    'sienna': (160, 82, 45),
    'silver': (192, 192, 192),
    'skyblue': (135, 206, 235),
    'slateblue': (106, 90, 205),
    'slategray': (119, 128, 144),
    'slategrey': (119, 128, 144),
    'snow': (255, 250, 250),
    'springgreen': (0, 255, 127),
    'steelblue': (70, 130, 180),
    'tan': (210, 180, 140),
    'teal': (0, 128, 128),
    'thistle': (216, 191, 216),
    'tomato': (255, 99, 71),
    'turquoise': (64, 224, 208),
    'violet': (238, 130, 238),
    'wheat': (245, 222, 179),
    'white': (255, 255, 255),
    'whitesmoke': (245, 245, 245),
    'yellow': (255, 255, 0),
    'yellowgreen': (154, 205, 50),
}

def parse_hex_color(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.strip().lstrip('#')
    
    if len(hex_str) == 3:
        r = int(hex_str[0], 16) * 17
        g = int(hex_str[1], 16) * 17
        b = int(hex_str[2], 16) * 17
        return (r, g, b)
    elif len(hex_str) == 6:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return (r, g, b)
    elif len(hex_str) == 8:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return (r, g, b)
    
    return (0, 0, 0)

def parse_rgb_color(rgb_str: str) -> tuple[int, int, int]:
    rgb_str = rgb_str.strip().lower()
    
    match = re.match(r'rgba?\(([^)]+)\)', rgb_str)
    if not match:
        return (0, 0, 0)
    
    values = match.group(1).split(',')
    if len(values) < 3:
        return (0, 0, 0)
    
    try:
        r = int(float(values[0].strip()))
        g = int(float(values[1].strip()))
        b = int(float(values[2].strip()))
        
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        
        return (r, g, b)
    except (ValueError, IndexError):
        return (0, 0, 0)

def parse_color(color_str: str, node: Node = None) -> tuple[int, int, int] | None:
    if not color_str:
        return None
    
    color_str = color_str.strip()
    
    resolved = resolve_color_value(color_str, node)
    if resolved == 'none':
        return None
    
    if resolved != color_str:
        color_str = resolved
    
    color_str = color_str.lower()
    
    if color_str in NAMED_COLORS:
        return NAMED_COLORS[color_str]
    
    if color_str.startswith('#'):
        return parse_hex_color(color_str)
    
    if color_str.startswith('rgb'):
        return parse_rgb_color(color_str)
    
    return (0, 0, 0)

def get_color_with_opacity(color: tuple[int, int, int] | None, opacity: float) -> tuple[int, int, int, int]:
    if color is None:
        return (0, 0, 0, 0)
    
    r, g, b = color
    a = int(opacity * 255)
    return (r, g, b, a)

def blend_colors(foreground: tuple[int, int, int, int], 
                 background: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    fg_r, fg_g, fg_b, fg_a = foreground
    bg_r, bg_g, bg_b, bg_a = background
    
    fg_alpha = fg_a / 255.0
    bg_alpha = bg_a / 255.0
    
    out_alpha = fg_alpha + bg_alpha * (1 - fg_alpha)
    
    if out_alpha == 0:
        return (0, 0, 0, 0)
    
    if bg_alpha >= 1.0:
        out_r = int(fg_r * fg_alpha + bg_r * (1 - fg_alpha))
        out_g = int(fg_g * fg_alpha + bg_g * (1 - fg_alpha))
        out_b = int(fg_b * fg_alpha + bg_b * (1 - fg_alpha))
    else:
        out_r = int((fg_r * fg_alpha + bg_r * bg_alpha * (1 - fg_alpha)) / out_alpha)
        out_g = int((fg_g * fg_alpha + bg_g * bg_alpha * (1 - fg_alpha)) / out_alpha)
        out_b = int((fg_b * fg_alpha + bg_b * bg_alpha * (1 - fg_alpha)) / out_alpha)
    
    out_a = int(out_alpha * 255)
    
    return (out_r, out_g, out_b, out_a)

def get_node_color(node: Node, color_attr: str = 'fill', 
                   opacity_attr: str = 'opacity') -> tuple[int, int, int, int]:
    color_str = get_attribute_with_default(node, color_attr, use_inheritance=True)
    if color_str is None:
        if color_attr == 'fill':
            color_str = 'black'
        else:
            color_str = 'none'
    
    color = parse_color(color_str, node)
    
    opacity_str = get_attribute_with_default(node, opacity_attr, use_inheritance=True)
    if opacity_str:
        try:
            opacity = float(opacity_str)
            opacity = max(0.0, min(1.0, opacity))
        except (ValueError, TypeError):
            opacity = 1.0
    else:
        opacity = 1.0
    
    specific_opacity_attr = f"{color_attr}-opacity"
    specific_opacity_str = get_attribute_with_default(node, specific_opacity_attr, use_inheritance=True)
    if specific_opacity_str:
        try:
            specific_opacity = float(specific_opacity_str)
            specific_opacity = max(0.0, min(1.0, specific_opacity))
            opacity *= specific_opacity
        except (ValueError, TypeError):
            pass
    
    return get_color_with_opacity(color, opacity)

