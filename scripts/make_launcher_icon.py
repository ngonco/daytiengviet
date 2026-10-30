"""Build the code-drawn V/play launcher icon at standard Windows icon sizes."""
from pathlib import Path
from PIL import Image,ImageDraw


def main():
    root=Path(__file__).resolve().parents[1]
    image=Image.new('RGBA',(512,512),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((16,16,496,496),radius=112,fill='#063c40')
    draw.line([(115,128),(245,386),(375,128)],fill='#fbf5e9',width=61,joint='curve')
    draw.ellipse((321,321,485,485),fill='#cb4822')
    draw.polygon([(382,356),(382,447),(447,402)],fill='#fbf5e9')
    image.save(root/'assets/vietcut.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])


if __name__=='__main__':main()
