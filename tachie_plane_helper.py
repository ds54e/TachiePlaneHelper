bl_info = {
    "name": "Tachie Plane Helper",
    "author": "ds54e",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > TPH",
    "description": "Assist to generate Tachie plane and material",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}


import re
from pathlib import Path
from math import radians

import bpy
import bpy_extras
from bpy.props import StringProperty, BoolProperty, PointerProperty
from rna_prop_ui import rna_idprop_ui_prop_update


class TachiePlaneHelperPanel(bpy.types.Panel):
    bl_label = "Tachie Plane Helper"
    bl_idname = "OBJECT_PT_tachie"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "TPH"
    
    def draw(self, context):
        layout = self.layout
        tp = context.scene.tp

        layout.prop(tp, "directory")
        layout.row().operator("object.tp_generate_text_operator")
        
        layout.row().separator()
        layout.prop(tp, "create_new_plane")
        layout.prop(tp, "use_fake_user")
        layout.row().operator("object.tp_generate_material_operator")
        
        layout.row().separator()
        layout.prop_search(tp, "object", context.scene, "objects")
        layout.prop_search(tp, "material", bpy.data, "materials")
        layout.row().operator("object.tp_add_drivers_operator")
        
    

class TachiePlaneHelperGenerateTextOperator(bpy.types.Operator):
    bl_idname = "object.tp_generate_text_operator"
    bl_label = "Generate layers.txt"
    
    def execute(self, context):
        tp = context.scene.tp
        generate_text(
            tachie_dir=Path(tp.directory)
        )
        return {"FINISHED"}


def generate_text(
    tachie_dir=Path(".")
):
    layer_names = [path.name for path in tachie_dir.iterdir() if path.is_dir()]
    with (tachie_dir/"layers.txt").open("w") as f:
        f.write("\n".join(layer_names))
    
   
class TachiePlaneHelperGenerateMaterialOperator(bpy.types.Operator):
    bl_idname = "object.tp_generate_material_operator"
    bl_label = "Generate Material"
    
    def execute(self, context):
        tp = context.scene.tp
        
        material, image_size = generate_material(
            tachie_dir=Path(tp.directory),
            material_name=Path(tp.directory).name,
            use_fake_user=tp.use_fake_user,
        )
        tp.material = material
        
        if tp.create_new_plane:
            image_width, image_height = image_size
            if (image_width > 0) and (image_height > 0):
                plane = generate_plane(
                    width=1.0*(image_width/image_height),
                    height=1.0,
                )
                plane.data.materials.append(material)
                tp.object = plane
                
        return {"FINISHED"}
      
      
def generate_material(
    tachie_dir=Path("."),
    material_name="TachieMaterial",
    use_fake_user=False,
):
    layer_names = []
    with (tachie_dir/"layers.txt").open() as f:
        for line in f:
            line = line.strip()
            if line:
                layer_names.append(line)

    material = bpy.data.materials.new(material_name)
    material.use_nodes = True
    material.blend_method = "CLIP"
    material.shadow_method = "CLIP"
    material.use_fake_user = use_fake_user

    nodes = material.node_tree.nodes
    links = material.node_tree.links

    for node in nodes:
        nodes.remove(node)
        
    texture_coordinate = nodes.new("ShaderNodeTexCoord")
    texture_coordinate.location = (-500, 0)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-300, 0)
    links.new(
        texture_coordinate.outputs[2], # UV
        mapping.inputs[0] # Vector
    )
         
    n_layers = len(layer_names)
    image_textures = []
    math_adds = []
    mix_rgbs = []
    image_size = (0, 0)

    for i, layer_name in enumerate(layer_names):
        image_names = sorted([
            path.name
            for path in (tachie_dir/layer_name).iterdir()
            if path.is_file() and path.suffix==".png"
        ])
        image = bpy_extras.image_utils.load_image(
            imagepath=str(tachie_dir/layer_name/image_names[0]),
            dirname=str(tachie_dir/layer_name)
        )
        if i == 0:
            image_size = (image.size[0], image.size[1])
             
        image.source = "SEQUENCE"

        image_texture = nodes.new("ShaderNodeTexImage")
        if i < 2:
            image_texture.location = (0, -450*i)
        else:
            image_texture.location = (350*(i-1), -450)
        image_texture.label = layer_name
        image_texture.image = image
        image_texture.extension = "CLIP"
        image_texture.image_user.frame_duration = 1
        image_texture.image_user.frame_start = 1
        image_texture.image_user.frame_offset = get_image_numbers(image_texture)[0]-1
        image_texture.image_user.use_auto_refresh = True
        image_textures.append(image_texture)
        links.new(
            mapping.outputs[0], # Vector
            image_texture.inputs[0] # Vector
        )

        if i < (n_layers-1):
            mix_rgb = nodes.new("ShaderNodeMixRGB")
            mix_rgb.location = (350*(i+1), 0)
            mix_rgbs.append(mix_rgb)

            math_add = nodes.new("ShaderNodeMath")
            math_add.operation = "ADD"
            math_add.use_clamp = True
            math_add.location = (350*(i+1), -200)
            math_adds.append(math_add)

    if n_layers > 1:
        for i in range(n_layers-1):
            if i == 0:
                links.new(
                    image_textures[i].outputs[0], # Color
                    mix_rgbs[i].inputs[1] # Color1
                )
                links.new(
                    image_textures[i].outputs[1], # Alpha
                    math_adds[i].inputs[0] # Value1
                )
            else:
                links.new(
                    mix_rgbs[i-1].outputs[0], # Color
                    mix_rgbs[i].inputs[1] # Color1
                )
                links.new(
                    math_adds[i-1].outputs[0], # Value
                    math_adds[i].inputs[0] # Value1
                )
            links.new(
                image_textures[i+1].outputs[1], # Alpha
                mix_rgbs[i].inputs[0] # Fac
            )
            links.new(
                image_textures[i+1].outputs[0], # Color
                mix_rgbs[i].inputs[2] # Color2
            )
            links.new(
                image_textures[i+1].outputs[1], # Alpha
                math_adds[i].inputs[1] # Value2
            )
            
    principled_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    principled_bsdf.inputs[9].default_value = 1.0 # Roughness
    if n_layers == 1:
        principled_bsdf.location = (image_textures[0].location[0]+300, 0)
        links.new(
            image_textures[0].outputs[0], # Color
            principled_bsdf.inputs[0] # Base Color
        )
        links.new(
            image_textures[0].outputs[1], # Alpha
            principled_bsdf.inputs[21] # Alpha
        )
    elif n_layers > 1:
        principled_bsdf.location = (mix_rgbs[-1].location[0]+300, 0)
        links.new(
            mix_rgbs[-1].outputs[0], # Color
            principled_bsdf.inputs[0] # Base Color
        )
        links.new(
            math_adds[-1].outputs[0], # Value
            principled_bsdf.inputs[21] # Alpha
        )

    material_output = nodes.new("ShaderNodeOutputMaterial")
    material_output.location = (principled_bsdf.location[0]+300, 0)
    links.new(
        principled_bsdf.outputs[0], # BSDF
        material_output.inputs[0] # Surface
    )
    return material, image_size
         

