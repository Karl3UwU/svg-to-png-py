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
                 height: Optional[int] = None, background_color: Tuple[int, int, int] = (255, 255, 255)):
        self.svg_state = svg_state
        
        if width is None:
            width = int(svg_state.viewport_width)
        if height is None:
            height = int(svg_state.viewport_height)
        
        self.width = width
        self.height = height
        
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
    
    def _svg_to_pixel(self, x: float, y: float) -> Tuple[int, int]:
        px, py = self.svg_state.transform_point(x, y)
        ctx = self._get_current_context()
        px, py = ctx.transform.transform_point(px, py)
        pixel_x = int(round(px))
        pixel_y = int(round(py))
        
        return (pixel_x, pixel_y)
    
    def _set_pixel(self, x: int, y: int, color: Tuple[int, int, int, int]):
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return
        
        current = tuple(self.buffer[y, x, :])
        blended = blend_colors(color, current)
        self.buffer[y, x, :] = blended
    
    def _set_pixel_safe(self, x: float, y: float, color: Tuple[int, int, int, int]):
        pixel_x, pixel_y = self._svg_to_pixel(x, y)
        self._set_pixel(pixel_x, pixel_y, color)
    
    def render(self):
        if self.svg_state.svg_tree is None:
            return
        self._render_node(self.svg_state.svg_tree)
    
    def _render_node(self, node: Node):
        if node is None:
            return
        
        ctx = self._get_current_context()
        ctx.apply_node_attributes(node)
        
        transform_str = node.get_attribute('transform', None, use_inheritance=False)
        if transform_str:
            ctx.apply_transform(transform_str)
        
        if node.tag == 'g':
            self._push_context()
            for child in node.children:
                self._render_node(child)
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
        
        if node.tag not in ['g']:
            for child in node.children:
                self._render_node(child)
    
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
        
        min_x, min_y = self._svg_to_pixel(x, y)
        max_x, max_y = self._svg_to_pixel(x + width, y + height)
        
        if fill_color[3] > 0:
            for py in range(min_y, max_y + 1):
                for px in range(min_x, max_x + 1):
                    self._set_pixel(px, py, fill_color)
        
        if stroke_width > 0 and stroke_color[3] > 0:
            half_stroke = max(1, int(stroke_width / 2))
            
            for py in range(min_y, max_y + 1):
                for px in range(min_x, max_x + 1):
                    on_edge = (px < min_x + half_stroke or px > max_x - half_stroke or
                              py < min_y + half_stroke or py > max_y - half_stroke)
                    if on_edge:
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
        
        r_inner = max(0, radius_px - stroke_width / 2) if stroke_width > 0 else 0
        r_outer = radius_px + stroke_width / 2 if stroke_width > 0 else radius_px
        r_inner_sq = r_inner * r_inner
        r_outer_sq = r_outer * r_outer
        radius_sq = radius_px * radius_px
        
        for py in range(min_y, max_y + 1):
            for px in range(min_x, max_x + 1):
                dx = px - center_x
                dy = py - center_y
                dist_sq = dx * dx + dy * dy
                
                if fill_color[3] > 0 and dist_sq <= radius_sq:
                    self._set_pixel(px, py, fill_color)
                
                if stroke_width > 0 and stroke_color[3] > 0 and r_inner_sq < dist_sq <= r_outer_sq:
                    self._set_pixel(px, py, stroke_color)
    
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
        
        rx_inner = max(0, radius_x_px - stroke_width / 2) if stroke_width > 0 else 0
        ry_inner = max(0, radius_y_px - stroke_width / 2) if stroke_width > 0 else 0
        rx_outer = radius_x_px + stroke_width / 2 if stroke_width > 0 else radius_x_px
        ry_outer = radius_y_px + stroke_width / 2 if stroke_width > 0 else radius_y_px
        
        for py in range(min_y, max_y + 1):
            for px in range(min_x, max_x + 1):
                dx = px - center_x
                dy = py - center_y
                
                ellipse_val = (dx * dx) / (radius_x_px * radius_x_px) + (dy * dy) / (radius_y_px * radius_y_px) if radius_x_px > 0 and radius_y_px > 0 else 1.0
                
                if fill_color[3] > 0 and ellipse_val <= 1.0:
                    self._set_pixel(px, py, fill_color)
                
                if stroke_width > 0 and stroke_color[3] > 0:
                    inner_val = (dx * dx) / (rx_inner * rx_inner) + (dy * dy) / (ry_inner * ry_inner) if rx_inner > 0 and ry_inner > 0 else 0.0
                    outer_val = (dx * dx) / (rx_outer * rx_outer) + (dy * dy) / (ry_outer * ry_outer) if rx_outer > 0 and ry_outer > 0 else 1.0
                    
                    if inner_val > 1.0 and outer_val <= 1.0:
                        self._set_pixel(px, py, stroke_color)
    
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
        
        half_width = max(1, int(stroke_width / 2))
        perp_x = -dy / length
        perp_y = dx / length
        
        adx = abs(dx)
        ady = abs(dy)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = adx - ady
        
        x, y = x1, y1
        distance = 0.0
        
        if dash_array and len(dash_array) > 0:
            dash_pattern_length = sum(dash_array)
            if dash_pattern_length > 0:
                dash_offset = dash_offset % dash_pattern_length
                dash_index = 0
                dash_phase = dash_offset
                
                while dash_phase >= dash_array[dash_index]:
                    dash_phase -= dash_array[dash_index]
                    dash_index = (dash_index + 1) % len(dash_array)
                
                is_dash = dash_index % 2 == 0
                dash_remaining = dash_array[dash_index] - dash_phase
            else:
                is_dash = True
                dash_remaining = float('inf')
        else:
            is_dash = True
            dash_remaining = float('inf')
        
        while True:
            if dash_array and len(dash_array) > 0:
                if dash_remaining <= 0:
                    dash_index = (dash_index + 1) % len(dash_array)
                    dash_remaining = dash_array[dash_index]
                    is_dash = dash_index % 2 == 0
            
            if is_dash:
                for offset in range(-half_width, half_width + 1):
                    px = int(x + offset * perp_x)
                    py = int(y + offset * perp_y)
                    self._set_pixel(px, py, stroke_color)
            
            if x == x2 and y == y2:
                break
            
            e2 = 2 * err
            moved = False
            if e2 > -ady:
                err -= ady
                x += sx
                moved = True
            if e2 < adx:
                err += adx
                y += sy
                moved = True
            
            if moved:
                distance += 1.0
                if dash_array and len(dash_array) > 0:
                    dash_remaining -= 1.0
    
    def _draw_line_cap(self, x: int, y: int, angle: float, 
                      stroke_color: Tuple[int, int, int, int], 
                      stroke_width: float, cap_type: str):
        if stroke_width <= 0 or stroke_color[3] == 0:
            return
        
        half_width = max(1, int(stroke_width / 2))
        
        if cap_type == 'round':
            for offset_y in range(-half_width, half_width + 1):
                for offset_x in range(-half_width, half_width + 1):
                    dist_sq = offset_x * offset_x + offset_y * offset_y
                    if dist_sq <= half_width * half_width:
                        self._set_pixel(x + offset_x, y + offset_y, stroke_color)
        elif cap_type == 'square':
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            extend_x = int(half_width * cos_a)
            extend_y = int(half_width * sin_a)
            
            for offset_y in range(-half_width, half_width + 1):
                for offset_x in range(-half_width, half_width + 1):
                    self._set_pixel(x + offset_x + extend_x, y + offset_y + extend_y, stroke_color)
    
    def _draw_line_join(self, x: int, y: int, angle1: float, angle2: float,
                       stroke_color: Tuple[int, int, int, int],
                       stroke_width: float, join_type: str, miter_limit: float = 4.0):
        if stroke_width <= 0 or stroke_color[3] == 0:
            return
        
        half_width = max(1, int(stroke_width / 2))
        bisect_angle = (angle1 + angle2) / 2.0
        
        if join_type == 'round':
            for offset_y in range(-half_width, half_width + 1):
                for offset_x in range(-half_width, half_width + 1):
                    dist_sq = offset_x * offset_x + offset_y * offset_y
                    if dist_sq <= half_width * half_width:
                        self._set_pixel(x + offset_x, y + offset_y, stroke_color)
        elif join_type == 'miter':
            angle_diff = abs(angle2 - angle1)
            if angle_diff > math.pi:
                angle_diff = 2 * math.pi - angle_diff
            
            if angle_diff < 0.001:
                return
            
            miter_length = half_width / math.sin(angle_diff / 2.0)
            
            if miter_length <= miter_limit * half_width:
                cos_a = math.cos(bisect_angle)
                sin_a = math.sin(bisect_angle)
                miter_x = int(miter_length * cos_a)
                miter_y = int(miter_length * sin_a)
                
                for offset_y in range(-half_width, half_width + 1):
                    for offset_x in range(-half_width, half_width + 1):
                        self._set_pixel(x + offset_x, y + offset_y, stroke_color)
                
                for i in range(half_width, int(miter_length) + 1):
                    self._set_pixel(x + int(i * cos_a), y + int(i * sin_a), stroke_color)
            else:
                join_type = 'bevel'
        
        if join_type == 'bevel':
            cos_a1 = math.cos(angle1)
            sin_a1 = math.sin(angle1)
            cos_a2 = math.cos(angle2)
            sin_a2 = math.sin(angle2)
            
            for offset_y in range(-half_width, half_width + 1):
                for offset_x in range(-half_width, half_width + 1):
                    self._set_pixel(x + offset_x, y + offset_y, stroke_color)
            
            for i in range(1, half_width + 1):
                self._set_pixel(x + int(i * cos_a1), y + int(i * sin_a1), stroke_color)
                self._set_pixel(x + int(i * cos_a2), y + int(i * sin_a2), stroke_color)
    
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
    
    def _render_path(self, node: Node):
        pass
    
    def get_rgb_buffer(self) -> np.ndarray:
        return self.buffer[:, :, 0:3].copy()
    
    def get_rgba_buffer(self) -> np.ndarray:
        return self.buffer.copy()

