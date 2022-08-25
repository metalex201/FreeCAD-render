# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2019 Yorik van Havre <yorik@uncreated.net>              *
# *   Copyright (c) 2022 Howefuft <howetuft-at-gmail>                       *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

"""Cycles renderer plugin for FreeCAD Render workbench."""

# Suggested documentation links:
# NOTE Standalone Cycles is experimental, so no documentation is available.
# Instead, documentation must be searched directly in code (via reverse
# engineering), and in the examples provided with it.
# Here are some links:
# https://wiki.blender.org/wiki/Source/Render/Cycles/Standalone
# https://developer.blender.org/diffusion/C/browse/master/src/
# https://developer.blender.org/diffusion/C/browse/master/src/render/nodes.cpp
# https://developer.blender.org/diffusion/C/browse/master/src/app/cycles_xml.cpp
# https://developer.blender.org/diffusion/C/browse/master/examples/
#
# A few hints (my understanding of cycles_standalone):
#
# The 'int main()' is in 'src/app/cycles_standalone.cpp' (but you may not be
# most interested in it)
#
# The xml input file is processed by 'src/app/cycles_xml.cpp' functions.
# The entry point is 'xml_read_file', which cascades to 'xml_read_scene' via
# 'xml_read_include' function.
#
# 'xml_read_scene' is a key function to study: it recognizes and dispatches all
# the possible nodes to 'xml_read_*' node-specialized parsing functions.
# A few more 'xml_read_*' (including 'xml_read_node' are defined in
# /src/graph/node_xml.cpp


import pathlib
from math import degrees, asin, sqrt, radians, atan2

import FreeCAD as App

TEMPLATE_FILTER = "Cycles templates (cycles_*.xml)"

# ===========================================================================
#                             Objects
# ===========================================================================


def write_mesh(name, mesh, material):
    """Compute a string in renderer SDL to represent a FreeCAD mesh."""
    # Compute material values
    matval = material.get_material_values(
        name, _write_texture, _write_value, _write_texref
    )

    snippet_mat = _write_material(name, matval)

    points = [
        f"{round(p.x, 8)} {round(p.y, 8)} {round(p.z, 8)}"
        for p in mesh.Topology[0]
    ]
    points = "  ".join(points)
    verts = [f"{v[0]} {v[1]} {v[2]}" for v in mesh.Topology[1]]
    verts = "  ".join(verts)
    nverts = ["3"] * len(mesh.Topology[1])
    nverts = "  ".join(nverts)

    if mesh.has_uvmap():
        uv = [f"{p.x} {p.y}" for p in mesh.uvmap_per_vertex()]
        uv = "  ".join(uv)
        uv_statement = f'    UV="{uv}"\n'
    else:
        uv_statement = ""

    snippet_obj = f"""
<state shader="{name}">
<mesh
    P="{points}"
    verts="{verts}"
    nverts="{nverts}"
{uv_statement}/>
</state>
"""

    snippet = snippet_mat + snippet_obj

    return snippet

    return snippet.format(
        n=name, p="  ".join(points), i="  ".join(nverts), v="  ".join(verts)
    )


def write_camera(name, pos, updir, target, fov):
    """Compute a string in renderer SDL to represent a camera."""
    # This is where you create a piece of text in the format of
    # your renderer, that represents the camera.

    # Cam rotation is angle(deg) axisx axisy axisz
    # Scale needs to have z inverted to behave like a decent camera.
    # No idea what they have been doing at blender :)
    snippet = """
<!-- Generated by FreeCAD - Camera '{n}' -->
<transform
    rotate="{a} {r.x} {r.y} {r.z}"
    translate="{p.x} {p.y} {p.z}"
    scale="1 1 -1" >
    <camera
        type="perspective"
        fov="{f}"
    />
</transform>"""

    return snippet.format(
        n=name,
        a=degrees(pos.Rotation.Angle),
        r=pos.Rotation.Axis,
        p=pos.Base,
        f=radians(fov),
    )


