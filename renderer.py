from __future__ import annotations
import numpy as np
from typing import Optional, Tuple
from parser import Node
from svg_state import SVGState
from drawing_context import DrawingContext, TransformMatrix
from colors import blend_colors, get_color_with_opacity

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
        pass
    
    def _render_circle(self, node: Node):
        pass
    
    def _render_ellipse(self, node: Node):
        pass
    
    def _render_line(self, node: Node):
        pass
    
    def _render_polyline(self, node: Node):
        pass
    
    def _render_path(self, node: Node):
        pass
    
    def get_rgb_buffer(self) -> np.ndarray:
        return self.buffer[:, :, 0:3].copy()
    
    def get_rgba_buffer(self) -> np.ndarray:
        return self.buffer.copy()

