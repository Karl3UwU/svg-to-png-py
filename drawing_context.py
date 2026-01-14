from __future__ import annotations
import math
import re
from typing import Optional
from parser import Node
from colors import get_node_color

class TransformMatrix:
    def __init__(self, a: float = 1.0, b: float = 0.0, c: float = 0.0, 
                 d: float = 1.0, e: float = 0.0, f: float = 0.0):
        self.a = a
        self.b = b
        self.c = c
        self.d = d
        self.e = e
        self.f = f
    
    def identity() -> 'TransformMatrix':
        return TransformMatrix(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    
    def translate(tx: float, ty: float) -> 'TransformMatrix':
        return TransformMatrix(1.0, 0.0, 0.0, 1.0, tx, ty)
    
    def scale(sx: float, sy: float = None) -> 'TransformMatrix':
        if sy is None:
            sy = sx
        return TransformMatrix(sx, 0.0, 0.0, sy, 0.0, 0.0)
    
    def rotate(angle_degrees: float, cx: float = 0.0, cy: float = 0.0) -> 'TransformMatrix':
        angle_rad = math.radians(angle_degrees)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        
        if cx != 0.0 or cy != 0.0:
            t1 = TransformMatrix.translate(-cx, -cy)
            r = TransformMatrix(cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            t2 = TransformMatrix.translate(cx, cy)
            return t2.multiply(r).multiply(t1)
        else:
            return TransformMatrix(cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
    
    def multiply(self, other: 'TransformMatrix') -> 'TransformMatrix':
        return TransformMatrix(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f
        )
    
    def is_identity(self) -> bool:
        return (abs(self.a - 1.0) < 1e-6 and abs(self.b) < 1e-6 and 
                abs(self.c) < 1e-6 and abs(self.d - 1.0) < 1e-6 and 
                abs(self.e) < 1e-6 and abs(self.f) < 1e-6)
    
    def transform_point(self, x: float, y: float) -> tuple[float, float]:
        new_x = self.a * x + self.c * y + self.e
        new_y = self.b * x + self.d * y + self.f
        return (new_x, new_y)
    
    def inverse(self) -> 'TransformMatrix':
        det = self.a * self.d - self.b * self.c
        if abs(det) < 1e-10:
            return TransformMatrix.identity()
        
        inv_det = 1.0 / det
        new_a = self.d * inv_det
        new_b = -self.b * inv_det
        new_c = -self.c * inv_det
        new_d = self.a * inv_det
        new_e = (self.c * self.f - self.d * self.e) * inv_det
        new_f = (self.b * self.e - self.a * self.f) * inv_det
        return TransformMatrix(new_a, new_b, new_c, new_d, new_e, new_f)
    
    def copy(self) -> 'TransformMatrix':
        return TransformMatrix(self.a, self.b, self.c, self.d, self.e, self.f)

class DrawingContext:
    def __init__(self):
        self.transform = TransformMatrix.identity()
        self.fill_color = (0, 0, 0, 255)
        self.stroke_color = (0, 0, 0, 255)
        self.stroke_width = 1.0
        self.opacity = 1.0
        self.clip_region = None
    
    def push(self) -> 'DrawingContext':
        new_ctx = DrawingContext()
        new_ctx.transform = self.transform.copy()
        new_ctx.fill_color = self.fill_color
        new_ctx.stroke_color = self.stroke_color
        new_ctx.stroke_width = self.stroke_width
        new_ctx.opacity = self.opacity
        new_ctx.clip_region = self.clip_region
        return new_ctx
    
    def apply_node_attributes(self, node: Node):
        self.fill_color = get_node_color(node, 'fill', 'opacity')
        self.stroke_color = get_node_color(node, 'stroke', 'opacity')
        
        stroke_width_str = node.get_attribute('stroke-width', '1', use_inheritance=True)
        if stroke_width_str:
            try:
                self.stroke_width = float(stroke_width_str)
            except (ValueError, TypeError):
                self.stroke_width = 1.0
        
        opacity_str = node.get_attribute('opacity', '1', use_inheritance=True)
        if opacity_str:
            try:
                self.opacity = float(opacity_str)
                self.opacity = max(0.0, min(1.0, self.opacity))
            except (ValueError, TypeError):
                self.opacity = 1.0
    
    def apply_transform(self, transform_str: str, svg_state = None):
        if not transform_str:
            return
        
        transform_pattern = re.compile(
            r'(matrix|translate|rotate|scale|skewX|skewY)\s*\(([^)]+)\)',
            re.IGNORECASE
        )
        
        matches = transform_pattern.findall(transform_str)
        for func_name, params in matches:
            params_str = params.strip()
            params_list = re.split(r'[,\s]+', params_str)
            params = [float(p) for p in params_list if p]
            func_name = func_name.lower()
            
            if func_name == 'matrix' and len(params) >= 6:
                new_transform = TransformMatrix(params[0], params[1], params[2], 
                                               params[3], params[4], params[5])
                self.transform = self.transform.multiply(new_transform)
            
            elif func_name == 'translate':
                tx = params[0] if len(params) > 0 else 0.0
                ty = params[1] if len(params) > 1 else 0.0
                new_transform = TransformMatrix.translate(tx, ty)
                self.transform = self.transform.multiply(new_transform)
            
            elif func_name == 'rotate':
                angle = params[0] if len(params) > 0 else 0.0
                cx = params[1] if len(params) > 1 else 0.0
                cy = params[2] if len(params) > 2 else 0.0
                if svg_state and svg_state.viewbox is not None:
                    cx, cy = svg_state.transform_point(cx, cy)
                new_transform = TransformMatrix.rotate(angle, cx, cy)
                self.transform = self.transform.multiply(new_transform)
            
            elif func_name == 'scale':
                sx = params[0] if len(params) > 0 else 1.0
                sy = params[1] if len(params) > 1 else sx
                new_transform = TransformMatrix.scale(sx, sy)
                self.transform = self.transform.multiply(new_transform)
            
            elif func_name == 'skewx':
                angle = params[0] if len(params) > 0 else 0.0
                tan_a = math.tan(math.radians(angle))
                new_transform = TransformMatrix(1.0, 0.0, tan_a, 1.0, 0.0, 0.0)
                self.transform = self.transform.multiply(new_transform)
            
            elif func_name == 'skewy':
                angle = params[0] if len(params) > 0 else 0.0
                tan_a = math.tan(math.radians(angle))
                new_transform = TransformMatrix(1.0, tan_a, 0.0, 1.0, 0.0, 0.0)
                self.transform = self.transform.multiply(new_transform)

