from __future__ import annotations
import sys
import os
from parser import parse_svg_file
from svg_state import SVGState
from renderer import Renderer

def process_svg_file(svg_path: str, output_path: str = None, verbose: bool = False,
                    width: int = None, height: int = None, 
                    background: tuple[int, int, int] = (255, 255, 255),
                    skip_render: bool = False, anti_aliasing: bool = False):
    if not os.path.exists(svg_path):
        print(f"Error: File not found: {svg_path}")
        return False
    
    if not svg_path.lower().endswith('.svg'):
        print(f"Warning: {svg_path} does not have .svg extension bruh")
    
    try:
        entries = parse_svg_file(svg_path)
        svg_state = SVGState(entries)
        
        if verbose:
            print(f"\nProcessing: {svg_path}")
            print(f"Viewport: {svg_state.viewport_width}x{svg_state.viewport_height}")
            if svg_state.viewbox:
                print(f"ViewBox: {svg_state.viewbox}")
            svg_state.print_validation_report()
        
        # Validate SVG
        if not svg_state.is_valid():
            print(f"Error: {svg_path} has validation errors")
            return False
        
        if output_path is None:
            base_name = os.path.splitext(os.path.basename(svg_path))[0]
            output_path = f"{base_name}.png"
        
        if verbose:
            print(f"Output will be: {output_path}")
            if width or height:
                print(f"Output dimensions: {width or int(svg_state.viewport_width)}x{height or int(svg_state.viewport_height)}")
            print(f"Background color: RGB{background}")
        
        if not skip_render:
            try:
                renderer = Renderer(svg_state, width=width, height=height, background_color=background, anti_aliasing=anti_aliasing)
                renderer.render()
                
                try:
                    from PIL import Image
                    rgb_buffer = renderer.get_rgb_buffer()
                    image = Image.fromarray(rgb_buffer, 'RGB')
                    image.save(output_path)
                    if verbose:
                        print(f"[OK] Rendered and saved: {output_path}")
                    else:
                        print(f"[OK] {svg_path} -> {output_path}")
                except ImportError:
                    if verbose:
                        print(f"[WARNING] PIL/Pillow not installed. Buffer created but PNG export skipped.")
                        print(f"         Install with: pip install Pillow")
                    print(f"[OK] Rendered: {svg_path} (PNG export requires Pillow)")
                except Exception as e:
                    print(f"Error saving PNG: {e}")
                    return False
            except Exception as e:
                print(f"Error during rendering: {e}")
                if verbose:
                    import traceback
                    traceback.print_exc()
                return False
        else:
            print(f"[OK] Parsed: {svg_path} -> {output_path} (rendering skipped)")
        
        return True
        
    except Exception as e:
        print(f"Error processing {svg_path}: {e}")
        return False

def main():
    args = sys.argv[1:]
    
    if len(args) == 0:
        print("SVG to PNG Converter")
        print("Usage: python main.py <svg_file1> [svg_file2] ... [options]")
        print("\nOptions:")
        print("  -v, --verbose         Print detailed information")
        print("  -o, --output PATH     Specify output directory or file pattern")
        print("  -w, --width WIDTH     Override output width in pixels")
        print("  -h, --height HEIGHT   Override output height in pixels")
        print("  -b, --background RGB  Background color as R,G,B (default: 255,255,255)")
        print("  -aa, --anti-aliasing  Enable anti-aliasing (default: off)")
        print("  --skip-render         Skip rendering (only parse and validate)")
        print("\nExamples:")
        print("  python main.py test.svg")
        print("  python main.py file1.svg file2.svg file3.svg")
        print("  python main.py *.svg -v")
        print("  python main.py test.svg -w 800 -h 600")
        print("  python main.py test.svg -b 0,0,0  # Black background")
        return
    
    verbose = False
    output_dir = None
    width = None
    height = None
    background = (255, 255, 255)
    skip_render = False
    anti_aliasing = False
    svg_files = []
    
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ['-v', '--verbose']:
            verbose = True
        elif arg in ['-o', '--output']:
            if i + 1 < len(args):
                output_dir = args[i + 1]
                i += 1
            else:
                print("Error: -o/--output requires a path argument")
                return
        elif arg in ['-w', '--width']:
            if i + 1 < len(args):
                try:
                    width = int(args[i + 1])
                    if width <= 0:
                        print("Error: Width must be positive")
                        return
                except ValueError:
                    print("Error: Width must be an integer")
                    return
                i += 1
            else:
                print("Error: -w/--width requires a value")
                return
        elif arg in ['-h', '--height']:
            if i + 1 < len(args):
                try:
                    height = int(args[i + 1])
                    if height <= 0:
                        print("Error: Height must be positive")
                        return
                except ValueError:
                    print("Error: Height must be an integer")
                    return
                i += 1
            else:
                print("Error: -h/--height requires a value")
                return
        elif arg in ['-b', '--background']:
            if i + 1 < len(args):
                try:
                    rgb_parts = args[i + 1].split(',')
                    if len(rgb_parts) != 3:
                        print("Error: Background must be R,G,B (e.g., 255,255,255)")
                        return
                    r = int(rgb_parts[0].strip())
                    g = int(rgb_parts[1].strip())
                    b = int(rgb_parts[2].strip())
                    r = max(0, min(255, r))
                    g = max(0, min(255, g))
                    b = max(0, min(255, b))
                    background = (r, g, b)
                except (ValueError, IndexError):
                    print("Error: Background must be R,G,B integers (e.g., 255,255,255)")
                    return
                i += 1
            else:
                print("Error: -b/--background requires R,G,B values")
                return
        elif arg in ['-aa', '--anti-aliasing']:
            if i + 1 < len(args):
                aa_value = args[i + 1].lower()
                if aa_value in ['true', '1', 'yes', 'on']:
                    anti_aliasing = True
                elif aa_value in ['false', '0', 'no', 'off']:
                    anti_aliasing = False
                else:
                    print("Error: -aa/--anti-aliasing requires true/false, 1/0, yes/no, or on/off")
                    return
                i += 1
            else:
                anti_aliasing = True
        elif arg == '--skip-render':
            skip_render = True
        elif arg.startswith('-'):
            print(f"Unknown option: {arg}")
            return
        else:
            svg_files.append(arg)
        i += 1
    
    if len(svg_files) == 0:
        print("Error: No SVG files specified")
        return
    
    success_count = 0
    for svg_file in svg_files:
        output_path = None
        if output_dir:
            if os.path.isdir(output_dir):
                base_name = os.path.splitext(os.path.basename(svg_file))[0]
                output_path = os.path.join(output_dir, f"{base_name}.png")
            else:
                if len(svg_files) == 1:
                    output_path = output_dir
                else:
                    print(f"Warning: -o with multiple files requires a directory, not a file")
        
        if process_svg_file(svg_file, output_path, verbose, width, height, background, skip_render, anti_aliasing):
            success_count += 1
    
    print(f"\nProcessed {success_count}/{len(svg_files)} file(s) successfully")

if __name__ == "__main__":
    main()
