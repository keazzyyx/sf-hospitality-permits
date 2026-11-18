// Whether WebGL here is drawn by the processor (SwiftShader, llvmpipe: a machine with no graphics card, a plain
// headless browser). The living grid never rests, so in software it would take the whole main thread: the page
// uses the drawn map there instead.

/** One probe answers both questions (is there WebGL, and is it drawn in software), once: `null` without WebGL. */
let probed: boolean | null | undefined;
export function webglKind(): "hardware" | "software" | null {
  if (probed === undefined) {
    try {
      const canvas = document.createElement("canvas");
      const gl = (canvas.getContext("webgl2") ?? canvas.getContext("webgl")) as WebGLRenderingContext | null;
      if (!gl) probed = null;
      else {
        const info = gl.getExtension("WEBGL_debug_renderer_info");
        const renderer = info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : "";
        gl.getExtension("WEBGL_lose_context")?.loseContext();
        probed = /swiftshader|llvmpipe|software|basic render/i.test(renderer);
      }
    } catch {
      probed = null;
    }
  }
  return probed === null ? null : probed ? "software" : "hardware";
}

export function softwareWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    const gl = (canvas.getContext("webgl2") ?? canvas.getContext("webgl")) as WebGLRenderingContext | null;
    if (!gl) return true;
    const info = gl.getExtension("WEBGL_debug_renderer_info");
    const renderer = info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : "";
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return /swiftshader|llvmpipe|software|basic render/i.test(renderer);
  } catch {
    return true;
  }
}
