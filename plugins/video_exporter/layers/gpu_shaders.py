"""GPU shader utilities for VJing effects using ModernGL.

This module provides GPU-accelerated rendering for computationally expensive
visual effects like plasma, fractals, and metaballs.

Palettes are passed dynamically as uniforms, allowing customizable colors.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import numpy as np
from PIL import Image

# Try to import moderngl, fallback gracefully if not available
try:
    import moderngl

    MODERNGL_AVAILABLE = True
    _TRIANGLE_STRIP: Any = moderngl.TRIANGLE_STRIP
except ImportError:
    MODERNGL_AVAILABLE = False
    _TRIANGLE_STRIP = None
    logging.warning("[GPU Shaders] moderngl not installed, GPU effects disabled")

# Global lock for thread-safe GPU access (OpenGL contexts are NOT thread-safe)
_gpu_lock = threading.Lock()

# Contexte ModernGL par thread : sur macOS, NSOpenGLContext/CGL est lié au thread créateur.
# Quand ce thread se termine, ModernGL invalide le contexte (classe → InvalidObject).
# Un threading.local() garantit que chaque thread (preview, export…) a son propre contexte.
_thread_local_gl = threading.local()


def _is_gl_context_valid(ctx: Any) -> bool:
    """Vérifie que ctx.mglo n'est pas un InvalidObject ModernGL.

    version_code est stocké comme entier Python sur le Context à la création :
    ctx.version_code reste accessible même après ctx.release(). On inspecte
    directement le type de ctx.mglo pour détecter les contextes libérés.
    """
    if ctx is None:
        return False
    try:
        return type(ctx.mglo).__name__ != "InvalidObject"
    except AttributeError:
        return False


def get_shared_gl_context() -> Any:
    """Retourne le contexte ModernGL du thread courant, le crée si nécessaire.

    Tous les layers GPU (VJing, MilkDrop, etc.) du même thread partagent ce contexte
    pour éviter les collisions de contexte OpenGL courant entre layers.
    Doit être appelée depuis l'intérieur de _gpu_lock.
    """
    ctx = getattr(_thread_local_gl, "ctx", None)
    if not _is_gl_context_valid(ctx):
        if ctx is not None:
            logging.warning("[GPU Shaders] Contexte GL invalide (mglo = InvalidObject), recréation")
        if not MODERNGL_AVAILABLE:
            raise RuntimeError("moderngl absent — installer avec : uv sync --extra video")
        import moderngl as _mgl

        new_ctx = _mgl.create_standalone_context()
        if not _is_gl_context_valid(new_ctx):
            raise RuntimeError("mgl.create_standalone_context() a retourné un contexte invalide")
        _thread_local_gl.ctx = new_ctx
    return _thread_local_gl.ctx


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

# Common palette functions (included in all fragment shaders)
PALETTE_FUNCTIONS = """
// Palette colors (5 colors, normalized 0-1)
uniform vec3 palette[5];

// Get interpolated color from palette based on position (0-1)
vec3 getPaletteColor(float t) {
    t = fract(t);  // Wrap to 0-1
    float pos = t * 4.0;  // 5 colors = 4 segments
    int idx = int(pos);
    float blend = fract(pos);

    // Interpolate between adjacent colors
    vec3 c1 = palette[idx];
    vec3 c2 = palette[min(idx + 1, 4)];
    return mix(c1, c2, blend);
}

// Get palette color with time-based cycling
vec3 getPaletteColorCycled(float t, float timeOffset) {
    return getPaletteColor(t + timeOffset);
}
"""

# Plasma shader with palette support
PLASMA_SHADER = (
    """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float time;
uniform float energy;
uniform float bass;
uniform float mid;
uniform vec2 resolution;
uniform float intensity;

"""
    + PALETTE_FUNCTIONS
    + """

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

    // Get color from palette with time cycling
    vec3 color = getPaletteColorCycled(plasma, time * 0.1);

    fragColor = vec4(color, intensity);
}
"""
)

# Fractal (Julia set) shader with palette support
FRACTAL_SHADER = (
    """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float time;
uniform float energy;
uniform float bass;
uniform vec2 resolution;
uniform float intensity;

"""
    + PALETTE_FUNCTIONS
    + """

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
        // Center of fractal: fully transparent to show effects underneath
        fragColor = vec4(0.0, 0.0, 0.0, 0.0);
    } else {
        float t = float(iter) / float(maxIter);
        // Get color from palette based on iteration count
        vec3 color = getPaletteColorCycled(t * 3.0, time * 0.1);
        fragColor = vec4(color, intensity * (0.5 + t * 0.5));
    }
}
"""
)

# Metaballs shader with palette support
METABALLS_SHADER = (
    """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float time;
