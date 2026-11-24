"""Static/page-changing video TAB to GP5. Run with --help."""
import argparse, json, re, tempfile, subprocess, sys, shutil
from pathlib import Path
import cv2
import numpy as np
import pytesseract


def runs(indices):
    return [int(np.mean(g)) for g in np.split(indices, np.where(np.diff(indices)>1)[0]+1) if len(g)]


def read_frets(strip, gap, confidence):
    columns = np.flatnonzero(np.any(strip, axis=0))
    spans = np.split(columns, np.where(np.diff(columns) > max(2, round(gap * .12)))[0] + 1)
    for span in spans:
        if not len(span):
            continue
        left, right = span[0], span[-1] + 1
        glyph = strip[:, left:right]
        rows = np.flatnonzero(np.any(glyph, axis=1))
        height = rows[-1] - rows[0] + 1
        width = right - left
        if height < gap * .25 or not gap * .10 <= width <= gap * 1.6:
            continue
        if abs(np.mean([rows[0], rows[-1]]) - (len(strip) - 1) / 2) > gap * .23:
            continue
        glyph = 255 - glyph[rows[0]:rows[-1] + 1]
        scale = 42 / height
        glyph = cv2.resize(glyph, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        glyph = cv2.copyMakeBorder(glyph, 14, 14, 14, 14, cv2.BORDER_CONSTANT, value=255)
        modes = (10, 8) if width / height < .82 else (8,)
        for mode in modes:
            data = pytesseract.image_to_data(
                glyph, config=f'--psm {mode} -c tessedit_char_whitelist=0123456789',
                output_type=pytesseract.Output.DICT,
            )
            value = ''.join(data['text']).strip()
            score = max(map(float, data['conf']), default=-1)
            if re.fullmatch(r'\d{1,2}', value) and int(value) <= 24 and score >= confidence:
                yield (left + right) / 2, int(value), round(score, 1)
                break


def detect_staff(mask):
    h,w=mask.shape
    horizontal=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((1,max(15,w//12)),np.uint8))
    rows=runs(np.flatnonzero(np.count_nonzero(horizontal,axis=1)>w*.22))
    candidates=[]
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            d=b-a
            if d<5 or d>h/5: continue
            group=[min(rows,key=lambda y:abs(y-(a+k*d))) for k in range(6)]
            err=max(abs(y-(a+k*d)) for k,y in enumerate(group))
            if len(set(group))==6 and err<=max(2,d*.15):
                score=sum(np.count_nonzero(horizontal[y]) for y in group)-err*w*.1
                candidates.append((score,group))
    return max(candidates,key=lambda x:x[0])[1] if candidates else None


def find_tab(frame, args):
    h,w=frame.shape[:2]
    x,y,r,b=args.roi or (0,.55,1,1)
    crop=frame[int(y*h):int(b*h),int(x*w):int(r*w)]
    if not crop.size:
        raise SystemExit('ROI is smaller than one pixel. Increase the crop bounds.')
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    _,mask=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    if np.mean(mask)>127: mask=255-mask
    lines=detect_staff(mask) if not args.lines else [round(v*(len(mask)-1)) for v in args.lines]
    used_fallback = lines is None
    if used_fallback:
        # A dark area outside the score can pull the global threshold too low.
        _, fallback = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
        lines = detect_staff(fallback)
        if lines is None:
            return None
        mask = fallback
    if np.median(np.diff(lines)) < 4:
        return None
    return mask, lines, used_fallback


def tab_fingerprint(mask, lines):
    margin = round(np.median(np.diff(lines)) / 2)
    staff = mask[max(0, lines[0] - margin):lines[-1] + margin + 1]
    horizontal = cv2.morphologyEx(staff, cv2.MORPH_OPEN, np.ones((1, margin * 6), np.uint8))
    ink = cv2.bitwise_and(staff, cv2.bitwise_not(horizontal))
    return cv2.resize(ink, (512, 96), interpolation=cv2.INTER_AREA)


def same_tab_page(current, previous):
    # Compression and staff localization can shift ink by a pixel or two.
    tolerance = np.ones((5, 3), np.uint8)
    added = cv2.subtract(current, cv2.dilate(previous, tolerance))
    removed = cv2.subtract(previous, cv2.dilate(current, tolerance))
    return np.mean(added) + np.mean(removed) < 1.2


def recognize(mask, lines, args):
    gap=float(np.median(np.diff(lines)))
    # Long horizontal staff strokes and full-height barlines are outside fret glyphs.
    horizontal=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((1,max(15,int(gap*3))),np.uint8))
    barlines=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((round(gap*2),1),np.uint8))
    clean=cv2.bitwise_and(mask,cv2.bitwise_not(horizontal))
    bridged=cv2.morphologyEx(clean,cv2.MORPH_CLOSE,np.ones((max(3,round(gap*.2)+1),1),np.uint8))
    clean=cv2.bitwise_or(clean,cv2.bitwise_and(bridged,horizontal))
    clean=cv2.bitwise_and(clean,cv2.bitwise_not(barlines))
    events=[]
    for string,cy in enumerate(lines,1):
        top=max(0,round(cy-gap*.48)); bottom=min(len(clean),round(cy+gap*.48)+1)
        for px,fret,confidence in read_frets(clean[top:bottom],gap,args.confidence):
            events.append((px,string,fret,confidence))
    groups=[]
    for px,string,fret,conf in sorted(events):
        if not groups or px-groups[-1]['x']>gap*.45 or any(n['string']==string for n in groups[-1]['notes']):
            groups.append({'x':round(px,1),'notes':[]})
        groups[-1]['notes'].append({'string':string,'fret':fret,'confidence':conf})
    return groups


def signature(groups):
    return tuple(tuple(sorted((n['string'],n['fret']) for n in g['notes'])) for g in groups)


def export_gp5(groups,path,bpm,duration,title):
    import guitarpro as gp
    song=gp.Song(title=title,tempo=bpm)
    track=song.tracks[0]; track.name='Guitar'; track.strings=[gp.GuitarString(i,p) for i,p in enumerate([64,59,55,50,45,40],1)]
    per=duration # 4/4: number of equal-duration beats per bar
    for i in range(0,len(groups),per):
        if i or not track.measures: song.newMeasure()
        measure=track.measures[-1]; voice=measure.voices[0]; voice.beats.clear()
        chunk=groups[i:i+per]
        for j in range(per):
            notes=chunk[j]['notes'] if j<len(chunk) else []
            beat=gp.Beat(voice); beat.duration.value=duration; beat.start=measure.start+j*(3840//duration)
            beat.status=gp.BeatStatus.normal if notes else gp.BeatStatus.rest
            for n in notes:
                beat.notes.append(gp.Note(beat,string=int(n['string']),value=int(n['fret']),type=gp.NoteType.normal))
            voice.beats.append(beat)
    gp.write(song,str(path),version=(5,1,0))
    gp.parse(str(path)) # verify serialization can be read back


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',help='Local video, authorized YouTube URL, or previously exported JSON')
    p.add_argument('-o','--output',default='output.gp5'); p.add_argument('--bpm',type=int,default=120)
    p.add_argument('--duration',type=int,choices=[4,8,16,32],default=8,help='Assumed note length: 4=quarter, 8=eighth')
    p.add_argument('--roi',type=float,nargs=4,metavar=('LEFT','TOP','RIGHT','BOTTOM'),help='Normalized crop bounds; default bottom 45%%')
    p.add_argument('--lines',type=float,nargs=6,help='Manual string Y positions (0..1 relative to cropped region)')
    p.add_argument('--interval',type=float,default=1,help='Seconds between sampled frames')
    p.add_argument('--start',type=float,default=0); p.add_argument('--end',type=float)
    p.add_argument('--confidence',type=float,default=25); p.add_argument('--tesseract'); p.add_argument('--title',default='Video TAB')
    a=p.parse_args(); out=Path(a.output).with_suffix('.gp5'); out.parent.mkdir(parents=True,exist_ok=True)
    if a.interval<=0 or a.start<0 or (a.end is not None and a.end<=a.start) or not 20<=a.bpm<=300: p.error('Invalid time range, interval or BPM')
    if a.roi and not (0<=a.roi[0]<a.roi[2]<=1 and 0<=a.roi[1]<a.roi[3]<=1): p.error('Invalid ROI')
    if a.lines and not (0<=a.lines[0] and a.lines[-1]<=1 and all(x<y for x,y in zip(a.lines,a.lines[1:]))): p.error('Invalid string positions')
    if a.tesseract: pytesseract.pytesseract.tesseract_cmd=a.tesseract
    elif sys.platform=='win32' and not shutil.which('tesseract'):
        path=Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe')
        if path.exists(): pytesseract.pytesseract.tesseract_cmd=str(path)
    groups=[]
    from_json = a.source.lower().endswith('.json')
    if from_json:
        groups=json.loads(Path(a.source).read_text(encoding='utf-8-sig'))['events']
    else:
        pytesseract.get_tesseract_version()
        with tempfile.TemporaryDirectory() as temp:
            source=a.source
            if source.startswith(('https://','http://')):
                cmd=[sys.executable,'-m','yt_dlp','--no-playlist','-f','bestvideo[ext=mp4]/best[ext=mp4]/bestvideo/best','-o',str(Path(temp)/'video.%(ext)s'),source]
                subprocess.run(cmd,check=True); files=list(Path(temp).glob('video.*')); source=str(files[0])
            cap=cv2.VideoCapture(source)
            if not cap.isOpened(): raise RuntimeError('Cannot open video')
            fps=cap.get(cv2.CAP_PROP_FPS); count=cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if fps<=0 or count<=0: raise RuntimeError('Video duration unavailable')
            end=min(count/fps,a.end if a.end is not None else count/fps)
            previous=None; previous_image=None; pending_fallback=None; t=a.start
            while t<end:
                cap.set(cv2.CAP_PROP_POS_MSEC,t*1000); ok,frame=cap.read()
                if not ok: break
                tab = find_tab(frame, a)
                if tab is None:
                    pending_fallback = None
                    t+=a.interval; continue
                mask, lines, used_fallback = tab
                tiny = tab_fingerprint(mask, lines)
                if previous_image is not None and same_tab_page(tiny,previous_image):
                    pending_fallback = None
                    t+=a.interval; continue
                # Confirm the less reliable threshold across two samples.
                if used_fallback and (pending_fallback is None or not same_tab_page(tiny, pending_fallback)):
                    pending_fallback = tiny
                    t+=a.interval; continue
                pending_fallback = None
                page=recognize(mask, lines, a)
                if page:
                    sig=signature(page)
                    if sig!=previous:
                        for event in page: event['frame_seconds']=round(t,3)
                        groups.extend(page); previous=sig
                        print(f'{t:.1f}s: {len(page)} beats',flush=True)
                previous_image=tiny
                t+=a.interval
            cap.release()
    if not groups: raise SystemExit('No notes detected. Try --roi, --lines or lower --confidence.')
    export_gp5(groups,out,a.bpm,a.duration,a.title)
    json_path = out.with_suffix('.json')
    if not from_json or json_path.resolve() != Path(a.source).resolve():
        json_path.write_text(json.dumps({'rhythm':'assumed equal duration','events':groups},indent=2),encoding='utf-8')
        print(f'Saved {out} and {json_path}.')
    else:
        print(f'Saved {out}.')
    print('Rhythm is estimated, not transcribed.')

if __name__=='__main__': main()
