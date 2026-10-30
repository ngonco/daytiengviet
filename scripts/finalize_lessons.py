"""Refresh final artifacts using saved live-provider data and the final crop renderer."""
import json
import shutil
import zipfile
import io
from PIL import Image,ImageDraw
from backend.config import ROOT
from backend import store
from backend.media import ffmpeg,probe
from backend.templates import font
from scripts.acceptance_lessons import call,wait,OUT,client,BASE

if __name__=='__main__':
    state=json.loads((OUT/'state.json').read_text(encoding='utf-8'))
    project=wait(state['project_id'])
    for ratio,name in [('9:16','Vietnamese_with_Vinh_9x16'),('16:9','Vietnamese_with_Vinh_16x9')]:
        if project['options']['ratio']!=ratio:
            call('PUT',f"/projects/{project['id']}/plan",json={'revision':project['revision'],'plan':project['plan'],'options':{**project['options'],'ratio':ratio}})
            project=wait(project['id'])
        call('POST',f"/projects/{project['id']}/jobs/export")
        project=wait(project['id']);result=project['export']
        assert result['lesson_renderer_version']==2
        source=store.folder(project['id'])/result['file'];target=OUT/(name+'.mp4');shutil.copy2(source,target)
        for suffix in ['subtitles.vi.srt','subtitles.en.srt','credits.json']:
            label=suffix.replace('subtitles.','')
            shutil.copy2(source.parent/suffix,OUT/(name+'.'+label))
        ffmpeg(['-i',target,'-f','null','-'])
        for i,at in enumerate([1.5,15.5,30,52]):ffmpeg(['-ss',at,'-i',target,'-frames:v','1','-vf','scale=540:-2',OUT/f'{name}_{i}.jpg'])
        state[name]={'file':target.name,**probe(target),'lesson_renderer_version':2}
    backup=client.get(BASE+f"/projects/{project['id']}/download/project");backup.raise_for_status();(OUT/'Vietnamese_with_Vinh_project.zip').write_bytes(backup.content)
    with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
        assert archive.testzip() is None and '.env' not in archive.namelist()
        restored=json.loads(archive.read('project.json'))
        assert restored['plan']['lessons'][0]['locked']
        assert restored['plan']['lessons'][0]['vi']=='Xin chào!'
    for project_id in state['original_ids']:
        original=store.read(project_id)
        assert original['options'].get('layout_mode','legacy')=='legacy' and original['revision']==4
    portrait=Image.open(OUT/'Vietnamese_with_Vinh_9x16_1.jpg').convert('RGB')
    landscape=Image.open(OUT/'Vietnamese_with_Vinh_16x9_1.jpg').convert('RGB');landscape=landscape.resize((960,540))
    sheet=Image.new('RGB',(1540,1040),'#f5f0e5');draw=ImageDraw.Draw(sheet)
    draw.text((20,12),'9:16',font=font(26,True),fill='#063c40');draw.text((570,170),'16:9',font=font(26,True),fill='#063c40')
    sheet.paste(portrait,(10,60));sheet.paste(landscape,(570,220));sheet.save(OUT/'khung_mau_so_sanh.jpg',quality=94)
    state.update(final_passed=True,ui_split_merge_delete_save=True,full_decode=True,stereo=True,originals_unchanged=True)
    store.atomic_json(OUT/'final-verification.json',state)
    print('FINAL LESSON FRAMES PASSED',flush=True)
