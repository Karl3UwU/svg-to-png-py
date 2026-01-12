from __future__ import annotations
import math, re, numpy, sys

xml_pattern = re.compile(r'\<(.*?)\>', flags=re.DOTALL | re.MULTILINE)
comment_pattern = re.compile(r'\!--(.*?)--', flags=re.DOTALL | re.MULTILINE)
first_word_pattern = re.compile(r'^\s*[/!?]*\s*(\w+)')

def is_self_terminating(svg_value: str):
    return svg_value.endswith('/')

def is_terminator(svg_value: str):
    return svg_value.startswith('/')

def get_tag(svg_value: str):
    return first_word_pattern.search(svg_value).group(1)

def str_to_int(value: str):
    return int(value)

def str_to_float(value: str):
    return float(value)

hex_converter = {
    3: [1, 16],
    6: [2, 256]
}

def str_to_hex(value: str):
    value = value[1:]
    splits = [int(value[i:i+hex_converter[len(value)][0]], 16)/hex_converter[len(value)][1] for i in range(0, len(value), hex_converter[len(value)][0])]
    
    return splits

def mapRange(x, frommin, frommax, tomin, tomax):
    return ((x-frommin)/(frommax-frommin))*(tomax-tomin)+tomin

def clamp(x, minx, maxx):
    return max(min(x, maxx), minx)

def extractArguments(line: str):
    line2 = line.split(" ", 1)[1]
    args = {}
    state = 0
    accumulator = ""
    temp_hash_key = ""
    for i in range(len(line2)):
        if(line2[i] == '='):
            if(state == 0):
                temp_hash_key = accumulator
                args[temp_hash_key] = None
                accumulator = ""
                state = 1
        if(state == 0):
            if(line2[i] != ' '):
                accumulator = accumulator + line2[i]
        elif (state == 1):
            if(line2[i] == '\"'):
                state = 2
        elif (state == 2):
            if(line2[i] == '\\'):
                state = 3
            elif (line2[i] == '\"'):
                args[temp_hash_key] = accumulator
                state = 0
                accumulator = ""
            else:
                accumulator = accumulator + line2[i]
        elif(state == 3):
            accumulator = accumulator + line2[i]
            if(line2[i] == '\"'):
                state = 2
    return args

class Node:
    def __init__(self, value: str):
        self.value = value
        self.tag = get_tag(value)
        self.children = []
        self.parent = None
        
    def add_child(self, value: str):
        new_node = Node(value)
        new_node.parent = self
        new_node.tag = get_tag(new_node.value)
        self.children.append(new_node)
    
    def add_node_child(self, new_node: Node):
        new_node.parent = self
        self.children.append(new_node)
        
    def compare_tag(self, compare_svg: str) -> bool:
        return self.tag == get_tag(compare_svg)

    def print_tree(self, level=0):
        indent = '    ' * level
        print(f"{indent}- {self.tag}")
        for child in self.children:
            child.print_tree(level + 1)

class SVGState:
    def __init__(self, entries: list[str] = []):
        self.metadata = {}
        self.svg_tree: Node = None
        self.parse_svg_contents(entries)
        pass
    
    def parse_svg_contents(self, entries: list[str]):
        iterator = iter(entries)
        
        for svg_element in iterator:
            tag = get_tag(svg_element)
            if tag == "svg":
                self.svg_tree = Node(svg_element)
                r = self.svg_tree
                break
            self.metadata[tag] = svg_element

        for svg_element in iterator:
            if(r == None): return
            if(is_terminator(svg_element) and r.compare_tag(svg_element)):
                r = r.parent
                continue
            if(is_self_terminating(svg_element)):
                r.add_child(svg_element)
            else:
                new_child = Node(svg_element)
                r.add_node_child(new_child)
                r = new_child

class Renderer:
    def __init__(self):
        self.render_matrix = numpy.full((100, 100, 3), 0)
        self.svg_state = None
        self.path = None
    
    def read_svg_file(self, path):
        self.path = path
        # read shit
        file = open(path, 'r')
        data = file.read()
        entries = xml_pattern.findall(data)
        # remove comments
        entries = [x for x in entries if not comment_pattern.search(x)]
        # create state object
        self.svg_state = SVGState(entries)
        # self.svg_state.svg_tree.print_tree()
    
    def render(self):
        if(not self.path):
            raise Exception("Tried to render without initializing the svg state, killing myself...")
        self._render(self.svg_state.svg_tree)
    
    def _render(self, r:Node):
        if(r.tag == 'rect'):
            args = extractArguments(r.value)
            x = str_to_float(args['x'])
            y = str_to_float(args['y'])
            width = str_to_float(args['width'])
            height = str_to_float(args['height'])
            stroke_width = str_to_float(args['stroke-width'])
            bounds = {
                'x_left': x - stroke_width/2,
                'x_right': x + width + stroke_width/2,
                'y_top': y - stroke_width/2,
                'y_bot': y + height + stroke_width/2
            }
            # continue next year
            
        

args = sys.argv
if(len(args) < 2):
    raise Exception("I will raise my goddamn fist if you don't use 'python main.py <arg1, arg2, arg3, ...>'")

renderer = Renderer()
renderer.read_svg_file(args[1])