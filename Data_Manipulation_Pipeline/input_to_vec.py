from PIL import Image
from . import annotate, embed_transformers
DEVICE = "cpu" #CUDA is not an option...
TEXT_PROMPT = "shirt . jacket . pants"
BOX_THRESH = 0.3
TEXT_THRESH = 0.25


##instances = generate_instances(gdino_model= gdino, sam_predictor=sam_predictor, image_path= img_path, text_prompt= args.text_prompt,box_thresh= args.box_thresh, text_thresh= args.text_thresh, device= args.device)

def img_to_vector(input_image_path, gdino, sam):
    #This function is to assemble the full pipeline into one function
    #From input image -> annotated / cropped image -> vector embedding!

    #For future referemce, there should be only one instance of clothing.
    instance = annotate.generate_instances(gdino, sam, input_image_path, TEXT_PROMPT, BOX_THRESH, TEXT_THRESH, DEVICE)
    if not instance:
        return {"error": "No clothing instances detected"}
    # if len(instance) > 1:
    #     return("Multiple clothing pieces detected")

    
    embeddings = embed_transformers.encode_image_objects([Image.fromarray(instance[0]["crop"])])
    if embeddings.shape[0] == 0:
        return {"error": "Degenerate crop, could not embed"}
    return {
        "image_path": input_image_path,
        "category": instance[0]["category"],
        "embedding": embeddings[0]
    }
