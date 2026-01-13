from __future__ import annotations
import re

xml_pattern = re.compile(r'(\<[^>]*?\>)', flags=re.DOTALL | re.MULTILINE)
comment_pattern = re.compile(r'\<!--.*?--\>', flags=re.DOTALL | re.MULTILINE)
first_word_pattern = re.compile(r'^\s*[/!?]*\s*(\w+)')

def is_self_terminating(svg_value: str) -> bool:
    return svg_value.rstrip().endswith('/>')

def is_terminator(svg_value: str) -> bool:
    return svg_value.strip().startswith('</')

def get_tag(svg_value: str) -> str:
    content = svg_value.strip()
    if content.startswith('</'):
        content = content[2:]
    elif content.startswith('<'):
        content = content[1:]
    if content.endswith('>'):
        content = content[:-1]
    if content.endswith('/'):
        content = content[:-1]
    
    match = first_word_pattern.search(content)
    if match:
        return match.group(1)
    return ""

def parse_attributes(element: str) -> dict:
    attributes = {}
    
    content = element.strip()
    if content.startswith('</'):
        return attributes
    if content.startswith('<'):
        content = content[1:]
    if content.endswith('>'):
        content = content[:-1]
    if content.endswith('/'):
        content = content[:-1].rstrip()
    
    parts = content.split(None, 1)
    if len(parts) < 2:
        return attributes
    
    attr_string = parts[1]
    
    state = 0
    accumulator = ""
    current_key = ""
    
    for i in range(len(attr_string)):
        char = attr_string[i]
        
        if state == 0:
            if char == '=':
                current_key = accumulator.strip()
                accumulator = ""
                state = 1
            elif char != ' ':
                accumulator += char
        elif state == 1:
            if char == '"':
                state = 2
            elif char == "'":
                state = 2
        elif state == 2:
            if char == '\\':
                state = 3
            elif char == '"' or char == "'":
                attributes[current_key] = accumulator
                accumulator = ""
                current_key = ""
                state = 0
            else:
                accumulator += char
        elif state == 3:
            accumulator += char
            state = 2
    
    if current_key and not attributes.get(current_key):
        if accumulator:
            attributes[current_key] = accumulator
    
    return attributes

def parse_svg_file(path: str) -> list[str]:
    with open(path, 'r', encoding='utf-8') as file:
        data = file.read()
    
    entries = xml_pattern.findall(data)
    entries = [x for x in entries if not comment_pattern.search(x)]
    
    return entries

class Node:
    def __init__(self, element: str):
        self.element = element
        self.tag = get_tag(element)
        self.attributes = parse_attributes(element)
        self.children = []
        self.parent = None
        
    def add_child(self, element: str):
        new_node = Node(element)
        new_node.parent = self
        self.children.append(new_node)
        return new_node
    
    def add_node_child(self, new_node: 'Node'):
        new_node.parent = self
        self.children.append(new_node)
        return new_node
        
    def compare_tag(self, element: str) -> bool:
        return self.tag == get_tag(element)

    def get_inherited_attributes(self) -> dict:
        inherited_attrs = {
            'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin',
            'stroke-miterlimit', 'stroke-dasharray', 'stroke-dashoffset',
            'opacity', 'fill-opacity', 'stroke-opacity',
            'font-family', 'font-size', 'font-weight', 'font-style',
            'text-anchor', 'color', 'visibility', 'display',
            'clip-path', 'mask', 'filter'
        }
        
        merged = self.attributes.copy()
        current = self.parent
        while current is not None:
            for attr_name, attr_value in current.attributes.items():
                if attr_name in inherited_attrs and attr_name not in merged:
                    merged[attr_name] = attr_value
            current = current.parent
        
        return merged
    
    def get_attribute(self, attr_name: str, default: str = None, use_inheritance: bool = True) -> str:
        if use_inheritance:
            inherited = self.get_inherited_attributes()
            return inherited.get(attr_name, default)
        else:
            return self.attributes.get(attr_name, default)

    def print_tree(self, level=0):
        indent = '    ' * level
        attrs_str = ', '.join([f"{k}={v}" for k, v in list(self.attributes.items())[:3]])
        if len(self.attributes) > 3:
            attrs_str += "..."
        print(f"{indent}- {self.tag} ({attrs_str})")
        for child in self.children:
            child.print_tree(level + 1)