def generate_plane(
    width=1.0,
    height=1.2,
):
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    plane = bpy.context.active_object
    plane.scale = (width, height, 0)
    plane.rotation_euler = (radians(90), 0, 0)
    plane.location = (0, 0, height/2)
    bpy.ops.object.transform_apply()
    return plane
     
     
class TachiePlaneHelperAddDriversOperator(bpy.types.Operator):
    bl_idname = "object.tp_add_drivers_operator"
    bl_label = "Add Drivers"
    
    def execute(self, context):
        tp = context.scene.tp
        
        image_sequences = get_image_sequences(
            material=tp.material
        )
        for image_sequence in image_sequences:
            nums = get_image_numbers(image_sequence)
            add_custom_property(
                object=tp.object,
                prop=image_sequence.label,
                default=nums[0]-1,
                min=nums[0]-1,
                max=nums[-1]-1,
            )
            d = image_sequence.image_user.driver_add("frame_offset")
            d.driver.type = "SCRIPTED"
            var = d.driver.variables.new()
            var.name = "var"
            var.type = "SINGLE_PROP"
            var.targets[0].id = tp.object
            var.targets[0].data_path = f'["{image_sequence.label}"]'
            d.driver.expression = "var"
            
        return {"FINISHED"}
      
     
def get_image_sequences(
    material,
):
    image_sequences = []
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeTexImage":
            if node.image.source == "SEQUENCE":
                image_sequences.append(node)
    return image_sequences
     
     
def get_image_numbers(
    image_sequence,
):
    filepath = Path(image_sequence.image.filepath)
    matched = re.match(r"(?P<name>.*?)(?P<num>\d+)", filepath.stem)
    name = matched.group("name")
    
    numbers = []
    for path in filepath.parent.iterdir():
        if (path.is_file() and path.suffix==filepath.suffix and path.stem.startswith(name)):
            matched = re.match(r"(?P<name>.*?)(?P<num>\d+)", path.stem)
            numbers.append(int(matched.group("num")))
    return sorted(numbers)
     
     
def add_custom_property(
    object,
    prop="prop",
    default=0,
    min=0,
    max=1,
    step=1,
):
    object[prop] = default
    ui_data = object.id_properties_ui(prop)
    ui_data.update(
        soft_min=min,
        soft_max=max,
        min=min,
        max=max,
        step=step,
    )
    rna_idprop_ui_prop_update(object, prop)
    

class TachiePlaneHelperProperties(bpy.types.PropertyGroup):
    directory: StringProperty(
        name="Path",
        subtype="DIR_PATH"
    )
    
    create_new_plane: BoolProperty(
        name = "Create New Plane",
        default = True
    )
    
    use_fake_user: BoolProperty(
        name = "Enable Fake User",
        default = False
    )
    
    object: PointerProperty(
        name = "Object",
        type=bpy.types.Object
    )
    
    material: PointerProperty(
        name = "Material",
        type=bpy.types.Material
    )
    

def register():
    bpy.utils.register_class(TachiePlaneHelperProperties)
    bpy.types.Scene.tp = PointerProperty(type=TachiePlaneHelperProperties)
    bpy.utils.register_class(TachiePlaneHelperPanel)
    bpy.utils.register_class(TachiePlaneHelperGenerateTextOperator)
    bpy.utils.register_class(TachiePlaneHelperGenerateMaterialOperator)
    bpy.utils.register_class(TachiePlaneHelperAddDriversOperator)


def unregister():
    bpy.utils.unregister_class(TachiePlaneHelperProperties)
    bpy.utils.unregister_class(TachiePlaneHelperPanel)
    bpy.utils.unregister_class(TachiePlaneHelperGenerateTextOperator)
    bpy.utils.unregister_class(TachiePlaneHelperGenerateMaterialOperator)
    bpy.utils.unregister_class(TachiePlaneHelperAddDriversOperator)
    del bpy.types.Scene.tp


if __name__ == "__main__":
    register()
