from __future__ import annotations
import math
from parser import Node, is_self_terminating, is_terminator, get_tag, parse_svg_file
from geometry import normalize_unit, parse_number_with_unit

class SVGState:
    def __init__(self, entries: list[str] = []):
        self.metadata = {}
        self.svg_tree: Node = None
        self.viewport_width = None
        self.viewport_height = None
        self.viewbox = None
        self.validation_errors = []
        self.validation_warnings = []
        self.parse_svg_contents(entries)
        self._extract_viewport_info()
        self.validate()
    
    def parse_svg_contents(self, entries: list[str]):
        iterator = iter(entries)
        r = None
        
        for svg_element in iterator:
            tag = get_tag(svg_element)
            if tag == "svg":
                self.svg_tree = Node(svg_element)
                r = self.svg_tree
                break
            self.metadata[tag] = svg_element
        
        if r is None:
            return
        
        for svg_element in iterator:
            if r is None:
                return
            
            if is_terminator(svg_element) and r.compare_tag(svg_element):
                r = r.parent
                continue
            
            if is_self_terminating(svg_element):
                r.add_child(svg_element)
            else:
                new_child = Node(svg_element)
                r.add_node_child(new_child)
                r = new_child
    
    def _extract_viewport_info(self):
        if self.svg_tree is None:
            return
        
        attrs = self.svg_tree.attributes
        
        if 'width' in attrs:
            self.viewport_width = normalize_unit(attrs['width'])
        if 'height' in attrs:
            self.viewport_height = normalize_unit(attrs['height'])
        
        if 'viewBox' in attrs:
            viewbox_str = attrs['viewBox']
            parts = viewbox_str.strip().split()
            if len(parts) >= 4:
                try:
                    min_x = float(parts[0])
                    min_y = float(parts[1])
                    width = float(parts[2])
                    height = float(parts[3])
                    self.viewbox = (min_x, min_y, width, height)
                except ValueError:
                    self.viewbox = None
        
        if self.viewbox and (self.viewport_width is None or self.viewport_height is None):
            if self.viewport_width is None:
                self.viewport_width = self.viewbox[2]
            if self.viewport_height is None:
                self.viewport_height = self.viewbox[3]
        
        if self.viewport_width is None:
            self.viewport_width = 100.0
        if self.viewport_height is None:
            self.viewport_height = 100.0
        
        self._calculate_viewbox_transform()
    
    def _calculate_viewbox_transform(self):
        if self.viewbox is None:
            self.viewbox_scale_x = 1.0
            self.viewbox_scale_y = 1.0
            self.viewbox_offset_x = 0.0
            self.viewbox_offset_y = 0.0
            return
        
        vb_min_x, vb_min_y, vb_width, vb_height = self.viewbox
        
        preserve_aspect = self.svg_tree.get_attribute('preserveAspectRatio', 'xMidYMid meet')
        
        parts = preserve_aspect.strip().split()
        if len(parts) == 0 or parts[0].lower() == 'none':
            self.viewbox_scale_x = self.viewport_width / vb_width if vb_width > 0 else 1.0
            self.viewbox_scale_y = self.viewport_height / vb_height if vb_height > 0 else 1.0
            self.viewbox_offset_x = -vb_min_x * self.viewbox_scale_x
            self.viewbox_offset_y = -vb_min_y * self.viewbox_scale_y
        else:
            scale_x = self.viewport_width / vb_width if vb_width > 0 else 1.0
            scale_y = self.viewport_height / vb_height if vb_height > 0 else 1.0
            
            meet_or_slice = parts[1].lower() if len(parts) > 1 else 'meet'
            
            if meet_or_slice == 'meet':
                scale = min(scale_x, scale_y)
            else:
                scale = max(scale_x, scale_y)
            
            self.viewbox_scale_x = scale
            self.viewbox_scale_y = scale
            
            scaled_width = vb_width * scale
            scaled_height = vb_height * scale
            
            align = parts[0].lower()
            
            if 'xmin' in align:
                offset_x = 0.0
            elif 'xmid' in align or 'xmid' not in align and 'xmax' not in align:
                offset_x = (self.viewport_width - scaled_width) / 2.0
            else:
                offset_x = self.viewport_width - scaled_width
            
            if 'ymin' in align:
                offset_y = 0.0
            elif 'ymid' in align or 'ymid' not in align and 'ymax' not in align:
                offset_y = (self.viewport_height - scaled_height) / 2.0
            else:  # yMax
                offset_y = self.viewport_height - scaled_height
            
            self.viewbox_offset_x = offset_x - vb_min_x * scale
            self.viewbox_offset_y = offset_y - vb_min_y * scale
    
    def transform_point(self, x: float, y: float) -> tuple[float, float]:
        if self.viewbox is None:
            return (x, y)
        
        px = x * self.viewbox_scale_x + self.viewbox_offset_x
        py = y * self.viewbox_scale_y + self.viewbox_offset_y
        return (px, py)
    
    def transform_length(self, length: float, is_horizontal: bool = True) -> float:
        if self.viewbox is None:
            return length
        
        if is_horizontal:
            return length * self.viewbox_scale_x
        else:
            return length * self.viewbox_scale_y
    
    def validate(self):
        self.validation_errors = []
        self.validation_warnings = []
        
        if self.svg_tree is None:
            self.validation_errors.append("No root <svg> element found")
            return
        
        if self.svg_tree.tag != 'svg':
            self.validation_errors.append(f"Root element is not <svg>, found: <{self.svg_tree.tag}>")
        
        if self.viewport_width is not None and self.viewport_width <= 0:
            self.validation_errors.append(f"Invalid viewport width: {self.viewport_width}")
        
        if self.viewport_height is not None and self.viewport_height <= 0:
            self.validation_errors.append(f"Invalid viewport height: {self.viewport_height}")
        
        if self.viewbox is not None:
            vb_min_x, vb_min_y, vb_width, vb_height = self.viewbox
            if vb_width <= 0:
                self.validation_errors.append(f"Invalid viewBox width: {vb_width}")
            if vb_height <= 0:
                self.validation_errors.append(f"Invalid viewBox height: {vb_height}")
        
        self._validate_node(self.svg_tree)
    
    def _validate_node(self, node: Node):
        if node is None:
            return
        
        if node.tag == 'rect':
            self._validate_rect(node)
        elif node.tag == 'circle':
            self._validate_circle(node)
        elif node.tag == 'ellipse':
            self._validate_ellipse(node)
        elif node.tag == 'line':
            self._validate_line(node)
        elif node.tag == 'polyline' or node.tag == 'polygon':
            self._validate_polyline(node)
        elif node.tag == 'path':
            self._validate_path(node)
        
        numeric_attrs = ['x', 'y', 'width', 'height', 'cx', 'cy', 'r', 'rx', 'ry', 
                        'x1', 'y1', 'x2', 'y2', 'stroke-width', 'opacity']
        for attr in numeric_attrs:
            if attr in node.attributes:
                value = node.attributes[attr]
                try:
                    num_value, unit = parse_number_with_unit(value)
                    if math.isnan(num_value) or math.isinf(num_value):
                        self.validation_warnings.append(
                            f"<{node.tag}> has invalid {attr} value: {value}")
                except:
                    self.validation_warnings.append(
                        f"<{node.tag}> has non-numeric {attr} value: {value}")
        
        for child in node.children:
            self._validate_node(child)
    
    def _validate_rect(self, node: Node):
        attrs = node.attributes
        if 'width' not in attrs and 'height' not in attrs:
            self.validation_warnings.append("<rect> should have width or height")
        
        if 'width' in attrs:
            try:
                w = normalize_unit(attrs['width'])
                if w < 0:
                    self.validation_warnings.append(f"<rect> has negative width: {w}")
            except:
                pass
        
        if 'height' in attrs:
            try:
                h = normalize_unit(attrs['height'])
                if h < 0:
                    self.validation_warnings.append(f"<rect> has negative height: {h}")
            except:
                pass
    
    def _validate_circle(self, node: Node):
        attrs = node.attributes
        if 'r' not in attrs:
            self.validation_warnings.append("<circle> should have radius (r)")
        else:
            try:
                r = normalize_unit(attrs['r'])
                if r < 0:
                    self.validation_warnings.append(f"<circle> has negative radius: {r}")
            except:
                pass
    
    def _validate_ellipse(self, node: Node):
        attrs = node.attributes
        if 'rx' not in attrs and 'ry' not in attrs:
            self.validation_warnings.append("<ellipse> should have rx or ry")
    
    def _validate_line(self, node: Node):
        attrs = node.attributes
        required = ['x1', 'y1', 'x2', 'y2']
        missing = [r for r in required if r not in attrs]
        if missing:
            self.validation_warnings.append(f"<line> missing attributes: {', '.join(missing)}")
    
    def _validate_polyline(self, node: Node):
        attrs = node.attributes
        if 'points' not in attrs:
            self.validation_warnings.append(f"<{node.tag}> should have points attribute")
        else:
            points_str = attrs['points']
            if not points_str or len(points_str.strip()) < 3:
                self.validation_warnings.append(f"<{node.tag}> has invalid points attribute")
    
    def _validate_path(self, node: Node):
        attrs = node.attributes
        if 'd' not in attrs:
            self.validation_warnings.append("<path> should have 'd' (path data) attribute")
        else:
            d = attrs['d']
            if not d or len(d.strip()) == 0:
                self.validation_warnings.append("<path> has empty 'd' attribute")
    
    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0
    
    def print_validation_report(self):
        if self.is_valid() and len(self.validation_warnings) == 0:
            print("SVG validation: [OK] Valid")
            return
        
        if not self.is_valid():
            print("SVG validation: [ERROR] Errors found:")
            for error in self.validation_errors:
                print(f"  ERROR: {error}")
        
        if self.validation_warnings:
            print("SVG validation: [WARNING] Warnings:")
            for warning in self.validation_warnings:
                print(f"  WARNING: {warning}")

