"""Deterministic font lettering; the diffusion model never draws dialogue."""
from PIL import Image,ImageDraw,ImageOps

def spoken_text(panel):
    return ' '.join(x['text'] for x in panel.get('dialogue',[])) if panel.get('dialogue') else panel['narration']

def wrap(draw,text,font,width):
    lines=[];line=''
    for word in text.split():
        candidate=(line+' '+word).strip()
        if draw.textlength(candidate,font=font)>width and line:lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    return lines

def dialogue_card(data,panel,art,width,font):
    from speech_layout import compose
    return compose(data,panel,art,width,font)

def legacy_dialogue_card(data,panel,art,width,font):
    entries=panel.get('dialogue',[])
    if len(entries)>4:raise ValueError('Use at most four speech balloons per panel.')
    header=width//14;band=max(width//4,len(entries)*width//5)
    top=header+band;height=top+width
    image=Image.new('RGB',(width,height),'#eff3f8');image.paste(ImageOps.pad(art.convert('RGB'),(width,width)),(0,top))
    draw=ImageDraw.Draw(image);draw.rectangle((0,0,width,header),fill='#111827')
    draw.text((width//40,header//4),data['title'],font=font(width//34),fill='white')
    # Reserved balloon band leaves every face/action unobscured. Tails indicate
    # the staged character positions; the storyboard can refine mouth anchors.
    margin=width//40;gap=width//40
    n=max(1,len(entries));cell=width-2*margin if n==1 else (width-3*margin)//2
    for j,entry in enumerate(entries):
        row_height=band//n
        size=width//31
        while size>=width//48:
            f=font(size);lines=wrap(draw,entry['text'],f,cell-2*margin)
            if len(lines)*(size+6)<row_height-2*margin:break
            size-=1
        else:raise ValueError('Dialogue does not fit readable speech balloons. Shorten the line.')
        anchor=panel.get('speaker_positions',{}).get(entry['speaker'],{'x':(j+.5)/n,'y':.4})
        x=margin if n==1 or anchor['x']<.5 else width-margin-cell
        y=header+margin+j*row_height
        box=(x,y,x+cell,header+(j+1)*row_height-margin)
        tip=(int(anchor['x']*width),int(top+anchor['y']*width))
        base=min(max(tip[0],x+margin),x+cell-margin)
        draw.polygon([(base-margin//2,box[3]-2),(base+margin//2,box[3]-2),tip],fill='white',outline='black',width=2)
        draw.rounded_rectangle(box,radius=width//30,fill='white',outline='black',width=3)
        yy=y+(box[3]-y-len(lines)*(size+6))//2
        for line in lines:
            xx=x+(cell-draw.textlength(line,font=f))/2
            draw.text((xx,yy),line,font=f,fill='black');yy+=size+6
    return image,{'width':width,'height':height,'art_top':top,'art_size':width,'speech_balloons':True}
