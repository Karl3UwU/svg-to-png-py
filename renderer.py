from __future__ import annotations
import numpy as np
import math
import re
from typing import Optional, Tuple, List
from parser import Node
from svg_state import SVGState
from drawing_context import DrawingContext, TransformMatrix
from colors import blend_colors, get_color_with_opacity
from geometry import get_normalized_attribute, normalize_unit
from attributes import get_attribute_with_default

class Renderer:
    def __init__(self, svg_state: SVGState, width: Optional[int] = None, 
                 height: Optional[int] = None, background_color: Tuple[int, int, int] = (255, 255, 255),
                 anti_aliasing: bool = False):
        self.svg_state = svg_state
        self.anti_aliasing = anti_aliasing
        
        original_width = svg_state.viewport_width
        original_height = svg_state.viewport_height
        
        if width is None:
            width = int(original_width)
        if height is None:
            height = int(original_height)
        
        self.width = width
        self.height = height
        
        self.previousStack = None
        
        if width != original_width or height != original_height:
            svg_state.viewport_width = float(width)
            svg_state.viewport_height = float(height)
            svg_state._calculate_viewbox_transform()
        
        self.buffer = np.zeros((height, width, 4), dtype=np.uint8)
        self.buffer[:, :, 0] = background_color[0]
        self.buffer[:, :, 1] = background_color[1]
        self.buffer[:, :, 2] = background_color[2]
        self.buffer[:, :, 3] = 255
        
        self.context_stack = [DrawingContext()]
    
    def _get_current_context(self) -> DrawingContext:
        return self.context_stack[-1]
    
    def _push_context(self):
        new_ctx = self._get_current_context().push()
        self.context_stack.append(new_ctx)
    
    def _pop_context(self):
        if len(self.context_stack) > 1:
            self.context_stack.pop()
    
    def _svg_to_pixel(self, x, y) -> Tuple:
        if(isinstance(x, str) or isinstance(y, str)):
            return (x, y) 
        px, py = self.svg_state.transform_point(x, y)
        ctx = self._get_current_context()
        px, py = ctx.transform.transform_point(px, py)
        pixel_x = int(round(px))
        pixel_y = int(round(py))
        
        return (pixel_x, pixel_y)
    
    def _pixel_to_svg(self, px: float, py: float) -> Tuple[float, float]:
        ctx = self._get_current_context()
        inv_transform = ctx.transform.inverse()
        px, py = inv_transform.transform_point(px, py)
        if self.svg_state.viewbox is not None:
            if self.svg_state.viewbox_scale_x != 0:
                px = (px - self.svg_state.viewbox_offset_x) / self.svg_state.viewbox_scale_x
            if self.svg_state.viewbox_scale_y != 0:
                py = (py - self.svg_state.viewbox_offset_y) / self.svg_state.viewbox_scale_y
        return (px, py)
    
    def _is_point_clipped(self, x: int, y: int) -> bool:
        ctx = self._get_current_context()
        if ctx.clip_region is None:
            return False
        
        return self._check_clip_region(x, y, ctx.clip_region)
    
    def _check_clip_region(self, x: int, y: int, clip_region: dict) -> bool:
        if clip_region['type'] == 'rect':
            rx, ry, rw, rh = clip_region['bounds']
            return not (rx <= x < rx + rw and ry <= y < ry + rh)
        elif clip_region['type'] == 'polygon':
            return not self._point_in_polygon(x, y, clip_region['points'], clip_region['rule'])
        elif clip_region['type'] == 'intersection':
            for region in clip_region['regions']:
                if self._check_clip_region(x, y, region):
                    return True
            return False
        
        return False
    
    def _set_pixel(self, x: int, y: int, color: Tuple[int, int, int, int]):
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return
        
        if self._is_point_clipped(x, y):
            return
        
        current = tuple(self.buffer[y, x, :])
        blended = blend_colors(color, current)
        self.buffer[y, x, :] = blended
    
    def _set_pixel_aa(self, x: int, y: int, color: Tuple[int, int, int, int], coverage: float):
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return
        
        if self._is_point_clipped(x, y):
            return
        
        coverage = max(0.0, min(1.0, coverage))
        if coverage <= 0.0:
            return
        
        r, g, b, a = color
        aa_color = (r, g, b, int(a * coverage))
        
        current = tuple(self.buffer[y, x, :])
        blended = blend_colors(aa_color, current)
        self.buffer[y, x, :] = blended
    
    def _calculate_coverage(self, px: float, py: float, shape_func) -> float:
        samples = 2
        coverage = 0.0
        
        for sy in range(samples):
            for sx in range(samples):
                sample_x = px + (sx + 0.5) / samples
                sample_y = py + (sy + 0.5) / samples
                if shape_func(sample_x, sample_y):
                    coverage += 1.0
        
        return coverage / (samples * samples)
    
    def _set_pixel_safe(self, x: float, y: float, color: Tuple[int, int, int, int]):
        pixel_x, pixel_y = self._svg_to_pixel(x, y)
        self._set_pixel(pixel_x, pixel_y, color)
    
    def render(self):
        if self.svg_state.svg_tree is None:
            return
        self._render_node(self.svg_state.svg_tree)
    
    def _parse_clip_path(self, clip_path_str: str, node: Node) -> Optional[dict]:
        if not clip_path_str or clip_path_str.lower() == 'none':
            return None
        
        clip_path_str = clip_path_str.strip()
        if clip_path_str.startswith('url('):
            clip_id = clip_path_str[4:-1].strip().lstrip('#')
            clip_node = self._find_node_by_id(clip_id)
            if clip_node and clip_node.tag == 'clipPath':
                return self._process_clip_path(clip_node)
        
        return None
    
    def _find_node_by_id(self, node_id: str) -> Optional[Node]:
        def search_recursive(n: Node) -> Optional[Node]:
            if n.get_attribute('id', None, use_inheritance=False) == node_id:
                return n
            for child in n.children:
                result = search_recursive(child)
                if result:
                    return result
            return None
        
        if self.svg_state.svg_tree:
            return search_recursive(self.svg_state.svg_tree)
        return None
    
    def _process_clip_path(self, clip_path_node: Node) -> Optional[dict]:
        viewport_w = self.svg_state.viewport_width
        viewport_h = self.svg_state.viewport_height
        clip_rule = get_attribute_with_default(clip_path_node, 'clip-rule', use_inheritance=True) or 'nonzero'
        
        all_points = []
        
        for child in clip_path_node.children:
            if child.tag == 'rect':
                x = get_normalized_attribute(child, 'x', 0.0, viewport_w, viewport_h)
                y = get_normalized_attribute(child, 'y', 0.0, viewport_w, viewport_h)
                width = get_normalized_attribute(child, 'width', 0.0, viewport_w, viewport_h)
                height = get_normalized_attribute(child, 'height', 0.0, viewport_w, viewport_h)
                
                px1, py1 = self._svg_to_pixel(x, y)
                px2, py2 = self._svg_to_pixel(x + width, y)
                px3, py3 = self._svg_to_pixel(x + width, y + height)
                px4, py4 = self._svg_to_pixel(x, y + height)
                
                all_points.extend([(px1, py1), (px2, py2), (px3, py3), (px4, py4)])
            
            elif child.tag in ['circle', 'ellipse']:
                cx = get_normalized_attribute(child, 'cx', 0.0, viewport_w, viewport_h)
                cy = get_normalized_attribute(child, 'cy', 0.0, viewport_w, viewport_h)
                
                if child.tag == 'circle':
                    r = get_normalized_attribute(child, 'r', 0.0, viewport_w, viewport_h)
                    rx = ry = r
                else:
                    rx = get_normalized_attribute(child, 'rx', 0.0, viewport_w, viewport_h)
                    ry = get_normalized_attribute(child, 'ry', 0.0, viewport_w, viewport_h)
                
                center_x, center_y = self._svg_to_pixel(cx, cy)
                radius_x = abs(self.svg_state.transform_length(rx, True))
                radius_y = abs(self.svg_state.transform_length(ry, False))
                
                num_segments = max(8, int(2 * math.pi * max(radius_x, radius_y) / 2))
                for i in range(num_segments):
                    angle = 2 * math.pi * i / num_segments
                    px = int(center_x + radius_x * math.cos(angle))
                    py = int(center_y + radius_y * math.sin(angle))
                    all_points.append((px, py))
            
            elif child.tag == 'path':
                path_str = child.get_attribute('d', '', use_inheritance=True)
                if path_str:
                    path_points = self._parse_path(path_str, viewport_w, viewport_h)
                    pixel_points = [self._svg_to_pixel(x, y) for x, y in path_points]
                    all_points.extend(pixel_points)
        
        if len(all_points) < 3:
            return None
        
        if len(all_points) == 4:
            x_coords = [p[0] for p in all_points]
            y_coords = [p[1] for p in all_points]
            if (x_coords[0] == x_coords[3] and x_coords[1] == x_coords[2] and
                y_coords[0] == y_coords[1] and y_coords[2] == y_coords[3]):
                return {
                    'type': 'rect',
                    'bounds': (min(x_coords), min(y_coords), 
                              max(x_coords) - min(x_coords), 
                              max(y_coords) - min(y_coords))
                }
        
        return {
            'type': 'polygon',
            'points': all_points,
            'rule': clip_rule
        }

    def _render_node(self, node: Node):
        if node is None:
            return
        
        ctx = self._get_current_context()
        ctx.apply_node_attributes(node)
        
        transform_str = node.get_attribute('transform', None, use_inheritance=False)
        has_transform = transform_str is not None
        
        clip_path_str = node.get_attribute('clip-path', None, use_inheritance=True)
        
        if has_transform and node.tag != 'g':
            self._push_context()
            ctx = self._get_current_context()
            ctx.apply_node_attributes(node)
            ctx.apply_transform(transform_str, self.svg_state)
        elif transform_str:
            ctx.apply_transform(transform_str, self.svg_state)
        
        if clip_path_str:
            clip_region = self._parse_clip_path(clip_path_str, node)
            if clip_region:
                if ctx.clip_region is None:
                    ctx.clip_region = clip_region
                else:
                    ctx.clip_region = {
                        'type': 'intersection',
                        'regions': [ctx.clip_region, clip_region]
                    }
        
        if node.tag == 'g':
            self._push_context()
            currentContext = ctx.transform.copy()
            for child in node.children:
                self._render_node(child)
            ctx.transform = TransformMatrix.identity()
            self._pop_context()
            
        
        elif node.tag == 'rect':
            self._render_rect(node)
        
        elif node.tag == 'circle':
            self._render_circle(node)
        
        elif node.tag == 'ellipse':
            self._render_ellipse(node)
        
        elif node.tag == 'line':
            self._render_line(node)
        
        elif node.tag == 'polyline':
            self._render_polyline(node)
        
        elif node.tag == 'path':
            self._render_path(node)
        
        elif node.tag == 'use':
            self._render_use(node)
        
        if has_transform and node.tag != 'g':
            self._pop_context()
        
        if node.tag not in ['g']:
            for child in node.children:
                self._render_node(child)
                
        self.previousStack = self.context_stack
    
    def _render_rect(self, node: Node):
        ctx = self._get_current_context()
        
        viewport_w = self.svg_state.viewport_width
        viewport_h = self.svg_state.viewport_height
        
        x = get_normalized_attribute(node, 'x', 0.0, viewport_w, viewport_h)
        y = get_normalized_attribute(node, 'y', 0.0, viewport_w, viewport_h)
        width = get_normalized_attribute(node, 'width', 0.0, viewport_w, viewport_h)
        height = get_normalized_attribute(node, 'height', 0.0, viewport_w, viewport_h)
        
        if width <= 0 or height <= 0:
            return
        
        rx = get_normalized_attribute(node, 'rx', 0.0, viewport_w, viewport_h)
        ry = get_normalized_attribute(node, 'ry', 0.0, viewport_w, viewport_h)
        
        if rx > 0 and ry == 0:
            ry = rx
        elif ry > 0 and rx == 0:
            rx = ry
        
        max_rx = width / 2.0
        max_ry = height / 2.0
        rx = min(rx, max_rx)
        ry = min(ry, max_ry)
        
        stroke_width_svg = ctx.stroke_width
        stroke_width_px = 0.0
        if stroke_width_svg > 0:
            stroke_width_px = self.svg_state.transform_length(stroke_width_svg, True)
        
        fill_color = ctx.fill_color
        stroke_color = ctx.stroke_color
        
        if ctx.opacity < 1.0:
            if fill_color[3] > 0:
                fill_color = (fill_color[0], fill_color[1], fill_color[2], int(fill_color[3] * ctx.opacity))
            if stroke_color[3] > 0:
                stroke_color = (stroke_color[0], stroke_color[1], stroke_color[2], int(stroke_color[3] * ctx.opacity))
        
        px1, py1 = self._svg_to_pixel(x, y)
        px2, py2 = self._svg_to_pixel(x + width, y + height)
        px3, py3 = self._svg_to_pixel(x, y + height)
        px4, py4 = self._svg_to_pixel(x + width, y)
        
        all_px = [px1, px2, px3, px4]
        all_py = [py1, py2, py3, py4]
        
        min_x = min(all_px)
        max_x = max(all_px)
        min_y = min(all_py)
        max_y = max(all_py)
        
        if rx == 0 and ry == 0:
            def is_inside_rounded_rect(px: float, py: float) -> bool:
                svg_x, svg_y = self._pixel_to_svg(px, py)
                return x <= svg_x <= x + width and y <= svg_y <= y + height
            
            def is_inside_inner_rect(px: float, py: float) -> bool:
                if stroke_width_svg <= 0:
                    return False
                svg_x, svg_y = self._pixel_to_svg(px, py)
                half_stroke_svg = stroke_width_svg
                inner_min_x = x + half_stroke_svg
                inner_max_x = x + width - half_stroke_svg
                inner_min_y = y + half_stroke_svg
                inner_max_y = y + height - half_stroke_svg
                if inner_min_x >= inner_max_x or inner_min_y >= inner_max_y:
                    return False
                return inner_min_x <= svg_x <= inner_max_x and inner_min_y <= svg_y <= inner_max_y
        else:
            def is_inside_rounded_rect(px: float, py: float) -> bool:
                svg_x, svg_y = self._pixel_to_svg(px, py)
                
                if svg_x < x or svg_x > x + width or svg_y < y or svg_y > y + height:
                    return False
                
                corner_x = x + rx
                corner_y = y + ry
                
                if svg_x < corner_x and svg_y < corner_y:
                    dx = svg_x - corner_x
                    dy = svg_y - corner_y
                    return (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry) <= 1.0
                
                corner_x = x + width - rx
                if svg_x > corner_x and svg_y < corner_y:
                    dx = svg_x - corner_x
                    dy = svg_y - corner_y
                    return (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry) <= 1.0
                
                corner_y = y + height - ry
                if svg_x < x + rx and svg_y > corner_y:
                    dx = svg_x - (x + rx)
                    dy = svg_y - corner_y
                    return (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry) <= 1.0
                
                if svg_x > x + width - rx and svg_y > corner_y:
                    dx = svg_x - (x + width - rx)
                    dy = svg_y - corner_y
                    return (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry) <= 1.0
                
                return True
            
            def is_inside_inner_rect(px: float, py: float) -> bool:
                svg_x, svg_y = self._pixel_to_svg(px, py)
                
                half_stroke_svg = stroke_width_svg
                inner_min_x = x + half_stroke_svg
                inner_max_x = x + width - half_stroke_svg
                inner_min_y = y + half_stroke_svg
                inner_max_y = y + height - half_stroke_svg
                
                if inner_min_x >= inner_max_x or inner_min_y >= inner_max_y:
                    return False
                
                if svg_x < inner_min_x or svg_x > inner_max_x or svg_y < inner_min_y or svg_y > inner_max_y:
                    return False
                
                inner_rx = max(0, rx - half_stroke_svg)
                inner_ry = max(0, ry - half_stroke_svg)
                
                if inner_rx == 0 or inner_ry == 0:
                    return True
                
                corner_x = inner_min_x + inner_rx
                corner_y = inner_min_y + inner_ry
                
                if svg_x < corner_x and svg_y < corner_y:
                    dx = svg_x - corner_x
                    dy = svg_y - corner_y
                    return (dx * dx) / (inner_rx * inner_rx) + (dy * dy) / (inner_ry * inner_ry) <= 1.0
                
                corner_x = inner_max_x - inner_rx
                if svg_x > corner_x and svg_y < corner_y:
                    dx = svg_x - corner_x
                    dy = svg_y - corner_y
                    return (dx * dx) / (inner_rx * inner_rx) + (dy * dy) / (inner_ry * inner_ry) <= 1.0
                
                corner_y = inner_max_y - inner_ry
                if svg_x < inner_min_x + inner_rx and svg_y > corner_y:
                    dx = svg_x - (inner_min_x + inner_rx)
                    dy = svg_y - corner_y
                    return (dx * dx) / (inner_rx * inner_rx) + (dy * dy) / (inner_ry * inner_ry) <= 1.0
                
                if svg_x > inner_max_x - inner_rx and svg_y > corner_y:
                    dx = svg_x - (inner_max_x - inner_rx)
                    dy = svg_y - corner_y
                    return (dx * dx) / (inner_rx * inner_rx) + (dy * dy) / (inner_ry * inner_ry) <= 1.0
                
                return True
        
        def is_on_stroke_edge(px: float, py: float) -> bool:
            return is_inside_rounded_rect(px, py) and not is_inside_inner_rect(px, py)
        
        if rx == 0 and ry == 0 and ctx.transform.is_identity():
            min_x_int = max(0, int(min_x))
            max_x_int = min(self.width, int(max_x) + 1)
            min_y_int = max(0, int(min_y))
            max_y_int = min(self.height, int(max_y) + 1)
            
            if fill_color[3] > 0:
                for py in range(min_y_int, max_y_int):
                    for px in range(min_x_int, max_x_int):
                        self._set_pixel(px, py, fill_color)
            
            if stroke_width_px > 0 and stroke_color[3] > 0:
                stroke_half = int(stroke_width_px / 2)
                for py in range(min_y_int, max_y_int):
                    for px in range(min_x_int, max_x_int):
                        dist_to_edge = min(
                            px - min_x_int,
                            max_x_int - 1 - px,
                            py - min_y_int,
                            max_y_int - 1 - py
                        )
                        if dist_to_edge < stroke_half:
                            self._set_pixel(px, py, stroke_color)
        else:
            if fill_color[3] > 0:
                for py in range(max(0, min_y - 1), min(self.height, max_y + 2)):
                    for px in range(max(0, min_x - 1), min(self.width, max_x + 2)):
                        if self.anti_aliasing:
                            coverage = self._calculate_coverage(px, py, is_inside_rounded_rect)
                            if coverage > 0:
                                self._set_pixel_aa(px, py, fill_color, coverage)
                        elif is_inside_rounded_rect(px + 0.5, py + 0.5):
                            self._set_pixel(px, py, fill_color)
            
            if stroke_width_px > 0 and stroke_color[3] > 0:
                for py in range(max(0, min_y - 1), min(self.height, max_y + 2)):
                    for px in range(max(0, min_x - 1), min(self.width, max_x + 2)):
                        if self.anti_aliasing:
                            coverage = self._calculate_coverage(px, py, is_on_stroke_edge)
                            if coverage > 0:
                                self._set_pixel_aa(px, py, stroke_color, coverage)
                        elif is_on_stroke_edge(px + 0.5, py + 0.5):
                            self._set_pixel(px, py, stroke_color)
    
    def _render_circle(self, node: Node):
        ctx = self._get_current_context()
        
        viewport_w = self.svg_state.viewport_width
        viewport_h = self.svg_state.viewport_height
        
        cx = get_normalized_attribute(node, 'cx', 0.0, viewport_w, viewport_h)
        cy = get_normalized_attribute(node, 'cy', 0.0, viewport_w, viewport_h)
        r = get_normalized_attribute(node, 'r', 0.0, viewport_w, viewport_h)
        
        if r <= 0:
            return
        
        stroke_width = ctx.stroke_width
        if stroke_width > 0:
            stroke_width = self.svg_state.transform_length(stroke_width, True)
        
        fill_color = ctx.fill_color
        stroke_color = ctx.stroke_color
        
        if ctx.opacity < 1.0:
            if fill_color[3] > 0:
                fill_color = (fill_color[0], fill_color[1], fill_color[2], int(fill_color[3] * ctx.opacity))
            if stroke_color[3] > 0:
                stroke_color = (stroke_color[0], stroke_color[1], stroke_color[2], int(stroke_color[3] * ctx.opacity))
        
        center_x, center_y = self._svg_to_pixel(cx, cy)
        radius_px = abs(self.svg_state.transform_length(r, True))
        
        if radius_px <= 0:
            return
        
        min_x = max(0, center_x - int(radius_px) - int(stroke_width))
        max_x = min(self.width - 1, center_x + int(radius_px) + int(stroke_width))
        min_y = max(0, center_y - int(radius_px) - int(stroke_width))
        max_y = min(self.height - 1, center_y + int(radius_px) + int(stroke_width))
        
        center_x_int = int(round(center_x))
        center_y_int = int(round(center_y))
        radius_int = int(round(radius_px))
        
        if fill_color[3] > 0:
            self._draw_circle_fill_midpoint(center_x_int, center_y_int, radius_int, fill_color)
        
        if stroke_width > 0 and stroke_color[3] > 0:
            r_inner = max(0, radius_px - stroke_width / 2)
            r_outer = radius_px + stroke_width / 2
            r_inner_int = int(round(r_inner))
            r_outer_int = int(round(r_outer))
            self._draw_circle_stroke_midpoint(center_x_int, center_y_int, r_inner_int, r_outer_int, stroke_color)
    
    def _draw_circle_fill_midpoint(self, cx: int, cy: int, r: int, color: Tuple[int, int, int, int]):
        for i in range(cx-r, cx+r):
            for j in range(cy-r, cy+r):
                try:
                    sdf = self.sdEllipse([i-cx + 0.0001, j-cy + 0.0001], [r, r+0.5] )
                    if(sdf < 1.0):
                        self._set_pixel(i, j, (color[0], color[1], color[2], color[3]*((1.0-max(sdf,0.0))**2)))
                except:
                    self._set_pixel(i, j, color)
    
    def _draw_circle_stroke_midpoint(self, cx: int, cy: int, r_inner: int, r_outer: int, color: Tuple[int, int, int, int]):
        m = int((r_inner + r_outer)//2)
        j1 = max(r_inner, r_outer)
        for i in range(cx-j1*2, cx+j1*2):
            for j in range(cy-j1*2, cy+j1*2):
                try:
                    sdf = abs(self.sdEllipse([i-cx + 0.0001, j-cy + 0.0001], [m, m+0.5] )) - (r_outer-r_inner)/2
                    
                    if(sdf < 1.0):
                        self._set_pixel(i, j, (color[0], color[1], color[2], color[3]*((1.0-max(sdf,0.0))**2)))
                except:
                    self._set_pixel(i, j, color)
    
    def _render_ellipse(self, node: Node):
        ctx = self._get_current_context()
        
        viewport_w = self.svg_state.viewport_width
        viewport_h = self.svg_state.viewport_height
        
        cx = get_normalized_attribute(node, 'cx', 0.0, viewport_w, viewport_h)
        cy = get_normalized_attribute(node, 'cy', 0.0, viewport_w, viewport_h)
        rx = get_normalized_attribute(node, 'rx', 0.0, viewport_w, viewport_h)
        ry = get_normalized_attribute(node, 'ry', 0.0, viewport_w, viewport_h)
        
        if rx <= 0 or ry <= 0:
            return
        
        stroke_width = ctx.stroke_width
        if stroke_width > 0:
            stroke_width = self.svg_state.transform_length(stroke_width, True)
        
        fill_color = ctx.fill_color
        stroke_color = ctx.stroke_color
        
        if ctx.opacity < 1.0:
            if fill_color[3] > 0:
                fill_color = (fill_color[0], fill_color[1], fill_color[2], int(fill_color[3] * ctx.opacity))
            if stroke_color[3] > 0:
                stroke_color = (stroke_color[0], stroke_color[1], stroke_color[2], int(stroke_color[3] * ctx.opacity))
        
        center_x, center_y = self._svg_to_pixel(cx, cy)
        radius_x_px = abs(self.svg_state.transform_length(rx, True))
        radius_y_px = abs(self.svg_state.transform_length(ry, False))
        
        if radius_x_px <= 0 or radius_y_px <= 0:
            return
        
        min_x = max(0, center_x - int(radius_x_px) - int(stroke_width))
        max_x = min(self.width - 1, center_x + int(radius_x_px) + int(stroke_width))
        min_y = max(0, center_y - int(radius_y_px) - int(stroke_width))
        max_y = min(self.height - 1, center_y + int(radius_y_px) + int(stroke_width))
        
        center_x_int = int(round(center_x))
        center_y_int = int(round(center_y))
        rx_int = int(round(radius_x_px))
        ry_int = int(round(radius_y_px))
        
        if fill_color[3] > 0:
            self._draw_ellipse_fill_midpoint(center_x_int, center_y_int, rx_int, ry_int, fill_color)
        
        if stroke_width > 0 and stroke_color[3] > 0:
            rx_inner = max(0, radius_x_px - stroke_width / 2)
            ry_inner = max(0, radius_y_px - stroke_width / 2)
            rx_outer = radius_x_px + stroke_width / 2
            ry_outer = radius_y_px + stroke_width / 2
            rx_inner_int = int(round(rx_inner))
            ry_inner_int = int(round(ry_inner))
            rx_outer_int = int(round(rx_outer))
            ry_outer_int = int(round(ry_outer))
            self._draw_ellipse_stroke_midpoint(center_x_int, center_y_int, rx_inner_int, ry_inner_int, rx_outer_int, ry_outer_int, stroke_color)
    
    def sdCircle(self, p, r ):
        return math.sqrt(p[0]*p[0] + p[1]*p[1]) - r
    
    
    def sdEllipse(self, p, ab ):
        p = [abs(p[0]), abs(p[1])]
        if( p[0] > p[1] ):
            t = p[0]
            p[0] = p[1]
            p[1] = t
            t = ab[0]
            ab[0] = ab[1]
            ab[1] = t
        l = ab[1]*ab[1] - ab[0]*ab[0]
        m = ab[0]*p[0]/l;      
        m2 = m*m
        n = ab[1]*p[1]/l;      
        n2 = n*n
        c = (m2+n2-1.0)/3.0; 
        c3 = c*c*c
        q = c3 + m2*n2*2.0
        d = c3 + m2*n2
        g = m + m*n2
        co = 0
        if( d<0.0 ):
            h = math.acos(q/c3)/3.0
            s = math.cos(h)
            t = math.sin(h)*math.sqrt(3.0)
            rx = math.sqrt( -c*(s + t + 2.0) + m2 )
            ry = math.sqrt( -c*(s - t + 2.0) + m2 )
            co = (ry+np.sign(l)*rx+abs(g)/(rx*ry)- m)/2.0
        else:
            h = 2.0*m*n*math.sqrt( d )
            s = np.sign(q+h)*pow(abs(q+h), 1.0/3.0)
            u = np.sign(q-h)*pow(abs(q-h), 1.0/3.0)
            rx = -s - u - c*4.0 + 2.0*m2
            ry = (s - u)*math.sqrt(3.0)
            rm = math.sqrt( rx*rx + ry*ry )
            co = (ry/math.sqrt(rm-rx)+2.0*g/rm-m)/2.0
        r = [ab[0] * co, ab[1] * math.sqrt(1.0-co*co)]
        
        return math.sqrt((r[0]-p[0])**2 + (r[1]-p[1])**2) * np.sign(p[1]-r[1])
    
    
    def _draw_ellipse_fill_midpoint(self, cx: int, cy: int, rx: int, ry: int, color: Tuple[int, int, int, int]):
        
        for i in range(cx-rx, cx+rx):
            for j in range(cy-ry, cy+ry):
                #print(i-cx, j-cy)
                try:
                    sdf = self.sdEllipse([i-cx + 0.0001, j-cy + 0.0001], [rx, ry] )
                    if(sdf < 0.0):
                        self._set_pixel(i, j, color)
                except:
                    pass
        
        
        
    
    def _draw_ellipse_stroke_midpoint(self, cx: int, cy: int, rx_inner: int, ry_inner: int, 
                                     rx_outer: int, ry_outer: int, color: Tuple[int, int, int, int]):
        if rx_outer <= 0 or ry_outer <= 0:
            return
        
        mx = int((rx_inner + rx_outer)//2)
        my = int((ry_inner + ry_outer)//2)
        mv = max(max(rx_inner, rx_outer), max(ry_inner, ry_outer))
        c = rx_outer-rx_inner
        
        
        for i in range(cx-mv*2, cx+mv*2):
            for j in range(cy-mv*2, cy+mv*2):
                try:
                    sdf = abs(self.sdEllipse([i-cx + 0.0001, j-cy + 0.0001], [mx, my+0.5] )) - c/2
                    if(sdf < 1.0):
                        self._set_pixel(i, j, (color[0], color[1], color[2], color[3]*((1.0-max(sdf,0.0))**2)))
                except:
                    self._set_pixel(i, j, color)
    
    def _parse_dasharray(self, dasharray_str: str, viewport_w: float, viewport_h: float) -> List[float]:
        if not dasharray_str or dasharray_str.lower() == 'none':
            return []
        
        dash_values = []
        parts = re.split(r'[\s,]+', dasharray_str.strip())
        
        for part in parts:
            if part:
                try:
                    dash_len = normalize_unit(part, "length", viewport_w, viewport_h)
                    if dash_len > 0:
                        dash_values.append(dash_len)
                except (ValueError, TypeError):
                    continue
        
        if len(dash_values) % 2 == 1:
            dash_values.extend(dash_values)
        
        return dash_values
    
    def sdSegment( self, p, a, b ):
        pa = [p[0]-a[0], p[1]-a[1]]
        ba = [b[0]-a[0], b[1]-a[1]]
        h = min(max( (pa[0]*ba[0]+pa[1]*ba[1])/(ba[0]*ba[0]+ba[1]*ba[1]), 0.0), 1.0 )
        
        return math.sqrt( (pa[0] - ba[0]*h)**2 + (pa[1] - ba[1]*h)**2 )
    
    
    
    def _draw_line_segment(self, x1: int, y1: int, x2: int, y2: int, 
                          stroke_color: Tuple[int, int, int, int], 
                          stroke_width: float,
                          dash_array: List[float] = None,
                          dash_offset: float = 0.0):
        if stroke_width <= 0 or stroke_color[3] == 0:
            return
        
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx * dx + dy * dy)
        
        if length == 0:
            return
        
        half_width = stroke_width / 2.0
        perp_x = -dy / length
        perp_y = dx / length
        
        min_x = min(x1, x2) - half_width - 1
        max_x = max(x1, x2) + half_width + 1
        min_y = min(y1, y2) - half_width - 1
        max_y = max(y1, y2) + half_width + 1
        
        def calculate_line_coverage(px: float, py: float) -> float:
            vec_x = px - x1
            vec_y = py - y1
            proj = (vec_x * dx + vec_y * dy) / (length * length) if length > 0 else 0.0
            
            if proj < 0.0 or proj > 1.0:
                return 0.0
            
            closest_x = x1 + proj * dx
            closest_y = y1 + proj * dy
            dist = math.sqrt((px - closest_x) ** 2 + (py - closest_y) ** 2)
            
            if dist > half_width + 0.5:
                return 0.0
            
            if dash_array and len(dash_array) > 0:
                dash_pattern_length = sum(dash_array)
                if dash_pattern_length > 0:
                    t = proj * length + dash_offset
                    t = t % dash_pattern_length
                    dash_index = 0
                    dash_accum = 0.0
                    for i, dash_len in enumerate(dash_array):
                        if t < dash_accum + dash_len:
                            dash_index = i
                            break
                        dash_accum += dash_len
                    if dash_index % 2 != 0:
                        return 0.0
            
            if dist <= half_width - 0.5:
                return 1.0
            
            coverage = 1.0 - (dist - (half_width - 0.5))
            return max(0.0, min(1.0, coverage))
        
        for py in range(max(0, int(min_y)), min(self.height, int(max_y) + 1)):
            for px in range(max(0, int(min_x)), min(self.width, int(max_x) + 1)):
                if self.anti_aliasing:
                    coverage = calculate_line_coverage(px + 0.5, py + 0.5)
                    if coverage > 0:
                        self._set_pixel_aa(px, py, stroke_color, coverage)
                elif calculate_line_coverage(px + 0.5, py + 0.5) >= 0.5:
                    self._set_pixel(px, py, stroke_color)
    
    
    def _draw_line_cap(self, x: int, y: int, angle: float, 
                      stroke_color: Tuple[int, int, int, int], 
                      stroke_width: float, cap_type: str):
        if stroke_width <= 0 or stroke_color[3] == 0:
            return
        
        half_width = stroke_width / 2.0
        half_width_int = max(1, int(half_width))
        
        if cap_type == 'round':
            def is_inside_round_cap(px: float, py: float) -> bool:
                dx = px - x
                dy = py - y
                dist = math.sqrt(dx * dx + dy * dy)
                return dist <= half_width
            
            for py in range(max(0, y - half_width_int - 1), min(self.height, y + half_width_int + 2)):
                for px in range(max(0, x - half_width_int - 1), min(self.width, x + half_width_int + 2)):
                    if self.anti_aliasing:
                        coverage = self._calculate_coverage(px, py, is_inside_round_cap)
                        if coverage > 0:
                            self._set_pixel_aa(px, py, stroke_color, coverage)
                    elif is_inside_round_cap(px + 0.5, py + 0.5):
                        self._set_pixel(px, py, stroke_color)
        elif cap_type == 'square':
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            extend_x = half_width * cos_a
            extend_y = half_width * sin_a
            
            def is_inside_square_cap(px: float, py: float) -> bool:
                dx = px - (x + extend_x)
                dy = py - (y + extend_y)
                perp_x = -sin_a
                perp_y = cos_a
                perp_dist = abs(dx * perp_x + dy * perp_y)
                along_dist = dx * cos_a + dy * sin_a
                return perp_dist <= half_width and -half_width <= along_dist <= half_width
            
            for py in range(max(0, y - half_width_int - 1), min(self.height, y + half_width_int + 2)):
                for px in range(max(0, x - half_width_int - 1), min(self.width, x + half_width_int + 2)):
                    if self.anti_aliasing:
                        coverage = self._calculate_coverage(px, py, is_inside_square_cap)
                        if coverage > 0:
                            self._set_pixel_aa(px, py, stroke_color, coverage)
                    elif is_inside_square_cap(px + 0.5, py + 0.5):
                        self._set_pixel(px, py, stroke_color)
    
    def _draw_line_join(self, x: int, y: int, angle1: float, angle2: float,
                       stroke_color: Tuple[int, int, int, int],
                       stroke_width: float, join_type: str, miter_limit: float = 4.0):
        if stroke_width <= 0 or stroke_color[3] == 0:
            return
        
        half_width = stroke_width / 2.0
        half_width_int = max(1, int(half_width))
        bisect_angle = (angle1 + angle2) / 2.0
        
        if join_type == 'round' or join_type == 'miter' or join_type == 'bevel':
            def is_inside_round_join(px: float, py: float) -> bool:
                dx = px - x
                dy = py - y
                dist = math.sqrt(dx * dx + dy * dy)
                return dist <= half_width
            
            for py in range(max(0, y - half_width_int - 1), min(self.height, y + half_width_int + 2)):
                for px in range(max(0, x - half_width_int - 1), min(self.width, x + half_width_int + 2)):
                    if self.anti_aliasing:
                        coverage = self._calculate_coverage(px, py, is_inside_round_join)
                        if coverage > 0:
                            self._set_pixel_aa(px, py, stroke_color, coverage)
                    elif is_inside_round_join(px + 0.5, py + 0.5):
                        self._set_pixel(px, py, stroke_color)
    
    def _render_line(self, node: Node):
        ctx = self._get_current_context()
        
        viewport_w = self.svg_state.viewport_width
        viewport_h = self.svg_state.viewport_height
        
        x1 = get_normalized_attribute(node, 'x1', 0.0, viewport_w, viewport_h)
        y1 = get_normalized_attribute(node, 'y1', 0.0, viewport_w, viewport_h)
        x2 = get_normalized_attribute(node, 'x2', 0.0, viewport_w, viewport_h)
        y2 = get_normalized_attribute(node, 'y2', 0.0, viewport_w, viewport_h)
        
        stroke_width = ctx.stroke_width
        if stroke_width > 0:
            stroke_width = self.svg_state.transform_length(stroke_width, True)
        
        stroke_color = ctx.stroke_color
        
        if ctx.opacity < 1.0 and stroke_color[3] > 0:
            stroke_color = (stroke_color[0], stroke_color[1], stroke_color[2], int(stroke_color[3] * ctx.opacity))
        
        if stroke_width <= 0 or stroke_color[3] == 0:
            return
        
        px1, py1 = self._svg_to_pixel(x1, y1)
        px2, py2 = self._svg_to_pixel(x2, y2)
        
        linecap = get_attribute_with_default(node, 'stroke-linecap', use_inheritance=True) or 'butt'
        
        dasharray_str = get_attribute_with_default(node, 'stroke-dasharray', use_inheritance=True) or 'none'
        dash_array = self._parse_dasharray(dasharray_str, viewport_w, viewport_h)
        
        dashoffset_str = get_attribute_with_default(node, 'stroke-dashoffset', use_inheritance=True) or '0'
        try:
            dash_offset = normalize_unit(dashoffset_str, "length", viewport_w, viewport_h)
        except (ValueError, TypeError):
            dash_offset = 0.0
        
        angle = math.atan2(py2 - py1, px2 - px1)
        
        if linecap != 'butt' and (not dash_array or len(dash_array) == 0):
            self._draw_line_cap(px1, py1, angle + math.pi, stroke_color, stroke_width, linecap)
            self._draw_line_cap(px2, py2, angle, stroke_color, stroke_width, linecap)
        
        self._draw_line_segment(px1, py1, px2, py2, stroke_color, stroke_width, dash_array, dash_offset)
    
    def _parse_polyline_points(self, points_str: str, viewport_w: float, viewport_h: float) -> List[Tuple[float, float]]:
        if not points_str:
            return []
        
        points = []
        coords = re.split(r'[\s,]+', points_str.strip())
        
        i = 0
        while i < len(coords) - 1:
            try:
                x = float(coords[i])
                y = float(coords[i + 1])
                x_norm = normalize_unit(str(x), "length", viewport_w, viewport_h)
                y_norm = normalize_unit(str(y), "length", viewport_w, viewport_h)
                points.append((x_norm, y_norm))
                i += 2
            except (ValueError, IndexError):
                i += 1
        
        return points
    
    def _render_polyline(self, node: Node):
        ctx = self._get_current_context()
        
        viewport_w = self.svg_state.viewport_width
        viewport_h = self.svg_state.viewport_height
        
        points_str = node.get_attribute('points', '', use_inheritance=True)
        if not points_str:
            return
        
        points = self._parse_polyline_points(points_str, viewport_w, viewport_h)
        if len(points) < 2:
            return
        
        stroke_width = ctx.stroke_width
        if stroke_width > 0:
            stroke_width = self.svg_state.transform_length(stroke_width, True)
        
        stroke_color = ctx.stroke_color
        
        if ctx.opacity < 1.0 and stroke_color[3] > 0:
            stroke_color = (stroke_color[0], stroke_color[1], stroke_color[2], int(stroke_color[3] * ctx.opacity))
        
        if stroke_width <= 0 or stroke_color[3] == 0:
            return
        
        linecap = get_attribute_with_default(node, 'stroke-linecap', use_inheritance=True) or 'butt'
        linejoin = get_attribute_with_default(node, 'stroke-linejoin', use_inheritance=True) or 'miter'
        miter_limit_str = get_attribute_with_default(node, 'stroke-miterlimit', use_inheritance=True) or '4'
        
        try:
            miter_limit = float(miter_limit_str)
        except (ValueError, TypeError):
            miter_limit = 4.0
        
        dasharray_str = get_attribute_with_default(node, 'stroke-dasharray', use_inheritance=True) or 'none'
        dash_array = self._parse_dasharray(dasharray_str, viewport_w, viewport_h)
        
        dashoffset_str = get_attribute_with_default(node, 'stroke-dashoffset', use_inheritance=True) or '0'
        try:
            dash_offset = normalize_unit(dashoffset_str, "length", viewport_w, viewport_h)
        except (ValueError, TypeError):
            dash_offset = 0.0
        
        pixel_points = [self._svg_to_pixel(x, y) for x, y in points]
        
        cumulative_distance = 0.0
        
        for i in range(len(pixel_points) - 1):
            px1, py1 = pixel_points[i]
            px2, py2 = pixel_points[i + 1]
            
            segment_length = math.sqrt((px2 - px1) ** 2 + (py2 - py1) ** 2)
            segment_offset = dash_offset - cumulative_distance if cumulative_distance < dash_offset else 0.0
            
            angle = math.atan2(py2 - py1, px2 - px1)
            
            if i == 0 and linecap != 'butt' and (not dash_array or len(dash_array) == 0):
                self._draw_line_cap(px1, py1, angle + math.pi, stroke_color, stroke_width, linecap)
            
            if i == len(pixel_points) - 2 and linecap != 'butt' and (not dash_array or len(dash_array) == 0):
                self._draw_line_cap(px2, py2, angle, stroke_color, stroke_width, linecap)
            
            self._draw_line_segment(px1, py1, px2, py2, stroke_color, stroke_width, dash_array, segment_offset)
            
            if i < len(pixel_points) - 2:
                px3, py3 = pixel_points[i + 2]
                angle2 = math.atan2(py3 - py2, px3 - px2)
                self._draw_line_join(px2, py2, angle, angle2, stroke_color, stroke_width, linejoin, miter_limit)
            
            cumulative_distance += segment_length
    
    def _parse_path_numbers(self, path_str: str, start_pos: int) -> Tuple[List[float], int]:
        numbers = []
        pos = start_pos
        current_num = ""
        
        while pos < len(path_str):
            char = path_str[pos]
            
            if char in 'MmLlHhVvCcSsQqTtAaZz':
                break
            
            if char in ' \t\n\r,':
                if current_num:
                    try:
                        numbers.append(float(current_num))
                        current_num = ""
                    except ValueError:
                        pass
            elif char in '+-' or char.isdigit() or char == '.':
                if current_num and char in '+-' and current_num[-1] not in 'eE':
                    if current_num:
                        try:
                            numbers.append(float(current_num))
                        except ValueError:
                            pass
                    current_num = char
                else:
                    current_num += char
            else:
                if current_num:
                    try:
                        numbers.append(float(current_num))
                        current_num = ""
                    except ValueError:
                        pass
            
            pos += 1
        
        if current_num:
            try:
                numbers.append(float(current_num))
            except ValueError:
                pass
        
        return numbers, pos
    
    def _subdivide_cubic_bezier(self, p0: Tuple[float, float], p1: Tuple[float, float], 
                                p2: Tuple[float, float], p3: Tuple[float, float], 
                                tolerance: float = 0.5) -> List[Tuple[float, float]]:
        points = [p0]
        
        def midpoint(a, b):
            return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        
        def distance_sq(p1, p2):
            dx = p1[0] - p2[0]
            dy = p1[1] - p2[1]
            return dx * dx + dy * dy
        
        def flatness(p0, p1, p2, p3):
            ux = 3 * p1[0] - 2 * p0[0] - p3[0]
            uy = 3 * p1[1] - 2 * p0[1] - p3[1]
            vx = 3 * p2[0] - 2 * p3[0] - p0[0]
            vy = 3 * p2[1] - 2 * p3[1] - p0[1]
            return max(ux * ux + uy * uy, vx * vx + vy * vy)
        
        def subdivide(p0, p1, p2, p3, depth=0):
            if depth > 10:
                points.append(p3)
                return
            
            if flatness(p0, p1, p2, p3) < tolerance * tolerance:
                points.append(p3)
                return
            
            m01 = midpoint(p0, p1)
            m12 = midpoint(p1, p2)
            m23 = midpoint(p2, p3)
            m012 = midpoint(m01, m12)
            m123 = midpoint(m12, m23)
            m0123 = midpoint(m012, m123)
            
            subdivide(p0, m01, m012, m0123, depth + 1)
            subdivide(m0123, m123, m23, p3, depth + 1)
        
        subdivide(p0, p1, p2, p3)
        return points
    
    def _subdivide_quadratic_bezier(self, p0: Tuple[float, float], p1: Tuple[float, float], 
                                    p2: Tuple[float, float], tolerance: float = 0.5) -> List[Tuple[float, float]]:
        points = [p0]
        
        def midpoint(a, b):
            return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        
        def flatness(p0, p1, p2):
            ux = 2 * p1[0] - p0[0] - p2[0]
            uy = 2 * p1[1] - p0[1] - p2[1]
            return ux * ux + uy * uy
        
        def subdivide(p0, p1, p2, depth=0):
            if depth > 10:
                points.append(p2)
                return
            
            if flatness(p0, p1, p2) < tolerance * tolerance:
                points.append(p2)
                return
            
            m01 = midpoint(p0, p1)
            m12 = midpoint(p1, p2)
            m012 = midpoint(m01, m12)
            
            subdivide(p0, m01, m012, depth + 1)
            subdivide(m012, m12, p2, depth + 1)
        
        subdivide(p0, p1, p2)
        return points
    
    def _approximate_arc(self, x1: float, y1: float, rx: float, ry: float, 
                        rotation: float, large_arc: bool, sweep: bool,
                        x2: float, y2: float) -> List[Tuple[float, float]]:
        if rx == 0 or ry == 0:
            return [(x1, y1), (x2, y2)]
        
        cos_phi = math.cos(math.radians(rotation))
        sin_phi = math.sin(math.radians(rotation))
        
        dx = (x1 - x2) / 2
        dy = (y1 - y2) / 2
        x1p = cos_phi * dx + sin_phi * dy
        y1p = -sin_phi * dx + cos_phi * dy
        
        rx = abs(rx)
        ry = abs(ry)
        
        lambda_val = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
        if lambda_val > 1:
            rx *= math.sqrt(lambda_val)
            ry *= math.sqrt(lambda_val)
        
        factor = math.sqrt(max(0, (rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p) / 
                                 (rx * rx * y1p * y1p + ry * ry * x1p * x1p)))
        
        if large_arc == sweep:
            factor = -factor
        
        cxp = factor * rx * y1p / ry
        cyp = -factor * ry * x1p / rx
        
        cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2
        cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2
        
        def angle(u, v):
            return math.atan2(v, u)
        
        theta1 = angle((x1p - cxp) / rx, (y1p - cyp) / ry)
        dtheta = angle((-x1p - cxp) / rx, (-y1p - cyp) / ry) - theta1
        
        if sweep and dtheta < 0:
            dtheta += 2 * math.pi
        elif not sweep and dtheta > 0:
            dtheta -= 2 * math.pi
        
        num_segments = max(4, int(abs(dtheta) / (math.pi / 2)) + 1)
        points = []
        
        for i in range(num_segments + 1):
            theta = theta1 + dtheta * i / num_segments
            x = cx + rx * math.cos(theta) * cos_phi - ry * math.sin(theta) * sin_phi
            y = cy + rx * math.cos(theta) * sin_phi + ry * math.sin(theta) * cos_phi
            points.append((x, y))
        
        return points
    
    def _parse_path(self, path_str: str, viewport_w: float, viewport_h: float) -> List[Tuple[float, float]]:
        if not path_str:
            return []
        
        points = []
        pos = 0
        current_x, current_y = 0.0, 0.0
        start_x, start_y = 0.0, 0.0
        prev_cp_x, prev_cp_y = None, None
        prev_qcp_x, prev_qcp_y = None, None
        
        path_str = path_str.strip()
        
        while pos < len(path_str):
            while pos < len(path_str) and path_str[pos] in ' \t\n\r,':
                pos += 1
            
            if pos >= len(path_str):
                break
            
            cmd = path_str[pos]
            pos += 1
            is_relative = cmd.islower()
            cmd_upper = cmd.upper()
            
            if cmd_upper == 'Z':
                flag = True
                
                if len(points) > 0:
                    current_x, current_y = start_x, start_y
                    points.append((start_x, start_y))
                continue
            
            numbers, pos = self._parse_path_numbers(path_str, pos)
            
            flag = True
            
            if cmd_upper == 'M':
                if len(numbers) >= 2:
                    if(flag):
                        flag = False
                        points.append(("dummy", "dummy"))
                    if is_relative:
                        current_x += numbers[0]
                        current_y += numbers[1]
                    else:
                        current_x = numbers[0]
                        current_y = numbers[1]
                    start_x, start_y = current_x, current_y
                    points.append((current_x, current_y))
                    
                    i = 2
                    while i < len(numbers):
                        if is_relative:
                            current_x += numbers[i]
                            current_y += numbers[i + 1]
                        else:
                            current_x = numbers[i]
                            current_y = numbers[i + 1]
                        points.append((current_x, current_y))
                        i += 2
            
            elif cmd_upper == 'L':
                
                i = 0
                while i < len(numbers) - 1:
                    if is_relative:
                        current_x += numbers[i]
                        current_y += numbers[i + 1]
                    else:
                        current_x = numbers[i]
                        current_y = numbers[i + 1]
                    points.append((current_x, current_y))
                    i += 2
            
            elif cmd_upper == 'H':
                flag = True
                for num in numbers:
                    if is_relative:
                        current_x += num
                    else:
                        current_x = num
                    points.append((current_x, current_y))
            
            elif cmd_upper == 'V':
                flag = True
                for num in numbers:
                    if is_relative:
                        current_y += num
                    else:
                        current_y = num
                    points.append((current_x, current_y))
            
            elif cmd_upper == 'C':
                flag = True
                i = 0
                while i < len(numbers) - 5:
                    if is_relative:
                        cp1x = current_x + numbers[i]
                        cp1y = current_y + numbers[i + 1]
                        cp2x = current_x + numbers[i + 2]
                        cp2y = current_y + numbers[i + 3]
                        end_x = current_x + numbers[i + 4]
                        end_y = current_y + numbers[i + 5]
                    else:
                        cp1x = numbers[i]
                        cp1y = numbers[i + 1]
                        cp2x = numbers[i + 2]
                        cp2y = numbers[i + 3]
                        end_x = numbers[i + 4]
                        end_y = numbers[i + 5]
                    
                    curve_points = self._subdivide_cubic_bezier(
                        (current_x, current_y), (cp1x, cp1y), (cp2x, cp2y), (end_x, end_y))
                    points.extend(curve_points[1:])
                    current_x, current_y = end_x, end_y
                    prev_cp_x, prev_cp_y = cp2x, cp2y
                    i += 6
            
            elif cmd_upper == 'S':
                flag = True
                i = 0
                while i < len(numbers) - 3:
                    if prev_cp_x is not None:
                        cp1x = 2 * current_x - prev_cp_x
                        cp1y = 2 * current_y - prev_cp_y
                    else:
                        cp1x, cp1y = current_x, current_y
                    
                    if is_relative:
                        cp2x = current_x + numbers[i]
                        cp2y = current_y + numbers[i + 1]
                        end_x = current_x + numbers[i + 2]
                        end_y = current_y + numbers[i + 3]
                    else:
                        cp2x = numbers[i]
                        cp2y = numbers[i + 1]
                        end_x = numbers[i + 2]
                        end_y = numbers[i + 3]
                    
                    curve_points = self._subdivide_cubic_bezier(
                        (current_x, current_y), (cp1x, cp1y), (cp2x, cp2y), (end_x, end_y))
                    points.extend(curve_points[1:])
                    current_x, current_y = end_x, end_y
                    prev_cp_x, prev_cp_y = cp2x, cp2y
                    i += 4
            
            elif cmd_upper == 'Q':
                flag = True
                i = 0
                while i < len(numbers) - 3:
                    if is_relative:
                        cpx = current_x + numbers[i]
                        cpy = current_y + numbers[i + 1]
                        end_x = current_x + numbers[i + 2]
                        end_y = current_y + numbers[i + 3]
                    else:
                        cpx = numbers[i]
                        cpy = numbers[i + 1]
                        end_x = numbers[i + 2]
                        end_y = numbers[i + 3]
                    
                    curve_points = self._subdivide_quadratic_bezier(
                        (current_x, current_y), (cpx, cpy), (end_x, end_y))
                    points.extend(curve_points[1:])
                    current_x, current_y = end_x, end_y
                    prev_qcp_x, prev_qcp_y = cpx, cpy
                    i += 4
            
            elif cmd_upper == 'T':
                flag = True
                i = 0
                while i < len(numbers) - 1:
                    if prev_qcp_x is not None:
                        cpx = 2 * current_x - prev_qcp_x
                        cpy = 2 * current_y - prev_qcp_y
                    else:
                        cpx, cpy = current_x, current_y
                    
                    if is_relative:
                        end_x = current_x + numbers[i]
                        end_y = current_y + numbers[i + 1]
                    else:
                        end_x = numbers[i]
                        end_y = numbers[i + 1]
                    
                    curve_points = self._subdivide_quadratic_bezier(
                        (current_x, current_y), (cpx, cpy), (end_x, end_y))
                    points.extend(curve_points[1:])
                    current_x, current_y = end_x, end_y
                    prev_qcp_x, prev_qcp_y = cpx, cpy
                    i += 2
            
            elif cmd_upper == 'A':
                flag = True
                i = 0
                while i < len(numbers) - 6:
                    rx = numbers[i]
                    ry = numbers[i + 1]
                    rotation = numbers[i + 2]
                    large_arc = bool(int(numbers[i + 3]))
                    sweep = bool(int(numbers[i + 4]))
                    
                    if is_relative:
                        end_x = current_x + numbers[i + 5]
                        end_y = current_y + numbers[i + 6]
                    else:
                        end_x = numbers[i + 5]
                        end_y = numbers[i + 6]
                    
                    arc_points = self._approximate_arc(
                        current_x, current_y, rx, ry, rotation, large_arc, sweep, end_x, end_y)
                    points.extend(arc_points[1:])
                    current_x, current_y = end_x, end_y
                    i += 7
        
        return points
    
    def _point_in_polygon(self, x: int, y: int, points: List[Tuple[int, int]], fill_rule: str) -> bool:
        if len(points) < 3:
            return False
        
        if fill_rule == 'evenodd':
            inside = False
            j = len(points) - 1
            for i in range(len(points)):
                if((not (isinstance(points[i][0], str) or isinstance(points[i][1], str)))):
                    if((not (isinstance(points[j][0], str) or isinstance(points[j][1], str)))):
                        
                        xi, yi = points[i]
                        xj, yj = points[j]
                        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                            inside = not inside
                        j = i
            return inside
        else:
            winding = 0
            j = len(points) - 1
            for i in range(len(points)):
                if((not (isinstance(points[i][0], str) or isinstance(points[i][1], str)))):
                    if((not (isinstance(points[j][0], str) or isinstance(points[j][1], str)))):
                        xi, yi = points[i]
                        xj, yj = points[j]
                        if yi <= y:
                            if yj > y and (xj - xi) * (y - yi) - (yj - yi) * (x - xi) > 0:
                                winding += 1
                        else:
                            if yj <= y and (xj - xi) * (y - yi) - (yj - yi) * (x - xi) < 0:
                                winding -= 1
                        j = i
            return winding != 0
    
    def _render_path(self, node: Node):
        ctx = self._get_current_context()
        
        viewport_w = self.svg_state.viewport_width
        viewport_h = self.svg_state.viewport_height
        
        path_str = node.get_attribute('d', '', use_inheritance=True)
        if not path_str:
            return
        
        points = self._parse_path(path_str, viewport_w, viewport_h)
        
        
        if len(points) < 2:
            return
        
        pixel_points = [self._svg_to_pixel(x, y) for x, y in points]
        
        fill_color = ctx.fill_color
        stroke_color = ctx.stroke_color
        
        if ctx.opacity < 1.0:
            if fill_color[3] > 0:
                fill_color = (fill_color[0], fill_color[1], fill_color[2], int(fill_color[3] * ctx.opacity))
            if stroke_color[3] > 0:
                stroke_color = (stroke_color[0], stroke_color[1], stroke_color[2], int(stroke_color[3] * ctx.opacity))
        
        fill_rule = get_attribute_with_default(node, 'fill-rule', use_inheritance=True) or 'nonzero'
        
        if fill_color[3] > 0 and len(pixel_points) >= 3:
            
            if(not (isinstance(pixel_points[0], str) or isinstance(pixel_points[1], str))):
                
                
            
                min_x = int(min(p[0] if (not (isinstance(p[0], str) or isinstance(p[1], str))) else 100000000 for p in pixel_points))
                max_x = int(max(p[0] if (not (isinstance(p[0], str) or isinstance(p[1], str))) else -100000000 for p in pixel_points))
                min_y = int(min(p[1] if (not (isinstance(p[0], str) or isinstance(p[1], str))) else 100000000 for p in pixel_points))
                max_y = int(max(p[1] if (not (isinstance(p[0], str) or isinstance(p[1], str))) else -100000000 for p in pixel_points))
            
                int_pixel_points = [(int(round(p[0])), int(round(p[1]))) if (not (isinstance(p[0], str) or isinstance(p[1], str))) else p  for p in pixel_points]
                
                
            
                for py in range(max(0, min_y - 1), min(self.height, max_y + 2)):
                    for px in range(max(0, min_x - 1), min(self.width, max_x + 2)):
                        
                        if self._point_in_polygon(px, py, int_pixel_points, fill_rule):
                            self._set_pixel(px, py, fill_color)
    
        
        if stroke_color[3] > 0:
            stroke_width = ctx.stroke_width
            if stroke_width > 0:
                stroke_width = self.svg_state.transform_length(stroke_width, True)
            
            if stroke_width > 0:
                
                linecap = get_attribute_with_default(node, 'stroke-linecap', use_inheritance=True) or 'butt'
                linejoin = get_attribute_with_default(node, 'stroke-linejoin', use_inheritance=True) or 'miter'
                miter_limit_str = get_attribute_with_default(node, 'stroke-miterlimit', use_inheritance=True) or '4'
                
                try:
                    miter_limit = float(miter_limit_str)
                except (ValueError, TypeError):
                    miter_limit = 4.0
                
                dasharray_str = get_attribute_with_default(node, 'stroke-dasharray', use_inheritance=True) or 'none'
                dash_array = self._parse_dasharray(dasharray_str, viewport_w, viewport_h)
                
                dashoffset_str = get_attribute_with_default(node, 'stroke-dashoffset', use_inheritance=True) or '0'
                try:
                    dash_offset = normalize_unit(dashoffset_str, "length", viewport_w, viewport_h)
                except (ValueError, TypeError):
                    dash_offset = 0.0
                
                cumulative_distance = 0.0
                
                for i in range(len(pixel_points) - 1):
                    px1, py1 = pixel_points[i]
                    px2, py2 = pixel_points[i + 1]
                    
                    
                    if( (isinstance(pixel_points[i+1][0], str) or isinstance(pixel_points[i+1][1], str)) ):
                        px2, py2 = pixel_points[i]
                    if( (isinstance(pixel_points[i][0], str) or isinstance(pixel_points[i][1], str)) ):
                        px1, py1 = pixel_points[i+1]
                        
                    #print(px1, py1, px2, py2)
                    
                    segment_length = math.sqrt((px2 - px1) ** 2 + (py2 - py1) ** 2)
                    segment_offset = dash_offset - cumulative_distance if cumulative_distance < dash_offset else 0.0
                    
                    angle = math.atan2(py2 - py1, px2 - px1)
                    
                    if i == 0 and linecap != 'butt' and (not dash_array or len(dash_array) == 0):
                        self._draw_line_cap(px1, py1, angle + math.pi, stroke_color, stroke_width, linecap)
                    
                    if i == len(pixel_points) - 2 and linecap != 'butt' and (not dash_array or len(dash_array) == 0):
                        self._draw_line_cap(px2, py2, angle, stroke_color, stroke_width, linecap)
                    
                    self._draw_line_segment(px1, py1, px2, py2, stroke_color, stroke_width, dash_array, segment_offset)
                    
                    if i < len(pixel_points) - 2:
                        px3, py3 = pixel_points[i + 2]
                        if( (isinstance(pixel_points[i+2][0], str) or isinstance(pixel_points[i+2][1], str)) ):
                            if(not (isinstance(pixel_points[i+1][0], str) or isinstance(pixel_points[i+1][1], str)) ):
                                px3, py3 = pixel_points[i+1]
                            else:
                                px3, py3 = pixel_points[i]
                        
                        angle2 = math.atan2(py3 - py2, px3 - px2)
                        self._draw_line_join(px2, py2, angle, angle2, stroke_color, stroke_width, linejoin, miter_limit)
                    
                    cumulative_distance += segment_length
                
                #if len(pixel_points) > 2 and pixel_points[0] == pixel_points[-1]:
                #    
                #    px1, py1 = pixel_points[-2]
                #    px2, py2 = pixel_points[0]
                #    px3, py3 = pixel_points[1]
                #    angle1 = math.atan2(py2 - py1, px2 - px1)
                #    angle2 = math.atan2(py3 - py2, px3 - px2)
                #    self._draw_line_join(px2, py2, angle1, angle2, stroke_color, stroke_width, linejoin, miter_limit)
    
    def _render_use(self, node: Node):
        href = node.get_attribute('href', None, use_inheritance=False)
        if not href:
            href = node.get_attribute('xlink:href', None, use_inheritance=False)
        
        if not href:
            return
        
        href = href.strip()
        if href.startswith('#'):
            href = href[1:]
        
        referenced_node = self._find_node_by_id(href)
        if not referenced_node:
            return
        
        viewport_w = self.svg_state.viewport_width
        viewport_h = self.svg_state.viewport_height
        
        x = get_normalized_attribute(node, 'x', 0.0, viewport_w, viewport_h)
        y = get_normalized_attribute(node, 'y', 0.0, viewport_w, viewport_h)
        
        self._push_context()
        ctx = self._get_current_context()
        
        if x != 0.0 or y != 0.0:
            ctx.apply_transform(f"translate({x} {y})", self.svg_state)
        
        self._render_node(referenced_node)
        
        self._pop_context()
    
    def get_rgb_buffer(self) -> np.ndarray:
        return self.buffer[:, :, 0:3].copy()
    
    def get_rgba_buffer(self) -> np.ndarray:
        return self.buffer.copy()

