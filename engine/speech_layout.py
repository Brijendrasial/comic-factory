"""Place font-lettered comic balloons inside artwork, protecting faces."""
import math
from PIL import Image,ImageDraw,ImageOps

def overlap(a,b,pad=0):
    return a[0]<b[2]+pad and a[2]>b[0]-pad and a[1]<b[3]+pad and a[3]>b[1]-pad

def edge(box,p):
    cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2;rx=(box[2]-box[0])/2;ry=(box[3]-box[1])/2
    dx=p[0]-cx;dy=p[1]-cy;n=math.hypot(dx/rx,dy/ry)
    return (cx+dx/n,cy+dy/n) if n>1 else None

def hits(a,b,box):
    return any(box[0]<a[0]+(b[0]-a[0])*j/20<box[2] and box[1]<a[1]+(b[1]-a[1])*j/20<box[3] for j in range(1,20))

class BalloonLayoutError(ValueError):pass

def plan(panel,width,font):
    last=None
    for font_scale in (1,.94,.875,.8125,.75):
        try:return _plan(panel,width,font,font_scale)
        except BalloonLayoutError as exc:last=exc
    raise last

def _plan(panel,width,font,font_scale):
    from lettering import wrap
    entries=panel.get('dialogue',[])
    if len(entries)>4:raise ValueError('Use at most four balloons per panel.')
    names=list(dict.fromkeys(d['speaker'] for d in entries));saved=panel.get('speaker_positions',{});points={}
    for j,name in enumerate(names):
        p=next((v for k,v in saved.items() if k.casefold()==name.casefold()),{'x':(j+.5)/max(1,len(names)),'y':.4})
        points[name]=(min(.97,max(.03,p['x']))*width,min(.95,max(.12,p['y']))*width)
    faces={n:(x-.070*width,y-(.155 if n.casefold()=='batman' else .115)*width,x+.070*width,y+.035*width) for n,(x,y) in points.items()}
    protected=list(faces.values())+[tuple(v*width for v in b) for b in panel.get('lettering_avoid',[])]
    draw=ImageDraw.Draw(Image.new('RGB',(1,1)));size=max(22,round(width/32*font_scale));f=font(size);options=[]
    for entry in entries:
        mouth=points[entry['speaker']];candidates=[]
        for fraction in (.18,.20,.22,.26,.30,.34,.38,.42,.46,.50,.54):
            w=round(width*fraction);lines=wrap(draw,entry['text'],f,w*.76)
            if any(draw.textlength(line,font=f)>w*.76 for line in lines):continue
            h=round(max(width*.075,(len(lines)*size*1.18+size*.85)/.76))
            if h>width*.34:continue
            xs={round(width*.018+k*width*.035) for k in range(28)}
            xs.update(round(mouth[0]+d) for d in (-w-width*.04,-w/2,width*.04))
            for protected_box in protected:
                xs.update((round(protected_box[0]-w-width*.012),round(protected_box[2]+width*.012)))
            ys={round(width*.018+k*width*.03) for k in range(21)}
            ys.update(round(mouth[1]+d) for d in (-h-width*.19,-h-width*.06,-h/2,width*.05))
            for x in sorted(xs):
                if x<width*.015 or x+w>width*.985:continue
                for y in sorted(ys):
                    box=(x,y,x+w,y+h)
                    if y<width*.015 or y+h>width*.72 or any(overlap(box,b,width*.007) for b in protected):continue
                    start=edge(box,mouth)
                    if start is None:continue
                    distance=math.dist(start,mouth)
                    if not width*.018<distance<width*.23:continue
                    if any(hits(start,mouth,b) for name,b in faces.items() if name!=entry['speaker']):continue
                    score=distance/width*7+(y+h/2)/width*.45+w*h/width**2*.8
                    candidates.append(dict(box=box,start=start,mouth=mouth,score=score,lines=lines,size=size,speaker=entry['speaker']))
        candidates.sort(key=lambda b:b['score']);diverse=[]
        for candidate in candidates:
            b=candidate['box']
            if sum(abs(b[0]-v['box'][0])<width*.05 and abs(b[1]-v['box'][1])<width*.05 for v in diverse)>=2:continue
            diverse.append(candidate)
            if len(diverse)>=800:break
        if not diverse:raise BalloonLayoutError('No clear space for a balloon. Shorten the dialogue or adjust mouth positions in Review storyboard.')
        options.append(diverse)
    beam=[(0,[])]
    for choices in options:
        following=[]
        for score,placed in beam:
            for candidate in choices:
                box=candidate['box']
                if any(overlap(box,old['box'],width*.015) or hits(candidate['start'],candidate['mouth'],old['box']) or hits(old['start'],old['mouth'],box) for old in placed):continue
                if placed:
                    old=placed[-1]['box']
                    same_row=abs(box[1]-old[1])<=width*.035 and box[0]>old[2]+width*.01
                    if not same_row and box[1]<old[3]-width*.015:continue
                following.append((score+candidate['score'],placed+[candidate]))
        following.sort(key=lambda x:x[0]);beam=following[:150]
        if not beam:raise BalloonLayoutError('Balloons cannot fit safely in reading order. Shorten the dialogue or adjust the speaker positions.')
    return (beam[0][1] if beam else []),faces

def compose(data,panel,art,width,font):
    scale=2;w=width*scale;image=ImageOps.pad(art.convert('RGB'),(w,w));balloons,faces=plan(panel,w,font);draw=ImageDraw.Draw(image)
    for b in balloons:
        start=b['start'];mouth=b['mouth'];dx=mouth[0]-start[0];dy=mouth[1]-start[1];length=math.hypot(dx,dy);ux=dx/length;uy=dy/length
        # A comic tail points toward the lips but stops outside the head.
        # Never draw the white pointer across a face, helmet or cowl.
        face=faces[b['speaker']];stop=1
        for j in range(1,201):
            t=j/200;x=start[0]+dx*t;y=start[1]+dy*t
            if face[0]<=x<=face[2] and face[1]<=y<=face[3]:stop=max(0,t-w*.004/length);break
        tip=(start[0]+dx*stop,start[1]+dy*stop);b['tip']=tip
        half=w*.008;base=(start[0]-ux*w*.008,start[1]-uy*w*.008)
        triangle=[(base[0]-uy*half,base[1]+ux*half),(base[0]+uy*half,base[1]-ux*half),tip]
        draw.polygon(triangle,fill='white');draw.line([triangle[0],tip,triangle[1]],fill='black',width=max(2,round(w*.002)))
        draw.ellipse(b['box'],fill='white',outline='black',width=max(3,round(w*.0025)))
        f=font(b['size']);step=b['size']*1.18;box=b['box'];yy=(box[1]+box[3]-len(b['lines'])*step)/2
        for line in b['lines']:
            xx=(box[0]+box[2]-draw.textlength(line,font=f))/2;draw.text((round(xx),round(yy)),line,font=f,fill='black');yy+=step
    draw.rectangle((0,0,w-1,w-1),outline='black',width=max(4,round(w*.003)))
    audit=[{'speaker':b['speaker'],'box':[round(v/scale,2) for v in b['box']],
            'mouth':[round(v/scale,2) for v in b['mouth']],
            'tail_tip':[round(v/scale,2) for v in b['tip']],
            'tail_length':round(math.dist(b['start'],b['tip'])/scale,2)} for b in balloons]
    return image.resize((width,width),Image.Resampling.LANCZOS),{'width':width,'height':width,'art_top':0,'art_size':width,'speech_balloons':True,
        'balloons':audit,'face_keepouts':{n:[round(v/scale,2) for v in box] for n,box in faces.items()}}
