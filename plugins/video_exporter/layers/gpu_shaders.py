"""GPU shader utilities for VJing effects using ModernGL.

This module provides GPU-accelerated rendering for computationally expensive
visual effects like plasma, fractals, and metaballs.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

# Try to import moderngl, fallback gracefully if not available
try:
    import moderngl

    MODERNGL_AVAILABLE = True
except ImportError:
    MODERNGL_AVAILABLE = False
    logging.warning("[GPU Shaders] moderngl not installed, GPU effects disabled")

if TYPE_CHECKING:
    pass  # Reserved for future type hints


# =============================================================================
# Shader Programs (GLSL)
# =============================================================================

# Vertex shader (common to all effects)
VERTEX_SHADER = """
#version 330 core

in vec2 in_position;
in vec2 in_texcoord;
out vec2 uv;

void main() {
    gl_Position = vec4(in_position, 0.0, 1.0);
    uv = in_texcoord;
}
"""

# Plasma shader
PLASMA_SHADER = """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float time;
uniform float energy;
uniform float bass;
uniform float mid;
uniform vec2 resolution;
uniform float intensity;

void main() {
    vec2 p = uv * 4.0 - 2.0;
    float t = time * 2.0;

    // Multiple plasma waves
    float v1 = sin(p.x + t + bass * 3.14159);
    float v2 = sin(p.y + t * 0.7 + mid * 3.14159);
    float v3 = sin((p.x + p.y + t * 0.5) * 0.5);
    float v4 = sin(length(p - vec2(1.0)) + t + energy * 3.14159);

    float plasma = (v1 + v2 + v3 + v4) / 4.0;
    plasma = (plasma + 1.0) / 2.0;

    // RGB color cycling
    vec3 color;
    color.r = (sin(plasma * 6.28318 + t) + 1.0) / 2.0;
    color.g = (sin(plasma * 6.28318 + t + 2.094) + 1.0) / 2.0;
    color.b = (sin(plasma * 6.28318 + t + 4.188) + 1.0) / 2.0;

    fragColor = vec4(color, intensity);
}
"""

# Fractal (Julia set) shader
FRACTAL_SHADER = """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float time;
uniform float energy;
uniform float bass;
uniform vec2 resolution;
uniform float intensity;

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0/3.0, 1.0/3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

void main() {
    vec2 c = vec2(
        -0.7 + sin(time * 0.3) * 0.2 * (0.5 + bass * 0.5),
        0.27 + cos(time * 0.4) * 0.15
    );

    float zoom = 1.5 + sin(time * 0.2) * 0.3 * energy;
    vec2 z = (uv - 0.5) * zoom * 2.0;

    int maxIter = 64;
    int iter = 0;

    for (int i = 0; i < 64; i++) {
        if (dot(z, z) > 4.0) break;
        z = vec2(z.x * z.x - z.y * z.y, 2.0 * z.x * z.y) + c;
        iter++;
    }

    if (iter == maxIter) {
        fragColor = vec4(0.0, 0.0, 0.0, intensity);
    } else {
        float t = float(iter) / float(maxIter);
        float hue = fract(t * 3.0 + time * 0.1);
        vec3 color = hsv2rgb(vec3(hue, 0.8, 0.9));
        fragColor = vec4(color, intensity * (0.5 + t * 0.5));
    }
}
"""

# Metaballs shader
METABALLS_SHADER = """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float time;
uniform float energy;
uniform float bass;
uniform vec2 resolution;
uniform float intensity;

void main() {
    vec2 p = uv;
    float aspect = resolution.x / resolution.y;
    p.x *= aspect;

    float field = 0.0;

    // 5 metaballs
    for (int i = 0; i < 5; i++) {
        float fi = float(i);
        vec2 center = vec2(
            0.5 * aspect + sin(time * 0.5 + fi * 1.3) * 0.3 * (0.5 + bass * 0.5),
            0.5 + cos(time * 0.4 + fi * 1.7) * 0.3
        );
        float radius = 0.08 + energy * 0.04 + sin(time + fi) * 0.02;
        float d = length(p - center);
        field += radius / (d + 0.01);
    }

    // Threshold and color
    float threshold = 2.5;
    if (field > threshold) {
        float t = (field - threshold) / 2.0;
        t = clamp(t, 0.0, 1.0);

        // Gradient coloring
        vec3 color1 = vec3(0.1, 0.3, 0.8);
        vec3 color2 = vec3(0.8, 0.2, 0.5);
        vec3 color = mix(color1, color2, sin(time * 0.5 + field * 0.5) * 0.5 + 0.5);

        fragColor = vec4(color, intensity * t);
    } else {
        fragColor = vec4(0.0);
    }
}
"""

# Wormhole shader
WORMHOLE_SHADER = """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float time;
uniform float energy;
uniform float bass;
uniform vec2 resolution;
uniform float intensity;

