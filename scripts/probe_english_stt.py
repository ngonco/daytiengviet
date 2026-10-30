from pathlib import Path
import json
import httpx
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
config=dotenv_values(root/'.env')
audio=root/'data/projects/89eb517a77d34f8b/audio/000.flac'
with httpx.Client(timeout=240) as client:
    response=client.post('https://api.groq.com/openai/v1/audio/transcriptions',headers={'Authorization':f"Bearer {config['GROQ_API_KEY']}"},data={'model':config.get('GROQ_MODEL','whisper-large-v3'),'response_format':'verbose_json','timestamp_granularities[]':['word','segment'],'temperature':'0','language':'en','prompt':'An English and Vietnamese language lesson. Transcribe the spoken language faithfully. Preserve Vietnamese words and tone marks: xin chào, chào bạn, cảm ơn, tạm biệt.'},files={'file':('audio.flac',audio.read_bytes(),'audio/flac')})
    print('status',response.status_code)
    if response.is_success:
        data=response.json()
        folder=root/'data/diagnostics'
        folder.mkdir(parents=True,exist_ok=True)
        (folder/'english-stt.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'language':data.get('language'),'text':data.get('text'),'words':len(data.get('words',[]))},ensure_ascii=False))
