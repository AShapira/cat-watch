"""Source-pixel crops and buffered motion masks; presence polygons stay unchanged."""
import math
import cv2
import numpy as np


def region_masks(polygons, width, height, buffer=0., exclusions=()):
    allowed = np.ones((height, width), np.uint8)
    for x1,y1,x2,y2 in exclusions:
        allowed[int(y1*height):math.ceil(y2*height),int(x1*width):math.ceil(x2*width)] = 0
    result = {}
    for name,polygon in polygons.items():
        if len(polygon)<3:
            continue
        mask = np.zeros_like(allowed)
        points = np.round(np.array(polygon)*[width,height]).astype(np.int32)
        cv2.fillPoly(mask,[points],1)
        xs,ys = zip(*polygon)
        dx = math.ceil((max(xs)-min(xs))*width*buffer)
        dy = math.ceil((max(ys)-min(ys))*height*buffer)
        if dx or dy:
            mask = cv2.dilate(mask, np.ones((2*dy+1,2*dx+1),np.uint8))
        result[name] = mask & allowed
    return result


def crop_regions(polygons, width, height, context=.5):
    regions = []
    for area,polygon in polygons.items():
        if len(polygon)<3:
            continue
        xs,ys=zip(*polygon)
        dx,dy=(max(xs)-min(xs))*context,(max(ys)-min(ys))*context
        box=[max(0,math.floor((min(xs)-dx)*width)),max(0,math.floor((min(ys)-dy)*height)),
             min(width,math.ceil((max(xs)+dx)*width)),min(height,math.ceil((max(ys)+dy)*height))]
        regions.append({'areas':[area], 'box':box})
    # Food and fountain share context; litter-box evidence stays independently visible.
    food=[r for r in regions if r['areas'][0] in ('eating_pad','water_fountain')]
    if len(food)==2:
        a,b=[r['box'] for r in food]
        if max(a[0],b[0])<min(a[2],b[2]) and max(a[1],b[1])<min(a[3],b[3]):
            regions=[r for r in regions if r not in food]+[{'areas':['eating_pad','water_fountain'],
                'box':[min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])]}]
    return sorted(regions,key=lambda r:r['areas'])


def merge_detections(detections, threshold=.5):
    kept=[]
    for d in sorted(detections,key=lambda d:d['confidence'],reverse=True):
        a=d['box']; area=(a[2]-a[0])*(a[3]-a[1]); duplicate=False
        for k in kept:
            if d['class_id']!=k['class_id']:
                continue
            b=k['box']; overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
            union=area+(b[2]-b[0])*(b[3]-b[1])-overlap
            if union>0 and overlap/union>=threshold:
                duplicate=True;break
        if not duplicate:
            kept.append(d)
    return kept


def predict_regions(model, frame, polygons, context=.5, size=640):
    height,width=frame.shape[:2]
    regions=crop_regions(polygons,width,height,context)
    detections=[]
    for region in regions:
        x1,y1,x2,y2=region['box']
        # Crop the ORIGINAL decoded pixels before the model's letterbox resize.
        result=model.predict(frame[y1:y2,x1:x2],conf=.1,device=0,imgsz=size,verbose=False)[0]
        for box,score,cls in zip(result.boxes.xyxy.cpu().tolist(),result.boxes.conf.cpu().tolist(),result.boxes.cls.cpu().tolist()):
            detections.append({'box':[(box[0]+x1)/width,(box[1]+y1)/height,(box[2]+x1)/width,(box[3]+y1)/height],
                'confidence':score,'class_id':int(cls),'label':result.names[int(cls)]})
    return merge_detections(detections),regions