def write_pointlight(name, pos, color, power):
    """Compute a string in renderer SDL to represent a point light."""
    # This is where you write the renderer-specific code
    # to export a point light in the renderer format

    snippet = """
<!-- Generated by FreeCAD - Pointlight '{n}' -->
<shader name="{n}_shader">
    <emission
        name="{n}_emit"
        color="{c[0]} {c[1]} {c[2]}"
        strength="{s}"
    />
    <connect from="{n}_emit emission" to="output surface"/>
</shader>
<state shader="{n}_shader">
    <light
        type="point"
        co="{p.x} {p.y} {p.z}"
        strength="1 1 1"
    />
</state>
"""

    return snippet.format(n=name, c=color, p=pos, s=power * 100)


def write_arealight(name, pos, size_u, size_v, color, power, transparent):
    """Compute a string in renderer SDL to represent an area light."""
    # Transparent area light
    rot = pos.Rotation
    axis1 = rot.multVec(App.Vector(1.0, 0.0, 0.0))
    axis2 = rot.multVec(App.Vector(0.0, 1.0, 0.0))
    direction = axis1.cross(axis2)
    snippet1 = """
<!-- Generated by FreeCAD - Area light '{n}' (transparent) -->
<shader name="{n}_shader">
    <emission
        name="{n}_emit"
        color="{c[0]} {c[1]} {c[2]}"
        strength="{s}"
    />
    <connect from="{n}_emit emission" to="output surface"/>
</shader>
<state shader="{n}_shader">
    <light
        type="area"
        co="{round(p.x, 8)} {round(p.y, 8)} {round(p.z, 8)}"
        strength="{s} {s} {s}"
        axisu="{u.x} {u.y} {u.z}"
        axisv="{v.x} {v.y} {v.z}"
        sizeu="{a}"
        sizev="{b}"
        size="0.0"
        round="false"
        dir="{d.x} {d.y} {d.z}"
        use_mis = "true"
    />
</state>
"""

    # Opaque area light (--> mesh light)
    points = [
        (-size_u / 2, -size_v / 2, 0),
        (+size_u / 2, -size_v / 2, 0),
        (+size_u / 2, +size_v / 2, 0),
        (-size_u / 2, +size_v / 2, 0),
    ]
    points = [pos.multVec(App.Vector(*p)) for p in points]
    points = [f"{p.x} {p.y} {p.z}" for p in points]
    points = "  ".join(points)

    snippet2 = """
<!-- Generated by FreeCAD - Area light '{n}' (opaque) -->
<shader name="{n}_shader" use_mis="true">
    <emission
        name="{n}_emit"
        color="{c[0]} {c[1]} {c[2]}"
        strength="{s}"
    />
    <connect from="{n}_emit emission" to="output surface"/>
</shader>
<state shader="{n}_shader">
    <mesh
        P="{P}"
        nverts="4"
        verts="0 1 2 3"
        use_mis="true"
    />
</state>
"""

    snippet = snippet1 if transparent else snippet2
    strength = power if transparent else power / (size_u * size_v)

    return snippet.format(
        n=name,
        c=color,
        p=pos.Base,
        s=strength / 100,
        u=axis1,
        v=axis2,
        a=size_u,
        b=size_v,
        d=direction,
        P=points,
    )


def write_sunskylight(name, direction, distance, turbidity, albedo):
    """Compute a string in renderer SDL to represent a sunsky light."""
    # We use the new improved nishita model (2020)

    assert direction.Length
    _dir = App.Vector(direction)
    _dir.normalize()
    theta = asin(_dir.z / sqrt(_dir.x**2 + _dir.y**2 + _dir.z**2))
    phi = atan2(_dir.x, _dir.y)

    snippet = """
<!-- Generated by FreeCAD - Sun_sky light '{n}' -->
<background name="{n}_bg">
    <background name="{n}_bg" strength="0.3"/>
    <sky_texture
        name="{n}_tex"
        sky_type="nishita_improved"
        turbidity="{t}"
        ground_albedo="{g}"
        sun_disc="true"
        sun_elevation="{e}"
        sun_rotation="{r}"
    />
    <connect from="{n}_tex color" to="{n}_bg color" />
    <connect from="{n}_bg background" to="output surface" />
</background>
"""

    return snippet.format(n=name, t=turbidity, g=albedo, e=theta, r=phi)


