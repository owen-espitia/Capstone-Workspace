import time

from PIL import Image
from . import annotate, embed_transformers, student_segmenter
DEVICE = "cpu" #CUDA is not an option...
TEXT_PROMPT = "shirt . jacket . pants"
BOX_THRESH = 0.3
TEXT_THRESH = 0.25


##instances = generate_instances(gdino_model= gdino, sam_predictor=sam_predictor, image_path= img_path, text_prompt= args.text_prompt,box_thresh= args.box_thresh, text_thresh= args.text_thresh, device= args.device)

def img_to_vector(input_image_path, gdino, sam=None, student=None, timings=None):
    #This function is to assemble the full pipeline into one function
    #From input image -> annotated / cropped image -> vector embedding!
    #Pass `student` (student_segmenter.load_student) to segment with the fast student model, otherwise SAM is used.
    #Pass a dict as `timings` to have per-stage seconds filled in (student: load_image/detect/segment/crop/embed,
    #SAM: detect_and_segment/embed).

    #For future referemce, there should be only one instance of clothing.
    t0 = time.perf_counter()
    if student is not None:
        instance = student_segmenter.generate_instances_student(gdino, student, input_image_path, TEXT_PROMPT, BOX_THRESH, TEXT_THRESH, DEVICE, timings)
    else:
        instance = annotate.generate_instances(gdino, sam, input_image_path, TEXT_PROMPT, BOX_THRESH, TEXT_THRESH, DEVICE)
        if timings is not None:
            timings["detect_and_segment"] = time.perf_counter() - t0
    if not instance:
        return {"error": "No clothing instances detected"}
    # if len(instance) > 1:
    #     return("Multiple clothing pieces detected")


    t1 = time.perf_counter()
    embeddings = embed_transformers.encode_image_objects([Image.fromarray(instance[0]["crop"])])
    if timings is not None:
        timings["embed"] = time.perf_counter() - t1
    if embeddings.shape[0] == 0:
        return {"error": "Degenerate crop, could not embed"}
    return {
        "image_path": input_image_path,
        "category": instance[0]["category"],
        "embedding": embeddings[0]
    }