uniform float energy;
uniform float bass;
uniform vec2 resolution;
uniform float intensity;

"""
    + PALETTE_FUNCTIONS
    + """

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

        // Get gradient color from palette
        vec3 color = getPaletteColorCycled(field * 0.2, time * 0.1);
        // Brighten inside
        color = mix(color, vec3(1.0), t * 0.3);

        fragColor = vec4(color, intensity * t);
    } else {
        fragColor = vec4(0.0);
    }
}
"""
)

# Wormhole shader with palette support
WORMHOLE_SHADER = (
    """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float time;
uniform float energy;
uniform float bass;
uniform vec2 resolution;
uniform float intensity;

"""
    + PALETTE_FUNCTIONS
    + """

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

    // Get color from palette based on spiral position
    float colorPos = (spiral / 6.28318 + 0.5);
    vec3 color = getPaletteColorCycled(colorPos, time * 0.1);

    color *= bands * depth;
    color *= 1.0 + bass * 0.5;

    float alpha = depth * intensity * (0.5 + bands * 0.5);
    fragColor = vec4(color, alpha);
}
"""
)

# Voronoi shader with palette support
VORONOI_SHADER = (
    """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float time;
uniform float energy;
uniform float bass;
uniform vec2 resolution;
uniform float intensity;

"""
    + PALETTE_FUNCTIONS
    + """

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

    // Get color from palette based on cell position
    float colorPos = minPoint.x + minPoint.y * 0.5;
    vec3 color = getPaletteColorCycled(colorPos, time * 0.1);

    // Edge detection
    float edge = smoothstep(0.0, 0.1, minDist);
    color *= edge;
    color *= 1.0 + energy * 0.5;

    fragColor = vec4(color, intensity * edge);
}
"""
)

# Octagrams shader (raymarching, adapté du Shadertoy « Octagrams ») avec palette
OCTAGRAMS_SHADER = (
    """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float time;
uniform vec2 resolution;
uniform float intensity;

"""
    + PALETTE_FUNCTIONS
    + """

// Temps global modulé par itération de raymarching (cf. shader original)
float gTime = 0.;

// 回転行列 — matrice de rotation 2D
mat2 rot(float a) {
    float c = cos(a), s = sin(a);
    return mat2(c,s,-s,c);
}

// Distance signée à une boîte
float sdBox( vec3 p, vec3 b )
{
    vec3 q = abs(p) - b;
    return length(max(q,0.0)) + min(max(q.x,max(q.y,q.z)),0.0);
}

// Boîte de base mise à l'échelle puis transformée
float box(vec3 pos, float scale) {
    pos *= scale;
    float base = sdBox(pos, vec3(.4,.4,.1)) /1.5;
    pos.xy *= 5.;
    pos.y -= 3.5;
    pos.xy *= rot(.75);
    float result = -base;
    return result;
}

// Ensemble de boîtes animées formant l'octagramme
float box_set(vec3 pos, float iTime) {
    vec3 pos_origin = pos;
    pos = pos_origin;
    pos .y += sin(gTime * 0.4) * 2.5;
    pos.xy *=   rot(.8);
    float box1 = box(pos,2. - abs(sin(gTime * 0.4)) * 1.5);
    pos = pos_origin;
    pos .y -=sin(gTime * 0.4) * 2.5;
    pos.xy *=   rot(.8);
    float box2 = box(pos,2. - abs(sin(gTime * 0.4)) * 1.5);
    pos = pos_origin;
    pos .x +=sin(gTime * 0.4) * 2.5;
    pos.xy *=   rot(.8);
    float box3 = box(pos,2. - abs(sin(gTime * 0.4)) * 1.5);
    pos = pos_origin;
    pos .x -=sin(gTime * 0.4) * 2.5;
    pos.xy *=   rot(.8);
    float box4 = box(pos,2. - abs(sin(gTime * 0.4)) * 1.5);
    pos = pos_origin;
    pos.xy *=   rot(.8);
    float box5 = box(pos,.5) * 6.;
    pos = pos_origin;
    float box6 = box(pos,.5) * 6.;
    float result = max(max(max(max(max(box1,box2),box3),box4),box5),box6);
    return result;
}

// Carte de distance globale de la scène
float map(vec3 pos, float iTime) {
    vec3 pos_origin = pos;
    float box_set1 = box_set(pos, iTime);

    return box_set1;
}