def write_imagelight(name, image):
    """Compute a string in renderer SDL to represent an image-based light."""
    # Caveat: Cycles requires the image file to be in the same directory
    # as the input file
    filename = pathlib.Path(image).name
    snippet = """
<!-- Generated by FreeCAD - Image-based light '{n}' -->
<background>
    <background name="{n}_bg" />
    <environment_texture
        name= "{n}_tex"
        filename = "{f}"
    />
    <connect from="{n}_tex color" to="{n}_bg color" />
    <connect from="{n}_bg background" to="output surface" />
</background>
"""
    return snippet.format(
        n=name,
        f=filename,
    )


# ===========================================================================
#                              Material implementation
# ===========================================================================


def _write_material(name, matval):
    """Compute a string in the renderer SDL, to represent a material.

    This function should never fail: if the material is not recognized,
    a fallback material is provided.
    """
    try:
        snippet_mat = MATERIALS[matval.shadertype](name, matval)
        shadertype = matval.shadertype
    except KeyError:
        msg = (
            "'{}' - Material '{}' unknown by renderer, using fallback "
            "material\n"
        )
        App.Console.PrintWarning(msg.format(name, matval.shadertype))
        snippet_mat = _write_material_fallback(name, matval)
        shadertype = "Fallback"

    snippet_tex = matval.write_textures()

    if matval.has_bump() or matval.has_normal():
        # Add bump node (for bump and normal...) to snippet_tex
        snippet_tex = f"""
<bump name="{name}_bump"/>
<connect from="{name}_bump normal" to="{name}_bsdf normal"/>
<math name="{name}_bump_strength" math_type="minimum"/>
<connect from="{name}_bump_strength value" to="{name}_bump strength"/>
{snippet_tex}"""

    # Final result
    snippet_shader = f"""
<!-- Generated by FreeCAD - Shader '{shadertype}' - Object '{name}' -->
<shader name="{name}">
{snippet_mat}
{snippet_tex}
</shader>
"""

    return snippet_shader


def _write_material_passthrough(name, matval):
    """Compute a string in the renderer SDL for a passthrough material."""
    # snippet = indent(material.passthrough.string, "    ")
    snippet = matval["string"]
    return snippet.format(n=name, c=matval.default_color)


def _write_material_glass(name, matval, connect_to="output surface"):
    """Compute a string in the renderer SDL for a glass material."""
    return f"""
<glass_bsdf
    name="{name}_bsdf"
    IOR="{matval["ior"]}"
    color="{matval["color"]}"
/>
<connect from="{name}_bsdf bsdf" to="{connect_to}"/>"""


def _write_material_disney(name, matval, connect_to="output surface"):
    """Compute a string in the renderer SDL for a Disney material."""
    return f"""
<principled_bsdf
    name="{name}_bsdf"
    base_color = "{matval["basecolor"]}"
    subsurface = "{matval["subsurface"]}"
    metallic = "{matval["metallic"]}"
    specular = "{matval["specular"]}"
    specular_tint = "{matval["speculartint"]}"
    roughness = "{matval["roughness"]}"
    anisotropic = "{matval["anisotropic"]}"
    sheen = "{matval["sheen"]}"
    sheen_tint = "{matval["sheentint"]}"
    clearcoat = "{matval["clearcoat"]}"
    clearcoat_roughness = "{1 - float(matval["clearcoatgloss"])}"
/>
<connect from="{name}_bsdf bsdf" to="{connect_to}"/>"""


def _write_material_diffuse(name, matval, connect_to="output surface"):
    """Compute a string in the renderer SDL for a Diffuse material."""
    return f"""
<diffuse_bsdf name="{name}_bsdf" color="{matval["color"]}"/>
<connect from="{name}_bsdf bsdf" to="{connect_to}"/>"""