void main() {
    vec2 center = vec2(0.5);
    vec2 p = uv - center;

    float angle = atan(p.y, p.x);
    float dist = length(p);

    // Spiral distortion
    float spiral = angle + dist * 10.0 - time * 2.0 * (0.5 + energy * 0.5);

    // Radial bands
    float bands = sin(spiral * 5.0) * 0.5 + 0.5;

    // Depth effect
    float depth = 1.0 / (dist + 0.1);
    depth = clamp(depth * 0.3, 0.0, 1.0);

    // Color based on angle and depth
    vec3 color;
    color.r = sin(spiral + time) * 0.5 + 0.5;
    color.g = sin(spiral + time + 2.094) * 0.5 + 0.5;
    color.b = sin(spiral + time + 4.188) * 0.5 + 0.5;

    color *= bands * depth;
    color *= 1.0 + bass * 0.5;

    float alpha = depth * intensity * (0.5 + bands * 0.5);
    fragColor = vec4(color, alpha);
}
"""

# Voronoi shader
VORONOI_SHADER = """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float time;
uniform float energy;
uniform float bass;
uniform vec2 resolution;
uniform float intensity;

vec2 hash2(vec2 p) {
    p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return fract(sin(p) * 43758.5453);
}

void main() {
    vec2 p = uv * 5.0;
    vec2 ip = floor(p);
    vec2 fp = fract(p);

    float minDist = 1.0;
    vec2 minPoint = vec2(0.0);

    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            vec2 neighbor = vec2(float(x), float(y));
            vec2 point = hash2(ip + neighbor);

            // Animate points
            point = 0.5 + 0.5 * sin(time * 0.5 + 6.283 * point);

            vec2 diff = neighbor + point - fp;
            float d = length(diff);

            if (d < minDist) {
                minDist = d;
                minPoint = point;
            }
        }
    }

    // Color based on cell
    vec3 color = vec3(
        0.5 + 0.5 * sin(minPoint.x * 6.283 + time),
        0.5 + 0.5 * sin(minPoint.y * 6.283 + time + 2.0),
        0.5 + 0.5 * sin((minPoint.x + minPoint.y) * 3.14 + time)
    );

    // Edge detection
    float edge = smoothstep(0.0, 0.1, minDist);
    color *= edge;
    color *= 1.0 + energy * 0.5;

    fragColor = vec4(color, intensity * edge);
}
"""


# =============================================================================
# GPU Renderer Class
# =============================================================================


class GPUShaderRenderer:
    """GPU-accelerated shader renderer using ModernGL.

    This class manages an OpenGL context and compiles/runs fragment shaders
    for various visual effects.
    """

    def __init__(self, width: int, height: int) -> None:
        """Initialize the GPU renderer.

        Args:
            width: Output width in pixels.
            height: Output height in pixels.
        """
        self.width = width
        self.height = height
        self._ctx: moderngl.Context | None = None
        self._programs: dict[str, moderngl.Program] = {}
        self._vao: moderngl.VertexArray | None = None
        self._fbo: moderngl.Framebuffer | None = None
        self._initialized = False

        if not MODERNGL_AVAILABLE:
            logging.warning("[GPU Renderer] ModernGL not available")
            return

        try:
            self._init_context()
            self._initialized = True
            logging.info(f"[GPU Renderer] Initialized {width}x{height}")
        except Exception as e:
            logging.warning(f"[GPU Renderer] Failed to initialize: {e}")
            self._initialized = False

    def _init_context(self) -> None:
        """Initialize OpenGL context and resources."""
        # Create standalone context (headless)
        self._ctx = moderngl.create_standalone_context()

        # Create vertex buffer for fullscreen quad
        vertices = np.array(
            [
                # x, y, u, v
                -1.0, -1.0, 0.0, 0.0,
                 1.0, -1.0, 1.0, 0.0,
                -1.0,  1.0, 0.0, 1.0,
                 1.0,  1.0, 1.0, 1.0,
            ],
            dtype="f4",
        )
        self._vbo = self._ctx.buffer(vertices)

        # Create framebuffer for rendering
        self._texture = self._ctx.texture((self.width, self.height), 4)
        self._fbo = self._ctx.framebuffer(color_attachments=[self._texture])

        # Compile shader programs
        self._compile_programs()

    def _compile_programs(self) -> None:
        """Compile all shader programs."""
        shaders = {
            "plasma": PLASMA_SHADER,
            "fractal": FRACTAL_SHADER,
            "metaballs": METABALLS_SHADER,
            "wormhole": WORMHOLE_SHADER,
            "voronoi": VORONOI_SHADER,
        }

        for name, fragment in shaders.items():
            try:
                program = self._ctx.program(
                    vertex_shader=VERTEX_SHADER,
                    fragment_shader=fragment,
                )
                self._programs[name] = program

                # Create VAO for this program
                # (we store it on the program for convenience)
                program.vao = self._ctx.vertex_array(
                    program,
                    [(self._vbo, "2f 2f", "in_position", "in_texcoord")],
                )
                logging.debug(f"[GPU Renderer] Compiled shader: {name}")
            except Exception as e:
                logging.warning(f"[GPU Renderer] Failed to compile {name}: {e}")

    @property
    def available(self) -> bool:
        """Check if GPU rendering is available."""
        return self._initialized and self._ctx is not None

    def has_shader(self, name: str) -> bool:
        """Check if a shader is available.

        Args:
            name: Shader name.

        Returns:
            True if shader is compiled and ready.
        """
        return name in self._programs

    def render(
        self,
        shader_name: str,
        time_pos: float,
        energy: float = 0.5,
        bass: float = 0.5,
        mid: float = 0.5,
        treble: float = 0.5,
        intensity: float = 0.7,
    ) -> Image.Image | None:
        """Render a shader effect.

        Args:
            shader_name: Name of the shader to render.
            time_pos: Time position in seconds.
            energy: Audio energy (0-1).
            bass: Bass energy (0-1).
            mid: Mid energy (0-1).
            treble: Treble energy (0-1).
            intensity: Effect intensity (0-1).

        Returns:
            RGBA PIL Image or None if rendering failed.
        """
        if not self.available or shader_name not in self._programs:
            return None

        try:
            program = self._programs[shader_name]

            # Set uniforms
            if "time" in program:
                program["time"].value = time_pos
            if "energy" in program:
                program["energy"].value = energy
            if "bass" in program:
                program["bass"].value = bass
            if "mid" in program:
                program["mid"].value = mid
            if "resolution" in program:
                program["resolution"].value = (float(self.width), float(self.height))
            if "intensity" in program:
                program["intensity"].value = intensity

            # Render to framebuffer
            self._fbo.use()
            self._ctx.clear(0.0, 0.0, 0.0, 0.0)
            program.vao.render(moderngl.TRIANGLE_STRIP)

            # Read pixels
            data = self._fbo.read(components=4)
            img = Image.frombytes("RGBA", (self.width, self.height), data)
            # Flip vertically (OpenGL origin is bottom-left)
            img = img.transpose(Image.FLIP_TOP_BOTTOM)

            return img

        except Exception as e:
            logging.warning(f"[GPU Renderer] Render failed for {shader_name}: {e}")
            return None

    def cleanup(self) -> None:
        """Release GPU resources."""
        if self._ctx:
            self._ctx.release()
            self._ctx = None
            self._initialized = False
            logging.debug("[GPU Renderer] Cleaned up")


# Global renderer instance (lazy initialization)
_gpu_renderer: GPUShaderRenderer | None = None


def get_gpu_renderer(width: int, height: int) -> GPUShaderRenderer | None:
    """Get or create GPU renderer instance.

    Args:
        width: Output width.
        height: Output height.

    Returns:
        GPUShaderRenderer instance or None if unavailable.
    """
    global _gpu_renderer

    if not MODERNGL_AVAILABLE:
        return None

    if _gpu_renderer is None or _gpu_renderer.width != width or _gpu_renderer.height != height:
        if _gpu_renderer:
            _gpu_renderer.cleanup()
        _gpu_renderer = GPUShaderRenderer(width, height)

    return _gpu_renderer if _gpu_renderer.available else None