void main() {
    vec2 fragCoord = uv * resolution;
    float iTime = time;
    vec2 p = (fragCoord * 2. - resolution) / min(resolution.x, resolution.y);
    vec3 ro = vec3(0., -0.2 ,iTime * 4.);
    vec3 ray = normalize(vec3(p, 1.5));
    ray.xy = ray.xy * rot(sin(iTime * .03) * 5.);
    ray.yz = ray.yz * rot(sin(iTime * .05) * .2);
    float t = 0.1;
    vec3 col = vec3(0.);
    float ac = 0.0;

    // Boucle de raymarching identique à l'original (99 itérations)
    for (int i = 0; i < 99; i++){
        vec3 pos = ro + ray * t;
        pos = mod(pos-2., 4.) -2.;
        gTime = iTime -float(i) * 0.01;

        float d = map(pos, iTime);

        d = max(abs(d), 0.01);
        ac += exp(-d*23.);

        t += d* 0.55;
    }

    // Recolorisation via la palette du projet
    float glow = ac * 0.02;
    vec3 baseCol = getPaletteColorCycled(glow, iTime * 0.05);
    col = baseCol * glow;

    // Alpha original pondéré par l'intensité
    float a = (1.0 - t * (0.02 + 0.02 * sin(iTime))) * intensity;
    fragColor = vec4(col, clamp(a, 0.0, 1.0));
}
"""
)


# =============================================================================
# GPU Renderer Class
# =============================================================================


class GPUShaderRenderer:
    """GPU-accelerated shader renderer using ModernGL.

    This class manages an OpenGL context and compiles/runs fragment shaders
    for various visual effects. Palette colors are passed as uniforms.
    """

    def __init__(self, width: int, height: int) -> None:
        """Initialize the GPU renderer.

        Args:
            width: Output width in pixels.
            height: Output height in pixels.
        """
        self.width = width
        self.height = height
        self._ctx: Any = None
        self._programs: dict[str, Any] = {}
        self._vao: Any = None
        self._vbo: Any = None
        self._texture: Any = None
        self._fbo: Any = None
        self._initialized = False
        # Track creator thread - OpenGL context can only be used from this thread
        self._creator_thread_id: int | None = None

        if not MODERNGL_AVAILABLE:
            logging.warning("[GPU Renderer] ModernGL not available")
            return

        try:
            # _init_context() appelle get_shared_gl_context() qui crée le contexte
            # GL via create_standalone_context(). Cet appel DOIT être sérialisé par
            # _gpu_lock : la création de contexte touche l'état CGL global du
            # processus et n'est pas thread-safe (conflit potentiel sur macOS si
            # deux threads d'export l'instancient simultanément). Voir [C23].
            t0 = time.perf_counter()
            with _gpu_lock:
                self._init_context()
            self._creator_thread_id = threading.get_ident()
            self._initialized = True
            logging.info(
                "[GPU Renderer] [Timing] Initialized %dx%d (contexte + compilation "
                "des shaders): %.2fs",
                width,
                height,
                time.perf_counter() - t0,
            )
        except Exception as e:
            logging.warning(f"[GPU Renderer] Failed to initialize: {e}")
            # Libère toute ressource GL allouée avant l'échec
            self.cleanup()

    def _init_context(self) -> None:
        """Initialize OpenGL context and resources."""
        self._ctx = get_shared_gl_context()

        # Create vertex buffer for fullscreen quad
        vertices = np.array(
            [
                # x, y, u, v
                -1.0,
                -1.0,
                0.0,
                0.0,
                1.0,
                -1.0,
                1.0,
                0.0,
                -1.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
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
            "octagrams": OCTAGRAMS_SHADER,
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
                logging.warning(f"[GPU Renderer] Failed to compile {name}: {e}", exc_info=True)

    @property
    def available(self) -> bool:
        """Check if GPU rendering is available from current thread."""
        if not self._initialized or self._ctx is None:
            return False
        # OpenGL context can only be used from the thread that created it
        return threading.get_ident() == self._creator_thread_id

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
        palette: list[tuple[int, int, int]] | None = None,
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
            palette: List of 5 RGB tuples (0-255) for colors. Defaults to neon palette.

        Returns:
            RGBA PIL Image or None if rendering failed.
        """
        if not self.available or shader_name not in self._programs:
            return None

        # Default neon palette if none provided
        if palette is None:
            palette = [
                (255, 0, 128),  # Hot pink
                (0, 255, 255),  # Cyan
                (255, 255, 0),  # Yellow
                (128, 0, 255),  # Purple
                (0, 255, 128),  # Spring green
            ]

        # Normalize palette colors to 0-1 range for shader
        palette_normalized = [
            (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0) for c in palette[:5]  # Take first 5 colors
        ]
        # Pad to 5 colors if needed
        while len(palette_normalized) < 5:
            palette_normalized.append(
                palette_normalized[-1] if palette_normalized else (1.0, 1.0, 1.0)
            )

        # Serialize GPU access - OpenGL contexts are NOT thread-safe
        with _gpu_lock:
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

                # Set palette colors (write entire array at once)
                if "palette" in program:
                    program["palette"].value = palette_normalized

                # Render to framebuffer
                self._fbo.use()
                self._ctx.clear(0.0, 0.0, 0.0, 0.0)
                program.vao.render(_TRIANGLE_STRIP)

                # Read pixels
                data = self._fbo.read(components=4)
                img = Image.frombytes("RGBA", (self.width, self.height), data)
                # Flip vertically (OpenGL origin is bottom-left)
                img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

                return img

            except Exception as e:
                logging.warning(f"[GPU Renderer] Render failed for {shader_name}: {e}")
                return None

    def cleanup(self) -> None:
        """Libère les ressources GPU propres à ce renderer.

        Ne libère PAS le contexte GL partagé — il est géré par
        get_shared_gl_context() / _thread_local_gl.
        """
        if self._fbo:
            try:
                self._fbo.release()
            except Exception:
                logging.debug("[GPU Renderer] cleanup: FBO release ignoré (contexte déjà libéré)")
            self._fbo = None
        if self._texture:
            try:
                self._texture.release()
            except Exception:
                logging.debug(
                    "[GPU Renderer] cleanup: texture release ignoré (contexte déjà libéré)"
                )
            self._texture = None
        if self._vbo:
            try:
                self._vbo.release()
            except Exception:
                logging.debug("[GPU Renderer] cleanup: VBO release ignoré (contexte déjà libéré)")
            self._vbo = None
        for prog in self._programs.values():
            try:
                prog.vao.release()
            except Exception:
                logging.debug("[GPU Renderer] cleanup: VAO release ignoré")
            try:
                prog.release()
            except Exception:
                logging.debug(
                    "[GPU Renderer] cleanup: program release ignoré (contexte déjà libéré)"
                )
        self._programs.clear()
        self._ctx = None
        self._initialized = False
        logging.debug("[GPU Renderer] Cleaned up")