def _write_material_mixed(name, matval, connect_to="output surface"):
    """Compute a string in the renderer SDL for a Mixed material."""
    # Glass
    submat_g = matval.getmixedsubmat("glass")
    snippet_g = _write_material_glass(
        f"{name}_glass", submat_g, f"{name}_bsdf closure2"
    )
    snippet_g_tex = submat_g.write_textures()

    # Diffuse
    submat_d = matval.getmixedsubmat("diffuse")
    snippet_d = _write_material_diffuse(
        f"{name}_diffuse", submat_d, f"{name}_bsdf closure1"
    )
    snippet_d_tex = submat_d.write_textures()

    # Mix
    snippet_m = f"""
<mix_closure name="{name}_bsdf" fac="{matval["transparency"]}" />
<connect from="{name}_bsdf closure" to="{connect_to}" />"""

    return snippet_m + snippet_g + snippet_d + snippet_g_tex + snippet_d_tex


def _write_material_carpaint(name, matval, connect_to="output surface"):
    """Compute a string in the renderer SDL for a carpaint material."""
    return f"""
<!-- Main: principled with coating -->
<principled_bsdf
    name="{name}_bsdf"
    base_color = "{matval["basecolor"]}"
    specular = "0.1"
    roughness = "0.5"
    clearcoat = "1.0"
    clearcoat_roughness = "0.05"
/>
<connect from="{name}_bsdf bsdf" to="{connect_to}"/>

<!-- ColorRamp for noise -->
<rgb_ramp
    name="{name}_noiseramp"
    ramp="1.0 1.0 1.0 0.0 0.0 0.0"
    ramp_alpha="0.0 0.4"
/>
<connect from="{name}_noiseramp color" to="{name}_main metallic"/>

<!-- Noise -->
<noise_texture
    name="{name}_noise"
    dimensions="3D"
    scale="1000000"
    detail="5"
/>
<connect from="{name}_noise fac" to="{name}_noiseramp fac"/>"""


def _write_material_fallback(name, matval):
    """Compute a string in the renderer SDL for a fallback material.

    Fallback material is a simple Diffuse material.
    """
    try:
        red = float(matval.default_color.r)
        grn = float(matval.default_color.g)
        blu = float(matval.default_color.b)
        assert (0 <= red <= 1) and (0 <= grn <= 1) and (0 <= blu <= 1)
    except (AttributeError, ValueError, TypeError, AssertionError):
        red, grn, blu = 1, 1, 1
    snippet = """
<diffuse_bsdf name="{n}_bsdf" color="{r}, {g}, {b}"/>
<connect from="{n}_bsdf bsdf" to="output surface"/>"""
    return snippet.format(n=name, r=red, g=grn, b=blu)


MATERIALS = {
    "Passthrough": _write_material_passthrough,
    "Glass": _write_material_glass,
    "Disney": _write_material_disney,
    "Diffuse": _write_material_diffuse,
    "Mixed": _write_material_mixed,
    "Carpaint": _write_material_carpaint,
}

# ===========================================================================
#                             Textures
# ===========================================================================

# Mapping between shader fields and sockets to connect texture to
SOCKET_MAPPING = {
    "ior": "IOR",
    "basecolor": "base_color",
    "speculartint": "specular_tint",
    "sheentint": "sheen_tint",
    "transparency": "fac",
}


