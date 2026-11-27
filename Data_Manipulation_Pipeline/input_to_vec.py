import time

import numpy as np
from PIL import Image
from . import annotate, detector as yolo_detector, embed_transformers, student_segmenter
DEVICE = "cpu" #CUDA is not an option...
TEXT_PROMPT = "shirt . jacket . pants"
BOX_THRESH = 0.3
TEXT_THRESH = 0.25


##instances = generate_instances(gdino_model= gdino, sam_predictor= sam_predictor, image_path= img_path, text_prompt= args.text_prompt,box_thresh= args.box_thresh, text_thresh= args.text_thresh, device= args.device)

def _instances_with_yolo(detector, image_path, sam, student, timings):
    #Fast path: YOLO box -> student/SAM mask -> crop. Returns (instances, fallback_reason); reason is None on success.
    t0 = time.perf_counter()
    image_src = np.array(Image.open(image_path).convert("RGB"))  # same decode as GroundingDINO's load_image
    t1 = time.perf_counter()
    dets, reason = yolo_detector.detect(detector, image_src, DEVICE)
    if timings is not None:
        timings.update(load_image=t1 - t0, yolo=time.perf_counter() - t1)
    if not dets:
        return [], reason
    # the API uses one garment per upload: the most confident usable box
    best = dets[0]
    boxes = np.array([best["bbox"]], dtype=np.float32)
    if student is not None:
        instances = student_segmenter.instances_from_boxes(student, image_src, boxes, [best["category"]], [best["score"]], timings)
    else:
        t2 = time.perf_counter()
        instances = annotate.instances_from_boxes_sam(sam, image_src, boxes, [best["category"]], [best["score"]], DEVICE)
        if timings is not None:
            timings["segment_and_crop"] = time.perf_counter() - t2
    if not instances:
        return [], "empty_mask"
    return instances, None


def img_to_vector(input_image_path, gdino, sam=None, student=None, timings=None, detector=None):
    #This function is to assemble the full pipeline into one function
    #From input image -> annotated / cropped image -> vector embedding!
    #Pass `student` (student_segmenter.load_student) to segment with the fast student model, otherwise SAM is used.
    #Pass `detector` (detector.load_detector) to find the garment with YOLO first; GroundingDINO is only used when YOLO
    #has no confident, plausibly sized box (see detector.py), so the result is never worse than before for odd photos.
    #Pass a dict as `timings` to have per-stage seconds filled in (YOLO path: load_image/yolo/segment/crop/embed,
    #GroundingDINO path: load_image/detect/segment/crop/embed, SAM: detect_and_segment/embed; a fallback also has yolo).

    #For future referemce, there should be only one instance of clothing.
    instance, detector_used, fallback_reason = None, "groundingdino", None
    if detector is not None:
        instance, fallback_reason = _instances_with_yolo(detector, input_image_path, sam, student, timings)
        if instance:
            detector_used = "yolo"
    if not instance:
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
        "embedding": embeddings[0],
        "detector": detector_used,
        "fallback_reason": fallback_reason,  # why YOLO was skipped; None when YOLO was used or is not configured
    }