# Renderers GPU par thread : chaque thread (main, export worker…) a ses propres renderers
# pour éviter tout accès GL cross-thread (= SIGSEGV sur macOS/CGL).
# Cache par taille (width, height) : plusieurs layers de tailles différentes peuvent
# coexister dans le même thread (ex. playground : preview 512×512 + LED panel 64×64).
# Un slot unique provoquait l'éviction (cleanup) du renderer de l'autre taille, laissant
# le premier layer avec une référence morte → effets GPU silencieusement absents.
_gpu_renderer_local = threading.local()


def get_gpu_renderer(width: int, height: int) -> GPUShaderRenderer | None:
    """Retourne le renderer GPU du thread courant pour cette taille, le crée si nécessaire.

    Args:
        width: Output width.
        height: Output height.

    Returns:
        GPUShaderRenderer instance ou None si indisponible.
    """
    if not MODERNGL_AVAILABLE:
        return None

    renderers: dict[tuple[int, int], GPUShaderRenderer] | None = getattr(
        _gpu_renderer_local, "renderers", None
    )
    if renderers is None:
        renderers = {}
        _gpu_renderer_local.renderers = renderers

    renderer = renderers.get((width, height))
    if renderer is None or not renderer._initialized:
        renderer = GPUShaderRenderer(width, height)
        renderers[(width, height)] = renderer

    return renderer if renderer.available else None


def release_shared_gl_context() -> None:
    """Libère le contexte ModernGL du thread courant et les renderers associés.

    À appeler explicitement en teardown (test, arrêt d'un worker d'export) pour
    éviter qu'un contexte CGL/NSOpenGL vivant jusqu'à la finalisation de
    l'interpréteur ne provoque un segfault au milieu des finaliseurs natifs
    (moderngl / numpy / scipy) qui s'exécutent dans un ordre non déterministe.

    Sans contexte ni renderer alloué, l'appel est un no-op sûr (idempotent).
    """
    with _gpu_lock:
        renderers: dict[tuple[int, int], GPUShaderRenderer] | None = getattr(
            _gpu_renderer_local, "renderers", None
        )
        if renderers:
            for renderer in renderers.values():
                renderer.cleanup()
            renderers.clear()

        ctx = getattr(_thread_local_gl, "ctx", None)
        if ctx is not None:
            try:
                ctx.release()
            except Exception:
                logging.debug(
                    "[GPU Shaders] release_shared_gl_context: ctx.release() ignoré "
                    "(contexte déjà libéré)"
                )
            _thread_local_gl.ctx = None