def _write_texture(objname, propname, proptype, propvalue):
    """Compute a string in renderer SDL to describe a texture.

    The texture is computed from a property of a shader (as the texture is
    always integrated into a shader). Property's data are expected as
    arguments.

    Args:
        objname -- Object name for which the texture is computed
        propname -- Name of the shader property
        proptype -- Type of the shader property
        propvalue -- Value of the shader property

    Returns:
        the name of the texture
        the SDL string of the texture
    """
    # TODO bump, normal, disp...
    if propname in ["disp", "clearcoat_roughness"]:
        return "", ""

    # TODO Scale, rotation... etc.

    # Compute socket name (in general, it should yield propname...)
    socket = SOCKET_MAPPING.get(propname, propname)

    # Compute texture name
    texname = f"{objname}_{propname}_tex"

    # Compute file name
    # Caveat: Cycles requires the image file to be in the same directory
    # as the input file
    filename = pathlib.Path(propvalue.file).name

    scale, rotation = float(propvalue.scale), float(propvalue.rotation)
    translation_u = float(propvalue.translation_u)
    translation_v = float(propvalue.translation_v)

    # https://blender.stackexchange.com/questions/16443/using-a-normal-map-together-with-a-bump-map

    if propname == "bump":
        # Bump texture
        texture = f"""
<image_texture
    name="{texname}"
    filename="{filename}"
    colorspace="__builtin_raw"
    tex_mapping.scale="{scale} {scale} {scale}"
    tex_mapping.rotation="{rotation} {rotation} {rotation}"
    tex_mapping.translation="{translation_u} {translation_v} 0.0"
/>
<connect from="{texname} color" to="{objname}_bump height"/>
<value name="{texname}_val" value="0.2"/>
<connect from="{texname}_val value" to="{objname}_bump_strength value1"/>"""

    elif propname == "normal":
        # Normal texture
        texture = f"""
<image_texture
    name="{texname}"
    filename="{filename}"
    colorspace="__builtin_raw"
    tex_mapping.scale="{scale} {scale} {scale}"
    tex_mapping.rotation="{rotation} {rotation} {rotation}"
    tex_mapping.translation="{translation_u} {translation_v} 0.0"
/>
<normal_map name="{texname}_normalmap" space="object" attribute="UVMap" strength="0.2"/>
<connect from="{texname} color" to="{texname}_normalmap color"/>
<connect from="{texname}_normalmap normal" to="{objname}_bump normal"/>
<value name="{texname}_val" value="0.2"/>
<connect from="{texname}_val value" to="{objname}_bump_strength value2"/>"""

    else:
        # Plain texture
        colorspace = (
            "__builtin_srgb" if "color" in propname else "__builtin_raw"
        )
        texture = f"""
<image_texture
    name="{texname}"
    filename="{filename}"
    colorspace="{colorspace}"
    tex_mapping.scale="{scale} {scale} {scale}"
    tex_mapping.rotation="{rotation} {rotation} {rotation}"
    tex_mapping.translation="{translation_u} {translation_v} 0.0"
/>
<connect from="{texname} color" to="{objname}_bsdf {socket}"/>"""

    return texname, texture


def _write_value(proptype, propvalue):
    """Compute a string in renderer SDL from a shader property value.

    Args:
        proptype -- Shader property's type
        propvalue -- Shader property's value

    The result depends on the type of the value...
    """
    val = propvalue

    # Snippets for values
    if proptype == "RGB":
        value = f"{round(val.r, 8)} {round(val.g, 8)} {round(val.b,8)}"
    elif proptype == "float":
        value = f"{round(val, 8)}"
    elif proptype == "node":
        value = ""
    elif proptype == "RGBA":
        value = f"{round(val.r, 8)} {round(val.g, 8)} {round(val.b, 8)} {round(val.a, 8)}"
    elif proptype == "texonly":
        value = f"{val}"
    elif proptype == "str":
        value = f"{val}"
    else:
        raise NotImplemented

    return value


def _write_texref(texname):
    """Compute a string in SDL for a reference to a texture in a shader."""
    return ""  # In Cycles, there is no reference to textures in shaders...


# ===========================================================================
#                              Render function
# ===========================================================================


def render(project, prefix, external, output, width, height):
    """Generate renderer command.

    Args:
        project -- The project to render
        prefix -- A prefix string for call (will be inserted before path to
            renderer)
        external -- A boolean indicating whether to call UI (true) or console
            (false) version of renderder
        width -- Rendered image width, in pixels
        height -- Rendered image height, in pixels

    Returns:
        The command to run renderer (string)
        A path to output image file (string)
    """
    # Here you trigger a render by firing the renderer
    # executable and passing it the needed arguments, and
    # the file it needs to render
    params = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Render")
    prefix = params.GetString("Prefix", "")
    if prefix:
        prefix += " "
    rpath = params.GetString("CyclesPath", "")
    args = params.GetString("CyclesParameters", "")
    args += f""" --output "{output}" """
    if not external:
        args += " --background"
    if not rpath:
        App.Console.PrintError(
            "Unable to locate renderer executable. "
            "Please set the correct path in "
            "Edit -> Preferences -> Render\n"
        )
        return None, None
    args += " --width " + str(width)
    args += " --height " + str(height)
    filepath = f'"{project.PageResult}"'
    cmd = prefix + rpath + " " + args + " " + filepath

    return cmd, output
